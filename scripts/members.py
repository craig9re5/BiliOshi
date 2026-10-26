"""Compatibility entry point; implementation lives in bilioshi.members."""

import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bilioshi import members as _implementation

if __name__ == "__main__":
    from bilioshi.entrypoints import run_cli

    raise SystemExit(run_cli(_implementation.main))
else:
    sys.modules[__name__] = _implementation
