"""Build the exposure graph around one manuscript and write it into Relate.

Hops are counted from the manuscript M:
  M -> B   the manuscript's own references (from a .bib or a published paper)
  B -> R1  their references (ids come free with each B record)
  R1 -> R2 references of references; only retracted R2 are fetched, via a
           server-side OpenAlex filter, so cost stays ~1 request per 100 R1 papers.
"""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from . import fulltext, intent, intent_model, openalex, retractionwatch, s2, store
from .openalex import norm_doi, short_id


@dataclass
class Expansion:
    root_id: str
    root_title: str
    refs_total: int = 0
    refs_resolved: int = 0
    unresolved: list[dict] = field(default_factory=list)
    retracted: dict[str, dict] = field(default_factory=dict)   # id -> work
    papers: dict[str, dict] = field(default_factory=dict)      # id -> slim record
    edges: set[tuple[str, str]] = field(default_factory=set)


def _slim(w: dict) -> dict:
    return {
        "id": short_id(w["id"]),
        "doi": norm_doi(w.get("doi")),
        "title": w.get("title"),
        "year": w.get("publication_year"),
        "pub_date": w.get("publication_date"),
    }


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def expand(refs: list[dict], root_id: str, root_title: str, root_work: dict | None, depth: int) -> Expansion:
    ex = Expansion(root_id=root_id, root_title=root_title, refs_total=len(refs))
    root_rec = _slim(root_work) if root_work else {"id": root_id, "doi": None, "title": root_title, "year": None, "pub_date": None}
    root_rec["id"] = root_id
    ex.papers[root_id] = root_rec

    # Hop 1: resolve the manuscript's references.
    if root_work and root_work.get("referenced_works"):
        b_works = openalex.works_by_ids(root_work["referenced_works"])
    else:
        b_works = openalex.works_by_dois(r["doi"] for r in refs if r.get("doi"))
    by_doi = {norm_doi(w.get("doi")): w for w in b_works}
    if not root_work:
        ex.unresolved = [r for r in refs if not r.get("doi") or norm_doi(r["doi"]) not in by_doi]
    ex.refs_resolved = len(b_works)
    _log(f"hop 1: {len(b_works)} references resolved")
    notices = retractionwatch.load()
    for w in b_works:
        rec = _slim(w)
        ex.papers[rec["id"]] = rec
        ex.edges.add((root_id, rec["id"]))
        if w.get("is_retracted") or notices.get(rec["doi"], {}).get("nature") == "Retraction":
            ex.retracted[rec["id"]] = w

    # Hop 2: which of the references' references are retracted? (server-side intersection)
    b_ids = [short_id(w["id"]) for w in b_works]
    if depth >= 2 and b_ids:
        hop2 = openalex.retracted_cited_by(b_ids)
        hop2_ids = {short_id(w["id"]) for w in hop2}
        for w in hop2:
            rec = _slim(w)
            ex.papers[rec["id"]] = rec
            ex.retracted[rec["id"]] = w
        for w in b_works:
            for rid in w.get("referenced_works") or []:
                if short_id(rid) in hop2_ids:
                    ex.edges.add((short_id(w["id"]), short_id(rid)))
        _log(f"hop 2: {len(hop2)} retracted papers among the references' references")

    # Hop 3: references of references of references, retracted only.
    if depth >= 3 and b_works:
        r1_ids = sorted({short_id(r) for w in b_works for r in (w.get("referenced_works") or [])} - set(ex.retracted))
        _log(f"hop 3: scanning {len(r1_ids)} second-level papers ({(len(r1_ids) + 99) // 100} requests)")
        b_refs = {short_id(w["id"]): {short_id(r) for r in (w.get("referenced_works") or [])} for w in b_works}
        for i in range(0, len(r1_ids), 100):
            batch = r1_ids[i:i + 100]
            bad_works = openalex.retracted_cited_by(batch)
            if not bad_works:
                continue
            bad_ids = set()
            for bad in bad_works:
                bad_id = short_id(bad["id"])
                bad_ids.add(bad_id)
                ex.retracted[bad_id] = bad
                ex.papers[bad_id] = _slim(bad)
            # One more request for the whole batch: its reference lists tell us
            # exactly which papers cite which retracted work (≤ 2 requests / 100 papers).
            for c in openalex.works_by_ids(batch):
                hits = {short_id(r) for r in (c.get("referenced_works") or [])} & bad_ids
                if not hits:
                    continue
                cid = short_id(c["id"])
                ex.papers.setdefault(cid, _slim(c))
                for bad_id in hits:
                    ex.edges.add((cid, bad_id))
                for b_id, refs_of_b in b_refs.items():
                    if cid in refs_of_b:
                        ex.edges.add((b_id, cid))
        _log(f"hop 3: {len(ex.retracted)} retracted papers reachable in total")
    return ex


def retraction_rows(ex: Expansion) -> list[dict]:
    """Notice facts per paper flagged by OpenAlex or listed as retracted in Retraction Watch."""
    rows = []
    missing = 0
    for pid, w in ex.retracted.items():
        doi = norm_doi(w.get("doi"))
        n, source = retractionwatch.resolve(doi, bool(w.get("is_retracted")))
        missing += n is None
        rows.append({
            "id": pid,
            "nature": n["nature"] if n else None,
            "date": n["date"] if n else None,
            "reasons": n["reasons"] if n else [],
            "notice_id": (f"RW{n['record_id']}" if n.get("record_id") else f"CR:{n['notice_doi']}") if n and (n.get("record_id") or n.get("notice_doi")) else None,
            "notice_doi": n["notice_doi"] if n else None,
            "source": source or "openalex",
        })
    _log(f"notices: {sum(r['source'] == 'retraction_watch' for r in rows)} Retraction Watch, "
         f"{sum(r['source'] == 'crossref' for r in rows)} Crossref, {missing} OpenAlex flag only")
    return rows


def path_edges(conn, root: str, depth: int) -> list[tuple[str, str]]:
    """Edges that lie on some manuscript -> retracted path: the only ones worth reading."""
    q = store.bounded(
        "MATCH p = (m:Manuscript {id: $root})-[c0:CITES WHERE NOT coalesce(c0.anachronistic, false)]->(:Paper)"
        "-[c:CITES WHERE NOT coalesce(c.anachronistic, false)]->{0,%(extra)d}(bad:Retracted) "
        "UNWIND relationships(p) AS r RETURN DISTINCT startNode(r).id AS src, endNode(r).id AS dst", depth)
    return [(row["src"], row["dst"]) for row in conn.execute(q, {"root": root})]


def read_contexts(conn, ex: Expansion, edges: list[tuple[str, str]], skip_root: bool, s2_limit: int = 40) -> list[dict]:
    """Classify each on-path citation from its citing sentence(s).

    Europe PMC full text is read for every citing paper. Semantic Scholar is a fallback,
    capped at `s2_limit` calls and spent first on the citations nearest the manuscript.
    """
    near = {dst for src, dst in edges if src == ex.root_id}
    s2_calls = 0
    by_src: dict[str, list[str]] = {}
    for src, dst in edges:
        if skip_root and src == ex.root_id:
            continue
        by_src.setdefault(src, []).append(dst)
    def targets_of(dsts: list[str]) -> dict[str, tuple[str | None, str]]:
        return {d: (ex.papers.get(d, {}).get("doi"), ex.papers.get(d, {}).get("title") or "") for d in dsts}

    def read_fulltext(item):
        src, dsts = item
        doi = ex.papers.get(src, {}).get("doi")
        return src, (fulltext.contexts_for(doi, targets_of(dsts)) if doi else ("no_fulltext", {}))

    # Europe PMC tolerates parallel requests; Semantic Scholar (below) is called one at a time.
    with ThreadPoolExecutor(max_workers=8) as pool:
        fulltexts = dict(pool.map(read_fulltext, sorted(by_src.items())))
    _log(f"contexts: {sum(1 for s, _ in fulltexts.values() if s == 'fulltext')}/{len(by_src)} citing papers have open full text")

    # 1. Gather the citing sentences for every on-path citation (full text first, S2 as fallback).
    gathered: list[dict] = []
    ordered = sorted(by_src.items(), key=lambda kv: (kv[0] not in near, kv[0]))
    for src, dsts in ordered:
        doi = ex.papers.get(src, {}).get("doi")
        targets = targets_of(dsts)
        status, found = fulltexts[src]
        s2_refs = None
        for dst in dsts:
            ctxs = found.get(dst, [])
            evidence = "fulltext" if ctxs else ("metadata_only" if status == "fulltext" else "no_fulltext")
            s2_intents: list[str] = []
            if not ctxs and doi and (s2_refs is not None or s2_calls < s2_limit):
                if s2_refs is None:
                    s2_refs = s2.references(doi)
                    s2_calls += 1
                tdoi, ttitle = targets[dst]
                tkey = fulltext._norm_title(ttitle)
                match = next((r for r in s2_refs if (tdoi and r["doi"] == tdoi) or
                              (len(tkey) > 25 and fulltext._norm_title(r["title"]) == tkey)), None)
                if match and match["contexts"]:
                    evidence = "s2"
                    ctxs = [fulltext.Context("", "other", c) for c in match["contexts"]]
                    s2_intents = [i for i in match["intents"] if i in ("methodology", "result")]
            gathered.append({"src": src, "dst": dst, "ctxs": ctxs, "evidence": evidence, "s2_intents": s2_intents})

    # 2. What kind of work is each cited paper? A review is not primary evidence (intent v1).
    cited = sorted({g["dst"] for g in gathered if g["ctxs"]})
    types = cited_types(cited)
    for pid, t in types.items():
        ex.papers.setdefault(pid, {"id": pid})["work_type"] = t
    store.set_work_types(conn, types)

    # 3. Method probabilities from the fine-tuned model, if installed (one batch for all sentences).
    model = intent_model.load_default()
    flat = [c for g in gathered for c in g["ctxs"]]
    probs = iter(model.predict_proba([c.sentence for c in flat], [c.section for c in flat]) if model and flat else [])
    classifier = "v1+biomedbert-scicite" if model else "v1-rules"
    _log(f"intent: {classifier}; {len(flat)} sentences, {sum(1 for t in types.values() if t == 'review')}/{len(types)} cited works are reviews")

    out = []
    for g in gathered:
        labels = []
        for c in g["ctxs"]:
            p = next(probs)["method"] if model else None
            labels.append(intent.classify_v1(c.sentence, c.section_type, types.get(g["dst"]), p))
        labels += [(intent.S2_MAP[i], f"s2 intent: {i}") for i in g["s2_intents"]]
        label = intent.combine([lab for lab, _ in labels])
        rule = next((r for lab, r in labels if lab == label), "no citing sentence")
        ctxs = g["ctxs"]
        best = next((c for c, (lab, _) in zip(ctxs, labels) if lab == label), ctxs[0] if ctxs else None)
        out.append({
            "src": g["src"], "dst": g["dst"], "intent": label, "rule": rule,
            "section": best.section if best else None, "context": best.sentence if best else None,
            "evidence": g["evidence"], "n_contexts": len(ctxs), "classifier": classifier if ctxs else None,
        })
    return out


def cited_types(ids: list[str]) -> dict[str, str]:
    """OpenAlex work type ('article', 'review', …) for each id: ~1 request per 100 papers, cached."""
    if not ids:
        return {}
    return {short_id(w["id"]): w.get("type") for w in openalex.works_by_ids(ids, select="id,type")}


def build(conn, refs: list[dict], root_id: str, root_title: str, root_work: dict | None, depth: int,
          s2_limit: int = 40) -> Expansion:
    ex = expand(refs, root_id, root_title, root_work, depth)
    store.upsert_papers(conn, list(ex.papers.values()))
    store.mark_manuscript(conn, root_id)
    store.mark_retracted(conn, retraction_rows(ex))
    store.upsert_citations(conn, [{"src": s, "dst": d} for s, d in ex.edges])
    dates = store.flag_citation_dates(conn)
    if dates["anachronistic"] or dates["year_conflict"]:
        _log(f"dates: {dates['anachronistic']} impossible citations excluded, "
             f"{dates['year_conflict']} date conflicts with retracted papers kept as unverified")
    on_path = path_edges(conn, root_id, depth)
    _log(f"{len(on_path)} citations lie on a path to a retracted paper; reading their contexts")
    store.annotate_citations(conn, read_contexts(conn, ex, on_path, skip_root=root_work is None, s2_limit=s2_limit))
    store.index_paper_vectors(conn)
    return ex
