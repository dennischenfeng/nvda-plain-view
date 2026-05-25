# -*- coding: UTF-8 -*-
# PlainView NVDA add-on
# Copyright (C) 2026 Dennis Feng
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.
# See COPYING.txt at the root of this project for the full license text.

"""Pure terminal-text analysis: dump hygiene plus pattern recognition for
Claude Code and Codex CLI output.

This module deliberately imports nothing from NVDA — only the standard
library `re`. Everything here is a plain function of strings, so it can be
imported and unit-tested on any machine without NVDA running. Keep it that
way: the NVDA glue lives in the sibling modules.
"""

import re

# Claude Code attention-point patterns, ported from the VS Code prototype.
_CC_ITEM_LINE_RE = re.compile(r"^[∴●•›>❯!].*\S")
_CC_HRULE = "───"
_CC_PROMPT_SCAN_LINES = 10
# Matches a line whose first non-whitespace character is the selection chevron
# used to mark the currently highlighted multiple-choice option — ❯ in Claude
# Code, › in Codex — and captures the text after it.
_CC_SELECTED_OPTION_RE = re.compile(r"^\s*[❯›]\s*(.*)$")

# Codex CLI markers. `•` prefixes each assistant response/step; `›` prefixes the
# user prompt line. Nav considers both; the attention jump targets bullets only,
# since the goal is the start of the most recent assistant response.
_CODEX_ITEM_LINE_RE = re.compile(r"^[•›].*\S")
_CODEX_BULLET_RE = re.compile(r"^•.*\S")


def tidy_dump(text: str) -> str:
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


def line_is_cc_item(line: str) -> bool:
    return _CC_ITEM_LINE_RE.search(line) is not None


def line_is_codex_item(line: str) -> bool:
    return _CODEX_ITEM_LINE_RE.search(line) is not None


def line_is_hrule(line: str) -> bool:
    return _CC_HRULE in line


def find_codex_attention_line(text: str) -> int | None:
    """Return the 1-based line number of the last `•`-prefixed line in `text`,
    or None if no bullet line is present.
    """
    lines = text.splitlines()
    for idx in range(len(lines) - 1, -1, -1):
        if _CODEX_BULLET_RE.search(lines[idx]):
            return idx + 1
    return None


def find_last_claude_code_selected_option(text: str) -> str | None:
    """Return the text after the last `❯ ` chevron-prefixed line in `text`, or
    None if no such line is present.
    """
    last_match: str | None = None
    for line in text.split("\n"):
        m = _CC_SELECTED_OPTION_RE.match(line)
        if m:
            last_match = m.group(1)
    return last_match


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


def find_claude_code_attention_line(text: str) -> int | None:
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
        line_is_cc_item if _is_claude_code_awaiting_regular_prompt(lines) else line_is_hrule
    )
    for idx in range(len(lines) - 1, -1, -1):
        if predicate(lines[idx]):
            return idx + 1
    return None
