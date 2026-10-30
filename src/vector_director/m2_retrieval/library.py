"""Ingest open-license SVGs: normalize, render a thumbnail, embed, store in LanceDB."""

from __future__ import annotations

from pathlib import Path

from vector_director.core.interfaces import Embedder, Renderer


class AssetLibrary:
    """TODO(M2): one LanceDB table with id, svg, tags, license, text and image vectors."""

    def __init__(self, db_path: Path, embedder: Embedder, renderer: Renderer) -> None:
        self.db_path, self.embedder, self.renderer = db_path, embedder, renderer

    def ingest(self, svg_dir: Path, license: str, source: str) -> int:
        """Returns the number of assets added."""
        raise NotImplementedError("M2: ingest SVGs")
