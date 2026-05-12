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
import subprocess
import tempfile
import time

import api
import globalPluginHandler
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


def _open_plain_view() -> int | None:
	"""Phase 1 core: scrape focused window text → temp file → Notepad → foreground.

	Returns the Notepad hwnd on success, or None if we couldn't locate it.
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
	return hwnd


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
		hwnd = _open_plain_view()
		if hwnd is None:
			return
		ui.message("attention jump - TBD")
