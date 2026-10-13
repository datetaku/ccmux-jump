# ccmux-jump

[日本語](README.ja.md)

Find an AI coding agent in a tmux popup and jump to its existing WezTerm tab,
keeping the source tab attached to its original tmux session.

Built for **Windows WezTerm + WSL**. A standalone Python script uses
[ccmux](https://github.com/epilande/ccmux) as its session data source and
[fzf](https://github.com/junegunn/fzf) as its picker. No modifications to ccmux
and no WezTerm Lua configuration are required. This is an independent project.

## What it does

- Lists status, agent, project, branch, task summary, and working directory.
- Puts agents waiting for input first, with a live tmux output preview.
- Refreshes the list and preview every three seconds while the picker is open.
- Activates the WezTerm pane/tab already attached to the selected tmux session.
- Opens a tab in the source window if that session has no attached WezTerm client.
- Keeps the source client's tmux session unchanged.

The popup is a custom fzf interface, rather than ccmux's built-in picker.
Agent discovery and status accuracy come from ccmux.

## Requirements

| Component | Requirement |
| --- | --- |
| Environment | Windows WezTerm running a local WSL distribution, with WSL interop enabled |
| Python | 3.10+ in WSL; standard library only, no pip packages |
| tmux | Popup and `run-shell -C` support; tested with 3.7c |
| fzf | 0.73.0+ for the [`every(N)` event](https://github.com/junegunn/fzf/blob/master/CHANGELOG.md#0730); tested with 0.74.4 |
| ccmux | Working `ccmux show --json`; tested with 1.4.3 |
| WezTerm | Windows CLI with `list`, [`activate-pane`](https://wezterm.org/cli/cli/activate-pane.html), and [`spawn`](https://wezterm.org/cli/cli/spawn.html) |

Install the dependencies first, following their upstream instructions. ccmux's
Bun-based installation also requires Bun. All of `python3`, `tmux`, `fzf`, and
`ccmux` must be accessible from the tmux popup's `PATH`.

## Install

Run inside WSL:

```sh
git clone https://github.com/datetaku/ccmux-jump.git
cd ccmux-jump
install -Dm755 ccmux_jump.py "$HOME/.local/bin/ccmux-jump"
```

The script looks for `wezterm.exe` in `PATH`, then in these locations:

- `/mnt/c/Program Files/WezTerm/wezterm.exe`
- `/mnt/c/WezTerm/wezterm.exe`

For another location, set the full **WSL path to the Windows executable** in
`~/.tmux.conf` before the binding below:

```tmux
set-environment -g CCMUX_JUMP_WEZTERM '/mnt/c/Tools/WezTerm/wezterm.exe'
```

Add this binding to `~/.tmux.conf`, choosing another key if `e` is already used:

```tmux
bind-key e run-shell -C 'display-popup -EE -w 90% -h 80% "~/.local/bin/ccmux-jump --client-tty #{client_tty}"'
```

Reload tmux:

```sh
tmux source-file ~/.tmux.conf
```

No WezTerm reload is needed. To update, pull this repository and repeat the
`install` command. To uninstall, remove the binding and the installed
`~/.local/bin/ccmux-jump` file, then reload tmux.

## Use

Open the popup with **your tmux prefix → e**. For a `Ctrl+Q` prefix, press
`Ctrl+Q`, release it, then press `e`; the binding does not change your prefix.

| Key | Action |
| --- | --- |
| Type text | Search the displayed fields |
| Up/Down or Ctrl+K/Ctrl+J | Select an agent |
| Enter | Jump to the selected agent's terminal tab |
| Ctrl+R | Refresh immediately |
| Esc | Close the picker |

If several WezTerm clients are attached to the target session, the current
client wins when it already shows that session. Otherwise the client with the
most recent tmux activity is selected.

An unsuccessful jump leaves its error visible in the popup. Press Esc to close it.

## How it works

```text
tmux popup → Python → ccmux show --json → fzf list + tmux capture-pane preview
                    ↓ Enter
              target tmux client
                    ↓ its WSL_INTEROP socket
              Windows WEZTERM_PANE → wezterm cli activate-pane / spawn
```

The script reads the tmux client's environment from `/proc/<pid>/environ`.
That client's WSL interop socket lets a short `cmd.exe` command read the
`WEZTERM_PANE` inherited by its Windows launcher, even when it is absent in WSL.
The ID is checked against `wezterm cli list --format json` before use.

It selects the target tmux window/pane, then activates its WezTerm pane. It never
calls `tmux switch-client` or `detach-client`. For a detached target, it starts
`wsl.exe` in a new tab and attaches the same distribution/user to the same tmux
socket and target session. No terminal keystrokes or title changes are used.

## Scope and troubleshooting

- Supported scope: local Windows WezTerm + WSL, with tmux clients launched from
  those WezTerm tabs. Native Linux/macOS, SSH, nested tmux, cross-distribution
  navigation, and other terminals are not supported by this implementation.
- Use the same tmux server as ccmux. Pane IDs such as `%3` are server-local.
- Multiple clients attached to the same tmux session share its window/pane
  selection, as usual. Selecting a target pane can therefore affect those clients.
- Multi-window foreground activation has not been verified; the tested workflow
  uses tabs in one WezTerm window.
- `unknown event: every` means fzf is too old. Install fzf 0.73.0 or newer.
- If the list is empty, first check `ccmux show --json`. Only entries with a
  tmux pane ID are listed. Start or repair ccmux using its own documentation.
- If a command is missing only in the popup, check the tmux server's `PATH`.
- If tab lookup fails, ensure the client still has a live `WSL_INTEROP` socket
  and was attached directly from a Windows WezTerm tab. Reattach from that tab
  after a WSL/terminal restart. A lookup failure reports an error rather than
  changing the source client's session.
- `cmd.exe` is found in `PATH`, with `/mnt/c/Windows/System32/cmd.exe` as a fallback.

This tool does not create agents, branches, or worktrees. Continue to use your
existing tools (including gtr, if desired) for those operations. It also does
not add desktop notifications or a background monitoring service.

## Development

```sh
python3 -m unittest discover -s tests -v
python3 ccmux_jump.py --help
```

The tests use mocks; they run on Linux without a live ccmux, tmux, or Windows GUI.
CI checks Python 3.10 and 3.14. GUI behavior needs a real Windows/WSL environment;
see [the manual verification steps](docs/testing.md).

## License

[MIT](LICENSE). ccmux, fzf, tmux, and WezTerm are separate projects with their own
licenses; they are not bundled here.
