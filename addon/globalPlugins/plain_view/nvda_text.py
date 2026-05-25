# -*- coding: UTF-8 -*-
# PlainView NVDA add-on
# Copyright (C) 2026 Dennis Feng
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.
# See COPYING.txt at the root of this project for the full license text.

"""NVDA caret/speech glue: read text from the focused control, navigate it
paragraph-by-paragraph, move the editor caret, and speak position info.

Everything here talks to NVDA's TextInfo/speech APIs. The pure pattern logic
these functions act on lives in `text.py`; navigation takes a predicate so it
stays decoupled from the specific patterns.
"""

import api
import controlTypes
import core
import speech
import textInfos
import ui
import winUser
from logHandler import log

try:
    import addonHandler

    addonHandler.initTranslation()
except Exception:
    pass


_GA_ROOT = 2


def _speak_caret_line(obj) -> None:
    """Cancel any in-progress speech and speak the line containing `obj`'s caret."""
    lineInfo = obj.makeTextInfo(textInfos.POSITION_CARET)
    lineInfo.expand(textInfos.UNIT_LINE)
    speech.cancelSpeech()
    speech.speakTextInfo(lineInfo, reason=controlTypes.OutputReason.CARET)


def grab_focused_text() -> str | None:
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


def move_caret_to_line(editor_hwnd: int, line: int, timeout_s: float = 1.6) -> None:
    """Asynchronously poll for NVDA focus to settle inside the given editor
    window, then move the caret to the 1-based `line` and speak it. Returns
    immediately; the actual move happens later on NVDA's wx event loop via
    core.callLater.
    """
    log.debug(
        "PlainView: scheduling caret move; editor_hwnd=%s target_line=%s", editor_hwnd, line
    )
    interval_ms = 40
    attempts = max(1, int((timeout_s * 1000) / interval_ms))

    def _try(remaining: int) -> None:
        candidate = api.getFocusObject()
        candidate_hwnd = getattr(candidate, "windowHandle", None) or 0
        root = winUser.getAncestor(candidate_hwnd, _GA_ROOT) if candidate_hwnd else 0
        # Require a descendant, not the chrome itself: after SetForegroundWindow
        # NVDA briefly reports focus on the outer editor window (role=WINDOW),
        # then refines to the inner RichEditD2DPT edit. Matching on the chrome
        # leads to updateCaret raising NotImplementedError.
        is_descendant = candidate_hwnd and root == editor_hwnd and candidate_hwnd != editor_hwnd
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
                "PlainView: focus did not propagate to editor inner edit (hwnd=%s)", editor_hwnd
            )
            return
        core.callLater(interval_ms, _try, remaining - 1)

    core.callLater(interval_ms, _try, attempts)


def nav_by_predicate(predicate, forward: bool) -> None:
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


def speak_line_position() -> None:
    """Announce the caret's 1-based line number and the document's total line count."""
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
