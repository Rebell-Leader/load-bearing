"""Claim audit over the source-located, hand-curated pilot evidence pack."""

from __future__ import annotations

from datetime import date
import re
from pathlib import Path

import relate

from .openalex import norm_doi


def build_snapshot(path: Path, facts: dict) -> None:
    """Build a dedicated Relate store from notice and publication facts, independent of case labels."""
    if path.exists():
        raise FileExistsError(path)
    pubs, notices = facts["publications"], facts["notices"]
    citations = [{"source": p["doi"], "target": doi} for p in pubs for doi in p["citations"]]
    outcomes = [{"doi": p["doi"], **{k: v for k, v in o.items() if k not in ("uses", "outside_scope")}}
                for p in pubs for o in p["outcomes"]]
    uses = [{"id": o["id"], "doi": doi, "role": role} for p in pubs for o in p["outcomes"]
            for role in ("uses", "outside_scope") for doi in o[role]]
    dois = sorted({p["doi"] for p in pubs} | {n["doi"] for n in notices} | {c["target"] for c in citations})
    conn = relate.connect(str(path))
    try:
        conn.execute("UNWIND $dois AS doi CREATE (:ClaimWork {doi: doi})", {"dois": dois})
        conn.execute("CREATE (:ClaimSnapshot {as_of: $as_of})", {"as_of": facts["as_of"]})
        conn.execute("""UNWIND $rows AS r MATCH (a:ClaimWork {doi: r.source}), (b:ClaimWork {doi: r.target})
                      CREATE (a)-[:CITES]->(b)""", {"rows": citations})
        conn.execute("""UNWIND $rows AS r MATCH (w:ClaimWork {doi: r.doi})
                      CREATE (o:Outcome) SET o = r CREATE (w)-[:REPORTS]->(o)""", {"rows": outcomes})
        conn.execute("""UNWIND $rows AS r MATCH (o:Outcome {id: r.id}), (w:ClaimWork {doi: r.doi})
                      CREATE (o)-[:STUDY_USE {role: r.role}]->(w)""", {"rows": uses})
        conn.execute("""UNWIND $rows AS r MATCH (w:ClaimWork {doi: r.doi})
                      CREATE (n:PublicationNotice) SET n = r CREATE (w)-[:HAS_NOTICE]->(n)""",
                     {"rows": notices})
    finally:
        conn.close()


def _normalized(text: str) -> str:
    return " " + " ".join(re.findall(r"\w+", text.casefold())) + " "


def _outcome_for(text: str, outcomes: list[dict], ref: str, upstream: str) -> dict | None:
    matches = [o for o in outcomes if o["ref"] == ref and o["doi"] == upstream
               and all(_normalized(term) in text for term in o["terms"])]
    return matches[0] if len(matches) == 1 else None


def _notices(conn, refs: list[str], as_of: str, indirect: bool) -> list[dict]:
    target = "(ref:ClaimWork)-[:CITES]->(w:ClaimWork)" if indirect else "(ref:ClaimWork)"
    work = "w" if indirect else "ref"
    rows = conn.execute(f"""MATCH {target}-[:HAS_NOTICE]->(n:PublicationNotice)
                WHERE ref.doi IN $refs AND n.date <= $as_of
                RETURN ref.doi AS ref, {work}.doi AS doi, n.kind AS kind, n.date AS date, n.url AS url
                ORDER BY n.date DESC, ref.doi, {work}.doi""", {"refs": refs, "as_of": as_of})
    latest = {}
    for row in rows:
        latest.setdefault((row["ref"], row["doi"]), dict(row))
    return list(latest.values())


_HISTORICAL_USE = re.compile(r"\b(?:document|discuss|describe)\b.*\b(?:retraction|retracted)\b", re.I)
_RELIANCE_USE = re.compile(r"\b(?:use|rely|support|evidence)\b", re.I)
_PRIORITY = ("review_direct", "review_indirect", "review_notice", "insufficient_evidence",
             "retain_with_notice", "retain_for_this_notice", "no_notice_as_of")


def audit(conn, *, claim: str, reference_dois: list[str], as_of: str, mode: str = "claim_aware",
          fixture_condition: str | None = None) -> dict:
    """Evaluate a claim against dated notices and explicitly recorded source outcomes."""
    if mode not in {"direct", "untyped", "claim_aware"}:
        raise ValueError(f"unknown audit mode: {mode}")
    if fixture_condition not in {None, "withhold_outcome_evidence"}:
        raise ValueError(f"unknown evidence condition: {fixture_condition}")
    as_of = date.fromisoformat(as_of).isoformat()
    snapshot_date = conn.execute("MATCH (s:ClaimSnapshot) RETURN s.as_of AS date").single()["date"]
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
                            o.locator AS locator, o.url AS url, o.finding AS finding, o.basis AS basis""",
                                                              {"refs": sorted(resolved)})]

    findings = []
    historical = _HISTORICAL_USE.search(claim) and not _RELIANCE_USE.search(claim)
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
            match = _outcome_for(text, outcomes, n["ref"], n["doi"])
            if match:
                item["evidence"] = {k: match[k] for k in ("id", "role", "locator", "url", "finding", "basis")}
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


def serve(snapshot: Path) -> None:
    """Expose the pilot's read-only claim audit through real MCP stdio."""
    from mcp.server.mcpserver import MCPServer
    from mcp.types import ToolAnnotations

    server = MCPServer(name="claim-pilot", title="Load Bearing claim audit pilot")

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
    def audit_claims(claims: list[dict]) -> list[dict]:
        """Audit up to 25 public claim objects with id, claim, reference_dois, as_of and optional fixture_condition."""
        if not 1 <= len(claims) <= 25:
            raise ValueError("Pass 1 to 25 claims.")
        conn = relate.connect(str(snapshot), read_only=True)
        try:
            return [{"id": c["id"], **audit(conn, claim=c["claim"], reference_dois=c["reference_dois"],
                                          as_of=c["as_of"], fixture_condition=c.get("fixture_condition"))}
                    for c in claims]
        finally:
            conn.close()

    server.run("stdio")
