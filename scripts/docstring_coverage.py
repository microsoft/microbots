#!/usr/bin/env python
"""Compute NumPy-docstring coverage for the project.

Coverage is measured against the *same* set of objects the numpydoc
validation hook inspects (modules, classes, functions and methods), using the
rules configured under ``[tool.numpydoc_validation]`` in ``pyproject.toml``.

An object "passes" when numpydoc reports no issues for it; coverage is the
percentage of passing objects over the total inspected.

Usage
-----
    python scripts/docstring_coverage.py [paths ...]

If no paths are given, ``src/microbots`` is scanned. When run inside GitHub
Actions (``GITHUB_OUTPUT`` set), the metrics are also written as step outputs
(``percent``, ``passing``, ``total``, ``failing``).
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

from numpydoc.hooks.validate_docstrings import (
    DocstringVisitor,
    parse_config,
    process_file,  # noqa: F401  (kept for parity / external reuse)
)
from numpydoc.hooks.utils import find_project_root

DEFAULT_PATHS = ["src/microbots"]


class CoverageVisitor(DocstringVisitor):
    """A :class:`DocstringVisitor` that also tallies pass/fail counts."""

    def __init__(self, filepath: str, config: dict) -> None:
        super().__init__(filepath=filepath, config=config)
        self.total = 0
        self.failing = 0

    def _get_numpydoc_issues(self, node: ast.AST) -> None:
        before = len(self.findings)
        super()._get_numpydoc_issues(node)
        self.total += 1
        if len(self.findings) > before:
            self.failing += 1


def iter_python_files(paths: list[str]) -> list[Path]:
    """Return all ``.py`` files under the given paths."""
    files: list[Path] = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            files.extend(sorted(p.rglob("*.py")))
        elif p.suffix == ".py" and p.is_file():
            files.append(p)
    return files


def main(argv: list[str]) -> int:
    paths = argv or DEFAULT_PATHS
    files = iter_python_files(paths)
    if not files:
        print(f"No Python files found under: {', '.join(paths)}")
        return 0

    project_root, _ = find_project_root([str(f) for f in files])
    config = parse_config(project_root)

    total = 0
    failing = 0
    for file in files:
        with open(file, encoding="utf-8") as fh:
            module_node = ast.parse(fh.read(), str(file))
        visitor = CoverageVisitor(filepath=str(file), config=config)
        visitor.visit(module_node)
        total += visitor.total
        failing += visitor.failing

    passing = total - failing
    percent = round(passing / total * 100) if total else 100

    print("NumPy docstring coverage")
    print(f"  passing : {passing}")
    print(f"  failing : {failing}")
    print(f"  total   : {total}")
    print(f"  percent : {percent}%")

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as out:
            out.write(f"percent={percent}\n")
            out.write(f"passing={passing}\n")
            out.write(f"total={total}\n")
            out.write(f"failing={failing}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
