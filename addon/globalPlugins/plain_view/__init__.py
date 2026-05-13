# -*- coding: UTF-8 -*-
# Plain View NVDA add-on
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
import controlTypes
import core
import globalPluginHandler
import speech
import textInfos
import ui
import winUser
from logHandler import log
from scriptHandler import script

try:
	import addonHandler
	addonHandler.initTranslation()
except Exception:
	pass


TEMP_FILENAME = "plainview.txt"
TEMP_PATH = os.path.join(tempfile.gettempdir(), TEMP_FILENAME)

_SW_MAXIMIZE = 3
_GA_ROOT = 2

# Claude Code attention-point patterns, ported from the VS Code prototype.
_CC_ITEM_LINE_RE = re.compile(r"^[∴●>❯!].*\S")
_CC_HRULE = "───"
_CC_PROMPT_SCAN_LINES = 10


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
	"""Find a visible top-level window whose title contains `needle` and ends
	with " - Notepad". Polls until the window appears or `timeout_s` elapses.
	Works for both classic Notepad (new process per launch) and Win11 tabbed
	Notepad (new tab in singleton).
	"""
	def predicate(hwnd: int) -> bool:
		if not winUser.isWindowVisible(hwnd):
			return False
		title = winUser.getWindowText(hwnd)
		return needle in title and title.endswith(" - Notepad")

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
	awaiting_prompt = _is_claude_code_awaiting_regular_prompt(lines)
	for idx in range(len(lines) - 1, -1, -1):
		line = lines[idx]
		matched = _CC_ITEM_LINE_RE.search(line) if awaiting_prompt else _CC_HRULE in line
		if matched:
			return idx + 1
	return None


def _move_notepad_caret_to_line(notepad_hwnd: int, line: int, timeout_s: float = 1.6) -> None:
	"""Asynchronously poll for NVDA focus to settle inside the given Notepad
	window, then move the caret to the 1-based `line` and speak it. Returns
	immediately; the actual move happens later on NVDA's wx event loop via
	core.callLater.
	"""
	log.debug("PlainView: scheduling caret move; notepad_hwnd=%s target_line=%s", notepad_hwnd, line)
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
					lineInfo = candidate.makeTextInfo(textInfos.POSITION_CARET)
					lineInfo.expand(textInfos.UNIT_LINE)
					speech.cancelSpeech()
					speech.speakTextInfo(lineInfo, reason=controlTypes.OutputReason.CARET)
					return
				# Short move means the document isn't fully loaded yet; keep polling.
				log.debug("PlainView: short paragraph move (%s of %s); continuing to poll", moved, want)
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
		ui.message(_("Plain View: could not write temp file"))
		return None

	try:
		subprocess.Popen(["notepad.exe", TEMP_PATH], close_fds=True)
	except OSError:
		log.error("PlainView: failed to launch Notepad", exc_info=True)
		ui.message(_("Plain View: could not launch Notepad"))
		return None

	hwnd = _find_notepad_hwnd(TEMP_FILENAME)
	if hwnd is None:
		ui.message(_("Plain View: could not locate Notepad window"))
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
			ui.message(_("No Claude Code attention point found"))
			return
		_move_notepad_caret_to_line(hwnd, target_line)
