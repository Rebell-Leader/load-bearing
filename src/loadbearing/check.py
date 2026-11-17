"""The check itself, shared by the CLI and the MCP server.

run_check() expands the graph around a manuscript (or reads an existing store),
runs the exposure query in Relate, and returns a summary grouped by retracted paper.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import relate

from . import bib, expand, openalex, retractionwatch, store
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
            "nature": None if r.get("notice_source") == "openalex" else r["nature"],
            "retraction_date": r["retraction_date"], "reasons": r["reasons"],
            "notice_doi": r.get("notice_doi"), "notice_source": r.get("notice_source"),
            "via": {}, "paths": [],
        })
        ref = r["chain"][1]
        g["via"][ref["id"]] = {"id": ref["id"], "doi": ref["doi"], "title": ref["title"], "year": ref["year"],
                               "bib_key": ref_keys.get(ref["doi"] or "")}
        g["paths"].append(r)
    for g in by_bad.values():
        g["notice_on_record"] = has_retraction_notice(g)
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
        "without_retraction_notice": sum(1 for g in groups if not g["notice_on_record"]),
    }


def has_retraction_notice(g: dict) -> bool:
    """False when only OpenAlex marks the paper retracted, or the only notice found is not a retraction."""
    return g.get("notice_source") in {"retraction_watch", "crossref"} and g.get("nature") == "Retraction"


def notice_label(g: dict) -> str:
    """A flagged paper's status in words. A paper is only called retracted when a notice says so."""
    date = g.get("retraction_date")
    if g.get("notice_source") == "openalex":
        return "marked retracted by OpenAlex, no notice found"
    if has_retraction_notice(g):
        return f"Retraction {date or '(date unknown)'}"
    if g.get("nature") and g.get("notice_source") in {"retraction_watch", "crossref"}:
        kind = g["nature"].lower()
        return (f"marked retracted by OpenAlex, but the only notice found is {'an' if kind[0] in 'aeiou' else 'a'} "
                f"{kind} ({date or 'date unknown'})")
    return "flagged in the graph, no retraction notice on record"


def run_check(store_path: str, *, bib_path: str | None = None, refs: list[dict] | None = None,
              label: str | None = None, doi: str | None = None, depth: int = 3,
              offline: bool = False, s2_limit: int = 40) -> CheckResult:
    """Check a .bib file, a list of reference dicts ({key, doi, title}), or a published paper (doi).

    Offline, nothing touches the network: a DOI is looked up in the store, and a manuscript that
    isn't in the store is an error rather than an empty report.
    """
    work = None
    if doi:
        root_id, title, refs = None, doi, []
        if not offline:
            work = openalex.work(doi)
            root_id, title = short_id(work["id"]), work.get("title") or doi
    else:
        if bib_path:
            refs = bib.read_references(bib_path)
            label = label or Path(bib_path).stem
        title = label or "manuscript"
        root_id = f"M:{title}"
    ref_keys = {r["doi"]: r["key"] for r in refs or [] if r.get("doi")}
    # Offline checks only read: open read-only so a shipped store is never rewritten.
    conn = relate.connect(store_path, read_only=True) if offline else store.open_store(store_path)
    try:
        if offline:
            found = store.find_manuscript(conn, doi=norm_doi(doi) if doi else None,
                                          root_id=None if doi else root_id)
            if not found:
                what = f"doi:{norm_doi(doi)}" if doi else root_id
                raise LookupError(f"{what} is not a checked manuscript in {store_path}; "
                                  "run without --offline to build it")
            root_id, title = found["id"], found["title"] or title
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
    wanted = [d for d in (norm_doi(x) for x in dois) if d]
    works = {norm_doi(w.get("doi")): w for w in openalex.works_by_dois(wanted, select=openalex.SLIM_FIELDS)} if wanted else {}
    out = []
    for d in wanted:
        w = works.get(d)
        marked_retracted = bool(w and w.get("is_retracted"))
        n, source = retractionwatch.resolve(d, marked_retracted)
        confirmed = bool(n and n["nature"] == "Retraction")
        if confirmed:
            status = "retracted"
        elif n and n["nature"] == "Expression of concern":
            status = "expression_of_concern"
        elif n and n["nature"] == "Correction":
            status = "corrected"
        elif marked_retracted:
            status = "marked_retracted"
        elif w:
            status = "no_notice_found"
        else:
            status = "not_found"
        out.append({
            "doi": d, "status": status, "title": (w or {}).get("title"), "year": (w or {}).get("publication_year"),
            "openalex_id": short_id(w["id"]) if w else None,
            "openalex_marked_retracted": marked_retracted, "notice_on_record": confirmed,
            "notice": {**{k: n[k] for k in ("nature", "date", "reasons", "notice_doi")}, "source": source} if n else None,
        })
    return out
