"""Enable ``python -m microbots.auto_memory``."""

from __future__ import annotations

import sys

from microbots.auto_memory.cli import main


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())