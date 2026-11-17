"""Export an evidence pack for the browser viewer (viewer/evidence.json).

  uv run python scripts/export_viewer.py

The browser build of Relate can't open a .rl file, so the viewer loads this JSON into an in-memory
Relate store. The pack holds two manuscripts: the demo paper (from data/demo.rl) and the grant draft
from the agent demo (checked here, on a temporary copy, at depth 2; served from the HTTP cache).
"""

import datetime as dt
import json
import shutil
import tempfile
from pathlib import Path

import relate

from loadbearing import bib, store as lb_store
from loadbearing.check import run_check

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "viewer" / "evidence.json"


def plain(value):
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return value


def export(store: str) -> dict:
    conn = relate.connect(store, read_only=True)
    nodes = [{"id": r["id"], "labels": sorted(r["labels"]),
              "props": {k: plain(v) for k, v in r["props"].items() if v is not None and k != "vec"}}
             for r in conn.execute("MATCH (n) RETURN n.id AS id, labels(n) AS labels, properties(n) AS props ORDER BY id")]
    rels = [{"type": r["type"], "s": r["s"], "t": r["t"], "props": {k: plain(v) for k, v in r["props"].items() if v is not None}}
            for r in conn.execute("MATCH (a)-[r]->(b) RETURN type(r) AS type, a.id AS s, b.id AS t, properties(r) AS props ORDER BY s, t")]
    manuscripts = [dict(r) for r in conn.execute("MATCH (m:Manuscript) RETURN m.id AS id, m.title AS title ORDER BY id")]
    conn.close()
    return {"nodes": nodes, "rels": rels, "manuscripts": manuscripts}


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="lb-viewer-")
    store = str(Path(tmp) / "pack.rl")
    shutil.copy(ROOT / "data" / "demo.rl", store)
    draft = (ROOT / "examples" / "draft_background.md").read_text()
    refs = bib.parse_references(draft)
    run_check(store, refs=refs, label="grant-draft", depth=2)
    pack = export(store)
    shutil.rmtree(tmp, ignore_errors=True)
    titles = {"W4408770418": "Demo paper: Redox Biology 2025 (72 references, depth 3)",
              "M:grant-draft": "Agent demo: grant background draft (7 references, depth 2)"}
    for m in pack["manuscripts"]:
        m["label"] = titles.get(m["id"], m["title"])
        m["depth"] = 2 if m["id"] == "M:grant-draft" else 3
    pack["meta"] = {"generated": dt.date.today().isoformat(), "source": "data/demo.rl + examples/draft_background.md",
                    "nodes": len(pack["nodes"]), "relationships": len(pack["rels"])}
    # The viewer runs exactly the statements the CLI and MCP server run (store.py), not a JS copy.
    pack["queries"] = {"exposure": lb_store.EXPOSURE_QUERY, "load_bearing_only": lb_store.LOAD_BEARING_ONLY,
                       "ignored": lb_store.IGNORED_QUERY,
                       "load_bearing_intents": lb_store.LOAD_BEARING_INTENTS}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(pack, ensure_ascii=False, separators=(",", ":")))
    print(f"{len(pack['nodes'])} nodes, {len(pack['rels'])} relationships, "
          f"{len(pack['manuscripts'])} manuscripts -> {OUT} ({OUT.stat().st_size / 1e6:.2f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
