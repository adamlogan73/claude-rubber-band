# claude-rubber-band

Claude Code plugin — two hooks that keep Claude's shell habits tidy.

## Hooks

### `PreToolUse` — block bad Bash habits

Runs before every `Bash` tool call. Blocks patterns where a dedicated tool is better, and explains why.

| ID | Pattern blocked | Better alternative |
|---|---|---|
| `pipe_redirect` | `2>&1 \|` | `\|&` |
| `cat` | `cat <file>` | `Read` tool |
| `head_tail` | `head`/`tail <file>` | `Read` tool |
| `sed_i` | `sed -i` | `Edit` tool |
| `awk_i` | `awk -i` | `Edit` tool |
| `tee` | `tee <file>` | `Write` tool |
| `git_add_all` | `git add -A` / `git add .` | Stage specific files by name |
| `redirect` | `> file` / `>> file` (source/data files) | `Write` or `Edit` tool |

Allows: `/dev/null`, `/dev/std*`, `/tmp/*`, `/proc/*`, `*.log`, fd redirects.

#### Custom rules

Add project-specific or personal rules via JSON config. Both files are loaded and merged if present:

- **Global:** `~/.claude/rubber-band.json`
- **Project:** `.claude/rubber-band.json`

```json
{
  "disabled": ["cat", "head_tail"],
  "extra_habits": [
    {
      "pattern": "(?<!uv )pip[23]?\\s+install\\b|(?<!uv )python[23]?\\s+-m\\s+pip\\s+install\\b",
      "reason": "Use `uv add` instead of `pip install` — keeps deps in pyproject.toml."
    },
    {
      "pattern": "\\bpython[23]?\\s+-c\\b",
      "reason": "Write script to `.dev_scripts/` and run with `uv run`. Use `_tmp_<name>.py` prefix for throwaway scripts."
    }
  ]
}
```

`disabled`: suppress built-in rules by ID (see table above). IDs: `pipe_redirect`, `cat`, `head_tail`, `sed_i`, `awk_i`, `tee`, `git_add_all`, `redirect`.

`extra_habits`: each entry needs `pattern` (Python regex) and `reason` (message shown on block). No validator support — match = block.

### `Stop` — clean up temp scripts

Runs when the session ends. Deletes `_tmp_*.py` files from `.dev_scripts/` in the working directory.

Pairs with the convention of naming throwaway scripts `_tmp_<name>.py` — they're cleaned up automatically without manual housekeeping.

## Installation

```sh
claude plugin install https://github.com/adamlogan73/claude-rubber-band
```

Or clone and install locally:

```sh
git clone https://github.com/adamlogan73/claude-rubber-band
claude plugin install ./claude-rubber-band
```

## License

MIT
