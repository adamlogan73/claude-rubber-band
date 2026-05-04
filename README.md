# claude-rubber-band

Claude Code plugin — hook that keeps Claude's shell habits tidy.

## Hook

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
| `grep` | `grep <file>` / `grep -r` | `Grep` tool |
| `trailing_cat` | `cmd \| cat` / `cmd \|& cat` | Remove — Bash tool captures all output |
| `redirect` | `> file` / `>> file` (source/data files) | `Write` or `Edit` tool |

Allows: `/dev/null`, `/dev/std*`, `/tmp/*`, `/proc/*`, `*.log`, fd redirects, `cmd | grep` (stdin filter), `tail -f` (follow mode).

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
    }
  ]
}
```

`disabled` and `extra_habits` are **additive** — both global and project configs contribute to the merged set.

`blocked_extensions`, `allowed_prefixes`, and `allowed_suffixes` **replace** their defaults when set (last file wins).

#### Config keys

| Key | Type | Description |
|---|---|---|
| `disabled` | `string[]` | Built-in rule IDs to suppress |
| `extra_habits` | `object[]` | Custom rules: `{id?, pattern, reason}` |
| `blocked_extensions` | `string[]` | Extensions blocked by redirect rule (replaces defaults) |
| `allowed_prefixes` | `string[]` | Path prefixes exempt from redirect rule (replaces defaults) |
| `allowed_suffixes` | `string[]` | File suffixes exempt from redirect rule (replaces defaults) |

Built-in rule IDs: `pipe_redirect`, `cat`, `head_tail`, `sed_i`, `awk_i`, `tee`, `git_add_all`, `redirect`, `grep`, `trailing_cat`

Default blocked extensions: `.py .pyi .md .rst .txt .json .jsonl .yaml .yml .toml .ini .cfg .conf .sh .bash .zsh .fish .js .ts .tsx .jsx .mjs .cjs .html .htm .css .scss .sass .go .rs .c .h .cpp .hpp .cc .java .kt .rb .php .sql .csv .tsv .xml .env .lock .dockerfile`

## Installation

Add this repo as a marketplace, then install:

```sh
/plugin marketplace add adamlogan73/claude-rubber-band
/plugin install claude-rubber-band@claude-rubber-band
```

## License

MIT
