"""The Relate graph: schema, upserts, and the queries Load-Bearing is built on.

Model
  (:Paper {id, doi, title, year, pub_date})            OpenAlex work (id = 'W…')
  (:Paper:Manuscript)                                   the thing being checked
  (:Paper:Retracted {retraction_date, nature, reasons}) per Retraction Watch / OpenAlex
  (:Paper:Review {work_type: 'review'})                 OpenAlex work type (reviews aren't primary evidence)
  (:Paper)-[:CITES {intent, rule, section, context, evidence, zombie, classifier,
                    anachronistic, year_conflict}]->(:Paper)
      anachronistic  the cited (non-retracted) paper is dated 2+ years after the citing one: bad upstream
                     data, excluded from every path
      year_conflict  the same for a retracted cited paper; kept (OpenAlex sometimes dates a retracted paper
                     by its notice) but a path through it is never 'load_bearing', only 'unverified'
  (:Paper:Retracted)-[:RETRACTED_BY]->(:Notice {id, nature, date, reasons, notice_doi})
"""

from __future__ import annotations

import relate

SCHEMA = [
    "CREATE CONSTRAINT paper_id IF NOT EXISTS FOR (p:Paper) REQUIRE p.id IS UNIQUE",
    "CREATE CONSTRAINT notice_id IF NOT EXISTS FOR (n:Notice) REQUIRE n.id IS UNIQUE",
    "CREATE FULLTEXT INDEX paper_title IF NOT EXISTS FOR (p:Paper) ON EACH [p.title]",
]

LOAD_BEARING_INTENTS = ["method", "result"]

# Every path from the manuscript to a retracted paper, at most `depth` citations long,
# with a status computed from the intents on the edges *after* the first hop.
# (The first hop is the author's own citation; they decide what it means.)
EXPOSURE_QUERY = """
MATCH p = (m:Manuscript {id: $root})-[c0:CITES WHERE NOT coalesce(c0.anachronistic, false)]->(:Paper)
          -[c:CITES WHERE NOT coalesce(c.anachronistic, false)]->{0,%(extra)d}(bad:Retracted)
WITH p, bad, relationships(p) AS rels
WITH p, bad, rels, [r IN tail(rels) | coalesce(r.intent, 'unknown')] AS downstream
RETURN bad.id AS bad_id, bad.title AS bad_title, bad.year AS bad_year, bad.doi AS bad_doi,
       toString(bad.retraction_date) AS retraction_date, bad.nature AS nature, bad.reasons AS reasons,
       bad.notice_source AS notice_source, [(bad)-[:RETRACTED_BY]->(n:Notice) | n.notice_doi][0] AS notice_doi,
       length(p) AS hops,
       [n IN nodes(p) | {id: n.id, title: n.title, year: n.year, doi: n.doi}] AS chain,
       [r IN rels | {intent: coalesce(r.intent, 'unknown'), rule: r.rule, section: r.section,
                     context: r.context, evidence: r.evidence, zombie: coalesce(r.zombie, false),
                     year_conflict: coalesce(r.year_conflict, false)}] AS edges,
       CASE
         WHEN length(p) = 1 THEN 'direct'
         WHEN any(i IN downstream WHERE i = 'critical') THEN 'defused'
         WHEN any(r IN tail(rels) WHERE coalesce(r.year_conflict, false)) THEN 'unverified'
         WHEN all(i IN downstream WHERE i IN $load_bearing) THEN 'load_bearing'
         WHEN any(i IN downstream WHERE i = 'background') THEN 'mention_only'
         ELSE 'unverified'
       END AS status
ORDER BY hops, bad_id
"""

# The query from the pitch: only paths where every downstream citation is load-bearing.
LOAD_BEARING_ONLY = """
MATCH p = (m:Manuscript {id: $root})-[c0:CITES WHERE NOT coalesce(c0.anachronistic, false)]->(:Paper)
          (()-[c:CITES WHERE c.intent IN ['method', 'result']
                     AND NOT coalesce(c.anachronistic, false) AND NOT coalesce(c.year_conflict, false)]->()){0,2}
          (bad:Retracted)
RETURN bad.title AS retracted, [x IN nodes(p) | x.title] AS chain, length(p) AS hops
ORDER BY hops
"""


# Impossible citations that would otherwise have put a path on the report.
IGNORED_QUERY = """
MATCH p = (m:Manuscript {id: $root})-[:CITES]->(:Paper)-[:CITES]->{0,%(extra)d}(bad:Retracted)
UNWIND [r IN relationships(p) WHERE coalesce(r.anachronistic, false)] AS r
WITH DISTINCT startNode(r) AS a, endNode(r) AS b
RETURN a.title AS citing, a.year AS citing_year, b.title AS cited, b.year AS cited_year
"""


def open_store(path: str) -> relate.Connection:
    conn = relate.connect(path)
    for stmt in SCHEMA:
        conn.execute(stmt)
    return conn


def upsert_papers(conn, papers: list[dict]) -> None:
    """papers: [{id, doi, title, year, pub_date}] — missing keys are left untouched."""
    if not papers:
        return
    conn.execute(
        """
        UNWIND $rows AS r
        MERGE (p:Paper {id: r.id})
        SET p.doi = coalesce(r.doi, p.doi),
            p.title = coalesce(r.title, p.title),
            p.year = coalesce(r.year, p.year),
            p.pub_date = CASE WHEN r.pub_date IS NULL THEN p.pub_date ELSE date(r.pub_date) END
        """,
        {"rows": papers},
    )


def mark_manuscript(conn, paper_id: str) -> None:
    conn.execute("MATCH (p:Paper {id: $id}) SET p:Manuscript", {"id": paper_id})


def mark_retracted(conn, rows: list[dict]) -> None:
    """rows: [{id, nature, date, reasons, notice_id, notice_doi}]"""
    if not rows:
        return
    conn.execute(
        """
        UNWIND $rows AS r
        MATCH (p:Paper {id: r.id})
        SET p:Retracted,
            p.nature = r.nature,
            p.reasons = r.reasons,
            p.notice_source = r.source,
            p.retraction_date = CASE WHEN r.date IS NULL THEN null ELSE date(r.date) END
        WITH p, r WHERE r.notice_id IS NOT NULL
        MERGE (n:Notice {id: r.notice_id})
        SET n.nature = r.nature, n.reasons = r.reasons, n.notice_doi = r.notice_doi, n.source = r.source,
            n.date = CASE WHEN r.date IS NULL THEN null ELSE date(r.date) END
        MERGE (p)-[:RETRACTED_BY]->(n)
        """,
        {"rows": rows},
    )


def upsert_citations(conn, edges: list[dict]) -> None:
    """edges: [{src, dst}] — creates the CITES relationship if missing."""
    if not edges:
        return
    conn.execute(
        """
        UNWIND $rows AS r
        MATCH (a:Paper {id: r.src}), (b:Paper {id: r.dst})
        MERGE (a)-[:CITES]->(b)
        """,
        {"rows": edges},
    )


def annotate_citations(conn, edges: list[dict]) -> None:
    """edges: [{src, dst, intent, rule, section, context, evidence, n_contexts}]"""
    if not edges:
        return
    conn.execute(
        """
        UNWIND $rows AS r
        MATCH (a:Paper {id: r.src})-[c:CITES]->(b:Paper {id: r.dst})
        SET c.intent = r.intent, c.rule = r.rule, c.section = r.section, c.context = r.context,
            c.evidence = r.evidence, c.n_contexts = r.n_contexts, c.classifier = r.classifier,
            c.zombie = (b.retraction_date IS NOT NULL AND a.pub_date IS NOT NULL AND a.pub_date > b.retraction_date)
        """,
        {"rows": edges},
    )


def flag_citation_dates(conn) -> dict:
    """Mark citations whose cited paper is dated more than a year after the citing paper.

    One year of slack covers 'in press' references. Returns counts for the report.
    """
    conn.execute(
        """
        MATCH (a:Paper)-[c:CITES]->(b:Paper)
        WHERE a.year IS NOT NULL AND b.year IS NOT NULL
        SET c.anachronistic = (b.year > a.year + 1 AND NOT b:Retracted),
            c.year_conflict = (b.year > a.year + 1 AND b:Retracted)
        """
    )
    row = conn.execute(
        "MATCH ()-[c:CITES]->() RETURN sum(CASE WHEN c.anachronistic THEN 1 ELSE 0 END) AS anachronistic, "
        "sum(CASE WHEN c.year_conflict THEN 1 ELSE 0 END) AS year_conflict"
    ).single()
    return dict(row)


def ignored_citations(conn, root: str, depth: int = 3) -> list[dict]:
    """Impossible citations that would otherwise have put a path on the report (for transparency)."""
    q = IGNORED_QUERY % {"extra": max(depth - 1, 0)}
    return [dict(r) for r in conn.execute(q, {"root": root})]


def set_work_types(conn, types: dict[str, str]) -> None:
    """Record OpenAlex work types; reviews also get the :Review label for easy querying."""
    if not types:
        return
    rows = [{"id": k, "t": v} for k, v in types.items() if v]
    conn.execute("UNWIND $rows AS r MATCH (p:Paper {id: r.id}) SET p.work_type = r.t", {"rows": rows})
    conn.execute("UNWIND $ids AS id MATCH (p:Paper {id: id}) SET p:Review",
                 {"ids": [r["id"] for r in rows if r["t"] == "review"]})


def exposure(conn, root: str, depth: int = 3) -> list[dict]:
    q = EXPOSURE_QUERY % {"extra": max(depth - 1, 0)}
    return list(conn.execute(q, {"root": root, "load_bearing": LOAD_BEARING_INTENTS}))


def stats(conn) -> dict:
    row = conn.execute(
        "MATCH (p:Paper) WITH count(p) AS papers "
        "OPTIONAL MATCH ()-[c:CITES]->() WITH papers, count(c) AS cites "
        "OPTIONAL MATCH (r:Retracted) RETURN papers, cites, count(r) AS retracted"
    ).single()
    return dict(row)
