# -*- coding: UTF-8 -*-
# Plain View NVDA add-on
# Copyright (C) 2026 Dennis Feng
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.
# See COPYING.txt at the root of this project for the full license text.

import globalPluginHandler
from scriptHandler import script
import ui

addonHandler = None
try:
	import addonHandler
	addonHandler.initTranslation()
except Exception:
	pass


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	scriptCategory = "Plain View"

	@script(
		description=_("Open Plain View: copy terminal text to a temp file and open it in Notepad."),
		category="Plain View",
		gesture=None,
	)
	def script_openPlainView(self, gesture):
		ui.message("open plainview - not yet implemented")

	@script(
		description=_("Open Plain View with Claude Code attention jump."),
		category="Plain View",
		gesture=None,
	)
	def script_openPlainViewWithClaudeCodeAttentionJump(self, gesture):
		ui.message("open plainview with claude code attention jump - not yet implemented")
