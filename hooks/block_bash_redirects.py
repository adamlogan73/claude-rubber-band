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
  - `grep <file>`                      → use Grep tool
  - `cmd |& cat` / `cmd | cat`        → remove trailing cat

Allows /dev/null, /dev/std*, /tmp/*, *.log, fd redirects (>&, >()).
`cmd | grep` (stdin filter) and `tail -f` (follow mode) are also allowed.

Config: ~/.claude/rubber-band.json (global) and/or .claude/rubber-band.json
(project-level). Both are merged — disabled/extra_habits are additive across
both files; blocked_extensions/allowed_prefixes/allowed_suffixes from the
project file replace the global file's value (last write wins).

Supported config keys:
  "disabled":            list of built-in rule IDs to suppress
  "extra_habits":        list of {id?, pattern, reason} objects to add
  "blocked_extensions":  list of extensions to block (replaces default)
  "allowed_prefixes":    list of path prefixes to allow (replaces default)
  "allowed_suffixes":    list of file suffixes to allow (replaces default)

Built-in rule IDs:
  pipe_redirect, cat, head_tail, sed_i, awk_i, tee, git_add_all, redirect,
  grep, trailing_cat
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import NamedTuple

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

ALLOWED_PREFIXES: tuple[str, ...] = ("/dev/", "/tmp/", "/var/tmp/", "/proc/")
ALLOWED_SUFFIXES: tuple[str, ...] = (".log",)

_REGEX_TIMEOUT: float = 0.5

REDIRECT_RE = re.compile(r"(?<![>&\d])>{1,2}(?![>&(])\s*([^\s;|&)]+)")
QUOTED_RE = re.compile(r"\"[^\"]*\"|'[^']*'")


class HabitEntry(NamedTuple):
    id: str
    pattern: re.Pattern[str]
    reason: str
    validator: Callable[[re.Match[str]], bool] | None = None
    trusted: bool = True


class _RedirectCfg(NamedTuple):
    blocked_extensions: frozenset[str] = BLOCKED_EXTENSIONS
    allowed_prefixes: tuple[str, ...] = ALLOWED_PREFIXES
    allowed_suffixes: tuple[str, ...] = ALLOWED_SUFFIXES


_DEFAULT_REDIRECT_CFG: _RedirectCfg = _RedirectCfg()


def is_allowed_target(target: str, cfg: _RedirectCfg = _DEFAULT_REDIRECT_CFG) -> bool:
    if not target or target.startswith("&"):
        return True
    if target.startswith(cfg.allowed_prefixes):
        return True
    if any(target.endswith(suffix) for suffix in cfg.allowed_suffixes):
        return True
    return Path(target).suffix.lower() not in cfg.blocked_extensions


def _safe_search(
    pattern: re.Pattern[str],
    text: str,
) -> re.Match[str] | None:
    """Run pattern.search in a daemon thread; return None on timeout."""
    result: list[re.Match[str] | None] = [None]

    def _run() -> None:
        result[0] = pattern.search(text)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=_REGEX_TIMEOUT)
    return result[0]


def _head_tail_has_file_arg(m: re.Match[str]) -> bool:
    tokens = m.group(2).split()
    # -f / -F / --follow are follow-mode flags (tail -f), not file args
    if any(t in {"-f", "-F", "--follow"} for t in tokens):
        return False
    return any(not t.startswith("-") and not t.lstrip("+").isdigit() for t in tokens)


def _make_tee_validator(
    cfg: _RedirectCfg,
) -> Callable[[re.Match[str]], bool]:
    def _validator(m: re.Match[str]) -> bool:
        return not is_allowed_target(target=m.group(1).rstrip(";|&)"), cfg=cfg)

    return _validator


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
        reason="Use `Write` tool instead of `tee` — file writes stay explicit and reviewable.",  # noqa: E501
        # validator injected at runtime by _make_active_habits to respect user config
    ),
    HabitEntry(
        id="git_add_all",
        pattern=re.compile(r"\bgit\s+add\s+(-A|--all|\.)(?:\s|$)"),
        reason="Stage specific files by name — avoids accidentally committing secrets or large binaries.",  # noqa: E501
    ),
    HabitEntry(
        id="grep",
        pattern=re.compile(r"(?:^|[;&]\s*)grep\b"),
        reason="Use `Grep` tool instead of `grep` — results stay in context, supports recursive search. `cmd | grep` (stdin filter) is still fine.",  # noqa: E501
    ),
    HabitEntry(
        id="trailing_cat",
        pattern=re.compile(r"\|&?\s+cat\s*(?:$|;)"),
        reason="Remove trailing `cat` — Bash tool captures all output directly.",
    ),
]

_BUILTIN_IDS: frozenset[str] = frozenset(h.id for h in _BAD_HABITS) | {"redirect"}


def _warn(msg: str) -> None:
    print(f"rubber-band: {msg}", file=sys.stderr)


def _parse_list_field(
    data: dict[str, Any],
    key: str,
    source: str,
) -> list[str] | None:
    """Return validated list value for key, or None if absent/invalid."""
    raw = data.get(key)
    if raw is None:
        return None
    if not isinstance(raw, list):
        _warn(f"{key} must be a list in {source} — using previous value")
        return None
    return [item for item in raw if isinstance(item, str)]


def _parse_extra_habits(raw: list[Any], source: str) -> list[HabitEntry]:
    habits: list[HabitEntry] = []
    for entry in raw:
        if not isinstance(entry, dict):
            _warn(f"extra_habits entry must be an object in {source} — skipping")
            continue
        pattern_str = entry.get("pattern", "")
        reason = entry.get("reason", "")
        habit_id = entry.get("id", "")
        if not isinstance(pattern_str, str) or not isinstance(reason, str):
            _warn(f"extra_habits: non-string pattern/reason in {source} — skipping")
            continue
        if pattern_str and reason:
            try:
                compiled = re.compile(pattern_str)
                habits.append(
                    HabitEntry(
                        id=habit_id,
                        pattern=compiled,
                        reason=reason,
                        trusted=False,
                    ),
                )
            except re.error as exc:
                _warn(f"invalid regex '{pattern_str}' in {source}: {exc}")
    return habits


def _load_config() -> tuple[list[HabitEntry], set[str], _RedirectCfg]:
    """Load config from global then project file, merging both."""
    paths = [
        Path.home() / ".claude" / "rubber-band.json",
        Path(os.environ.get("PWD", ".")) / ".claude" / "rubber-band.json",
    ]
    extra: list[HabitEntry] = []
    disabled: set[str] = set()
    blocked_extensions: frozenset[str] = BLOCKED_EXTENSIONS
    allowed_prefixes: tuple[str, ...] = ALLOWED_PREFIXES
    allowed_suffixes: tuple[str, ...] = ALLOWED_SUFFIXES

    for path in paths:
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue

        for rule_id in data.get("disabled", []):
            disabled.add(rule_id)
            if rule_id not in _BUILTIN_IDS:
                _warn(f"unknown rule ID '{rule_id}' in disabled list ({path.name})")

        raw_habits = data.get("extra_habits", [])
        if not isinstance(raw_habits, list):
            _warn(f"extra_habits must be a list in {path.name} — skipping")
        else:
            extra.extend(_parse_extra_habits(raw=raw_habits, source=path.name))

        ext_list = _parse_list_field(
            data=data,
            key="blocked_extensions",
            source=path.name,
        )
        if ext_list is not None:
            blocked_extensions = frozenset(ext_list)

        pfx_list = _parse_list_field(
            data=data,
            key="allowed_prefixes",
            source=path.name,
        )
        if pfx_list is not None:
            allowed_prefixes = tuple(pfx_list)

        sfx_list = _parse_list_field(
            data=data,
            key="allowed_suffixes",
            source=path.name,
        )
        if sfx_list is not None:
            allowed_suffixes = tuple(sfx_list)

    return (
        extra,
        disabled,
        _RedirectCfg(
            blocked_extensions=blocked_extensions,
            allowed_prefixes=allowed_prefixes,
            allowed_suffixes=allowed_suffixes,
        ),
    )


def _make_active_habits(
    disabled: set[str],
    extra: list[HabitEntry],
    redirect_cfg: _RedirectCfg,
) -> list[HabitEntry]:
    """Build the active habit list with config-aware tee validator."""
    tee_validator = _make_tee_validator(cfg=redirect_cfg)
    result: list[HabitEntry] = []
    for h in _BAD_HABITS:
        if h.id in disabled:
            continue
        result.append(h._replace(validator=tee_validator) if h.id == "tee" else h)
    return result + extra


def _find_blocked_redirect(command: str, cfg: _RedirectCfg) -> str | None:
    """Return first redirect target that should be blocked, or None."""
    stripped = QUOTED_RE.sub("", command)
    for match in REDIRECT_RE.finditer(stripped):
        target = match.group(1).rstrip(";|&)")
        if not is_allowed_target(target=target, cfg=cfg):
            return target
    return None


def check_command(
    command: str,
    habits: list[HabitEntry],
    disabled: set[str] | None = None,
    redirect_cfg: _RedirectCfg = _DEFAULT_REDIRECT_CFG,
) -> str | None:
    """Return block reason for command, or None if allowed."""
    # "X" placeholder (not "") so quoted file args like cat "file.py" are still matched.
    stripped = QUOTED_RE.sub("X", command)
    for habit in habits:
        m = (
            habit.pattern.search(stripped)
            if habit.trusted
            else _safe_search(habit.pattern, stripped)
        )
        if m and (habit.validator is None or habit.validator(m)):
            return habit.reason

    if "redirect" not in (disabled or set()):
        blocked = _find_blocked_redirect(command=command, cfg=redirect_cfg)
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

    extra_habits, disabled, redirect_cfg = _load_config()
    habits = _make_active_habits(
        disabled=disabled,
        extra=extra_habits,
        redirect_cfg=redirect_cfg,
    )
    reason = check_command(
        command=command,
        habits=habits,
        disabled=disabled,
        redirect_cfg=redirect_cfg,
    )

    if reason is None:
        return 0

    print(
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
