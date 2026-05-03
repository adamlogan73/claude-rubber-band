"""Tests for block_bash_redirects hook."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "hooks"))

from block_bash_redirects import _BAD_HABITS
from block_bash_redirects import _DEFAULT_REDIRECT_CFG
from block_bash_redirects import HabitEntry
from block_bash_redirects import _load_config
from block_bash_redirects import _make_active_habits
from block_bash_redirects import check_command
from block_bash_redirects import is_allowed_target


def habits() -> list[HabitEntry]:
    return _make_active_habits(
        disabled=set(),
        extra=[],
        redirect_cfg=_DEFAULT_REDIRECT_CFG,
    )


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
    ("command", "rule_id"),
    [
        ("echo foo 2>&1 | cat", "pipe_redirect"),
        ("cat file.py", "cat"),
        ("cat ./src/main.py", "cat"),
        ('cat "file.py"', "cat"),  # quoted arg still blocked
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
        ("grep pattern file.py", "grep"),
        ("grep -r pattern src/", "grep"),
        ("uv run pytest |& cat", "trailing_cat"),
        ("uv run pytest | cat", "trailing_cat"),
        ("uv run pytest | cat;", "trailing_cat"),
        ("cmd | cat", "trailing_cat"),
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
        "cmd | head",  # head as pure stdin consumer
        "cmd | tail",
        "tail -f /var/log/syslog",  # follow mode, not a file read
        "tail -F service.log",
        "tail --follow app.log",
        "echo foo > /dev/null",
        "echo foo > output.log",
        "echo foo > /tmp/scratch",
        "git add specific_file.py",
        "git add src/module.py tests/test_foo.py",
        "tee /tmp/debug",
        "tee output.log",
        "cmd | grep pattern",
        "uv run pytest |& head -20",
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
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = tmp_path / ".claude" / "rubber-band.json"
    config.parent.mkdir()
    config.write_text(json.dumps({"disabled": ["cat"]}))
    monkeypatch.setenv("PWD", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "no-home")

    extra, disabled, redirect_cfg = _load_config()
    active = _make_active_habits(
        disabled=disabled,
        extra=extra,
        redirect_cfg=redirect_cfg,
    )
    assert check_command(command="cat file.py", habits=active) is None


def test_disabled_does_not_affect_other_rules(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = tmp_path / ".claude" / "rubber-band.json"
    config.parent.mkdir()
    config.write_text(json.dumps({"disabled": ["cat"]}))
    monkeypatch.setenv("PWD", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "no-home")

    extra, disabled, redirect_cfg = _load_config()
    active = _make_active_habits(
        disabled=disabled,
        extra=extra,
        redirect_cfg=redirect_cfg,
    )
    assert check_command(command="git add .", habits=active) is not None


# --- config: extra_habits ---


def test_extra_habits_blocks_custom_pattern(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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

    extra, disabled, redirect_cfg = _load_config()
    active = _make_active_habits(
        disabled=disabled,
        extra=extra,
        redirect_cfg=redirect_cfg,
    )
    assert check_command(command="pip install requests", habits=active) == "Use uv add."


def test_extra_habits_with_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = tmp_path / ".claude" / "rubber-band.json"
    config.parent.mkdir()
    config.write_text(
        json.dumps(
            {
                "extra_habits": [
                    {"id": "no-pip", "pattern": r"\bpip\b", "reason": "Use uv add."},
                ],
            },
        ),
    )
    monkeypatch.setenv("PWD", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "no-home")

    extra, _, _ = _load_config()
    assert len(extra) == 1
    assert extra[0].id == "no-pip"
    assert not extra[0].trusted


def test_extra_habits_trusted_false(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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

    extra, _, _ = _load_config()
    assert len(extra) == 1
    assert not extra[0].trusted


def test_extra_habits_invalid_regex_skipped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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

    extra, _, __ = _load_config()
    assert extra == []


def test_missing_config_is_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PWD", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "no-home")
    extra, disabled, _ = _load_config()
    assert extra == []
    assert disabled == set()


def test_disabled_redirect_suppresses_redirect_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = tmp_path / ".claude" / "rubber-band.json"
    config.parent.mkdir()
    config.write_text(json.dumps({"disabled": ["redirect"]}))
    monkeypatch.setenv("PWD", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "no-home")

    extra, disabled, redirect_cfg = _load_config()
    active = _make_active_habits(
        disabled=disabled,
        extra=extra,
        redirect_cfg=redirect_cfg,
    )
    result = check_command(
        command="echo foo > file.py",
        habits=active,
        disabled=disabled,
    )
    assert result is None


# --- global + project config merge ---


def test_project_config_extends_global(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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

    extra, disabled, _ = _load_config()
    assert "cat" in disabled
    assert len(extra) == 1


# --- redirect config overrides ---


def test_custom_blocked_extension(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = tmp_path / ".claude" / "rubber-band.json"
    config.parent.mkdir()
    config.write_text(json.dumps({"blocked_extensions": [".lua"]}))
    monkeypatch.setenv("PWD", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "no-home")

    _, _, redirect_cfg = _load_config()
    assert (
        check_command(
            command="echo x > script.lua",
            habits=habits(),
            redirect_cfg=redirect_cfg,
        )
        is not None
    )
    assert (
        check_command(
            command="echo x > file.py",
            habits=habits(),
            redirect_cfg=redirect_cfg,
        )
        is None
    )


def test_custom_allowed_prefix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / ".claude" / "rubber-band.json"
    config.parent.mkdir()
    scratch = str(tmp_path / "scratch") + "/"
    prefixes = ["/dev/", "/tmp/", "/var/tmp/", "/proc/", scratch]
    config.write_text(json.dumps({"allowed_prefixes": prefixes}))
    monkeypatch.setenv("PWD", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "no-home")

    _, _, redirect_cfg = _load_config()
    assert (
        check_command(
            command=f"echo x > {scratch}out.py",
            habits=habits(),
            redirect_cfg=redirect_cfg,
        )
        is None
    )


def test_custom_allowed_suffix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / ".claude" / "rubber-band.json"
    config.parent.mkdir()
    config.write_text(json.dumps({"allowed_suffixes": [".log", ".out"]}))
    monkeypatch.setenv("PWD", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "no-home")

    _, _, redirect_cfg = _load_config()
    assert (
        check_command(
            command="cmd > result.out",
            habits=habits(),
            redirect_cfg=redirect_cfg,
        )
        is None
    )


def test_override_removes_default_allowed_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = tmp_path / ".claude" / "rubber-band.json"
    config.parent.mkdir()
    config.write_text(json.dumps({"allowed_prefixes": ["/dev/"]}))
    monkeypatch.setenv("PWD", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "no-home")

    _, _, redirect_cfg = _load_config()
    assert (
        check_command(
            command="echo x > /tmp/out.py",
            habits=habits(),
            redirect_cfg=redirect_cfg,
        )
        is not None
    )


# --- config validation ---


def test_non_list_blocked_extensions_falls_back_to_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = tmp_path / ".claude" / "rubber-band.json"
    config.parent.mkdir()
    config.write_text(json.dumps({"blocked_extensions": ".py"}))
    monkeypatch.setenv("PWD", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "no-home")

    _, _, redirect_cfg = _load_config()
    # Fell back to default — .py is still blocked
    assert redirect_cfg.blocked_extensions != frozenset({".py", "p", "."})
    assert (
        check_command(
            command="echo x > file.py",
            habits=habits(),
            redirect_cfg=redirect_cfg,
        )
        is not None
    )


def test_non_string_items_in_blocked_extensions_filtered(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = tmp_path / ".claude" / "rubber-band.json"
    config.parent.mkdir()
    config.write_text(json.dumps({"blocked_extensions": [".lua", 42, None]}))
    monkeypatch.setenv("PWD", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "no-home")

    _, _, redirect_cfg = _load_config()
    assert redirect_cfg.blocked_extensions == frozenset({".lua"})


def test_unknown_disabled_id_warns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = tmp_path / ".claude" / "rubber-band.json"
    config.parent.mkdir()
    config.write_text(json.dumps({"disabled": ["typo_rule_id"]}))
    monkeypatch.setenv("PWD", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "no-home")

    _load_config()
    assert "typo_rule_id" in capsys.readouterr().err
