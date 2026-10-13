import importlib.util
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("jump", Path(__file__).resolve().parents[1] / "ccmux_jump.py")
jump = importlib.util.module_from_spec(spec)
spec.loader.exec_module(jump)


class JumpTests(unittest.TestCase):
    def setUp(self):
        self.source = dict(pid=100, tty="/dev/pts/1", session="$1", activity=20)
        self.target = dict(pid=200, tty="/dev/pts/2", session="$2", activity=10)

    def run_jump(self, clients, target_session="$2"):
        commands, actions, locations = [], [], []

        def tmux(*args):
            commands.append(args)
            if args[0] == "display-message":
                return target_session
            return ""

        def locate(client):
            locations.append(client["tty"])
            return dict(pane_id=20, window_id=1)

        with patch.object(jump, "tmux", side_effect=tmux), \
             patch.object(jump, "clients", return_value=clients), \
             patch.object(jump, "is_wezterm", return_value=True), \
             patch.object(jump, "client_environment", return_value={"WSL_INTEROP": "/source/interop"}), \
             patch.object(jump.shutil, "which", return_value="/usr/bin/tmux"), \
             patch.object(jump, "locate", side_effect=locate), \
             patch.object(jump, "wezterm", side_effect=lambda *x: actions.append(x)), \
             patch.dict(os.environ, WSL_DISTRO_NAME="ExampleLinux", TMUX="/tmp/server,12,1"):
            jump.jump_to("%42", self.source["tty"])
        self.assertFalse(any(c[0] in {"switch-client", "detach-client"} for c in commands))
        return commands, actions, locations

    def test_attached_target_receives_focus_and_source_is_untouched(self):
        commands, actions, locations = self.run_jump([self.source, self.target])
        self.assertEqual(locations, [self.target["tty"]])
        self.assertEqual(actions, [("activate-pane", "--pane-id", "20")])
        self.assertIn(("select-window", "-t", "%42"), commands)
        self.assertIn(("select-pane", "-t", "%42"), commands)

    def test_current_client_wins_when_already_in_target_session(self):
        self.target["session"] = "$1"
        self.target["activity"] = 999
        _, _, locations = self.run_jump([self.source, self.target], "$1")
        self.assertEqual(locations, [self.source["tty"]])

    def test_most_recent_target_client_wins(self):
        recent = dict(self.target, pid=300, tty="/dev/pts/3", activity=999)
        _, _, locations = self.run_jump([self.source, self.target, recent])
        self.assertEqual(locations, [recent["tty"]])

    def test_detached_target_requests_new_tab_in_source_window(self):
        _, actions, locations = self.run_jump([self.source])
        self.assertEqual(locations, [self.source["tty"]])
        self.assertEqual(actions[0][:5], ("spawn", "--window-id", "1", "--domain-name", "local"))
        self.assertEqual(actions[0][-5:], ("-S", "/tmp/server", "attach-session", "-t", "$2"))

    def test_disconnected_source_does_not_mutate_tmux(self):
        with patch.object(jump, "clients", return_value=[self.target]), \
             patch.object(jump, "tmux") as tmux:
            with self.assertRaises(RuntimeError):
                jump.jump_to("%42", self.source["tty"])
            tmux.assert_not_called()

    def test_invalid_pane_is_never_passed_to_tmux(self):
        with patch.object(jump, "tmux") as tmux:
            with self.assertRaises(RuntimeError):
                jump.jump_to("%42; touch /tmp/no", self.source["tty"])
            tmux.assert_not_called()

    def test_lookup_uses_targets_interop_and_matching_windows_pane(self):
        panes = [dict(pane_id=1, window_id=0), dict(pane_id=2, window_id=1)]
        response = subprocess.CompletedProcess([], 0, stdout=b"2\r\n", stderr=b"")
        with patch.object(jump, "client_environment", return_value={"WSL_INTEROP": "/target/interop"}), \
             patch.object(jump.subprocess, "run", return_value=response) as cmd, \
             patch.object(jump, "wezterm", return_value=json.dumps(panes)), \
             patch.dict(os.environ, WSL_INTEROP="/wrong/interop"):
            result = jump.locate(self.target)
        self.assertEqual(result["pane_id"], 2)
        self.assertEqual(cmd.call_args.kwargs["env"]["WSL_INTEROP"], "/target/interop")

    def test_missing_windows_pane_is_rejected(self):
        response = subprocess.CompletedProcess([], 0, stdout=b"%WEZTERM_PANE%\r\n", stderr=b"")
        with patch.object(jump, "client_environment", return_value={"WSL_INTEROP": "/target/interop"}), \
             patch.object(jump.subprocess, "run", return_value=response), \
             patch.object(jump, "wezterm") as wezterm:
            with self.assertRaises(RuntimeError):
                jump.locate(self.target)
            wezterm.assert_not_called()

    def test_stale_windows_pane_is_rejected(self):
        response = subprocess.CompletedProcess([], 0, stdout=b"99\r\n", stderr=b"")
        with patch.object(jump, "client_environment", return_value={"WSL_INTEROP": "/target/interop"}), \
             patch.object(jump.subprocess, "run", return_value=response), \
             patch.object(jump, "wezterm", return_value='[{"pane_id": 2}]'):
            with self.assertRaisesRegex(RuntimeError, "no longer exists"):
                jump.locate(self.target)

    def test_missing_interop_does_not_run_windows_commands(self):
        with patch.object(jump, "client_environment", return_value={}), \
             patch.object(jump.subprocess, "run") as run:
            with self.assertRaisesRegex(RuntimeError, "WSL_INTEROP"):
                jump.locate(self.target)
            run.assert_not_called()

    def test_rows_prioritize_attention_and_sanitize_labels(self):
        data = [
            dict(tmuxPane="%1", status="idle", project="idle"),
            dict(tmuxPane="%2", status="waiting", attentionType="question", project="ask\n\x1b]test\x07"),
            dict(tmuxPane=None, status="waiting", project="no pane"),
        ]
        with patch.object(jump, "run", return_value=json.dumps(data)):
            rows = jump.rows().splitlines()
        self.assertEqual(len(rows), 2)
        self.assertTrue(rows[0].startswith("%2\t"))
        self.assertIn("Question", rows[0])
        self.assertNotIn("\x1b", rows[0])


class ExecutableTests(unittest.TestCase):
    def test_explicit_path_with_spaces_is_passed_as_one_argument(self):
        executable = "/mnt/c/Custom Tools/WezTerm/wezterm.exe"
        with patch.dict(os.environ, CCMUX_JUMP_WEZTERM=executable), \
             patch.object(jump, "run", return_value="[]") as run:
            jump.wezterm("list", "--format", "json")
            run.assert_called_once_with(executable, "cli", "list", "--format", "json")

    def test_windows_executable_on_path_takes_precedence(self):
        with patch.dict(os.environ, CCMUX_JUMP_WEZTERM=""), \
             patch.object(jump.shutil, "which", return_value="/custom/wezterm.exe"):
            self.assertEqual(jump.wezterm_executable(), "/custom/wezterm.exe")

    def test_standard_windows_install_is_discovered(self):
        with patch.dict(os.environ, CCMUX_JUMP_WEZTERM=""), \
             patch.object(jump.shutil, "which", return_value=None), \
             patch.object(Path, "is_file", return_value=True):
            self.assertEqual(jump.wezterm_executable(), "/mnt/c/Program Files/WezTerm/wezterm.exe")

    def test_missing_executable_gives_configuration_hint(self):
        with patch.dict(os.environ, CCMUX_JUMP_WEZTERM=""), \
             patch.object(jump.shutil, "which", return_value=None), \
             patch.object(Path, "is_file", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "CCMUX_JUMP_WEZTERM"):
                jump.wezterm_executable()


if __name__ == "__main__":
    unittest.main()
