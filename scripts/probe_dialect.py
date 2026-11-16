"""Spike probe: does Relate 1.0.1 support every query shape Load-Bearing needs?

Run: uv run python scripts/probe_dialect.py
Each check prints OK/FAIL so the result reads as a checklist.
"""

import os
import tempfile
import time

import relate

CHECKS: list[tuple[str, bool, str]] = []


def check(name, fn):
    try:
        detail = fn()
        CHECKS.append((name, True, str(detail)))
    except Exception as exc:  # noqa: BLE001 - we want every failure reported
        CHECKS.append((name, False, f"{type(exc).__name__}: {exc}"))


tmp = tempfile.mkdtemp()
path = os.path.join(tmp, "probe.rl")
conn = relate.connect(path)

# Toy citation graph:  mine -> a -(method)-> b -(result)-> R (retracted)
#                      mine -> c -(background)-> R    (mention only, must NOT count)
#                      z -(result, cited after retraction)-> R   (zombie citation)
SEED = """
CREATE (mine:Paper {id: 'W_MINE', title: 'My manuscript on amyloid oligomers', year: 2026}),
       (a:Paper {id: 'W_A', title: 'Oligomer toxicity review', year: 2015}),
       (b:Paper {id: 'W_B', title: 'Abeta star 56 replication in mice', year: 2010}),
       (c:Paper {id: 'W_C', title: 'History of the amyloid hypothesis', year: 2019}),
       (z:Paper {id: 'W_Z', title: 'Post-retraction mouse study', year: 2025}),
       (r:Paper {id: 'W_R', title: 'A specific amyloid-beta protein assembly in the brain impairs memory',
                 year: 2006, retracted: true, retraction_date: date('2024-06-24')}),
       (n:Notice {doi: '10.1038/s41586-024-07691-8', date: date('2024-06-24'), reasons: ['Concerns about images']}),
       (r)-[:RETRACTED_BY]->(n),
       (mine)-[:CITES {intent: 'result'}]->(a),
       (a)-[:CITES {intent: 'method'}]->(b),
       (b)-[:CITES {intent: 'result'}]->(r),
       (mine)-[:CITES {intent: 'background'}]->(c),
       (c)-[:CITES {intent: 'background'}]->(r),
       (z)-[:CITES {intent: 'result', cited_on: date('2025-03-01')}]->(r)
"""

check("single-file store + CREATE", lambda: conn.execute(SEED).stats["nodes_created"])

check(
    "uniqueness constraint",
    lambda: conn.execute(
        "CREATE CONSTRAINT paper_id IF NOT EXISTS FOR (p:Paper) REQUIRE p.id IS UNIQUE"
    ).stats,
)

LOAD_BEARING = """
MATCH p = (m:Paper {id: $id})
          (()-[c:CITES WHERE c.intent IN ['method', 'result']]->()){1,3}
          (bad:Paper WHERE bad.retracted = true)
RETURN bad.id AS bad, [x IN nodes(p) | x.id] AS chain, length(p) AS hops
ORDER BY hops
"""


def qpp():
    rows = list(conn.execute(LOAD_BEARING, {"id": "W_MINE"}))
    assert rows and rows[0]["chain"] == ["W_MINE", "W_A", "W_B", "W_R"], rows
    assert all("W_C" not in r["chain"] for r in rows), "background path leaked"
    return rows


check("quantified path + inline rel WHERE (load-bearing only)", qpp)


def zombie():
    rows = list(
        conn.execute(
            """
            MATCH (citer:Paper)-[c:CITES]->(r:Paper {retracted: true})
            WHERE c.cited_on > r.retraction_date
            RETURN citer.id AS citer, toString(c.cited_on) AS on, duration.between(r.retraction_date, c.cited_on).days AS days_after
            """
        )
    )
    assert rows and rows[0]["citer"] == "W_Z", rows
    return rows


check("date comparison (zombie citations)", zombie)


def fulltext():
    conn.execute("CREATE FULLTEXT INDEX paper_title IF NOT EXISTS FOR (p:Paper) ON EACH [p.title]")
    rows = list(
        conn.execute(
            "MATCH (p:Paper) SEARCH p IN (FULLTEXT INDEX paper_title FOR $q LIMIT 3) SCORE AS s "
            "RETURN p.id AS id, s ORDER BY s DESC",
            {"q": "amyloid memory"},
        )
    )
    assert rows and rows[0]["id"] == "W_R", rows
    return rows


check("full-text index + SEARCH", fulltext)


def vector():
    conn.execute("MATCH (p:Paper) SET p.emb = [toFloat(size(p.title)) / 100.0, 0.5, toFloat(p.year) / 3000.0]")
    conn.execute(
        "CREATE VECTOR INDEX paper_emb IF NOT EXISTS FOR (p:Paper) ON (p.emb) "
        "OPTIONS {indexConfig: {`vector.dimensions`: 3, `vector.similarity_function`: 'cosine'}}"
    )
    rows = list(
        conn.execute(
            "MATCH (p:Paper) SEARCH p IN (VECTOR INDEX paper_emb FOR $v LIMIT 2) SCORE AS s RETURN p.id AS id, s",
            {"v": [0.5, 0.5, 0.67]},
        )
    )
    assert len(rows) == 2, rows
    return rows


check("vector index + SEARCH", vector)


def bulk():
    n = 20000
    t = time.time()
    conn.execute(
        "UNWIND range(1, $n) AS i MERGE (:Paper {id: 'B' + toString(i), title: 'bulk ' + toString(i), year: 2000})",
        {"n": n},
    )
    t_nodes = time.time() - t
    edges = [{"s": f"B{i}", "t": f"B{(i * 7) % n + 1}", "intent": "result"} for i in range(1, n + 1)]
    t = time.time()
    conn.execute(
        "UNWIND $rows AS row MATCH (s:Paper {id: row.s}), (t:Paper {id: row.t}) "
        "MERGE (s)-[:CITES {intent: row.intent}]->(t)",
        {"rows": edges},
    )
    t_edges = time.time() - t
    return f"{n} nodes in {t_nodes:.2f}s, {n} edges in {t_edges:.2f}s"


check("bulk UNWIND/MERGE throughput", bulk)

conn.close()


def reopen():
    c = relate.connect(path)
    n = c.execute("MATCH (p:Paper) RETURN count(p) AS n").single()["n"]
    rows = list(c.execute(LOAD_BEARING, {"id": "W_MINE"}))
    c.close()
    return f"{n} papers after reopen, {len(rows)} load-bearing path(s), file {os.path.getsize(path)} bytes"


check("reopen single file + query persists", reopen)

width = max(len(n) for n, _, _ in CHECKS)
for name, ok, detail in CHECKS:
    print(f"{'OK  ' if ok else 'FAIL'} {name:<{width}}  {detail[:220]}")
