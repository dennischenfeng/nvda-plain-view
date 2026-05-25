# -*- coding: UTF-8 -*-
# PlainView NVDA add-on
# Copyright (C) 2026 Dennis Feng
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.
# See COPYING.txt at the root of this project for the full license text.

"""Configuration: the config spec, the editor identity constants, and the
PlainView category panel shown in NVDA's Settings dialog.

Importing this module registers the config spec as a side effect, so it must
be imported before any code reads `config.conf[CONFIG_SECTION]`.
"""

import config
import gui
import wx
from gui.settingsDialogs import SettingsPanel

try:
    import addonHandler

    addonHandler.initTranslation()
except Exception:
    pass


CONFIG_SECTION = "plainView"
EDITOR_NOTEPAD = "notepad"
EDITOR_NOTEPAD_PP = "notepadpp"
EDITOR_CHOICES = (EDITOR_NOTEPAD, EDITOR_NOTEPAD_PP)

config.conf.spec[CONFIG_SECTION] = {
    "editor": f"option({', '.join(repr(c) for c in EDITOR_CHOICES)}, default='{EDITOR_NOTEPAD}')",
}


class PlainViewSettingsPanel(SettingsPanel):
    # Translators: title of the PlainView category in NVDA's Settings dialog.
    title = _("PlainView")

    # Translators: labels for the editor combo box choices, in the same order
    # as EDITOR_CHOICES above.
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
            self.editorCombo.SetSelection(EDITOR_CHOICES.index(current))
        except ValueError:
            self.editorCombo.SetSelection(0)

    def onSave(self):
        config.conf[CONFIG_SECTION]["editor"] = EDITOR_CHOICES[self.editorCombo.GetSelection()]
