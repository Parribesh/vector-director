"""`vd serve`: the gallery over local HTTP, for Studio.

GET   /health
GET   /search?q=stone+well&k=20&kind=prop&status=approved&mode=vector
GET   /items?kind=prop
GET   /items/<id>
PATCH /items/<id>      {"name", "description", "tags", "height_cm", "status"}
GET   /files/items/<id>.svg  and  /files/thumbs/<id>.png
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from vector_director.m2_retrieval.embedders import ClipEmbedder
from vector_director.m2_retrieval.library import Registry
from vector_director.m2_retrieval.retrievers import BM25Retriever, HybridRetriever, VectorRetriever

TYPES = {".svg": "image/svg+xml", ".png": "image/png"}


class Gallery:
    def __init__(self, root: Path | str) -> None:
        self.reg = Registry(root)
        self.bm25 = BM25Retriever(self.reg)
        self.vector = VectorRetriever(self.reg, ClipEmbedder())
        self.hybrid = HybridRetriever([self.bm25, self.vector], [1, 3])
        self.lock = threading.Lock()

    def search(
        self,
        q: str,
        k: int = 20,
        kind: str | None = None,
        status: str | None = None,
        mode: str = "vector",
    ) -> list[dict]:
        """Vector by default: it ranked best on data/eval/retrieval.jsonl (`vd library eval`)."""
        r = {"bm25": self.bm25, "hybrid": self.hybrid}.get(mode, self.vector)
        with self.lock:
            hits = r.search(q, k=k, kind=kind, status=status)
        return [{**asdict(self.reg.items[h.id]), "score": h.score} for h in hits]

    def edit(self, item_id: str, fields: dict) -> dict:
        with self.lock:
            item = self.reg.update(item_id, **fields)
            self.bm25.refresh()
            if {"name", "description", "tags"} & set(fields):
                self.vector.refresh_text(item_id)
        return asdict(item)


def handler_for(g: Gallery):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
            self.send_response(code)
            self.send_header("content-type", ctype)
            self.send_header("access-control-allow-origin", "*")
            self.send_header("access-control-allow-methods", "GET, PATCH, OPTIONS")
            self.send_header("access-control-allow-headers", "content-type")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, data) -> None:
            self._send(code, json.dumps(data, ensure_ascii=False).encode())

        def log_message(self, *args) -> None:
            pass

        def do_OPTIONS(self) -> None:
            self._send(204, b"")

        def do_GET(self) -> None:
            u = urlparse(self.path)
            parts = [unquote(p) for p in u.path.strip("/").split("/")]
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            if parts == ["health"]:
                return self._json(
                    200, {"ok": True, "items": len(g.reg.items), "embedded": len(g.vector.ids)}
                )
            if parts == ["search"]:
                return self._json(
                    200,
                    g.search(
                        q.get("q", ""),
                        int(q.get("k", 20)),
                        q.get("kind"),
                        q.get("status"),
                        q.get("mode", "vector"),
                    ),
                )
            if parts == ["items"]:
                return self._json(
                    200,
                    [
                        asdict(i)
                        for i in g.reg.items.values()
                        if not q.get("kind") or i.kind == q["kind"]
                    ],
                )
            if len(parts) == 2 and parts[0] == "items" and parts[1] in g.reg.items:
                return self._json(200, asdict(g.reg.items[parts[1]]))
            if len(parts) == 3 and parts[0] == "files" and parts[1] in ("items", "thumbs"):
                path = (g.reg.root / parts[1] / parts[2]).resolve()
                if path.parent == (g.reg.root / parts[1]).resolve() and path.exists():
                    return self._send(
                        200, path.read_bytes(), TYPES.get(path.suffix, "application/octet-stream")
                    )
            self._json(404, {"error": "not found"})

        def do_PATCH(self) -> None:
            parts = [unquote(p) for p in urlparse(self.path).path.strip("/").split("/")]
            if len(parts) != 2 or parts[0] != "items" or parts[1] not in g.reg.items:
                return self._json(404, {"error": "not found"})
            try:
                fields = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))))
                self._json(200, g.edit(parts[1], fields))
            except ValueError as e:
                self._json(400, {"error": str(e)})

    return Handler


def serve(root: Path | str = "library", port: int = 8772) -> None:
    g = Gallery(root)
    g.vector.embedder.embed_text(["warm up"])  # so the first search isn't the slow one
    print(
        f"gallery: {len(g.reg.items)} items, {len(g.vector.ids)} embedded, http://127.0.0.1:{port}",
        flush=True,
    )
    ThreadingHTTPServer(("127.0.0.1", port), handler_for(g)).serve_forever()
