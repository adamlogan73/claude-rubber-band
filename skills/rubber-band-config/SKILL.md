---
description: Create or update your rubber-band config (disabled rules, extra habits, extension/prefix/suffix overrides)
---

Help the user configure the rubber-band plugin. The plugin reads config from two locations (both merged, project wins on conflicts):

- **Global:** `~/.claude/rubber-band.json`
- **Project:** `.claude/rubber-band.json` (relative to current working directory)

## Config schema

```json
{
  "disabled": ["rule_id", ...],
  "extra_habits": [
    {"pattern": "<Python regex>", "reason": "<message shown on block>"}
  ],
  "blocked_extensions": [".py", ".sh", ...],
  "allowed_prefixes": ["/dev/", "/tmp/", ...],
  "allowed_suffixes": [".log", ...]
}
```

**Built-in rule IDs** (for `disabled`): `pipe_redirect`, `cat`, `head_tail`, `sed_i`, `awk_i`, `tee`, `git_add_all`, `redirect`, `grep`, `trailing_cat`

**Override semantics:** `blocked_extensions`, `allowed_prefixes`, and `allowed_suffixes` fully replace their defaults when present. `disabled` and `extra_habits` are additive across global and project configs.

**Default blocked extensions:** `.py .pyi .md .rst .txt .json .jsonl .yaml .yml .toml .ini .cfg .conf .sh .bash .zsh .fish .js .ts .tsx .jsx .mjs .cjs .html .htm .css .scss .sass .go .rs .c .h .cpp .hpp .cc .java .kt .rb .php .sql .csv .tsv .xml .env .lock .dockerfile`

**Default allowed prefixes:** `/dev/` `/tmp/` `/var/tmp/` `/proc/`

**Default allowed suffixes:** `.log`

## Steps

1. Ask the user: global config or project config (or both)?
2. Ask what they want to change: disable a rule, add a custom habit, or override extensions/prefixes/suffixes?
3. Read the existing config file if it exists.
4. Make the requested changes and write the file.
5. Show the final config so the user can confirm.
