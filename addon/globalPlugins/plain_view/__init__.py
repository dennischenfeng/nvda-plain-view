# -*- coding: UTF-8 -*-
# Plain View NVDA add-on
# Copyright (C) 2026 Dennis Feng
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.
# See COPYING.txt at the root of this project for the full license text.

import ctypes
import ctypes.wintypes as wt
import os
import re
import subprocess
import tempfile
import time

import api
import controlTypes
import core
import globalPluginHandler
import speech
import textInfos
import ui
from logHandler import log
from scriptHandler import script

try:
	import addonHandler
	addonHandler.initTranslation()
except Exception:
	pass


TEMP_FILENAME = "plainview.txt"
TEMP_PATH = os.path.join(tempfile.gettempdir(), TEMP_FILENAME)

_user32 = ctypes.windll.user32
_EnumWindowsProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
_SW_RESTORE = 9
_GA_ROOT = 2

# Claude Code attention-point patterns, ported from the VS Code prototype.
_CC_ITEM_LINE_RE = re.compile(r"^[∴●>❯!].*\S")
_CC_HRULE_RE = re.compile(r"───")


def _grab_focused_text() -> str:
	"""Pull all text from the currently-focused object via NVDA's TextInfo APIs.

	Falls back to the clipboard if TextInfo can't produce a POSITION_ALL range
	(some terminals/controls don't support it cleanly).
	"""
	focus = api.getFocusObject()
	try:
		ti = focus.makeTextInfo(textInfos.POSITION_ALL)
		text = ti.text
		if text:
			return text
	except Exception:
		log.debug("PlainView: POSITION_ALL TextInfo failed; falling back to clipboard", exc_info=True)
	try:
		return api.getClipData() or ""
	except Exception:
		log.debug("PlainView: clipboard fallback failed", exc_info=True)
		return ""


def _find_notepad_hwnd(needle: str, timeout_s: float = 1.5) -> int | None:
	"""Poll EnumWindows for a visible top-level window whose title contains
	`needle` and ends with " - Notepad". Works for both classic Notepad
	(new process per launch) and Win11 tabbed Notepad (new tab in singleton).
	"""
	deadline = time.monotonic() + timeout_s
	while time.monotonic() < deadline:
		found: list[int] = []

		def cb(hwnd, _lparam):
			if not _user32.IsWindowVisible(hwnd):
				return True
			length = _user32.GetWindowTextLengthW(hwnd)
			if length == 0:
				return True
			buf = ctypes.create_unicode_buffer(length + 1)
			_user32.GetWindowTextW(hwnd, buf, length + 1)
			title = buf.value
			if needle in title and title.endswith(" - Notepad"):
				found.append(hwnd)
				return False
			return True

		_user32.EnumWindows(_EnumWindowsProc(cb), 0)
		if found:
			return found[0]
		time.sleep(0.05)
	return None


def _foreground_window(hwnd: int) -> None:
	_user32.ShowWindow(hwnd, _SW_RESTORE)
	_user32.SetForegroundWindow(hwnd)


def _is_claude_code_awaiting_regular_prompt(lines: list[str]) -> bool:
	"""True if the bottom ~10 lines contain Claude Code's prompt-input box:
	three consecutive lines starting with ───, ❯, and ─── respectively.
	"""
	total = len(lines)
	start = max(0, total - 10)
	for i in range(start, total - 2):
		if (
			lines[i].startswith("───")
			and lines[i + 1].startswith("❯")
			and lines[i + 2].startswith("───")
		):
			return True
	return False


def _find_claude_code_attention_line(text: str) -> int | None:
	"""Return the 1-based line number of the Claude Code attention point in `text`,
	or None if no attention point can be identified.

	- If Claude Code appears to be awaiting a regular text prompt: the last line
	  ending in one of ∴ ● > ❯ !  (a Claude Code item line).
	- Otherwise: the last line containing ───.
	"""
	lines = text.splitlines()
	if not lines:
		return None
	if _is_claude_code_awaiting_regular_prompt(lines):
		pattern = _CC_ITEM_LINE_RE
	else:
		pattern = _CC_HRULE_RE
	for idx in range(len(lines) - 1, -1, -1):
		if pattern.search(lines[idx]):
			return idx + 1
	return None


def _move_notepad_caret_to_line(notepad_hwnd: int, line: int, attempts: int = 40, interval_ms: int = 40) -> None:
	"""Asynchronously poll for NVDA focus to settle inside the given Notepad
	window, then move the caret to the 1-based `line`. Returns immediately;
	the actual move happens later on NVDA's wx event loop via core.callLater.
	Total budget ≈ attempts * interval_ms ms.
	"""
	log.debug("PlainView: scheduling caret move; notepad_hwnd=%s target_line=%s", notepad_hwnd, line)

	def _try(remaining: int) -> None:
		candidate = api.getFocusObject()
		candidate_hwnd = getattr(candidate, "windowHandle", None) or 0
		root = _user32.GetAncestor(candidate_hwnd, _GA_ROOT) if candidate_hwnd else 0
		is_descendant = candidate_hwnd and root == notepad_hwnd and candidate_hwnd != notepad_hwnd
		if is_descendant:
			try:
				ti = candidate.makeTextInfo(textInfos.POSITION_FIRST)
				if line > 1:
					ti.move(textInfos.UNIT_PARAGRAPH, line - 1)
				ti.updateCaret()
				lineInfo = candidate.makeTextInfo(textInfos.POSITION_CARET)
				lineInfo.expand(textInfos.UNIT_LINE)
				speech.cancelSpeech()
				speech.speakTextInfo(lineInfo, reason=controlTypes.OutputReason.CARET)
				return
			except NotImplementedError:
				log.debug("PlainView: focus object not editable yet; continuing to poll")
			except Exception:
				log.debug("PlainView: TextInfo caret move failed", exc_info=True)
				return
		if remaining <= 0:
			log.debug("PlainView: focus did not propagate to Notepad inner edit (hwnd=%s)", notepad_hwnd)
			return
		core.callLater(interval_ms, _try, remaining - 1)

	core.callLater(interval_ms, _try, attempts)


def _open_plain_view() -> tuple[int, str] | None:
	"""Phase 1 core: scrape focused window text → temp file → Notepad → foreground.

	Returns (notepad_hwnd, dumped_text) on success, or None if any step failed
	such that we couldn't get Notepad on screen with our file.
	"""
	text = _grab_focused_text()
	try:
		with open(TEMP_PATH, "w", encoding="utf-8", newline="") as f:
			f.write(text)
	except OSError:
		log.error("PlainView: failed to write temp file %s", TEMP_PATH, exc_info=True)
		ui.message("Plain View: could not write temp file")
		return None

	try:
		subprocess.Popen(["notepad.exe", TEMP_PATH], close_fds=True)
	except OSError:
		log.error("PlainView: failed to launch Notepad", exc_info=True)
		ui.message("Plain View: could not launch Notepad")
		return None

	hwnd = _find_notepad_hwnd(TEMP_FILENAME)
	if hwnd is None:
		ui.message("Plain View: could not locate Notepad window")
		return None

	_foreground_window(hwnd)
	return hwnd, text


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	scriptCategory = "Plain View"

	@script(
		description=_("Open Plain View: copy terminal text to a temp file and open it in Notepad."),
		category="Plain View",
		gesture=None,
	)
	def script_openPlainView(self, gesture):
		_open_plain_view()

	@script(
		description=_("Open Plain View with Claude Code attention jump."),
		category="Plain View",
		gesture=None,
	)
	def script_openPlainViewWithClaudeCodeAttentionJump(self, gesture):
		result = _open_plain_view()
		if result is None:
			return
		hwnd, text = result
		target_line = _find_claude_code_attention_line(text)
		if target_line is None:
			ui.message("No Claude Code attention point found")
			return
		_move_notepad_caret_to_line(hwnd, target_line)
