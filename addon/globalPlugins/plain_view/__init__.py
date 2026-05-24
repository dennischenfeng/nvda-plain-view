# -*- coding: UTF-8 -*-
# PlainView NVDA add-on
# Copyright (C) 2026 Dennis Feng
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.
# See COPYING.txt at the root of this project for the full license text.

import ctypes
import os
import re
import subprocess
import tempfile
import time

import api
import config
import controlTypes
import core
import globalPluginHandler
import gui
import speech
import textInfos
import ui
import winUser
import wx
from gui.settingsDialogs import NVDASettingsDialog, SettingsPanel
from logHandler import log
from scriptHandler import script

try:
    import addonHandler

    addonHandler.initTranslation()
except Exception:
    pass


TEMP_FILENAME = "plainview.txt"
TEMP_PATH = os.path.join(tempfile.gettempdir(), TEMP_FILENAME)

CONFIG_SECTION = "plainView"
EDITOR_NOTEPAD = "notepad"
EDITOR_NOTEPAD_PP = "notepadpp"
_EDITOR_CHOICES = (EDITOR_NOTEPAD, EDITOR_NOTEPAD_PP)

config.conf.spec[CONFIG_SECTION] = {
    "editor": f"option({', '.join(repr(c) for c in _EDITOR_CHOICES)}, default='{EDITOR_NOTEPAD}')",
}


class PlainViewSettingsPanel(SettingsPanel):
    # Translators: title of the PlainView category in NVDA's Settings dialog.
    title = _("PlainView")

    # Translators: labels for the editor combo box choices, in the same order
    # as _EDITOR_CHOICES above.
    _EDITOR_LABELS = (_("Notepad"), _("Notepad++"))

    def makeSettings(self, settingsSizer):
        helper = gui.guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
        # Translators: label for the editor combo box in PlainView settings.
        self.editorCombo = helper.addLabeledControl(
            _("&Editor used to open the dumped text:"),
            wx.Choice,
            choices=list(self._EDITOR_LABELS),
        )
        current = config.conf[CONFIG_SECTION]["editor"]
        try:
            self.editorCombo.SetSelection(_EDITOR_CHOICES.index(current))
        except ValueError:
            self.editorCombo.SetSelection(0)

    def onSave(self):
        config.conf[CONFIG_SECTION]["editor"] = _EDITOR_CHOICES[self.editorCombo.GetSelection()]

_SW_MAXIMIZE = 3
_GA_ROOT = 2

# Claude Code attention-point patterns, ported from the VS Code prototype.
_CC_ITEM_LINE_RE = re.compile(r"^[∴●>❯!].*\S")
_CC_HRULE = "───"
_CC_PROMPT_SCAN_LINES = 10
# Matches a line whose first non-whitespace character is the ❯ chevron Claude
# Code uses to mark the currently selected multiple-choice option; captures the
# text after it.
_CC_SELECTED_OPTION_RE = re.compile(r"^\s*❯\s*(.*)$")


def _line_is_cc_item(line: str) -> bool:
    return _CC_ITEM_LINE_RE.search(line) is not None


def _line_is_hrule(line: str) -> bool:
    return _CC_HRULE in line


def _find_last_claude_code_selected_option(text: str) -> str | None:
    """Return the text after the last `❯ ` chevron-prefixed line in `text`, or
    None if no such line is present.
    """
    last_match: str | None = None
    for line in text.split("\n"):
        m = _CC_SELECTED_OPTION_RE.match(line)
        if m:
            last_match = m.group(1)
    return last_match


def _speak_caret_line(obj) -> None:
    """Cancel any in-progress speech and speak the line containing `obj`'s caret."""
    lineInfo = obj.makeTextInfo(textInfos.POSITION_CARET)
    lineInfo.expand(textInfos.UNIT_LINE)
    speech.cancelSpeech()
    speech.speakTextInfo(lineInfo, reason=controlTypes.OutputReason.CARET)


def _tidy_dump(text: str) -> str:
    """Strip trailing whitespace from every line and drop trailing blank lines.
    Preserves blank lines in the body; only fully-whitespace lines at the very
    end of the document are removed.
    """
    lines = [line.rstrip() for line in text.splitlines()]
    while lines and not lines[-1]:
        lines.pop()
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def _grab_focused_text() -> str | None:
    """Pull all text from the currently-focused object via NVDA's TextInfo APIs.

    Returns None and announces the situation if the focused control doesn't
    expose a usable POSITION_ALL range or yields no text.
    """
    focus = api.getFocusObject()
    try:
        ti = focus.makeTextInfo(textInfos.POSITION_ALL)
        text = ti.text
        if text:
            return text
    except Exception:
        log.debug("PlainView: POSITION_ALL TextInfo failed", exc_info=True)
        ui.message(_("PlainView: focused control does not expose readable text"))
        return None
    ui.message(_("PlainView: focused control returned no text"))
    return None


def _find_notepad_hwnd(needle: str, title_suffix: str, timeout_s: float) -> int | None:
    """Find a visible top-level window whose title contains `needle` and ends
    with `title_suffix`. Polls until the window appears or `timeout_s` elapses.
    Works for both classic Notepad (new process per launch) and Win11 tabbed
    Notepad (new tab in singleton); also works for Notepad++.
    """

    def predicate(hwnd: int) -> bool:
        if not winUser.isWindowVisible(hwnd):
            return False
        title = winUser.getWindowText(hwnd)
        return needle in title and title.endswith(title_suffix)

    # Synchronous poll: blocks NVDA's main thread for up to timeout_s. Accepted
    # because EnumWindows doesn't depend on NVDA's event loop; switching to
    # core.callLater here would force _open_plain_view to become async too.
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        hwnd = winUser.findTopLevelWindow(predicate)
        if hwnd:
            return hwnd
        time.sleep(0.05)
    return None


def _foreground_window(hwnd: int) -> None:
    ctypes.windll.user32.ShowWindow(hwnd, _SW_MAXIMIZE)
    winUser.setForegroundWindow(hwnd)


def _is_claude_code_awaiting_regular_prompt(lines: list[str]) -> bool:
    """True if the bottom lines contain Claude Code's prompt-input box:
    three consecutive lines starting with ───, ❯, and ─── respectively.
    """
    total = len(lines)
    start = max(0, total - _CC_PROMPT_SCAN_LINES)
    for i in range(start, total - 2):
        if (
            lines[i].startswith(_CC_HRULE)
            and lines[i + 1].startswith("❯")
            and lines[i + 2].startswith(_CC_HRULE)
        ):
            return True
    return False


def _find_claude_code_attention_line(text: str) -> int | None:
    """Return the 1-based line number of the Claude Code attention point in `text`,
    or None if no attention point can be identified.

    - If Claude Code appears to be awaiting a regular text prompt: the last line
      starting with one of ∴ ● > ❯ !  (a Claude Code item line).
    - Otherwise: the last line containing ───.
    """
    lines = text.splitlines()
    if not lines:
        return None
    predicate = (
        _line_is_cc_item if _is_claude_code_awaiting_regular_prompt(lines) else _line_is_hrule
    )
    for idx in range(len(lines) - 1, -1, -1):
        if predicate(lines[idx]):
            return idx + 1
    return None


def _move_notepad_caret_to_line(notepad_hwnd: int, line: int, timeout_s: float = 1.6) -> None:
    """Asynchronously poll for NVDA focus to settle inside the given Notepad
    window, then move the caret to the 1-based `line` and speak it. Returns
    immediately; the actual move happens later on NVDA's wx event loop via
    core.callLater.
    """
    log.debug(
        "PlainView: scheduling caret move; notepad_hwnd=%s target_line=%s", notepad_hwnd, line
    )
    interval_ms = 40
    attempts = max(1, int((timeout_s * 1000) / interval_ms))

    def _try(remaining: int) -> None:
        candidate = api.getFocusObject()
        candidate_hwnd = getattr(candidate, "windowHandle", None) or 0
        root = winUser.getAncestor(candidate_hwnd, _GA_ROOT) if candidate_hwnd else 0
        # Require a descendant, not the chrome itself: after SetForegroundWindow
        # NVDA briefly reports focus on the outer Notepad window (role=WINDOW),
        # then refines to the inner RichEditD2DPT edit. Matching on the chrome
        # leads to updateCaret raising NotImplementedError.
        is_descendant = candidate_hwnd and root == notepad_hwnd and candidate_hwnd != notepad_hwnd
        if is_descendant:
            try:
                ti = candidate.makeTextInfo(textInfos.POSITION_FIRST)
                want = line - 1
                moved = ti.move(textInfos.UNIT_PARAGRAPH, want) if want > 0 else 0
                if moved == want:
                    ti.updateCaret()
                    _speak_caret_line(candidate)
                    return
                # Short move means the document isn't fully loaded yet; keep polling.
                log.debug(
                    "PlainView: short paragraph move (%s of %s); continuing to poll", moved, want
                )
            except NotImplementedError:
                log.debug("PlainView: focus object not editable yet; continuing to poll")
            except Exception:
                log.debug("PlainView: TextInfo caret move failed", exc_info=True)
                return
        if remaining <= 0:
            log.debug(
                "PlainView: focus did not propagate to Notepad inner edit (hwnd=%s)", notepad_hwnd
            )
            return
        core.callLater(interval_ms, _try, remaining - 1)

    core.callLater(interval_ms, _try, attempts)


def _nav_by_predicate(predicate, forward: bool) -> None:
    """Move the caret of the currently-focused text control to the next/previous
    paragraph where `predicate(text)` is truthy. Speaks the landing line, or
    announces "No more matches" if nothing matches in the chosen direction.

    Walks paragraph-by-paragraph from the caret; avoids slurping the whole
    document on every keystroke.
    """
    obj = api.getFocusObject()
    try:
        cur = obj.makeTextInfo(textInfos.POSITION_CARET)
        # Normalize to the start of the current paragraph so subsequent moves
        # are unambiguous and the current paragraph is excluded from search.
        cur.expand(textInfos.UNIT_PARAGRAPH)
        cur.collapse()
    except (NotImplementedError, RuntimeError):
        log.debug("PlainView: nav skipped — focused object has no usable TextInfo", exc_info=True)
        return
    step = 1 if forward else -1
    while True:
        try:
            moved = cur.move(textInfos.UNIT_PARAGRAPH, step)
        except Exception:
            log.debug("PlainView: paragraph move failed during nav", exc_info=True)
            return
        if moved == 0:
            break
        probe = cur.copy()
        probe.expand(textInfos.UNIT_PARAGRAPH)
        if predicate(probe.text):
            try:
                cur.updateCaret()
            except Exception:
                log.debug("PlainView: updateCaret failed during nav", exc_info=True)
                return
            _speak_caret_line(obj)
            return
    speech.cancelSpeech()
    ui.message(_("No more matches"))


def _resolve_editor_command() -> tuple[list[str], str, str, float] | None:
    """Return (argv-prefix, window-title-suffix, friendly-name, find-timeout-s)
    for the editor selected in config, or None if the configured editor cannot
    be located.
    """
    editor = config.conf[CONFIG_SECTION]["editor"]
    if editor == EDITOR_NOTEPAD_PP:
        for candidate in (
            r"C:\Program Files\Notepad++\notepad++.exe",
            r"C:\Program Files (x86)\Notepad++\notepad++.exe",
        ):
            if os.path.isfile(candidate):
                return [candidate], " - Notepad++", "Notepad++", 1.5
        ui.message(_("PlainView: Notepad++ not found; check the editor setting"))
        return None
    return ["notepad.exe"], " - Notepad", "Notepad", 1.5


def _open_plain_view() -> tuple[int, str] | None:
    """Phase 1 core: scrape focused window text → temp file → editor → foreground.

    Returns (editor_hwnd, dumped_text) on success, or None if any step failed
    such that we couldn't get the editor on screen with our file.
    """
    text = _grab_focused_text()
    if text is None:
        return None
    text = _tidy_dump(text)
    try:
        with open(TEMP_PATH, "w", encoding="utf-8", newline="") as f:
            f.write(text)
    except OSError:
        log.error("PlainView: failed to write temp file %s", TEMP_PATH, exc_info=True)
        ui.message(_("PlainView: could not write temp file"))
        return None

    resolved = _resolve_editor_command()
    if resolved is None:
        return None
    argv_prefix, title_suffix, friendly, find_timeout_s = resolved

    try:
        subprocess.Popen([*argv_prefix, TEMP_PATH], close_fds=True)
    except OSError:
        log.error("PlainView: failed to launch %s", friendly, exc_info=True)
        ui.message(_("PlainView: could not launch {editor}").format(editor=friendly))
        return None

    hwnd = _find_notepad_hwnd(TEMP_FILENAME, title_suffix, find_timeout_s)
    if hwnd is None:
        ui.message(_("PlainView: could not locate {editor} window").format(editor=friendly))
        return None

    _foreground_window(hwnd)
    return hwnd, text


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    scriptCategory = "PlainView"

    def __init__(self):
        super().__init__()
        NVDASettingsDialog.categoryClasses.append(PlainViewSettingsPanel)

    def terminate(self):
        try:
            NVDASettingsDialog.categoryClasses.remove(PlainViewSettingsPanel)
        except ValueError:
            pass
        super().terminate()

    @script(
        description=_("Open PlainView: copy terminal text to a temp file and open it in Notepad."),
        category="PlainView",
        gesture=None,
    )
    def script_openPlainView(self, gesture):
        _open_plain_view()

    @script(
        description=_("Open PlainView with Claude Code attention jump."),
        category="PlainView",
        gesture=None,
    )
    def script_openPlainViewWithClaudeCodeAttentionJump(self, gesture):
        result = _open_plain_view()
        if result is None:
            return
        hwnd, text = result
        target_line = _find_claude_code_attention_line(text)
        if target_line is None:
            ui.message(_("No Claude Code attention point found"))
            return
        _move_notepad_caret_to_line(hwnd, target_line)

    @script(
        description=_("PlainView: jump to next Claude Code item line."),
        category="PlainView",
        gesture=None,
    )
    def script_nextClaudeCodeItem(self, gesture):
        _nav_by_predicate(_line_is_cc_item, forward=True)

    @script(
        description=_("PlainView: jump to previous Claude Code item line."),
        category="PlainView",
        gesture=None,
    )
    def script_previousClaudeCodeItem(self, gesture):
        _nav_by_predicate(_line_is_cc_item, forward=False)

    @script(
        description=_("PlainView: jump to next horizontal rule."),
        category="PlainView",
        gesture=None,
    )
    def script_nextHorizontalRule(self, gesture):
        _nav_by_predicate(_line_is_hrule, forward=True)

    @script(
        description=_("PlainView: jump to previous horizontal rule."),
        category="PlainView",
        gesture=None,
    )
    def script_previousHorizontalRule(self, gesture):
        _nav_by_predicate(_line_is_hrule, forward=False)

    @script(
        description=_("PlainView: speak the currently selected Claude Code option."),
        category="PlainView",
        gesture=None,
    )
    def script_speakClaudeCodeSelectedOption(self, gesture):
        text = _grab_focused_text()
        if text is None:
            return
        selected = _find_last_claude_code_selected_option(text)
        speech.cancelSpeech()
        if selected is not None:
            speech.speakMessage(selected)
        else:
            ui.message(_("No selected option found"))

    @script(
        description=_("PlainView: speak the current line number and total line count."),
        category="PlainView",
        gesture=None,
    )
    def script_speakLinePosition(self, gesture):
        obj = api.getFocusObject()
        try:
            all_ti = obj.makeTextInfo(textInfos.POSITION_ALL)
            caret_ti = obj.makeTextInfo(textInfos.POSITION_CARET)
            head = obj.makeTextInfo(textInfos.POSITION_FIRST)
            head.setEndPoint(caret_ti, "endToStart")
        except (NotImplementedError, RuntimeError):
            log.debug(
                "PlainView: line position skipped — focused object has no usable TextInfo",
                exc_info=True,
            )
            return
        # Win11 Notepad's UIA GetText() returns \r-only line endings.
        head_text = head.text.replace("\r\n", "\n").replace("\r", "\n")
        current_line = head_text.count("\n") + 1
        total_lines = len(all_ti.text.splitlines())
        ui.message(
            _("Current line: {current}. Total lines: {total}.").format(
                current=current_line, total=total_lines
            )
        )
