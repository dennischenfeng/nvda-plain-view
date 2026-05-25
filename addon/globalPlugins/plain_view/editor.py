# -*- coding: UTF-8 -*-
# PlainView NVDA add-on
# Copyright (C) 2026 Dennis Feng
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.
# See COPYING.txt at the root of this project for the full license text.

"""Getting dumped text onto the screen: write the temp file, launch the
configured editor on it, locate its window, and bring it to the foreground.

`open_dump` is the single public entry point; everything else is a private
helper in service of it.
"""

import ctypes
import os
import shutil
import subprocess
import tempfile
import time

import config
import ui
import winUser
from logHandler import log

from .settings import CONFIG_SECTION, EDITOR_NOTEPAD_PP

try:
    import addonHandler

    addonHandler.initTranslation()
except Exception:
    pass


_TEMP_FILENAME = "plainview.txt"
_TEMP_PATH = os.path.join(tempfile.gettempdir(), _TEMP_FILENAME)

_SW_MAXIMIZE = 3


def _resolve_editor_command() -> tuple[list[str], str, str, float] | None:
    """Return (argv-prefix, window-title-suffix, friendly-name, find-timeout-s)
    for the editor selected in config, or None if the configured editor cannot
    be located.
    """
    editor = config.conf[CONFIG_SECTION]["editor"]
    if editor == EDITOR_NOTEPAD_PP:
        # Per-user installer first (no admin rights required, common on locked
        # down machines), then the two Program Files locations, then PATH.
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        candidates = [
            os.path.join(local_app_data, r"Programs\Notepad++\notepad++.exe")
            if local_app_data
            else None,
            r"C:\Program Files\Notepad++\notepad++.exe",
            r"C:\Program Files (x86)\Notepad++\notepad++.exe",
            shutil.which("notepad++"),
        ]
        for candidate in candidates:
            if candidate and os.path.isfile(candidate):
                # Cold-start with plugins routinely exceeds 1.5s; give it 5s.
                return [candidate], " - Notepad++", "Notepad++", 5.0
        ui.message(_("PlainView: Notepad++ not found; check the editor setting"))
        return None
    return ["notepad.exe"], " - Notepad", "Notepad", 1.5


def _find_editor_window(needle: str, title_suffix: str, timeout_s: float) -> int | None:
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
    # core.callLater here would force open_dump to become async too.
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


def open_dump(text: str) -> int | None:
    """Write `text` to the temp file, launch the configured editor on it, and
    bring its window to the foreground.

    Returns the editor window handle on success, or None if any step failed
    (each failure path announces itself to the user before returning).
    """
    try:
        with open(_TEMP_PATH, "w", encoding="utf-8", newline="") as f:
            f.write(text)
    except OSError:
        log.error("PlainView: failed to write temp file %s", _TEMP_PATH, exc_info=True)
        ui.message(_("PlainView: could not write temp file"))
        return None

    resolved = _resolve_editor_command()
    if resolved is None:
        return None
    argv_prefix, title_suffix, friendly, find_timeout_s = resolved

    try:
        subprocess.Popen([*argv_prefix, _TEMP_PATH], close_fds=True)
    except OSError:
        log.error("PlainView: failed to launch %s", friendly, exc_info=True)
        ui.message(_("PlainView: could not launch {editor}").format(editor=friendly))
        return None

    hwnd = _find_editor_window(_TEMP_FILENAME, title_suffix, find_timeout_s)
    if hwnd is None:
        ui.message(_("PlainView: could not locate {editor} window").format(editor=friendly))
        return None

    _foreground_window(hwnd)
    return hwnd
