"""Claim audit over dated notices and source-located outcome evidence."""

from __future__ import annotations

from datetime import date
import re
from pathlib import Path

import relate

from .openalex import norm_doi
from .store import atomic

ROOT = Path(__file__).resolve().parents[2]
DEMO_STORE = Path("data/claims.rl") if Path("data/claims.rl").is_file() else ROOT / "data/claims.rl"
DEMO_CLAIMS = Path("data/comparison/demo_claims.json")
if not DEMO_CLAIMS.is_file():
    DEMO_CLAIMS = ROOT / DEMO_CLAIMS
MODES = ("direct", "untyped", "claim_aware")
ACTIONS = {
    "review_direct": "Review the direct citation",
    "review_indirect": "Reassess the cited outcome",
    "review_notice": "Review the publication notice",
    "retain_with_notice": "Retain with the notice",
    "retain_for_this_notice": "Outside the scope of this notice",
    "no_notice_as_of": "No applicable notice in the snapshot at this date",
    "insufficient_evidence": "Insufficient evidence",
}


def build_snapshot(path: Path, facts: dict) -> None:
    """Build a dedicated Relate store from notice and publication facts, independent of case labels."""
    if path.exists():
        raise FileExistsError(path)
    write_snapshot(path, facts)


def write_snapshot(path: Path, facts: dict) -> None:
    """Create or extend a versioned claim graph in a single transaction."""
    pubs, notices = facts["publications"], facts["notices"]
    citations = [{"source": p["doi"], "target": doi} for p in pubs for doi in p["citations"]]
    outcomes = [{"doi": p["doi"], **{k: v for k, v in o.items() if k not in ("uses", "outside_scope")}}
                for p in pubs for o in p["outcomes"]]
    uses = [{"review_doi": p["doi"], "id": o["id"], "doi": doi, "role": role,
             **o.get("study_evidence", {}).get(doi, {})} for p in pubs for o in p["outcomes"]
            for role in ("uses", "outside_scope") for doi in o[role]]
    for outcome in outcomes:
        outcome.pop("study_evidence", None)
    dois = sorted({p["doi"] for p in pubs} | {n["doi"] for n in notices} | {c["target"] for c in citations})
    conn = relate.connect(str(path))
    try:
        with atomic(conn):
            previous = list(conn.execute("MATCH (s:ClaimSnapshot) RETURN s.as_of AS date"))
            if not previous:
                if conn.execute("MATCH (n) RETURN count(n) AS nodes").single()["nodes"]:
                    raise ValueError("This store contains a different graph. Use a new claim store.")
                conn.execute("CREATE (:ClaimSnapshot {as_of: $as_of})", {"as_of": facts["as_of"]})
            elif len(previous) != 1 or previous[0]["date"] != facts["as_of"]:
                raise ValueError("Append requires the same cutoff as the existing snapshot. Build a new store for a new cutoff.")
            conn.execute("UNWIND $dois AS doi MERGE (:ClaimWork {doi: doi})", {"dois": dois})
            conn.execute("""UNWIND $rows AS r MATCH (a:ClaimWork {doi: r.source}), (b:ClaimWork {doi: r.target})
                          MERGE (a)-[:CITES]->(b)""", {"rows": citations})
            conn.execute("""UNWIND $rows AS r MATCH (w:ClaimWork {doi: r.doi})
                          MERGE (w)-[:REPORTS]->(o:Outcome {id: r.id})
                          SET o.doi = r.doi, o.label = coalesce(r.label, o.label),
                              o.terms = coalesce(r.terms, o.terms), o.locator = coalesce(r.locator, o.locator),
                              o.url = coalesce(r.url, o.url), o.finding = coalesce(r.finding, o.finding),
                              o.basis = coalesce(r.basis, o.basis)""", {"rows": outcomes})
            conn.execute("""UNWIND $rows AS r
                          MATCH (:ClaimWork {doi: r.review_doi})-[:REPORTS]->(o:Outcome {id: r.id}),
                                (w:ClaimWork {doi: r.doi})
                          MERGE (o)-[u:STUDY_USE]->(w)
                          SET u.role = r.role, u.locator = coalesce(r.locator, u.locator),
                              u.url = coalesce(r.url, u.url), u.finding = coalesce(r.finding, u.finding),
                              u.reviewed_by = coalesce(r.reviewed_by, u.reviewed_by)""", {"rows": uses})
            conn.execute("""UNWIND $rows AS r MATCH (w:ClaimWork {doi: r.doi})
                          MERGE (w)-[:HAS_NOTICE]->(n:PublicationNotice {kind: r.kind, date: r.date, url: r.url})
                          SET n.doi = r.doi""", {"rows": notices})
    finally:
        conn.close()


def _normalized(text: str) -> str:
    return " " + " ".join(re.findall(r"\w+", text.casefold())) + " "


def _outcome_for(text: str, outcomes: list[dict], ref: str, upstream: str,
                 outcome_ids: list[str] | None) -> dict | None:
    matches = [o for o in outcomes if o["ref"] == ref and o["doi"] == upstream
               and (o["id"] in outcome_ids if outcome_ids is not None else
                    o["terms"] and all(_normalized(term) in text for term in o["terms"]))]
    return matches[0] if len(matches) == 1 else None


def _notices(conn, refs: list[str], as_of: str, indirect: bool) -> list[dict]:
    target = "(ref:ClaimWork)-[:CITES]->(w:ClaimWork)" if indirect else "(ref:ClaimWork)"
    work = "w" if indirect else "ref"
    rows = conn.execute(f"""MATCH {target}-[:HAS_NOTICE]->(n:PublicationNotice)
                WHERE ref.doi IN $refs AND n.date <= $as_of
                RETURN ref.doi AS ref, {work}.doi AS doi, n.kind AS kind, n.date AS date, n.url AS url
                ORDER BY n.date DESC, ref.doi, {work}.doi""", {"refs": refs, "as_of": as_of})
    by_pair = {}
    for row in rows:
        by_pair.setdefault((row["ref"], row["doi"]), []).append(dict(row))
    selected = []
    for candidates in by_pair.values():
        lifecycle = max((n for n in candidates if n["kind"] in {"retraction", "reinstatement"}),
                        key=lambda n: (n["date"], n["kind"] == "retraction"), default=None)
        current = lifecycle or candidates[0]
        if current["kind"] == "reinstatement":
            if candidates[0]["date"] <= current["date"]:
                continue
            current = candidates[0]
        selected.append(current)
    return selected


_HISTORICAL_USE = re.compile(
    r"(?:document|discuss|describe)\s+that\s+the cited(?: [\w-]+){0,5} "
    r"(?:paper|study|article) was retracted(?: as an example of a publication-status change)?[.!]?",
    re.I,
)
_PRIORITY = ("review_direct", "review_indirect", "review_notice", "insufficient_evidence",
             "retain_with_notice", "retain_for_this_notice", "no_notice_as_of")


def audit(conn, *, claim: str, reference_dois: list[str], as_of: str, mode: str = "claim_aware",
          fixture_condition: str | None = None, outcome_ids: list[str] | None = None) -> dict:
    """Evaluate a claim against dated notices and explicitly recorded source outcomes."""
    if mode not in MODES:
        raise ValueError(f"unknown audit mode: {mode}")
    if fixture_condition not in {None, "withhold_outcome_evidence"}:
        raise ValueError(f"unknown evidence condition: {fixture_condition}")
    as_of = date.fromisoformat(as_of).isoformat()
    metadata = list(conn.execute("MATCH (s:ClaimSnapshot) RETURN s.as_of AS date"))
    if len(metadata) != 1:
        raise ValueError("Expected a versioned claim evidence store.")
    snapshot_date = metadata[0]["date"]
    if as_of > snapshot_date:
        raise ValueError(f"audit date {as_of} is later than snapshot {snapshot_date}")

    refs = list(dict.fromkeys(norm_doi(ref) for ref in reference_dois))
    resolved = {r["doi"] for r in conn.execute("MATCH (w:ClaimWork) WHERE w.doi IN $refs RETURN w.doi AS doi",
                                             {"refs": [ref for ref in refs if ref]})}
    direct = _notices(conn, sorted(resolved), as_of, indirect=False)
    indirect = _notices(conn, sorted(resolved), as_of, indirect=True) if mode != "direct" else []
    outcomes = []
    if indirect and mode == "claim_aware" and fixture_condition != "withhold_outcome_evidence":
        outcomes = [dict(r) for r in conn.execute("""MATCH (ref:ClaimWork)-[:REPORTS]->(o:Outcome)
                     -[u:STUDY_USE]->(w:ClaimWork) WHERE ref.doi IN $refs
                     RETURN ref.doi AS ref, w.doi AS doi, u.role AS role, o.id AS id, o.terms AS terms,
                            o.label AS label, coalesce(u.locator, o.locator) AS locator,
                            coalesce(u.url, o.url) AS url, coalesce(u.finding, o.finding) AS finding,
                            o.basis AS basis, u.reviewed_by AS reviewed_by""",
                                                              {"refs": sorted(resolved)})]

    findings = []
    historical = len(refs) == 1 and _HISTORICAL_USE.fullmatch(claim.strip())
    for n in direct:
        action = "review_notice"
        if n["kind"] == "retraction":
            action = "retain_with_notice" if mode == "claim_aware" and historical else "review_direct"
        findings.append({"action": action, "path": [n["ref"]], "notice": n})
    text = _normalized(claim)
    for n in indirect:
        item = {"path": [n["ref"], n["doi"]], "notice": n}
        if mode == "untyped":
            item["action"] = "review_indirect" if n["kind"] == "retraction" else "review_notice"
        else:
            match = _outcome_for(text, outcomes, n["ref"], n["doi"], outcome_ids)
            if match:
                item["evidence"] = {k: match[k] for k in ("id", "role", "locator", "url", "finding", "basis",
                                                        "label", "reviewed_by") if match[k] is not None}
                item["action"] = "retain_for_this_notice" if match["role"] == "outside_scope" else (
                    "review_indirect" if n["kind"] == "retraction" else "review_notice")
            else:
                item["action"] = "insufficient_evidence"
        findings.append(item)

    unresolved = [ref for ref in refs if ref not in resolved]
    actions = {f["action"] for f in findings}
    if unresolved or not resolved:
        actions.add("insufficient_evidence")
    return {
        "action": next((a for a in _PRIORITY if a in actions), "no_notice_as_of"),
        "findings": findings, "as_of": as_of, "snapshot_date": snapshot_date,
        "resolved_references": sorted(resolved), "unresolved_references": unresolved,
    }


def audit_claims(snapshot: Path, claims: list[dict], mode: str = "claim_aware") -> list[dict]:
    """Audit a batch using a single read-only connection."""
    if not isinstance(claims, list) or not claims:
        raise ValueError("Pass a nonempty JSON array of claim objects.")
    seen = set()
    conn = relate.connect(str(snapshot), read_only=True)
    try:
        rows = []
        for item in claims:
            if not isinstance(item, dict):
                raise ValueError("Each claim must be an object.")
            claim_id = item.get("id")
            if not isinstance(claim_id, str) or not claim_id.strip() or claim_id in seen:
                raise ValueError("Each claim needs a unique, nonempty string id.")
            seen.add(claim_id)
            refs, outcomes = item.get("reference_dois"), item.get("outcome_ids")
            if not isinstance(refs, list) or not all(isinstance(doi, str) and norm_doi(doi) for doi in refs):
                raise ValueError(f"{claim_id}: reference_dois must be an array of DOI strings.")
            if outcomes is not None and (not isinstance(outcomes, list) or
                                         not all(isinstance(value, str) and value.strip() for value in outcomes)):
                raise ValueError(f"{claim_id}: outcome_ids must be an array of strings.")
            claim, as_of = item.get("claim"), item.get("as_of")
            if not isinstance(claim, str) or not claim.strip() or not isinstance(as_of, str):
                raise ValueError(f"{claim_id}: provide claim text and an ISO as_of date.")
            if outcomes and len({norm_doi(doi) for doi in refs}) != 1:
                raise ValueError(f"{claim_id}: confirmed outcome IDs require exactly one cited review DOI.")
            rows.append({"id": claim_id, "claim": claim,
                         **audit(conn, claim=claim, reference_dois=refs, as_of=as_of, mode=mode,
                                 fixture_condition=item.get("fixture_condition"), outcome_ids=outcomes)})
        return rows
    finally:
        conn.close()


def serve(snapshot: Path) -> None:
    """Expose the pilot's read-only claim audit through real MCP stdio."""
    from mcp.server.mcpserver import MCPServer
    from mcp.types import ToolAnnotations

    server = MCPServer(name="claim-pilot", title="Load Bearing claim audit pilot")

    @server.tool(name="audit_claims", annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
    def audit_batch(claims: list[dict]) -> list[dict]:
        """Audit up to 25 claim objects with id, claim, reference_dois, as_of and optional outcome_ids."""
        if not 1 <= len(claims) <= 25:
            raise ValueError("Pass 1 to 25 claims.")
        return audit_claims(snapshot, claims)

    server.run("stdio")
