# claude-rubber-band

Claude Code plugin — two hooks that keep Claude's shell habits tidy.

## Hooks

### `PreToolUse` — block bad Bash habits

Runs before every `Bash` tool call. Blocks patterns where a dedicated tool is better, and explains why.

| Pattern blocked | Better alternative |
|---|---|
| `> file` / `>> file` (source/data files) | `Write` or `Edit` tool |
| `cat <file>` | `Read` tool |
| `head`/`tail <file>` | `Read` tool |
| `sed -i` / `awk -i` | `Edit` tool |
| `tee <file>` | `Write` tool |
| `2>&1 \|` | `\|&` |
| `git add -A` / `git add .` | Stage specific files by name |

Allows: `/dev/null`, `/dev/std*`, `/tmp/*`, `/proc/*`, `*.log`, fd redirects.

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
