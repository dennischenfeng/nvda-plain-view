# -*- coding: UTF-8 -*-
# PlainView NVDA add-on
# Copyright (C) 2026 Dennis Feng
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.
# See COPYING.txt at the root of this project for the full license text.

"""PlainView entry point: the GlobalPlugin NVDA loads, its gesture scripts, and
the small orchestrator that ties the helper modules together.

The implementation is split across sibling modules:
- `text` — pure terminal-text analysis (no NVDA), Claude Code / Codex patterns.
- `editor` — write the dump to a temp file and open it in the chosen editor.
- `nvda_text` — read/navigate/speak text via NVDA's TextInfo APIs.
- `settings` — config spec and the Settings-dialog panel.
"""

import globalPluginHandler
import speech
import ui
from gui.settingsDialogs import NVDASettingsDialog
from scriptHandler import script

from . import editor, nvda_text, text
from .settings import PlainViewSettingsPanel

try:
    import addonHandler

    addonHandler.initTranslation()
except Exception:
    pass


def _open_plain_view() -> tuple[int, str] | None:
    """Phase 1 core: scrape focused window text → temp file → editor → foreground.

    Returns (editor_hwnd, dumped_text) on success, or None if any step failed
    such that we couldn't get the editor on screen with our file.
    """
    dump = nvda_text.grab_focused_text()
    if dump is None:
        return None
    dump = text.tidy_dump(dump)
    hwnd = editor.open_dump(dump)
    if hwnd is None:
        return None
    return hwnd, dump


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

    def _attention_jump(self, finder, not_found_msg: str) -> None:
        """Open PlainView, then jump the caret to the attention line that
        `finder(dumped_text)` returns. Announces `not_found_msg` if the finder
        reports no attention point. Shared by the per-agent jump scripts.
        """
        result = _open_plain_view()
        if result is None:
            return
        hwnd, dump = result
        target_line = finder(dump)
        if target_line is None:
            ui.message(not_found_msg)
            return
        nvda_text.move_caret_to_line(hwnd, target_line)

    @script(
        description=_(
            "Open PlainView: copy focused-window text to a temp file and open it in the configured editor."
        ),
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
        self._attention_jump(
            text.find_claude_code_attention_line,
            _("No Claude Code attention point found"),
        )

    @script(
        description=_("PlainView: jump to next Claude Code item line."),
        category="PlainView",
        gesture=None,
    )
    def script_nextClaudeCodeItem(self, gesture):
        nvda_text.nav_by_predicate(text.line_is_cc_item, forward=True)

    @script(
        description=_("PlainView: jump to previous Claude Code item line."),
        category="PlainView",
        gesture=None,
    )
    def script_previousClaudeCodeItem(self, gesture):
        nvda_text.nav_by_predicate(text.line_is_cc_item, forward=False)

    @script(
        description=_("Open PlainView with Codex attention jump."),
        category="PlainView",
        gesture=None,
    )
    def script_openPlainViewWithCodexAttentionJump(self, gesture):
        self._attention_jump(
            text.find_codex_attention_line,
            _("No Codex attention point found"),
        )

    @script(
        description=_("PlainView: jump to next Codex item line."),
        category="PlainView",
        gesture=None,
    )
    def script_nextCodexItem(self, gesture):
        nvda_text.nav_by_predicate(text.line_is_codex_item, forward=True)

    @script(
        description=_("PlainView: jump to previous Codex item line."),
        category="PlainView",
        gesture=None,
    )
    def script_previousCodexItem(self, gesture):
        nvda_text.nav_by_predicate(text.line_is_codex_item, forward=False)

    @script(
        description=_("PlainView: jump to next horizontal rule."),
        category="PlainView",
        gesture=None,
    )
    def script_nextHorizontalRule(self, gesture):
        nvda_text.nav_by_predicate(text.line_is_hrule, forward=True)

    @script(
        description=_("PlainView: jump to previous horizontal rule."),
        category="PlainView",
        gesture=None,
    )
    def script_previousHorizontalRule(self, gesture):
        nvda_text.nav_by_predicate(text.line_is_hrule, forward=False)

    @script(
        description=_("PlainView: speak the currently selected Claude Code option."),
        category="PlainView",
        gesture=None,
    )
    def script_speakClaudeCodeSelectedOption(self, gesture):
        dump = nvda_text.grab_focused_text()
        if dump is None:
            return
        selected = text.find_last_claude_code_selected_option(dump)
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
        nvda_text.speak_line_position()
