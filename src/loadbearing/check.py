"""The check itself, shared by the CLI and the MCP server.

run_check() expands the graph around a manuscript (or reads an existing store),
runs the exposure query in Relate, and returns a summary grouped by retracted paper.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import relate

from . import bib, crossref, expand, openalex, retractionwatch, store
from .openalex import norm_doi, short_id

ORDER = ["direct", "load_bearing", "unverified", "mention_only", "defused"]


@dataclass
class CheckResult:
    root_id: str
    title: str
    depth: int
    store_stats: dict
    summary: dict
    expansion: expand.Expansion | None


def summarize(rows: list[dict], ref_keys: dict[str, str] | None = None) -> dict:
    """Group paths by retracted paper; each takes the most serious status among its paths.

    ref_keys maps a reference DOI to its .bib key, so agents can point at their own citation.
    """
    ref_keys = ref_keys or {}
    by_bad: dict[str, dict] = {}
    edges: dict[tuple[str, str], dict] = {}
    for r in rows:
        for a, b, e in zip(r["chain"], r["chain"][1:], r["edges"]):
            edges[(a["id"], b["id"])] = e
        g = by_bad.setdefault(r["bad_id"], {
            "id": r["bad_id"], "title": r["bad_title"], "year": r["bad_year"], "doi": r["bad_doi"],
            "nature": r["nature"], "retraction_date": r["retraction_date"], "reasons": r["reasons"],
            "notice_doi": r.get("notice_doi"), "notice_source": r.get("notice_source"),
            "via": {}, "paths": [],
        })
        ref = r["chain"][1]
        g["via"][ref["id"]] = {"id": ref["id"], "doi": ref["doi"], "title": ref["title"], "year": ref["year"],
                               "bib_key": ref_keys.get(ref["doi"] or "")}
        g["paths"].append(r)
    for g in by_bad.values():
        g["status"] = min((p["status"] for p in g["paths"]), key=ORDER.index)
        best = [p for p in g["paths"] if p["status"] == g["status"]]
        g["best_path"] = min(best, key=lambda p: (p["hops"], -sum(1 for e in p["edges"] if e["context"])))
        g["via"] = sorted(g["via"].values(), key=lambda v: v["id"])
    groups = sorted(by_bad.values(), key=lambda g: (ORDER.index(g["status"]), -len(g["via"]), g["title"] or ""))
    evidence = Counter(e.get("evidence") or "none" for e in edges.values())
    return {
        "retracted": groups,
        "counts": Counter(g["status"] for g in groups),
        "refs_exposed": len({r["chain"][1]["id"] for r in rows}),
        "citations_on_paths": len(edges),
        "citations_read": evidence.get("fulltext", 0) + evidence.get("s2", 0),
        "evidence": dict(evidence),
        "zombies": sum(1 for e in edges.values() if e.get("zombie")),
        "date_conflicts": sum(1 for e in edges.values() if e.get("year_conflict")),
        "ignored_impossible": [],
    }


def run_check(store_path: str, *, bib_path: str | None = None, refs: list[dict] | None = None,
              label: str | None = None, doi: str | None = None, depth: int = 3,
              offline: bool = False, s2_limit: int = 40) -> CheckResult:
    """Check a .bib file, a list of reference dicts ({key, doi, title}), or a published paper (doi)."""
    if doi:
        work = openalex.work(doi)
        root_id, title, refs = short_id(work["id"]), work.get("title") or doi, []
    else:
        if bib_path:
            refs = bib.read_references(bib_path)
            label = label or Path(bib_path).stem
        work, title = None, label or "manuscript"
        root_id = f"M:{label or 'manuscript'}"
    ref_keys = {r["doi"]: r["key"] for r in refs or [] if r.get("doi")}
    # Offline checks only read: open read-only so a shipped store is never rewritten.
    conn = relate.connect(store_path, read_only=True) if offline else store.open_store(store_path)
    try:
        ex = None if offline else expand.build(conn, refs or [], root_id, title, work, depth, s2_limit=s2_limit)
        rows = store.exposure(conn, root_id, depth)
        ignored = store.ignored_citations(conn, root_id, depth)
        st = store.stats(conn)
    finally:
        conn.close()
    summary = summarize(rows, ref_keys)
    summary["ignored_impossible"] = ignored
    return CheckResult(root_id, title, depth, st, summary, ex)


def retraction_status(dois: list[str]) -> list[dict]:
    """Fast, direct status of specific DOIs: no graph expansion.

    Retraction Watch (local CSV) is authoritative for notices; OpenAlex fills in titles and
    catches retractions Retraction Watch hasn't recorded.
    """
    notices = retractionwatch.load()
    wanted = [d for d in (norm_doi(x) for x in dois) if d]
    works = {norm_doi(w.get("doi")): w for w in openalex.works_by_dois(wanted, select=openalex.SLIM_FIELDS)} if wanted else {}
    out = []
    for d in wanted:
        n, w = notices.get(d), works.get(d)
        if not n and w and w.get("is_retracted"):  # Retraction Watch lags; ask Crossref for the notice
            n = crossref.notice(d)
        if n and n["nature"] == "Retraction" or (w and w.get("is_retracted")):
            status = "retracted"
        elif n and n["nature"] == "Expression of concern":
            status = "expression_of_concern"
        elif n and n["nature"] == "Correction":
            status = "corrected"
        elif w:
            status = "no_notice_found"
        else:
            status = "not_found"
        out.append({
            "doi": d, "status": status, "title": (w or {}).get("title"), "year": (w or {}).get("publication_year"),
            "openalex_id": short_id(w["id"]) if w else None,
            "notice": {k: n[k] for k in ("nature", "date", "reasons", "notice_doi")} if n else None,
        })
    return out
