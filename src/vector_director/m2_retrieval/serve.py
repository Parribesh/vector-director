"""`vd serve`: the gallery over local HTTP, for Studio.

GET   /health
GET   /search?q=stone+well&k=20&kind=prop&status=approved&mode=vector
GET   /items?kind=prop
GET   /items/<id>
PATCH /items/<id>      {"name", "description", "tags", "height_cm", "status"}
GET   /files/items/<id>.svg  and  /files/thumbs/<id>.png

The director, with --sadhu (these answer {"job": id}; poll GET /jobs/<id> for steps and the result):
POST  /story      {"project", "template", "idea"}
POST  /breakdown  {"project": {...}, "story", "title", "language", "template"}
POST  /stage      {"project": {...}}
POST  /dress      {"project": {...}, "set": id}
GET   /templates
"""

from __future__ import annotations

import json
import threading
import uuid
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
        self.engine = None
        self.jobs: dict[str, dict] = {}

    def start_job(self, project_id: str, work) -> str:
        """Runs work(run) on its own thread; its steps and result are read from /jobs/<id>."""
        from vector_director.director.pipeline import Run

        job_id, job = uuid.uuid4().hex, {"steps": [], "done": False, "result": None, "error": None}
        steps: dict[str, dict] = {}

        def on_step(label, state, note=""):
            if label not in steps:
                steps[label] = {"label": label}
                job["steps"].append(steps[label])
            steps[label].update(state=state, note=note)

        def go():
            try:
                job["result"] = work(Run(project_id, self.engine, self, on_step))
            except Exception as e:  # noqa: BLE001
                job["error"] = str(e)
            job["done"] = True

        self.jobs[job_id] = job
        threading.Thread(target=go, daemon=True).start()
        return job_id

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
            self.send_header("access-control-allow-methods", "GET, PATCH, POST, OPTIONS")
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
            if len(parts) == 2 and parts[0] == "jobs" and parts[1] in g.jobs:
                return self._json(200, g.jobs[parts[1]])
            if parts == ["templates"] and g.engine:
                out = []
                for f in sorted((g.engine.root / "bible" / "templates").glob("*.json")):
                    t = json.loads(f.read_text())
                    out.append({"id": f.stem, "name": t["name"], "description": t.get("description", ""), "stages": [s["name"] for s in t["stages"]]})
                return self._json(200, out)
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

        def do_POST(self) -> None:
            from vector_director.director import pipeline as P

            path = urlparse(self.path).path.strip("/")
            if not g.engine:
                return self._json(503, {"error": "the director needs vd serve --sadhu <checkout>"})
            try:
                req = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))) or b"{}")
            except ValueError:
                return self._json(400, {"error": "not JSON"})
            project = req.get("project") or {}
            pid = project.get("id", "") if isinstance(project, dict) else project
            template = req.get("template") or "baba-rescue"
            if path == "story":
                work = lambda run: P.write_story(run, template, req.get("idea") or "")
            elif path == "breakdown":
                work = lambda run: P.run_pipeline(run, project, req["story"], req.get("title", ""), req.get("language", "hi"), template)
            elif path == "stage":

                def work(run):
                    P.direct_scenes(run, project["scenes"], project["sets"])
                    return {"scenes": project["scenes"], "stats": run.stats}

            elif path == "dress":
                st = next((s for s in project.get("sets", []) if s["id"] == req.get("set")), None)
                if not st:
                    return self._json(404, {"error": "no such set"})

                def work(run):
                    P.dress_set(run, pid, st, project.get("scenes", []))
                    return {"set": st, "wanted": run.wanted, "files": run.files, "stats": run.stats}

            else:
                return self._json(404, {"error": "not found"})
            self._json(200, {"job": g.start_job(pid, work)})

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


def serve(root: Path | str = "library", port: int = 8772, sadhu: Path | str | None = None) -> None:
    g = Gallery(root)
    if sadhu:
        from vector_director.director import llm
        from vector_director.director.pipeline import Engine

        g.engine = Engine(sadhu)
        home = Path(root).resolve().parent  # logs and the answer cache stay in vector-director
        llm.CACHE, llm.RUNS = str(home / ".cache" / "llm"), str(home / "runs")
    g.vector.embedder.embed_text(["warm up"])  # so the first search isn't the slow one
    print(
        f"gallery: {len(g.reg.items)} items, {len(g.vector.ids)} embedded, http://127.0.0.1:{port}",
        flush=True,
    )
    ThreadingHTTPServer(("127.0.0.1", port), handler_for(g)).serve_forever()
