# Plain View

An NVDA add-on that pipes the focused terminal's text into Notepad for easier screen-reader navigation. Built for working alongside CLI tools (e.g. Claude Code) where scrolling and jumping around the output with a screen reader is awkward.

## What it does

Two scripts, both unbound by default — assign keys via NVDA's Input Gestures dialog under the **Plain View** category.

- **Open Plain View** — copies the focused terminal's text via NVDA's TextInfo, writes it to `%TEMP%\plainview.txt`, opens that file in Notepad (a new tab in the existing Notepad instance on Win11), and brings Notepad to the foreground maximized.
- **Open Plain View with Claude Code attention jump** — same as above, plus moves the caret to the most useful read-from line for Claude Code output and speaks it (cancelling any in-progress speech). Specifically:
  - If Claude is awaiting a regular text prompt (the `───` / `❯` / `───` input box is visible near the bottom): the caret jumps to the most recent line beginning with one of `∴ ● > ❯ !`.
  - Otherwise (e.g. Claude is asking a multiple-choice question): the caret jumps to the most recent `───` divider.

If no attention point can be identified, the add-on says "No Claude Code attention point found" and leaves the caret at the top of the file.

## Installation

Grab a release `.nvda-addon` from this repo's releases (or build one — see below), then either double-click it or install via NVDA → Tools → Add-on Store → Install from external file. Restart NVDA. Min NVDA version: **2026.1**.

## Build from source

Requires [`uv`](https://docs.astral.sh/uv/):

```
uv run scons
```

The built package lands at `dist/PlainView-<version>.nvda-addon`.

## Implementation notes

A few things worth knowing if you read the code or hit unexpected behaviour:

- **The temp file at `%TEMP%\plainview.txt` is reused, not unique-per-invocation.** Each gesture overwrites it. The path is in your user's temp directory, readable by anything running as your user account. If you dump output that contains secrets, treat the file the same way you'd treat the terminal scrollback itself.
- **Fallback to the clipboard.** If NVDA's TextInfo path can't read the focused control (rare for terminals; possible for some non-terminal windows), the add-on falls back to reading the clipboard. If you fire the gesture from a window that NVDA can't read, whatever is currently on your clipboard gets dumped into `plainview.txt`. Be aware of this if you have a password manager primed.
- **Notepad detection is by window title** (matching `… - Notepad`), so the script works equally well for classic Notepad and the Win11 tabbed Notepad — including the case where opening the file just activates an existing tab inside the running Notepad singleton.
- **Caret movement is asynchronous.** After foregrounding Notepad, the add-on polls NVDA's focus state on the wx event loop until focus settles inside the Notepad edit control, then issues a TextInfo paragraph move. This avoids blocking NVDA's main thread during cross-app focus propagation.

## License

GPL v2 (see `COPYING.txt`). This is required because the project incorporates code patterns derived from mltony's GPL v2 NVDA add-ons. Any redistribution must include source.
