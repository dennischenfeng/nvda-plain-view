# Changelog

## 0.1.0

Initial release.

Pipes the focused terminal's text into Notepad for easier screen-reader navigation, with Claude Code-aware navigation gestures. All scripts are unbound by default; assign keys via NVDA's Input Gestures dialog under the **PlainView** category.

Eight scripts:

- **Open PlainView** — copies the focused terminal's text to `%TEMP%\plainview.txt`, opens it in Notepad, brings Notepad to the foreground maximized.
- **Open PlainView with Claude Code attention jump** — same as above, then moves the caret to the most useful read-from line in the dump (last `∴ ● > ❯ !` item line when Claude is awaiting a prompt; last `───` divider otherwise) and speaks it.
- **Jump to next / previous Claude Code item line** — caret-walks between lines starting with one of `∴ ● > ❯ !`.
- **Jump to next / previous horizontal rule** — caret-walks between lines containing `───`.
- **Speak the currently selected Claude Code option** — speaks the option text after the most recent `❯` chevron in the focused terminal when Claude shows a multiple-choice prompt.
- **Speak the current line number and total line count** — announces "Current line: N. Total lines: M." for the focused editable text control.

The four nav scripts operate on any focused editable text control, so they work in Notepad, VS Code, Word, and similar.

Minimum NVDA version: 2026.1.
