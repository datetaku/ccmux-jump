#!/usr/bin/env python3
"""ccmux + fzf picker that focuses the existing WezTerm tab (Windows/WSL)."""

import argparse
import json
import os
from pathlib import Path
import pwd
import re
import shlex
import shutil
import subprocess
import sys

def wezterm_executable():
    override = os.environ.get("CCMUX_JUMP_WEZTERM")
    if override:
        return override
    executable = shutil.which("wezterm.exe")
    if executable:
        return executable
    for candidate in ("/mnt/c/Program Files/WezTerm/wezterm.exe", "/mnt/c/WezTerm/wezterm.exe"):
        if Path(candidate).is_file():
            return candidate
    raise RuntimeError("Windows wezterm.exe not found. Set CCMUX_JUMP_WEZTERM to its WSL path.")


def run(*args):
    result = subprocess.run(args, text=True, capture_output=True, timeout=15)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"{args[0]}: exit {result.returncode}")
    return result.stdout.strip()


def socket_path():
    ambient = os.environ.get("TMUX", "")
    if not ambient:
        raise RuntimeError("Run ccmux-jump inside tmux.")
    return ambient.rsplit(",", 2)[0]


def tmux(*args):
    return run("tmux", "-S", socket_path(), *args)


def clients():
    lines = tmux("list-clients", "-F", "#{client_pid}|#{client_tty}|#{session_id}|#{client_activity}")
    result = []
    for line in lines.splitlines():
        pid, tty, session, activity = line.split("|")
        result.append(dict(pid=int(pid), tty=tty, session=session, activity=int(activity)))
    return result


def client_environment(client):
    # The CLIENT's environment identifies the outer terminal. The tmux server's
    # shared environment and an agent pane's WEZTERM_PANE may be stale or absent.
    try:
        entries = Path(f"/proc/{client['pid']}/environ").read_bytes().split(b"\0")
        return dict(entry.decode(errors="replace").split("=", 1) for entry in entries if b"=" in entry)
    except OSError:
        return {}


def is_wezterm(client):
    return client_environment(client).get("TERM_PROGRAM") == "WezTerm"


def valid_pane(pane):
    if not re.fullmatch(r"%[0-9]+", pane):
        raise RuntimeError("Invalid tmux pane ID.")
    return pane


def wezterm(*args):
    return run(wezterm_executable(), "cli", *args)


def locate(client):
    """Read the Windows launcher's pane ID through this client's WSL interop."""
    interop = client_environment(client).get("WSL_INTEROP")
    if not interop:
        raise RuntimeError("The target tmux client has no WSL_INTEROP socket.")
    # WEZTERM_PANE is absent on the Linux side here, but retained by the Windows
    # launcher. Use each client's interop socket, not the tmux server's socket.
    cmd = shutil.which("cmd.exe") or "/mnt/c/Windows/System32/cmd.exe"
    result = subprocess.run([
        cmd, "/d", "/c", "echo", "%WEZTERM_PANE%",
    ], env=dict(os.environ, WSL_INTEROP=interop), cwd=str(Path(cmd).parent), capture_output=True, timeout=15)
    pane_id = result.stdout.strip()
    if result.returncode or not pane_id.isdigit():
        raise RuntimeError("Could not read the target Windows WEZTERM_PANE.")
    panes = json.loads(wezterm("list", "--format", "json"))
    found = next((p for p in panes if p["pane_id"] == int(pane_id)), None)
    if found is None:
        raise RuntimeError("The target WezTerm pane no longer exists.")
    return found


def jump_to(pane, source_tty):
    valid_pane(pane)
    attached = clients()
    source = next((c for c in attached if c["tty"] == source_tty), None)
    if source is None or not is_wezterm(source):
        raise RuntimeError("The source WezTerm client was not found. Reopen the tmux popup.")
    # The tmux server may have inherited another tab's old interop socket.
    interop = client_environment(source).get("WSL_INTEROP")
    if interop:
        os.environ["WSL_INTEROP"] = interop

    session = tmux("display-message", "-p", "-t", pane, "#{session_id}")
    candidates = [c for c in attached if c["session"] == session and is_wezterm(c)]
    target = max(candidates, key=lambda c: (c["tty"] == source_tty, c["activity"]), default=None)
    terminal = locate(target or source)
    if target:
        action = ["activate-pane", "--pane-id", str(terminal["pane_id"])]
    else:
        distro = os.environ.get("WSL_DISTRO_NAME")
        if not distro:
            raise RuntimeError("WSL_DISTRO_NAME is required to open a new tab.")
        tmux_executable = shutil.which("tmux")
        if not tmux_executable:
            raise RuntimeError("tmux was not found in PATH.")
        action = ["spawn", "--window-id", str(terminal["window_id"]), "--domain-name", "local", "--",
                  "wsl.exe", "--distribution", distro, "--user", pwd.getpwuid(os.getuid()).pw_name,
                  "--exec", tmux_executable, "-S", socket_path(), "attach-session", "-t", session]

    # Select only within the TARGET session. Never switch/detach any client.
    tmux("select-window", "-t", pane)
    tmux("select-pane", "-t", pane)
    wezterm(*action)


def clean(value):
    return re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", str(value or ""))


def rows():
    sessions = json.loads(run("ccmux", "show", "--json"))
    priority = {"waiting": 0, "working": 1, "idle": 2}
    labels = {"waiting": "Waiting", "working": "Working", "idle": "Idle"}
    attention = {"permission": "Approval", "question": "Question", "plan": "Review plan"}
    sessions.sort(key=lambda s: (priority.get(s.get("status"), 3), s.get("project", "")))
    result = []
    for s in sessions:
        pane = s.get("tmuxPane") or ""
        if not re.fullmatch(r"%[0-9]+", pane):
            continue
        status = labels.get(s.get("status"), clean(s.get("status")) or "Unknown")
        if s.get("status") == "waiting":
            status = attention.get(s.get("attentionType"), status)
        branch = f" ({clean(s['gitBranch'])})" if s.get("gitBranch") else ""
        label = (f"[{status}] {clean(s.get('agentType'))} | {clean(s.get('project'))}{branch}"
                 f" | {clean(s.get('summary') or s.get('paneTitle'))} | {clean(s.get('cwd'))}")
        result.append(f"{pane}\t{label}")
    return "\n".join(result)


def picker():
    command = shlex.join([sys.executable, str(Path(__file__).resolve())])
    env = dict(os.environ, FZF_DEFAULT_OPTS="", FZF_DEFAULT_OPTS_FILE="")
    result = subprocess.run([
        "fzf", "--delimiter", "\t", "--with-nth", "2..", "--no-multi", "--no-sort",
        "--layout=reverse", "--border", "--track", "--id-nth", "1", "--prompt", "Agents> ",
        "--header", "Enter: jump to tab  Esc: close  Ctrl-J/K: select  Ctrl-R: refresh (auto: 3s)",
        "--bind", f"every(3),ctrl-r:reload-sync({command} --list)",
        "--bind", "load:refresh-preview",
        "--preview", f"{command} --preview {{1}}",
        "--preview-window", "right:55%:wrap",
    ], input=rows(), stdout=subprocess.PIPE, text=True, env=env)
    if result.returncode in (1, 130):
        return None
    if result.returncode:
        raise RuntimeError(f"fzf: exit {result.returncode}")
    return result.stdout.split("\t", 1)[0].strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-tty", help="tmux #{client_tty} of the client opening the popup")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--list", action="store_true", help="print rows for the picker")
    mode.add_argument("--preview", metavar="PANE", help="print a tmux pane's visible output and recent history")
    mode.add_argument("--jump", metavar="PANE", help="jump to a tmux pane's terminal tab")
    args = parser.parse_args()
    try:
        if args.list:
            print(rows())
        elif args.preview:
            print(tmux("capture-pane", "-p", "-t", valid_pane(args.preview), "-S", "-100"))
        else:
            if not args.client_tty:
                raise RuntimeError("Open the configured tmux popup, or pass --client-tty.")
            pane = args.jump or picker()
            if pane:
                jump_to(pane, args.client_tty)
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(f"ccmux-jump: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
