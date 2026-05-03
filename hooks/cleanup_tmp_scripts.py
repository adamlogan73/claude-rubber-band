#!/usr/bin/env python3
"""Stop hook: delete _tmp_*.py files from .dev_scripts/ at session end.

Pairs with the CLAUDE.md convention of naming throwaway scripts with a
`_tmp_` prefix so they're cleaned up automatically.
"""

from __future__ import annotations

import os
from pathlib import Path


def main() -> None:
    dev_scripts = Path(os.environ.get("PWD", ".")) / ".dev_scripts"
    if dev_scripts.is_dir():
        for f in dev_scripts.glob("_tmp_*.py"):
            f.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
