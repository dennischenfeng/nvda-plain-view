# Changelog

## 0.2.3

Internal refactor and consolidation of the agent-aware scripts:

- Split the monolithic global plugin into focused modules (pure text analysis, settings, editor launch, NVDA glue) for readability; the split itself changes no behavior.
- Merged the separate Claude Code and Codex item-line navigation into a single pair, **Jump to next / previous CC or Codex message item line**, since the predicate already matched both agents' markers (`∴ ● • › > ❯ !`). The standalone Codex item nav scripts were removed.
- Renamed **Speak the currently selected Claude Code option** to **Speak the currently selected CC or Codex option** (it already recognized both `❯` and `›`).
- Removed **Speak the current line number and total line count**, superseded by editor-provided line info.

Renaming and removing scripts changes their gesture identifiers, so reassign any keys you had bound to these in NVDA's Input Gestures dialog.

## 0.2.2

Added Codex CLI support, mirroring the Claude Code scripts:

- **Open PlainView with Codex attention jump** — dumps the focused terminal, then moves the caret to the most recent `•` bullet line (the start of the latest Codex response) and speaks it.
- **Jump to next / previous Codex item line** — caret-walks between lines starting with `•` (assistant response bullets) or `›` (user prompts).

The Claude Code item nav (and attention jump) now also recognizes `•` bullet and `›` lines.

The "speak the currently selected Claude Code option" script now also recognizes Codex's `›` selection chevron, so it works for both Claude Code (`❯`) and Codex menus.

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
