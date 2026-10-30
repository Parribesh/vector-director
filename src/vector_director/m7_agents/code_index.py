"""AST index of a codebase (e.g. sadhu) so a coding agent can extend it."""

from __future__ import annotations

from pathlib import Path


def index_repo(root: Path) -> list[dict]:
    """One record per function/class: path, name, signature, docstring, embedding."""
    raise NotImplementedError
