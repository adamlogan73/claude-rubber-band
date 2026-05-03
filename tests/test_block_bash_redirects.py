"""Tests for block_bash_redirects hook."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from block_bash_redirects import _BAD_HABITS
from block_bash_redirects import HabitEntry
from block_bash_redirects import _load_config
from block_bash_redirects import check_command
from block_bash_redirects import is_allowed_target


def habits() -> list[HabitEntry]:
    return list(_BAD_HABITS)


# --- is_allowed_target ---


@pytest.mark.parametrize(
    "target",
    [
        "/dev/null",
        "/dev/stdout",
        "/tmp/foo",
        "/var/tmp/bar",
        "/proc/self/fd/1",
        "output.log",
        "some/path/debug.log",
        "",
        "&1",
        "result.csv",  # not in BLOCKED_EXTENSIONS... wait, .csv IS blocked
    ],
)
def test_allowed_targets(target: str) -> None:
    # .csv is blocked — remove it and test separately
    if target == "result.csv":
        assert not is_allowed_target(target)
    else:
        assert is_allowed_target(target)


@pytest.mark.parametrize(
    "target",
    [
        "file.py",
        "script.sh",
        "config.json",
        "data.yaml",
        "style.css",
        "app.ts",
        "main.go",
        "result.csv",
    ],
)
def test_blocked_targets(target: str) -> None:
    assert not is_allowed_target(target)


# --- built-in habits: should block ---


@pytest.mark.parametrize(
    "command,rule_id",
    [
        ("echo foo 2>&1 | cat", "pipe_redirect"),
        ("cat file.py", "cat"),
        ("cat ./src/main.py", "cat"),
        ("head file.py", "head_tail"),
        ("tail -n 10 file.py", "head_tail"),
        ("head -20 config.yaml", "head_tail"),
        ("sed -i 's/foo/bar/' file.py", "sed_i"),
        ("sed --in-place 's/x/y/' a.txt", "sed_i"),
        ("awk -i inplace '{print}' file.py", "awk_i"),
        ("gawk -i inplace '{print}' file.py", "awk_i"),
        ("tee output.py", "tee"),
        ("git add -A", "git_add_all"),
        ("git add .", "git_add_all"),
        ("git add --all", "git_add_all"),
    ],
)
def test_blocks_bad_habits(command: str, rule_id: str) -> None:
    reason = check_command(command=command, habits=habits())
    assert reason is not None
    # confirm the right rule fired
    matching = next(h for h in _BAD_HABITS if h.id == rule_id)
    assert reason == matching.reason


@pytest.mark.parametrize(
    "command",
    [
        "echo foo > file.py",
        "echo bar >> config.json",
        "cmd > script.sh",
    ],
)
def test_blocks_redirects_to_source_files(command: str) -> None:
    reason = check_command(command=command, habits=habits())
    assert reason is not None
    assert "blocked" in reason


# --- built-in habits: should allow ---


@pytest.mark.parametrize(
    "command",
    [
        "cat /dev/stdin",
        "cmd | cat",  # cat with no file arg (piped)
        "cmd | head",  # head as pure stdin consumer
        "cmd | tail",
        "echo foo > /dev/null",
        "echo foo > output.log",
        "echo foo > /tmp/scratch",
        "git add specific_file.py",
        "git add src/module.py tests/test_foo.py",
        "tee /tmp/debug",
        "tee output.log",
    ],
)
def test_allows_good_commands(command: str) -> None:
    assert check_command(command=command, habits=habits()) is None


# --- redirect allowlist edge cases ---


@pytest.mark.parametrize(
    "command",
    [
        "cmd >&2",  # fd redirect
        "cmd >() subshell",  # process substitution
        "cmd 2>/dev/null",  # fd number before >
    ],
)
def test_allows_fd_redirects(command: str) -> None:
    assert check_command(command=command, habits=habits()) is None


# --- config: disabled ---


def test_disabled_suppresses_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = tmp_path / ".claude" / "rubber-band.json"
    config.parent.mkdir()
    config.write_text(json.dumps({"disabled": ["cat"]}))
    monkeypatch.setenv("PWD", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "no-home")

    extra, disabled = _load_config()
    active = [h for h in _BAD_HABITS if h.id not in disabled] + extra
    assert check_command(command="cat file.py", habits=active) is None


def test_disabled_does_not_affect_other_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = tmp_path / ".claude" / "rubber-band.json"
    config.parent.mkdir()
    config.write_text(json.dumps({"disabled": ["cat"]}))
    monkeypatch.setenv("PWD", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "no-home")

    extra, disabled = _load_config()
    active = [h for h in _BAD_HABITS if h.id not in disabled] + extra
    assert check_command(command="git add .", habits=active) is not None


# --- config: extra_habits ---


def test_extra_habits_blocks_custom_pattern(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = tmp_path / ".claude" / "rubber-band.json"
    config.parent.mkdir()
    config.write_text(
        json.dumps(
            {
                "extra_habits": [{"pattern": r"\bpip\b", "reason": "Use uv add."}],
            },
        ),
    )
    monkeypatch.setenv("PWD", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "no-home")

    extra, disabled = _load_config()
    active = [h for h in _BAD_HABITS if h.id not in disabled] + extra
    assert check_command(command="pip install requests", habits=active) == "Use uv add."


def test_extra_habits_invalid_regex_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = tmp_path / ".claude" / "rubber-band.json"
    config.parent.mkdir()
    config.write_text(
        json.dumps(
            {
                "extra_habits": [{"pattern": "[invalid", "reason": "bad"}],
            },
        ),
    )
    monkeypatch.setenv("PWD", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "no-home")

    extra, disabled = _load_config()
    assert extra == []


def test_missing_config_is_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PWD", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "no-home")
    extra, disabled = _load_config()
    assert extra == []
    assert disabled == set()


def test_disabled_redirect_suppresses_redirect_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = tmp_path / ".claude" / "rubber-band.json"
    config.parent.mkdir()
    config.write_text(json.dumps({"disabled": ["redirect"]}))
    monkeypatch.setenv("PWD", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "no-home")

    extra, disabled = _load_config()
    active = [h for h in _BAD_HABITS if h.id not in disabled] + extra
    assert check_command(command="echo foo > file.py", habits=active, disabled=disabled) is None


# --- global + project config merge ---


def test_project_config_extends_global(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    (home / ".claude").mkdir(parents=True)
    (project / ".claude").mkdir(parents=True)
    (home / ".claude" / "rubber-band.json").write_text(
        json.dumps(
            {
                "extra_habits": [{"pattern": r"\bpip\b", "reason": "Use uv add."}],
            },
        ),
    )
    (project / ".claude" / "rubber-band.json").write_text(
        json.dumps(
            {
                "disabled": ["cat"],
            },
        ),
    )
    monkeypatch.setenv("PWD", str(project))
    monkeypatch.setattr("pathlib.Path.home", lambda: home)

    extra, disabled = _load_config()
    assert "cat" in disabled
    assert len(extra) == 1
