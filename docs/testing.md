# Testing

## Automated tests

From the repository root:

```sh
python3 -m unittest discover -s tests -v
```

These tests mock command execution; they do not connect to a tmux server or
activate terminal tabs. They cover client selection, session preservation,
opening a new tab, Windows pane lookup, executable discovery, and list formatting.

## Windows/WSL smoke test

Use disposable tmux sessions and agents you can safely leave idle. Run the same
ccmux setup used for normal work. Do not point tests at ongoing agent tasks.

1. Open two WezTerm tabs attached to different tmux sessions on the same server,
   called A and B. Start a ccmux-visible agent in B.
2. From A, open the popup. Confirm that searching works, the right-hand preview
   matches B, and both update after three seconds. Esc should close the popup.
3. Open it again and choose B. Check that WezTerm selects B's existing tab, and
   A's tab remains attached to A. Compare `tmux list-clients -F
   '#{client_tty}:#{session_id}'` before and after.
4. Create a third session C with a ccmux-visible agent and detach its client.
   Select C from A. A new tab should attach C, leaving A and B unchanged.
5. Return to A and select C again. It should reuse the new tab.
6. If a session has multiple tmux windows/panes, select an agent in a different
   window/pane and verify that it becomes active within the target session.
7. Confirm that explicit terminal titles have not changed. Close only the test
   agents/sessions/tabs created for this check.

To test only navigation without creating agents, use a known disposable tmux
pane ID and source **client tty** (from `tmux list-clients`):

```sh
python3 ccmux_jump.py --client-tty /dev/pts/EXAMPLE --jump %EXAMPLE
```

Replace both placeholders. The client tty is the terminal outside tmux, not
the value of `tty` in a tmux pane. This bypasses fzf and ccmux listing only.
