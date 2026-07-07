# PlainView

PlainView is an NVDA add-on that aims to simply and quickly open a plaintext view of the terminal, especially useful for efficiently interacting withCLI-based  AI coding agents like Claude Code or Codex CLI.

Example usage scenario to illustrate its benefits:
- let's say I'm using Codex CLI in Windows Terminal, and I'm several user turns into a Codex conversation session. Codex gives me a long response, and I find it difficult to navigate the text effectively using the NVDA review cursor within the Windows Terminal app
- I press my hotkey (e.g. control+windows+j) to invoke the input gesture "Open PlainView with Codex attention jump", and immediately (<100 milliseconds) Notepad opens up and sets my cursor on the last AI assistant's message. Here, I typically invoke the "Read from cursor" command to read the full message.
- This plaintext view (in text editor) gives me full navigation capabilities, like control-f to find text, text selection start/stop markers (default hotkeys NVDA+F9 and NVDA+F10), IndentNav bookmark jumping on regex matches, etc. I find that unlocking these navigation capabilities is helpful for my productivity on terminal.
- I then press hotkeys for the input gesture "Jump to next/previous CC or Codex message item" to arrow up and down through the conversation, message by message, to read what occured.

PlainView supports Notepad and Notepad++. Choose the editor in NVDA's
PlainView settings panel.

# Details on the main gesture script
The main useful gesture script is called "Open PlainView with Codex attention jump" (or the Claude Code variant).

In particular, it performs the following sequence typically in <100 milliseconds:
1. copies the active terminal text into a fixed temp file
2. brings to foreground a text editor (like Notepad) and opens the temp file
3. moves the cursor (caret) to a structurally meaningful position in the terminal text, likely where you want to pay attention to first. I call it the "attention point", e.g. for Codex CLI, the attention point is the start of line of the latest AI assistant's message in the conversation history typically.

## Input gesture scripts (i.e. keystrokes)

PlainView scripts are unbound by default. Assign keys in NVDA's Input Gestures
dialog under the **PlainView** category.

| Script | Description |
| --- | --- |
| Open PlainView | Copy focused-window text to `plainview.txt`, open it in the configured editor, and bring that editor forward. |
| Open PlainView with Claude Code attention jump | Open PlainView, then jump to the most useful Claude Code line: the latest prompt/message marker for regular prompts, or the latest `───` divider for multiple-choice prompts. |
| Open PlainView with Codex attention jump | Open PlainView, then jump to the latest Codex response bullet line. |
| Jump to next CC or Codex message item line | Move to the next line starting with a Claude Code or Codex marker: `∴`, `●`, `•`, `›`, `>`, `❯`, or `!`. |
| Jump to previous CC or Codex message item line | Move to the previous Claude Code or Codex message marker line. |
| Jump to next horizontal rule | Move to the next line containing a Claude Code horizontal rule. |
| Jump to previous horizontal rule | Move to the previous line containing a Claude Code horizontal rule. |
| Speak the currently selected CC or Codex option | In a focused terminal, speak the latest selected multiple-choice option marked with `❯` or `›`. |

Navigation gestures work in the focused editable text control, not only in the
editor opened by PlainView. If no target is found, PlainView announces that
there are no more matches or that no attention point/selected option was found.

## Installation

Navigate the to `releases` directory, download a release `.nvda-addon`, open it, and restart NVDA.
Minimum NVDA version: **2026.1**.

## Build from source

Requires [`uv`](https://docs.astral.sh/uv/):

```console
uv run scons
```

The package is written to the repo root as `PlainView-<version>.nvda-addon`.

## Notes

- `plainview.txt` is reused on each capture. Treat it like terminal scrollback
  if it contains secrets.
- If NVDA cannot read the focused control, PlainView may fall back to clipboard
  text.
- Editor windows are detected by title, so existing Notepad tabs and Notepad++
  windows are reused when Windows does that naturally.

## License

GPL v2. See `COPYING.txt`.

## Credits

Built on the official [NVDA AddonTemplate](https://github.com/nvaccess/addonTemplate).
The task switching capability (bringing apps to foreground using Windows handlers) was initially inspired by mltony's open-sourced Task Switcher NVDA addon.
