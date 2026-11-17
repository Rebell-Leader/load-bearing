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
  (:Manuscript)-[:HAS_CLAIM]->(:Claim {id, text})-[:HAS_DISPOSITION]->(:Disposition {id, action, rationale, revision})
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import math
import re

import relate

SCHEMA = [
    "CREATE CONSTRAINT paper_id IF NOT EXISTS FOR (p:Paper) REQUIRE p.id IS UNIQUE",
    "CREATE CONSTRAINT notice_id IF NOT EXISTS FOR (n:Notice) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT claim_id IF NOT EXISTS FOR (c:Claim) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT disposition_id IF NOT EXISTS FOR (d:Disposition) REQUIRE d.id IS UNIQUE",
    "CREATE INDEX manuscript_id IF NOT EXISTS FOR (m:Manuscript) ON (m.id)",
    "CREATE INDEX paper_doi IF NOT EXISTS FOR (p:Paper) ON (p.doi)",
    "CREATE FULLTEXT INDEX paper_title IF NOT EXISTS FOR (p:Paper) ON EACH [p.title]",
]

VECTOR_DIM = 32
VECTOR_SCHEMA = (
    f"CREATE VECTOR INDEX paper_vec IF NOT EXISTS FOR (p:Paper) ON (p.vec) "
    f"OPTIONS {{indexConfig: {{`vector.dimensions`: {VECTOR_DIM}, `vector.similarity_function`: 'cosine'}}}}"
)

LOAD_BEARING_INTENTS = ["method", "result"]

# Every path from the manuscript to a retracted paper, at most `depth` citations long,
# with a status computed from the intents on the edges *after* the first hop
# (unless the manuscript's own citation is critical, which defuses the path immediately).
EXPOSURE_QUERY = """
MATCH p = (m:Manuscript {id: $root})-[c0:CITES WHERE NOT coalesce(c0.anachronistic, false)]->(:Paper)
          -[c:CITES WHERE NOT coalesce(c.anachronistic, false)]->{0,%(extra)d}(bad:Retracted)
WITH p, bad, relationships(p) AS rels
WITH p, bad, rels, [r IN tail(rels) | coalesce(r.intent, 'unknown')] AS downstream
WITH p, bad, rels, downstream,
     [(bad)-[:RETRACTED_BY]->(n:Notice)
      WHERE n.id = bad.active_notice_id OR
            (bad.active_notice_id IS NULL AND n.nature = bad.nature AND n.source = bad.notice_source
             AND (n.date = bad.retraction_date OR (n.date IS NULL AND bad.retraction_date IS NULL)))
      | n] AS notices
WITH p, bad, rels, downstream, CASE WHEN size(notices) = 1 THEN notices[0] ELSE null END AS notice
RETURN bad.id AS bad_id, bad.title AS bad_title, bad.year AS bad_year, bad.doi AS bad_doi,
       toString(CASE WHEN notice IS NULL THEN bad.retraction_date ELSE notice.date END) AS retraction_date,
       CASE WHEN notice IS NULL THEN bad.nature ELSE notice.nature END AS nature,
       CASE WHEN notice IS NULL THEN bad.reasons ELSE notice.reasons END AS reasons,
       CASE WHEN notice IS NULL THEN bad.notice_source ELSE notice.source END AS notice_source,
       notice.notice_doi AS notice_doi,
       length(p) AS hops,
       [n IN nodes(p) | {id: n.id, title: n.title, year: n.year, doi: n.doi}] AS chain,
       [r IN rels | {intent: coalesce(r.intent, 'unknown'), rule: r.rule, section: r.section,
                     context: r.context, evidence: r.evidence,
                     zombie: coalesce(r.zombie AND endNode(r).nature = 'Retraction'
                                      AND endNode(r).notice_source IN ['retraction_watch', 'crossref'], false),
                     year_conflict: coalesce(r.year_conflict, false)}] AS edges,
       CASE
         WHEN any(r IN rels WHERE r.intent = 'critical') THEN 'defused'
         WHEN length(p) = 1 THEN 'direct'
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


@contextmanager
def atomic(conn):
    """Commit related graph changes together, joining a caller-owned transaction if needed."""
    if not conn.autocommit:
        yield
        return
    conn.autocommit = False
    try:
        yield
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.autocommit = True


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
    with atomic(conn):
        conn.execute(
            """
            UNWIND $rows AS r
            MATCH (p:Paper {id: r.id})
            WITH p, r WHERE coalesce(r.source, '') <> 'openalex'
                            OR NOT coalesce(p.notice_source IN ['retraction_watch', 'crossref'], false)
            SET p.nature = r.nature,
                p.reasons = r.reasons,
                p.notice_source = r.source,
                p.active_notice_id = r.notice_id,
                p.retraction_date = CASE WHEN r.date IS NULL THEN null ELSE date(r.date) END
            WITH p, r WHERE r.notice_id IS NOT NULL
            MERGE (n:Notice {id: r.notice_id})
            SET n.nature = r.nature, n.reasons = r.reasons, n.notice_doi = r.notice_doi, n.source = r.source,
                n.date = CASE WHEN r.date IS NULL THEN null ELSE date(r.date) END
            MERGE (p)-[:RETRACTED_BY]->(n)
            """,
            {"rows": rows},
        )
        conn.execute(
            """
            UNWIND $rows AS r MATCH (p:Paper {id: r.id})
            WHERE p.nature IS NULL OR p.nature <> 'Reinstatement'
            SET p:Retracted
            """,
            {"rows": rows},
        )
        conn.execute(
            """
            UNWIND $rows AS r MATCH (p:Paper {id: r.id})
            WHERE p.nature = 'Reinstatement'
            REMOVE p:Retracted
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


def replace_draft_citations(conn, draft: str, edges: list[dict]) -> None:
    """Replace the draft's own references while preserving the shared literature graph."""
    with atomic(conn):
        conn.execute("MATCH (:Manuscript {id: $id})-[c:CITES]->() DELETE c", {"id": draft})
        upsert_citations(conn, edges)


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
            c.zombie = coalesce(b.nature = 'Retraction' AND b.notice_source IN ['retraction_watch', 'crossref']
                                AND a.pub_date > b.retraction_date, false)
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
    q = bounded(IGNORED_QUERY, depth)
    return [dict(r) for r in conn.execute(q, {"root": root})]


def set_work_types(conn, types: dict[str, str]) -> None:
    """Record OpenAlex work types; reviews also get the :Review label for easy querying."""
    if not types:
        return
    rows = [{"id": k, "t": v} for k, v in types.items() if v]
    conn.execute("UNWIND $rows AS r MATCH (p:Paper {id: r.id}) SET p.work_type = r.t", {"rows": rows})
    conn.execute("UNWIND $ids AS id MATCH (p:Paper {id: id}) SET p:Review",
                 {"ids": [r["id"] for r in rows if r["t"] == "review"]})


# The hops after the first, as written in the query templates, when there are none of them.
_NO_DOWNSTREAM = re.compile(r"\(:Paper\)\s*-\[c?:CITES[^\]]*\]->\{0,0\}")


def bounded(template: str, depth: int) -> str:
    """A path query template limited to `depth` citations.

    Relate rejects a {0,0} quantifier, so at depth 1 the downstream segment is dropped and the
    manuscript's own reference must be the retracted paper: a direct citation.
    """
    q = template % {"extra": max(depth - 1, 0)}
    if depth <= 1:
        q, n = _NO_DOWNSTREAM.subn("", q)
        assert n == 1, "path query template no longer matches the depth-1 rewrite"
    return q


def exposure(conn, root: str, depth: int = 3) -> list[dict]:
    q = bounded(EXPOSURE_QUERY, depth)
    return list(conn.execute(q, {"root": root, "load_bearing": LOAD_BEARING_INTENTS}))


def find_manuscript(conn, *, doi: str | None = None, root_id: str | None = None) -> dict | None:
    """A checked manuscript by DOI or id, or None. Lets offline checks run without any network."""
    if doi:
        rows = list(conn.execute("MATCH (m:Manuscript {doi: $doi}) RETURN m.id AS id, m.title AS title", {"doi": doi}))
    else:
        rows = list(conn.execute("MATCH (m:Manuscript {id: $id}) RETURN m.id AS id, m.title AS title", {"id": root_id}))
    return dict(rows[0]) if rows else None


def stats(conn) -> dict:
    row = conn.execute(
        "MATCH (p:Paper) WITH count(p) AS papers "
        "OPTIONAL MATCH ()-[c:CITES]->() WITH papers, count(c) AS cites "
        "OPTIONAL MATCH (r:Retracted) RETURN papers, cites, count(r) AS retracted"
    ).single()
    return dict(row)


def search_papers(conn, query: str, limit: int = 10) -> list[dict]:
    """Search papers by title using Relate's native FULLTEXT INDEX."""
    if not query or not query.strip():
        return []
    rows = conn.execute(
        """
        MATCH (p:Paper)
        SEARCH p IN (FULLTEXT INDEX paper_title FOR $q LIMIT $limit) SCORE AS score
        RETURN p.id AS id, p.doi AS doi, p.title AS title, p.year AS year,
               p:Retracted AS retracted, score
        ORDER BY score DESC
        """,
        {"q": query.strip(), "limit": limit},
    )
    return [dict(r) for r in rows]


def embed_text(text: str, dim: int = VECTOR_DIM) -> list[float]:
    """Deterministic L2-normalized token + character trigram feature-hashing vector."""
    vec = [0.0] * dim
    tokens = [w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) > 2]
    features = list(tokens)
    for tok in tokens:
        for i in range(max(0, len(tok) - 2)):
            features.append(tok[i:i + 3])
    for feat in features:
        h = int.from_bytes(hashlib.blake2b(feat.encode("utf-8"), digest_size=4).digest(), "little")
        idx = h % dim
        sign = 1.0 if (h & (1 << 31)) else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(x * x for x in vec))
    return [round(x / norm, 6) for x in vec] if norm > 0 else [1.0 / math.sqrt(dim)] * dim


def index_paper_vectors(conn, dim: int = VECTOR_DIM) -> int:
    """Populate semantic hash vectors on :Paper nodes and create Relate's VECTOR INDEX."""
    papers = [dict(r) for r in conn.execute("MATCH (p:Paper) WHERE p.title IS NOT NULL RETURN p.id AS id, p.title AS title")]
    if papers:
        rows = [{"id": p["id"], "vec": embed_text(p["title"], dim)} for p in papers]
        conn.execute("UNWIND $rows AS r MATCH (p:Paper {id: r.id}) SET p.vec = r.vec", {"rows": rows})
    conn.execute(VECTOR_SCHEMA)
    return len(papers)


def vector_search_papers(conn, query_text: str, limit: int = 5) -> list[dict]:
    """Semantic similarity search over :Paper nodes via Relate's VECTOR INDEX."""
    vec = embed_text(query_text)
    rows = conn.execute(
        """
        MATCH (p:Paper)
        SEARCH p IN (VECTOR INDEX paper_vec FOR $v LIMIT $limit) SCORE AS score
        RETURN p.id AS id, p.doi AS doi, p.title AS title, p.year AS year,
               p:Retracted AS retracted, score
        ORDER BY score DESC
        """,
        {"v": vec, "limit": limit},
    )
    return [dict(r) for r in rows]


def record_dispositions(conn, manuscript_id: str, items: list[dict]) -> int:
    """Persist claim-level audit decisions into the Relate graph.

    items: [{claim_id, claim, action, rationale, revision, reference_dois}]
    """
    if not items:
        return 0
    rows = []
    for i, item in enumerate(items, 1):
        cid = str(item.get("claim_id") or item.get("id") or f"claim:{i}").removeprefix(f"{manuscript_id}:")
        display_id = f"{manuscript_id}:{cid}"
        key = json.dumps([manuscript_id, cid], separators=(",", ":"))
        rows.append({
            "manuscript_id": manuscript_id,
            "claim_id": f"claim:{key}",
            "display_id": display_id,
            "disp_id": f"disposition:{key}",
            "legacy_dispositions": [f"{manuscript_id}:disp:{value}" for value in (cid, display_id)],
            "claim": item.get("claim") or "",
            "action": item.get("action") or "review",
            "rationale": item.get("rationale") or "",
            "revision": item.get("revision") or "",
            "dois": [d.strip().lower().removeprefix("https://doi.org/") for d in (item.get("reference_dois") or []) if d],
        })
    # When upgrading a previously saved claim, unlink that manuscript's legacy node.
    # Another manuscript may still reference it if the old keys collided.
    rows = list({row["claim_id"]: row for row in rows}.values())
    with atomic(conn):
        conn.execute(
            """
            UNWIND $rows AS r
            MATCH (:Manuscript {id: r.manuscript_id})-[link:HAS_CLAIM]->(:Claim)-[:HAS_DISPOSITION]->(d:Disposition)
            WHERE d.id IN r.legacy_dispositions
            DELETE link
            """,
            {"rows": rows},
        )
        conn.execute(
            """
            UNWIND $rows AS r
            MERGE (m:Paper:Manuscript {id: r.manuscript_id})
            MERGE (c:Claim {id: r.claim_id})
            SET c.text = r.claim, c.manuscript_id = r.manuscript_id, c.display_id = r.display_id
            MERGE (m)-[:HAS_CLAIM]->(c)
            MERGE (d:Disposition {id: r.disp_id})
            SET d.action = r.action, d.rationale = r.rationale, d.revision = r.revision
            MERGE (c)-[:HAS_DISPOSITION]->(d)
            """,
            {"rows": rows},
        )
        conn.execute(
            """
            UNWIND $rows AS r
            MATCH (:Claim {id: r.claim_id})-[link:CITES_WORK]->()
            DELETE link
            """,
            {"rows": rows},
        )
        conn.execute(
            """
            UNWIND $rows AS r
            MATCH (c:Claim {id: r.claim_id})
            UNWIND r.dois AS doi
            MATCH (p:Paper {doi: doi})
            MERGE (c)-[:CITES_WORK]->(p)
            """,
            {"rows": rows},
        )
    return len(rows)


def get_dispositions(conn, manuscript_id: str) -> list[dict]:
    """Return recorded claim dispositions for a manuscript from the Relate graph."""
    rows = conn.execute(
        """
        MATCH (m:Manuscript {id: $root})-[:HAS_CLAIM]->(c:Claim)-[:HAS_DISPOSITION]->(d:Disposition)
        RETURN coalesce(c.display_id, c.id) AS claim_id, c.text AS claim, d.action AS action,
               d.rationale AS rationale, d.revision AS revision,
               [(c)-[:CITES_WORK]->(p:Paper) | coalesce(p.doi, p.id)] AS references
        ORDER BY c.id
        """,
        {"root": manuscript_id},
    )
    return [dict(r) for r in rows]

