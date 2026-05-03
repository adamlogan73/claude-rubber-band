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
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

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

_HabitEntry = tuple["re.Pattern[str]", str, "Callable[[re.Match[str]], bool] | None"]


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


# Each entry: (pattern, reason, validator | None)
# validator(match) -> True means "block this match"
_BAD_HABITS: list[_HabitEntry] = [
    (
        re.compile(r"2>&1\s*\|"),
        "Use `|&` instead of `2>&1 |` — avoids false-positive write-permission prompts from `>`.",  # noqa: E501
        None,
    ),
    (
        re.compile(r"(?:^|[;&]\s*)cat\s+(?!/dev/)(?!\|)\S"),
        "Use `Read` tool instead of `cat` — file contents stay in context, not shell stdout.",  # noqa: E501
        None,
    ),
    (
        re.compile(r"\b(head|tail)\b([^\n;|&]*)"),
        "Use `Read` tool instead of `head`/`tail <file>` — pure stdin consumer (`cmd | head`) is allowed.",  # noqa: E501
        _head_tail_has_file_arg,
    ),
    (
        re.compile(r"\bsed\s+(-i\S*|--in-place\b)"),
        "Use `Edit` tool instead of `sed -i` — preserves file context, avoids silent overwrites.",  # noqa: E501
        None,
    ),
    (
        re.compile(r"\bg?awk\s+-i\b"),
        "Use `Edit` tool instead of `awk -i` — preserves file context, avoids silent overwrites.",  # noqa: E501
        None,
    ),
    (
        re.compile(r"\btee\s+(?:-\S+\s+)*(?!-)([^\s;|&)]+)"),
        "Use `Write` tool instead of `tee` — file writes stay explicit and reviewable.",
        _tee_targets_blocked_file,
    ),
    (
        re.compile(r"\bgit\s+add\s+(-A|--all|\.)(?:\s|$)"),
        "Stage specific files by name — avoids accidentally committing secrets or large binaries.",  # noqa: E501
        None,
    ),
]


def find_blocked_target(command: str) -> str | None:
    """Redirect check: iterates all `>` matches, returns first blocked target."""
    stripped = QUOTED_RE.sub("", command)
    for match in REDIRECT_RE.finditer(stripped):
        target = match.group(1).rstrip(";|&)")
        if not is_allowed_target(target=target):
            return target
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    command: str = payload.get("tool_input", {}).get("command", "")
    if not command:
        return 0

    stripped = QUOTED_RE.sub("", command)
    reason: str | None = None

    for pattern, reason_str, validator in _BAD_HABITS:
        m = pattern.search(stripped)
        if m and (validator is None or validator(m)):
            reason = reason_str
            break

    if reason is None:
        blocked = find_blocked_target(command=command)
        if blocked is not None:
            reason = (
                f"Redirect to '{blocked}' blocked. "
                f"Use Write/Edit tool instead. "
                f"For logs use *.log, /tmp/, or /dev/null."
            )

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