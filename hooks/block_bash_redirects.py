#!/usr/bin/env python3
"""PreToolUse Bash hook: nudge away from bad shell habits.

Blocks and explains:
  - `>` / `>>` to source/data files   → use Write/Edit tool
  - `cat <file>`                       → use Read tool
  - `head`/`tail <file>`              → use Read tool
  - `sed -i` / `awk -i`               → use Edit tool
  - `tee <file>`                       → use Write tool
  - `2>&1 |`                           → use `|&`
  - `git add -A` / `git add .`        → stage specific files

Allows /dev/null, /dev/std*, /tmp/*, *.log, fd redirects (>&, >()).

Config: ~/.claude/rubber-band.json (global) and/or .claude/rubber-band.json
(project-level). Both are merged. Supported keys:
  "disabled":     list of built-in rule IDs to suppress
  "extra_habits": list of {pattern, reason} objects to add

Built-in rule IDs: pipe_redirect, cat, head_tail, sed_i, awk_i, tee, git_add_all
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Callable

BLOCKED_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".py",
        ".pyi",
        ".md",
        ".rst",
        ".txt",
        ".json",
        ".jsonl",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".cfg",
        ".conf",
        ".sh",
        ".bash",
        ".zsh",
        ".fish",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".mjs",
        ".cjs",
        ".html",
        ".htm",
        ".css",
        ".scss",
        ".sass",
        ".go",
        ".rs",
        ".c",
        ".h",
        ".cpp",
        ".hpp",
        ".cc",
        ".java",
        ".kt",
        ".rb",
        ".php",
        ".sql",
        ".csv",
        ".tsv",
        ".xml",
        ".env",
        ".lock",
        ".dockerfile",
    },
)

ALLOWED_PREFIXES: tuple[str, ...] = ("/dev/", "/tmp/", "/var/tmp/", "/proc/")  # noqa: S108
ALLOWED_SUFFIXES: tuple[str, ...] = (".log",)

REDIRECT_RE = re.compile(r"(?<![>&\d])>{1,2}(?![>&(])\s*([^\s;|&)]+)")
QUOTED_RE = re.compile(r"\"[^\"]*\"|'[^']*'")


class HabitEntry(NamedTuple):
    id: str
    pattern: re.Pattern[str]
    reason: str
    validator: Callable[[re.Match[str]], bool] | None = None


def is_allowed_target(target: str) -> bool:
    if not target or target.startswith("&"):
        return True
    if target.startswith(ALLOWED_PREFIXES):
        return True
    if any(target.endswith(suffix) for suffix in ALLOWED_SUFFIXES):
        return True
    return Path(target).suffix.lower() not in BLOCKED_EXTENSIONS


def _head_tail_has_file_arg(m: re.Match[str]) -> bool:
    tokens = m.group(2).split()
    return any(not t.startswith("-") and not t.lstrip("+").isdigit() for t in tokens)


def _tee_targets_blocked_file(m: re.Match[str]) -> bool:
    return not is_allowed_target(target=m.group(1).rstrip(";|&)"))


# validator(match) -> True means "block this match"
_BAD_HABITS: list[HabitEntry] = [
    HabitEntry(
        id="pipe_redirect",
        pattern=re.compile(r"2>&1\s*\|"),
        reason="Use `|&` instead of `2>&1 |` — avoids false-positive write-permission prompts from `>`.",  # noqa: E501
    ),
    HabitEntry(
        id="cat",
        pattern=re.compile(r"(?:^|[;&]\s*)cat\s+(?!/dev/)(?!\|)\S"),
        reason="Use `Read` tool instead of `cat` — file contents stay in context, not shell stdout.",  # noqa: E501
    ),
    HabitEntry(
        id="head_tail",
        pattern=re.compile(r"\b(head|tail)\b([^\n;|&]*)"),
        reason="Use `Read` tool instead of `head`/`tail <file>` — pure stdin consumer (`cmd | head`) is allowed.",  # noqa: E501
        validator=_head_tail_has_file_arg,
    ),
    HabitEntry(
        id="sed_i",
        pattern=re.compile(r"\bsed\s+(-i\S*|--in-place\b)"),
        reason="Use `Edit` tool instead of `sed -i` — preserves file context, avoids silent overwrites.",  # noqa: E501
    ),
    HabitEntry(
        id="awk_i",
        pattern=re.compile(r"\bg?awk\s+-i\b"),
        reason="Use `Edit` tool instead of `awk -i` — preserves file context, avoids silent overwrites.",  # noqa: E501
    ),
    HabitEntry(
        id="tee",
        pattern=re.compile(r"\btee\s+(?:-\S+\s+)*(?!-)([^\s;|&)]+)"),
        reason="Use `Write` tool instead of `tee` — file writes stay explicit and reviewable.",
        validator=_tee_targets_blocked_file,
    ),
    HabitEntry(
        id="git_add_all",
        pattern=re.compile(r"\bgit\s+add\s+(-A|--all|\.)(?:\s|$)"),
        reason="Stage specific files by name — avoids accidentally committing secrets or large binaries.",  # noqa: E501
    ),
]


def _load_config() -> tuple[list[HabitEntry], set[str]]:
    """Load extra_habits and disabled IDs from global then project config."""
    paths = [
        Path.home() / ".claude" / "rubber-band.json",
        Path(os.environ.get("PWD", ".")) / ".claude" / "rubber-band.json",
    ]
    extra: list[HabitEntry] = []
    disabled: set[str] = set()
    for path in paths:
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        disabled.update(data.get("disabled", []))
        for entry in data.get("extra_habits", []):
            pattern_str = entry.get("pattern", "")
            reason = entry.get("reason", "")
            if pattern_str and reason:
                try:
                    extra.append(HabitEntry(id="", pattern=re.compile(pattern_str), reason=reason))
                except re.error:
                    pass
    return extra, disabled


def _find_blocked_redirect(command: str) -> str | None:
    """Return first redirect target that should be blocked, or None."""
    stripped = QUOTED_RE.sub("", command)
    for match in REDIRECT_RE.finditer(stripped):
        target = match.group(1).rstrip(";|&)")
        if not is_allowed_target(target=target):
            return target
    return None


def check_command(command: str, habits: list[HabitEntry]) -> str | None:
    """Return block reason for command, or None if allowed."""
    stripped = QUOTED_RE.sub("", command)
    for habit in habits:
        m = habit.pattern.search(stripped)
        if m and (habit.validator is None or habit.validator(m)):
            return habit.reason

    blocked = _find_blocked_redirect(command=command)
    if blocked is not None:
        return (
            f"Redirect to '{blocked}' blocked. "
            f"Use Write/Edit tool instead. "
            f"For logs use *.log, /tmp/, or /dev/null."
        )
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    command: str = payload.get("tool_input", {}).get("command", "")
    if not command:
        return 0

    extra_habits, disabled = _load_config()
    habits = [h for h in _BAD_HABITS if h.id not in disabled] + extra_habits
    reason = check_command(command=command, habits=habits)

    if reason is None:
        return 0

    print(  # noqa: T201
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                },
            },
        ),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
