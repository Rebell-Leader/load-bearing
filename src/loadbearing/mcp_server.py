"""Load-Bearing MCP server: retraction-exposure checks for AI agents, on a Relate graph.

Run:  uv run --directory <repo> loadbearing-mcp        (stdio)
Env:  LOADBEARING_STORE  Relate store (default data/evidence, a directory store that
                         `relate serve --read-only=live` can follow while this server writes)
      OPENALEX_API_KEY   optional; raises the OpenAlex daily budget

Tools
  retraction_status   is this DOI retracted? (instant, no graph expansion)
  check_references    exposure report for a bibliography (BibTeX or DOIs)
  check_paper         exposure report for a published paper
  explain_exposure    every path from a checked manuscript to one retracted paper, with sentences
  graph_schema        what the graph holds, with example Cypher
  query_graph         read-only Cypher over the evidence graph
"""

from __future__ import annotations

import json
import os
import textwrap
import threading

import relate
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from . import bib, store
from .check import ORDER, retraction_status as _retraction_status, run_check
from .openalex import norm_doi

STORE = os.environ.get("LOADBEARING_STORE", "data/evidence")
# A store has one writer. Tool calls run in worker threads, so checks take turns.
_WRITE_LOCK = threading.Lock()
MAX_ROWS = 200

GUIDANCE = {
    "direct": "You cite a retracted paper. Remove it, or cite it only to discuss the retraction.",
    "load_bearing": "A paper you cite may rely on retracted work for a method or result. Read the quoted "
                    "sentence first: intent v1 finds most real reliance but has ~33% precision on held-out "
                    "sentences (docs/EVAL.md). If your claim depends on that result, find independent support.",
    "unverified": "A path exists but at least one citation on it could not be read. Low priority unless "
                  "the retracted paper is central to your topic.",
    "mention_only": "Reached only through background mentions. Usually safe to ignore.",
    "defused": "A paper on the path already acknowledges the problem.",
}

INSTRUCTIONS = """Load-Bearing finds where a bibliography rests on retracted science.
Before citing a paper, call retraction_status. To audit a whole reference list, call check_references
(BibTeX or DOIs); for a published paper, check_paper. Act on 'direct' and 'load_bearing' findings;
quote the evidence sentence when you tell the user. Report what notices say: never call a paper or
author fraudulent. A path is evidence for a person to review, not a verdict."""

mcp = MCPServer(name="load-bearing", title="Load-Bearing", instructions=INSTRUCTIONS, version="0.1.0")

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
LOOKUP = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)
BUILDS = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True)


def _clip(text: str | None, n: int = 300) -> str | None:
    return textwrap.shorten(text, n, placeholder="…") if text else None


def _hops(path: dict) -> list[dict]:
    hops = []
    for a, b, e in zip(path["chain"], path["chain"][1:], path["edges"]):
        hops.append({
            "from": _clip(a["title"], 120), "to": _clip(b["title"], 120), "to_doi": b["doi"],
            "intent": e["intent"], "evidence": e["evidence"], "section": e["section"],
            "sentence": _clip(e["context"]), "cited_after_retraction": e["zombie"],
            "date_conflict": e.get("year_conflict", False),
        })
    return hops


def _report(res, limits: dict[str, int] | None = None) -> str:
    limits = limits or {"direct": 50, "load_bearing": 15, "unverified": 10, "mention_only": 5, "defused": 5}
    s = res.summary
    findings = []
    shown = dict.fromkeys(ORDER, 0)
    for g in s["retracted"]:
        st = g["status"]
        if shown[st] >= limits[st]:
            continue
        shown[st] += 1
        item = {
            "status": st, "retracted_id": g["id"], "title": g["title"], "year": g["year"], "doi": g["doi"],
            "notice": {"nature": g["nature"], "date": g["retraction_date"], "reasons": g["reasons"],
                       "notice_doi": g.get("notice_doi"), "source": g.get("notice_source")},
            "notice_on_record": g["notice_on_record"],
            "via_your_references": [{k: v for k, v in r.items() if v is not None} for r in g["via"]],
        }
        if st in ("direct", "load_bearing", "defused"):
            item["evidence_path"] = _hops(g["best_path"])
        findings.append(item)
    out = {
        "manuscript_id": res.root_id, "title": res.title, "depth": res.depth,
        "summary": {
            "retracted_papers_reached": len(s["retracted"]),
            "without_retraction_notice": s["without_retraction_notice"],
            "your_references_exposed": s["refs_exposed"],
            "by_status": {k: s["counts"][k] for k in ORDER if s["counts"][k]},
            "citations_on_paths": s["citations_on_paths"],
            "citing_sentences_read": s["citations_read"],
            "cited_after_retraction": s["zombies"],
            "date_conflicts_kept_as_unverified": s.get("date_conflicts", 0),
            "impossible_citations_ignored": s.get("ignored_impossible", []),
        },
        "guidance": {k: GUIDANCE[k] for k in ORDER if s["counts"][k]},
        "intent_classifier": "v1 (held-out reliance recall 0.69, precision 0.33; see docs/EVAL.md)",
        "findings": findings,
        "truncated": {k: s["counts"][k] - shown[k] for k in ORDER if s["counts"][k] > shown[k]},
        "next": f"explain_exposure(manuscript_id='{res.root_id}', retracted='<retracted_id>') lists every path with its sentences.",
    }
    return json.dumps(out, ensure_ascii=False, default=str)


@mcp.tool(annotations=LOOKUP)
def retraction_status(dois: list[str]) -> str:
    """Check whether specific papers are retracted, corrected or under an expression of concern.

    Fast and direct: no citation graph is built. Use it before citing a paper.
    Args:
        dois: DOIs, with or without https://doi.org/.
    """
    return json.dumps(_retraction_status(dois), ensure_ascii=False)


@mcp.tool(annotations=BUILDS)
def check_references(references: str, label: str = "draft", depth: int = 2) -> str:
    """Find which references in a bibliography rest on retracted science, directly or through the papers they cite.

    Builds or extends the citation graph in Relate, reads the sentence where each citation on a path
    appears, and groups findings by retracted paper: direct, load_bearing, unverified, mention_only, defused.
    Args:
        references: BibTeX entries, or text with one DOI per line.
        label: a short name for this manuscript; findings are stored under manuscript_id 'M:<label>'.
        depth: citation hops from the manuscript (1-3). 2 takes seconds; 3 can take minutes on a cold cache.
    """
    refs = bib.parse_references(references)
    if not any(r.get("doi") for r in refs):
        return json.dumps({"error": "no DOIs found; pass BibTeX with doi fields or one DOI per line"})
    with _WRITE_LOCK:
        res = run_check(STORE, refs=refs, label=label, depth=max(1, min(depth, 3)))
    return _report(res)


@mcp.tool(annotations=BUILDS)
def check_paper(doi: str, depth: int = 2) -> str:
    """Audit a published paper's reference list for reliance on retracted work.

    Uses the paper's open full text (Europe PMC) when available, so the first hop is classified too.
    Args:
        doi: the paper's DOI.
        depth: citation hops (1-3). 3 can take minutes on a cold cache.
    """
    with _WRITE_LOCK:
        res = run_check(STORE, doi=doi, depth=max(1, min(depth, 3)))
    return _report(res)


def _ro():
    return relate.connect(STORE, read_only=True)


@mcp.tool(annotations=READ_ONLY)
def explain_exposure(manuscript_id: str, retracted: str) -> str:
    """List every citation path from a checked manuscript to one retracted paper, with the citing sentences.

    Args:
        manuscript_id: from a check result ('M:<label>' or an OpenAlex id like 'W4408770418').
        retracted: the retracted paper's OpenAlex id (retracted_id in findings) or its DOI.
    """
    key = retracted if retracted.upper().startswith("W") else norm_doi(retracted)
    conn = _ro()
    try:
        rows = [r for r in store.exposure(conn, manuscript_id, 3) if key in (r["bad_id"], r["bad_doi"])]
    finally:
        conn.close()
    if not rows:
        return json.dumps({"error": f"no path from {manuscript_id} to {retracted} in the store; run a check first"})
    first = rows[0]
    return json.dumps({
        "retracted": {"id": first["bad_id"], "title": first["bad_title"], "doi": first["bad_doi"],
                      "notice": {"nature": first["nature"], "date": first["retraction_date"], "reasons": first["reasons"]}},
        "paths": [{"status": r["status"], "hops": _hops(r)} for r in rows[:30]],
        "total_paths": len(rows),
    }, ensure_ascii=False, default=str)


@mcp.tool(annotations=READ_ONLY)
def graph_schema() -> str:
    """Describe the evidence graph: labels, relationships, properties, counts and example Cypher."""
    conn = _ro()
    try:
        counts = {r["label"]: r["n"] for r in conn.execute(
            "MATCH (n) UNWIND labels(n) AS label RETURN label, count(*) AS n ORDER BY n DESC")}
        rels = {r["t"]: r["n"] for r in conn.execute("MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS n")}
        manuscripts = [dict(r) for r in conn.execute(
            "MATCH (m:Manuscript) RETURN m.id AS id, m.title AS title ORDER BY id LIMIT 20")]
    finally:
        conn.close()
    return json.dumps({
        "store": STORE,
        "model": store.__doc__,
        "node_counts": counts, "relationship_counts": rels, "manuscripts": manuscripts,
        "data_quality": "CITES.anachronistic = cited paper dated 2+ years after the citing paper (bad upstream data; "
                        "exclude it in your own path queries). CITES.year_conflict = the same for a retracted paper "
                        "(kept, never load-bearing).",
        "intents": {"method": "uses a method or protocol", "result": "builds on a finding",
                    "background": "general mention", "critical": "flags the cited work", "unknown": "no sentence read"},
        "examples": {
            "load_bearing_paths": store.LOAD_BEARING_ONLY.strip(),
            "most_reached_retracted": "MATCH (m:Manuscript {id: $root})-[:CITES]->(b:Paper)"
                                      "-[c:CITES WHERE NOT coalesce(c.anachronistic, false)]->{0,2}(bad:Retracted) "
                                      "RETURN bad.title AS title, count(DISTINCT b) AS via ORDER BY via DESC LIMIT 10",
            "impossible_citations": "MATCH (a:Paper)-[c:CITES]->(b:Paper) WHERE c.anachronistic OR c.year_conflict "
                                    "RETURN a.title, a.year, b.title, b.year, c.anachronistic, c.year_conflict",
            "cited_after_retraction": "MATCH (a:Paper)-[c:CITES {zombie: true}]->(r:Retracted) "
                                      "RETURN a.title, toString(a.pub_date), r.title, toString(r.retraction_date) LIMIT 20",
            "retracted_for_citing_retracted": "MATCH (r:Retracted) WHERE any(x IN r.reasons WHERE x CONTAINS 'Cites Retracted') "
                                              "RETURN r.title, toString(r.retraction_date)",
        },
    }, ensure_ascii=False, default=str)


@mcp.tool(annotations=READ_ONLY)
def query_graph(cypher: str, parameters: dict | None = None) -> str:
    """Run a read-only Cypher query on the evidence graph (Relate). Writes are refused.

    Call graph_schema first for labels and examples. At most 200 rows are returned.
    Args:
        cypher: a read query (MATCH ... RETURN ...). Bind values as $parameters.
        parameters: values for $parameters in the query.
    """
    conn = _ro()
    try:
        cur = conn.execute(cypher, parameters or {})
        rows = []
        for i, row in enumerate(cur):
            if i >= MAX_ROWS:
                break
            rows.append(dict(row))
        return json.dumps({"columns": cur.columns, "rows": rows, "truncated": len(rows) == MAX_ROWS},
                          ensure_ascii=False, default=str)
    except relate.Error as exc:
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"})
    finally:
        conn.close()


def main() -> None:
    mcp.run("stdio")


if __name__ == "__main__":
    main()
