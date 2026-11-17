"""Offline tests: citation-context extraction, intent rules, and the Relate exposure query."""

import json
import xml.etree.ElementTree as ET

import pytest
import relate

from loadbearing import bib, expand, fulltext, intent, store

JATS = """<article><body>
<sec><title>Introduction</title>
<p>Amyloid oligomers have long been studied<xref ref-type="bibr" rid="R1">1</xref>. Several groups
reported memory deficits<xref ref-type="bibr" rid="R2">2</xref>&#8211;<xref ref-type="bibr" rid="R4">4</xref>.</p></sec>
<sec><title>Methods</title>
<p>Oligomers were purified as described previously<xref ref-type="bibr" rid="R3">3</xref>.</p></sec>
<sec><title>Discussion</title>
<p>Note that the Ab*56 study<xref ref-type="bibr" rid="R2">2</xref> was retracted in 2024.</p></sec>
</body><back><ref-list>
<ref id="R1"><element-citation><article-title>History of amyloid</article-title><pub-id pub-id-type="doi">10.1/one</pub-id></element-citation></ref>
<ref id="R2"><element-citation><article-title>A specific amyloid-beta protein assembly in the brain impairs memory</article-title><pub-id pub-id-type="doi">10.1038/nature04533</pub-id></element-citation></ref>
<ref id="R3"><element-citation><article-title>Purification protocol</article-title><pub-id pub-id-type="doi">10.1/three</pub-id></element-citation></ref>
<ref id="R4"><element-citation><article-title>Fourth</article-title><pub-id pub-id-type="doi">10.1/four</pub-id></element-citation></ref>
</ref-list></back></article>"""


def test_contexts_expand_ranges_and_sections(monkeypatch):
    monkeypatch.setattr(fulltext, "pmcid_for_doi", lambda doi: "PMC1")
    monkeypatch.setattr(fulltext, "fetch_jats", lambda pmcid: ET.fromstring(JATS))
    status, found = fulltext.contexts_for("10.9/citing", {
        "lesne": ("10.1038/nature04533", ""),
        "proto": ("10.1/three", ""),
        "absent": ("10.1/nothere", ""),
    })
    assert status == "fulltext"
    assert found["absent"] == []
    # R3 is cited inside the range 2–4 (intro) and directly in Methods.
    assert {c.section_type for c in found["proto"]} == {"intro", "methods"}
    lesne = {c.section_type: c.sentence for c in found["lesne"]}
    assert "retracted" in lesne["discussion"]


def test_retracted_title_prefix_still_matches():
    # OpenAlex says 'RETRACTED ARTICLE: …'; the citing paper's reference list doesn't.
    assert fulltext._norm_title("RETRACTED ARTICLE: A specific amyloid-beta protein assembly") == \
        fulltext._norm_title("A specific amyloid-beta protein assembly")
    assert fulltext._title_match("RETRACTED: The Hepcidin-Binding Site on Ferroportin Is Evolutionarily Conserved",
                                 fulltext._tokens("The hepcidin-binding site on ferroportin is evolutionarily conserved."))


def test_elsevier_ext_link_doi():
    jats = ET.fromstring(
        '<article xmlns:xlink="http://www.w3.org/1999/xlink"><back><ref-list><ref id="bib1"><mixed-citation>'
        '<named-content>Holmberg C.G. Histaminolytic activity. Nature. 1948.</named-content>'
        '<ext-link ext-link-type="doi" xlink:href="10.1038/161236a0"/></mixed-citation></ref></ref-list></back></article>')
    refs, _ = fulltext._refs(jats)
    assert refs["bib1"][0] == "10.1038/161236a0"


def test_intent_rules():
    assert intent.classify("Oligomers were purified as described previously.", "other")[0] == "method"
    assert intent.classify("Anything at all.", "methods")[0] == "method"
    assert intent.classify("This was retracted in 2024.", "methods")[0] == "critical"
    assert intent.classify("Our data are consistent with earlier work.", "discussion")[0] == "result"
    assert intent.classify("Iron deficiency is the most common deficiency.", "discussion")[0] == "background"
    assert intent.classify("Amyloid has long been studied.", "intro")[0] == "background"
    assert intent.classify(None)[0] == "unknown"
    assert intent.combine(["background", "method"]) == "method"


def test_bib_reader(tmp_path):
    p = tmp_path / "refs.bib"
    p.write_text('@article{lesne2006,\n  title = {A specific amyloid},\n  doi = {10.1038/NATURE04533},\n}\n'
                 '@article{nodoi,\n  title = {No DOI here},\n}\n')
    refs = bib.read_references(p)
    assert refs[0]["doi"] == "10.1038/nature04533"
    assert refs[1]["doi"] is None


def test_bib_single_line_and_nested_braces():
    text = ('@article{a, title={The {A$\\beta$} hypothesis}, doi={https://doi.org/10.1/X}}\n'
            '@misc{b, title="Quoted", url = {https://doi.org/10.5555/y}, year=2020}\n'
            '@comment{ignore me}')
    refs = bib.parse_references(text)
    assert [(r["key"], r["doi"]) for r in refs] == [("a", "10.1/x"), ("b", "10.5555/y")]
    assert refs[0]["title"] == "The A$\\beta$ hypothesis"
    assert [r["doi"] for r in bib.parse_references("10.1038/nature04533\nsee doi:10.1126/science.1241224.")] == \
        ["10.1038/nature04533", "10.1126/science.1241224"]


def test_exposure_statuses():
    conn = relate.connect(":memory:")
    for stmt in store.SCHEMA:
        conn.execute(stmt)
    store.upsert_papers(conn, [
        {"id": "M", "title": "manuscript", "year": 2026, "doi": None, "pub_date": "2026-01-01"},
        {"id": "A", "title": "a", "year": 2020, "doi": None, "pub_date": "2020-01-01"},
        {"id": "B", "title": "b", "year": 2019, "doi": None, "pub_date": "2019-01-01"},
        {"id": "C", "title": "c", "year": 2025, "doi": None, "pub_date": "2025-01-01"},
        {"id": "R", "title": "retracted", "year": 2006, "doi": None, "pub_date": "2006-01-01"},
    ])
    store.mark_manuscript(conn, "M")
    store.mark_retracted(conn, [{"id": "R", "nature": "Retraction", "date": "2024-06-24", "reasons": ["Concerns about images"],
                                 "notice_id": "RW1", "notice_doi": None, "source": "retraction_watch"}])
    store.upsert_citations(conn, [{"src": s, "dst": d} for s, d in
                                  [("M", "A"), ("A", "R"), ("M", "B"), ("B", "R"), ("M", "C"), ("C", "R"), ("M", "R")]])
    store.annotate_citations(conn, [
        {"src": "A", "dst": "R", "intent": "method", "rule": "t", "section": "Methods", "context": "x", "evidence": "fulltext", "n_contexts": 1},
        {"src": "B", "dst": "R", "intent": "background", "rule": "t", "section": "Intro", "context": "y", "evidence": "fulltext", "n_contexts": 1},
        {"src": "C", "dst": "R", "intent": "critical", "rule": "t", "section": "Discussion", "context": "z", "evidence": "fulltext", "n_contexts": 1},
    ])
    statuses = {tuple(n["id"] for n in r["chain"]): r["status"] for r in store.exposure(conn, "M", 3)}
    assert statuses[("M", "R")] == "direct"
    assert statuses[("M", "A", "R")] == "load_bearing"
    assert statuses[("M", "B", "R")] == "mention_only"
    assert statuses[("M", "C", "R")] == "defused"
    zombie = conn.execute("MATCH (:Paper {id: 'C'})-[c:CITES]->(:Paper {id: 'R'}) RETURN c.zombie AS z").single()["z"]
    assert zombie is True
    lb = list(conn.execute(store.LOAD_BEARING_ONLY, {"root": "M"}))
    assert {tuple(r["chain"]) for r in lb} == {("manuscript", "retracted"), ("manuscript", "a", "retracted")}
    conn.close()
    # Depth 1 used to build a {0,0} quantifier, which Relate rejects: only the direct citation remains.
    conn = relate.connect(":memory:")
    for stmt in store.SCHEMA:
        conn.execute(stmt)
    store.upsert_papers(conn, [{"id": i, "title": i, "year": 2020, "doi": None, "pub_date": "2020-01-01"} for i in "MAR"])
    store.mark_manuscript(conn, "M")
    store.mark_retracted(conn, [{"id": "R", "nature": "Retraction", "date": "2024-06-24", "reasons": [],
                                 "notice_id": None, "notice_doi": None}])
    store.upsert_citations(conn, [{"src": s, "dst": d} for s, d in [("M", "A"), ("A", "R"), ("M", "R")]])
    assert [(tuple(n["id"] for n in r["chain"]), r["status"]) for r in store.exposure(conn, "M", 1)] == [(("M", "R"), "direct")]
    assert len(store.exposure(conn, "M", 2)) == 2
    assert store.ignored_citations(conn, "M", 1) == []
    assert sorted(expand.path_edges(conn, "M", 1)) == [("M", "R")]
    conn.close()


def test_notice_labels_never_call_a_flag_a_retraction():
    from loadbearing import check
    rw = {"notice_source": "retraction_watch", "nature": "Retraction", "retraction_date": "2024-06-24"}
    eoc = {"notice_source": "retraction_watch", "nature": "Expression of concern", "retraction_date": "2022-03-01"}
    flag = {"notice_source": "openalex", "nature": "Retraction", "retraction_date": None}
    assert check.notice_label(rw) == "Retraction 2024-06-24" and check.has_retraction_notice(rw)
    assert check.notice_label(eoc).endswith("only notice found is an expression of concern (2022-03-01)")
    assert check.notice_label(flag) == "marked retracted by OpenAlex, no notice found"
    assert not check.has_retraction_notice(eoc) and not check.has_retraction_notice(flag)
    assert not check.has_retraction_notice({"nature": "Retraction"})
    assert "no retraction notice" in check.notice_label({})


def test_direct_status_and_graph_use_the_same_notice_evidence(monkeypatch):
    from loadbearing import check, crossref, openalex, retractionwatch

    def notice(nature):
        return {"nature": nature, "date": "2024-06-24", "reasons": [], "notice_doi": "10.1000/notice"}

    flag, concern, upgraded, recorded = [f"10.1000/{key}" for key in ("flag", "concern", "upgraded", "recorded")]
    works = [{"id": f"W{i}", "doi": doi, "is_retracted": doi != recorded}
             for i, doi in enumerate((flag, concern, upgraded, recorded), 1)]
    rw = {concern: notice("Expression of concern"), upgraded: notice("Correction"), recorded: notice("Retraction")}
    monkeypatch.setattr(openalex, "works_by_dois", lambda *args, **kwargs: works)
    monkeypatch.setattr(retractionwatch, "load", lambda: rw)
    monkeypatch.setattr(crossref, "notice", lambda doi: notice("Retraction") if doi == upgraded else None)

    direct = check.retraction_status([flag, concern, upgraded, recorded])
    assert [r["status"] for r in direct] == ["marked_retracted", "expression_of_concern", "retracted", "retracted"]
    assert [r["notice_on_record"] for r in direct] == [False, False, True, True]
    assert direct[0]["notice"] is None and direct[1]["openalex_marked_retracted"]

    ex = expand.expand([{"doi": w["doi"]} for w in works], "M", "draft", None, 1)
    assert [(r["source"], r["nature"]) for r in expand.retraction_rows(ex)] == [
        ("openalex", None), ("retraction_watch", "Expression of concern"),
        ("crossref", "Retraction"), ("retraction_watch", "Retraction"),
    ]


def test_legacy_date_flags_require_a_retraction_notice():
    conn = relate.connect(":memory:")
    try:
        store.upsert_papers(conn, [{"id": i, "pub_date": "2025-01-01"} for i in ("M", "R", "C")])
        store.mark_manuscript(conn, "M")
        store.mark_retracted(conn, [
            {"id": i, "nature": kind, "date": "2024-06-24", "source": "crossref", "reasons": [],
             "notice_id": None, "notice_doi": None}
            for i, kind in (("R", "Retraction"), ("C", "Correction"))
        ])
        store.upsert_citations(conn, [{"src": "M", "dst": i} for i in ("R", "C")])
        conn.execute("MATCH ()-[c:CITES]->() SET c.zombie = true")
        assert {r["bad_id"]: r["edges"][0]["zombie"] for r in store.exposure(conn, "M", 1)} == {"C": False, "R": True}
    finally:
        conn.close()


def test_intent_v1():
    v1 = intent.classify_v1
    assert v1("This was retracted in 2024.", "results", "article")[0] == "critical"
    assert v1("the alleged requirement of PrPc (Lauren 2009)", "intro", "article")[0] == "critical"
    assert v1("The mechanism remains controversial [3].", "intro", "article")[0] == "result"  # no longer critical
    assert v1("Anything.", "methods", "article")[0] == "method"
    assert v1("Blots were run as previously described [4].", "other", "article")[0] == "method"  # rules fallback
    assert v1("Blots were run [4].", "other", "article", method_prob=0.9)[0] == "method"
    assert v1("X reduces Y in mice [4].", "intro", "article", method_prob=0.1)[0] == "result"
    assert v1("X reduces Y in mice [4].", "intro", "review", method_prob=0.1)[0] == "background"
    assert v1("Iron deficiency is common [4].", "discussion", None)[0] == "background"  # unknown type: v0 rules
    assert v1(None)[0] == "unknown"


def test_intent_v1_precision_guards():
    v1 = intent.classify_v1
    assert intent.citation_group_size("tied to neurodegeneration in AD35,36.") == 2
    assert intent.citation_group_size("animal models of the disease13–18.") == 6
    assert intent.citation_group_size("risk factors [3], [5–8].") == 5
    assert v1("Accumulating evidence indicates that APP cleavage is tied to AD [35,36].", "intro", "article")[0] == "background"
    assert v1("This has been shown in the pathology [13–18].", "intro", "article")[0] == "background"
    assert v1("Deferiprone mobilized Fe deposited in brain of mice [386].", "results", "article")[0] == "result"
    assert v1("Aβ at 5 µM activated p38 in cells [260–262].", "intro", "article")[0] == "result"  # group, but specific


def test_crossref_notice_fallback(monkeypatch):
    from loadbearing import crossref, http
    payload = {"message": {"items": [
        {"DOI": "10.1/orig", "title": ["RETRACTED: Paper"], "update-to": [{"DOI": "10.1/orig", "type": "retraction", "updated": {"date-parts": [[2011, 10, 1]]}}]},
        {"DOI": "10.1/notice", "title": ["Retraction notice to “Paper”"], "update-to": [{"DOI": "10.1/orig", "type": "erratum", "updated": {"date-parts": [[2026, 7, 1]]}}]},
    ]}}
    monkeypatch.setattr(http, "get", lambda url, **kw: payload)
    n = crossref.notice("10.1/orig")
    assert n["nature"] == "Retraction" and n["date"] == "2026-07-01" and n["notice_doi"] == "10.1/notice"


def test_impossible_citations_are_excluded_or_downgraded():
    conn = relate.connect(":memory:")
    for stmt in store.SCHEMA:
        conn.execute(stmt)
    papers = [("M", 2026), ("X", 2008), ("Y", 2012), ("Z", 2011), ("R", 2006), ("R2", 2020), ("A", 2015)]
    store.upsert_papers(conn, [{"id": i, "title": i, "year": y, "doi": None, "pub_date": None} for i, y in papers])
    store.mark_manuscript(conn, "M")
    store.mark_retracted(conn, [{"id": r, "nature": "Retraction", "date": None, "reasons": [], "notice_id": None,
                                 "notice_doi": None, "source": "openalex"} for r in ("R", "R2")])
    # M→X→Y→R : X (2008) "cites" Y (2012): impossible, non-retracted → path dropped
    # M→Z→R2  : Z (2011) cites retracted R2 dated 2020 → kept, but only as unverified
    # M→A→R   : ordinary load-bearing path, unaffected
    edges = [("M", "X"), ("X", "Y"), ("Y", "R"), ("M", "Z"), ("Z", "R2"), ("M", "A"), ("A", "R")]
    store.upsert_citations(conn, [{"src": s, "dst": d} for s, d in edges])
    counts = store.flag_citation_dates(conn)
    assert counts == {"anachronistic": 1, "year_conflict": 1}
    store.annotate_citations(conn, [{"src": s, "dst": d, "intent": "result", "rule": "t", "section": None, "context": "c",
                                     "evidence": "fulltext", "n_contexts": 1, "classifier": "test"} for s, d in edges[1:] if s != "M"])
    statuses = {tuple(n["id"] for n in r["chain"]): r["status"] for r in store.exposure(conn, "M", 3)}
    assert ("M", "X", "Y", "R") not in statuses
    assert statuses[("M", "Z", "R2")] == "unverified"
    assert statuses[("M", "A", "R")] == "load_bearing"
    ignored = store.ignored_citations(conn, "M", 3)
    assert [(i["citing_year"], i["cited_year"]) for i in ignored] == [(2008, 2012)]
    lb = {tuple(r["chain"]) for r in conn.execute(store.LOAD_BEARING_ONLY, {"root": "M"})}
    assert lb == {("M", "A", "R")}
    conn.close()


def test_offline_check_uses_only_the_store(monkeypatch):
    """--offline with --doi must resolve the paper from the shipped store, never the network."""
    from pathlib import Path
    from loadbearing import check, openalex

    def no_network(*a, **k):
        raise AssertionError("offline check touched the network")

    monkeypatch.setattr(openalex, "work", no_network)
    demo_store = str(Path(__file__).resolve().parents[1] / "data/demo.rl")
    DEMO = "https://doi.org/10.1016/J.REDOX.2025.103611"
    res = check.run_check(demo_store, doi=DEMO, depth=3, offline=True)
    assert res.root_id == "W4408770418" and res.title.startswith("Absence of astrocytic ceruloplasmin")
    assert res.summary["counts"]["load_bearing"] == 23
    lb = [g for g in res.summary["retracted"] if g["status"] == "load_bearing"]
    assert sum(g["notice_on_record"] for g in lb) == 21  # one OpenAlex flag only, one expression of concern
    assert check.run_check(demo_store, doi=DEMO, depth=1, offline=True).summary["retracted"] == []
    try:
        check.run_check(demo_store, doi="10.1000/not-in-store", offline=True)
    except LookupError as e:
        assert "not a checked manuscript" in str(e)
    else:
        raise AssertionError("missing manuscript should raise")


def test_first_hop_critical_citation_defuses_path():
    conn = relate.connect(":memory:")
    for stmt in store.SCHEMA:
        conn.execute(stmt)
    store.upsert_papers(conn, [
        {"id": "M", "title": "manuscript", "year": 2026, "doi": None, "pub_date": "2026-01-01"},
        {"id": "A", "title": "intermediate", "year": 2020, "doi": None, "pub_date": "2020-01-01"},
        {"id": "R", "title": "retracted paper", "year": 2006, "doi": "10.1038/nature04533", "pub_date": "2006-01-01"},
    ])
    store.mark_manuscript(conn, "M")
    store.mark_retracted(conn, [{"id": "R", "nature": "Retraction", "date": "2024-06-24", "reasons": [],
                                 "notice_id": "RW1", "notice_doi": None, "source": "retraction_watch"}])
    store.upsert_citations(conn, [{"src": "M", "dst": "R"}, {"src": "M", "dst": "A"}, {"src": "A", "dst": "R"}])
    store.annotate_citations(conn, [
        {"src": "M", "dst": "R", "intent": "critical", "rule": "cue: retracted", "section": "Discussion",
         "context": "Lesné 2006 was retracted.", "evidence": "fulltext", "n_contexts": 1, "classifier": "v1"},
        {"src": "M", "dst": "A", "intent": "critical", "rule": "cue: failed to replicate", "section": "Discussion",
         "context": "Failed to replicate A.", "evidence": "fulltext", "n_contexts": 1, "classifier": "v1"},
        {"src": "A", "dst": "R", "intent": "method", "rule": "section: methods", "section": "Methods",
         "context": "Purified as described.", "evidence": "fulltext", "n_contexts": 1, "classifier": "v1"},
    ])
    statuses = {tuple(n["id"] for n in r["chain"]): r["status"] for r in store.exposure(conn, "M", 3)}
    assert statuses[("M", "R")] == "defused"
    assert statuses[("M", "A", "R")] == "defused"
    conn.close()


def test_fulltext_vector_search_and_dispositions():
    conn = relate.connect(":memory:")
    for stmt in store.SCHEMA:
        conn.execute(stmt)
    store.upsert_papers(conn, [
        {"id": "M:draft", "title": "Grant draft", "year": 2026, "doi": None, "pub_date": "2026-01-01"},
        {"id": "W1", "title": "A specific amyloid-beta protein assembly in the brain impairs memory",
         "year": 2006, "doi": "10.1038/nature04533", "pub_date": "2006-03-16"},
        {"id": "W2", "title": "Iron transport across the blood-brain barrier",
         "year": 2014, "doi": "10.1000/iron", "pub_date": "2014-01-01"},
    ])
    store.mark_manuscript(conn, "M:draft")
    store.mark_retracted(conn, [{"id": "W1", "nature": "Retraction", "date": "2024-06-24", "reasons": [],
                                 "notice_id": "RW1", "notice_doi": None, "source": "retraction_watch"}])

    ft_hits = store.search_papers(conn, "amyloid memory", limit=3)
    assert ft_hits and ft_hits[0]["id"] == "W1" and ft_hits[0]["retracted"] is True

    n_indexed = store.index_paper_vectors(conn)
    assert n_indexed == 3
    vec_hits = store.vector_search_papers(conn, "amyloid-beta protein assembly memory", limit=2)
    assert vec_hits and vec_hits[0]["id"] == "W1"

    recorded = store.record_dispositions(conn, "M:draft", [{
        "claim_id": "c1",
        "claim": "Aβ*56 impairs memory in Tg2576 mice.",
        "action": "drop_citation",
        "rationale": "Sole support is Lesné 2006 (retracted 2024-06-24).",
        "revision": "Removed Aβ*56 sentence.",
        "reference_dois": ["https://doi.org/10.1038/nature04533"],
    }])
    assert recorded == 1
    disps = store.get_dispositions(conn, "M:draft")
    assert len(disps) == 1
    assert disps[0]["action"] == "drop_citation"
    assert disps[0]["references"] == ["10.1038/nature04533"]
    store.record_dispositions(conn, "M:draft-more", [
        {"claim_id": "M:draft-more:c1", "claim": "Different manuscript", "reference_dois": ["10.1000/iron"]},
    ])
    store.record_dispositions(conn, "M:draft", [
        {"claim_id": disps[0]["claim_id"], "claim": "Revised", "reference_dois": ["10.1000/iron"]},
        {"claim_id": "M:draft-more:c1", "claim": "Different claim scope"},
    ])
    revised = store.get_dispositions(conn, "M:draft")
    assert {row["claim"]: row["references"] for row in revised} == {
        "Revised": ["10.1000/iron"], "Different claim scope": [],
    }
    assert store.get_dispositions(conn, "M:draft-more")[0]["claim"] == "Different manuscript"
    store.record_dispositions(conn, "M:draft", [{"claim_id": "c1", "claim": "Citation deleted"}])
    assert next(row for row in store.get_dispositions(conn, "M:draft") if row["claim"] == "Citation deleted")["references"] == []
    conn.close()


def test_rechecking_draft_replaces_references_atomically(monkeypatch):
    conn = store.open_store(":memory:")
    root = "M:draft"

    def expansion(refs, *args):
        papers = {key: {"id": key, "title": key} for key in (root, "W1", "W2")}
        return expand.Expansion(root, "Draft", papers=papers, edges={(root, refs[0]["id"])})

    monkeypatch.setattr(expand, "expand", expansion)
    monkeypatch.setattr(expand, "read_contexts", lambda *a, **k: [])
    for work in ("W1", "W2"):
        expand.build(conn, [{"id": work}], root, "Draft", None, 1)
    query = "MATCH (:Manuscript {id: $id})-[:CITES]->(p) RETURN p.id AS id"
    assert [row["id"] for row in conn.execute(query, {"id": root})] == ["W2"]

    def failed_context(*args, **kwargs):
        raise RuntimeError("read failed")

    monkeypatch.setattr(expand, "read_contexts", failed_context)
    with pytest.raises(RuntimeError, match="read failed"):
        expand.build(conn, [{"id": "W1"}], root, "Draft", None, 1)
    assert [row["id"] for row in conn.execute(query, {"id": root})] == ["W2"]
    conn.close()


def test_notice_fields_and_url_follow_the_same_record(tmp_path, monkeypatch):
    from loadbearing import mcp_server

    database = tmp_path / "test.rl"
    conn = store.open_store(str(database))
    store.upsert_papers(conn, [
        {"id": "M", "title": "Manuscript"},
        {"id": "W1", "title": "Model findings one", "doi": "10.1234/first"},
        {"id": "W2", "title": "Model findings two", "doi": "10.1234/second"},
    ])
    store.mark_manuscript(conn, "M")
    for work, kind, date, identifier in [
        ("W1", "Correction", "2022-01-01", "correction"),
        ("W1", "Retraction", "2024-03-01", "retraction"),
        ("W2", "Retraction", "2024-04-01", "other-retraction"),
    ]:
        store.mark_retracted(conn, [{"id": work, "nature": kind, "date": date, "reasons": [],
                                     "source": "crossref", "notice_id": identifier, "notice_doi": f"10.1234/{identifier}"}])
    store.upsert_citations(conn, [{"src": "M", "dst": target} for target in ("W1", "W2")])
    hit = store.exposure(conn, "M", 1)[0]
    assert (hit["nature"], hit["retraction_date"], hit["notice_doi"]) == (
        "Retraction", "2024-03-01", "10.1234/retraction",
    )
    conn.execute("MATCH (p:Paper {id: 'W1'}) REMOVE p.active_notice_id")
    assert store.exposure(conn, "M", 1)[0]["notice_doi"] == "10.1234/retraction"
    conn.close()
    monkeypatch.setattr(mcp_server, "STORE", str(database))
    candidates = json.loads(mcp_server.explain_exposure("M", "model findings"))
    assert {candidate["id"] for candidate in candidates["candidates"]} == {"W1", "W2"}
    exact = json.loads(mcp_server.explain_exposure("M", "https://doi.org/10.1234/second"))
    assert exact["retracted"]["id"] == "W2"
    assert [path["hops"][-1]["to_doi"] for path in exact["paths"]] == ["10.1234/second"]


def test_reinstatement_supersedes_retraction_and_stale_metadata(tmp_path, monkeypatch):
    from loadbearing import retractionwatch

    source = tmp_path / "notices.csv"
    source.write_text(
        "Record ID,OriginalPaperDOI,RetractionNature,RetractionDate,RetractionDOI\n"
        "1,10.1234/first,Retraction,3/1/2024,10.1234/withdrawal\n"
        "2,10.1234/first,Reinstatement,4/1/2024,10.1234/restored\n"
    )
    data = retractionwatch.load(source)
    assert data["10.1234/first"]["nature"] == "Reinstatement"
    monkeypatch.setattr(retractionwatch, "load", lambda: data)
    monkeypatch.setattr(retractionwatch.crossref, "notice", lambda _: {
        "nature": "Retraction", "date": "2024-03-01",
    })
    notice, authority = retractionwatch.resolve("10.1234/first", marked_retracted=True)
    assert (notice["nature"], authority) == ("Reinstatement", "retraction_watch")

    conn = store.open_store(":memory:")
    store.upsert_papers(conn, [{"id": "W1", "title": "Reinstated paper"}])
    for kind, date, source in [("Retraction", "2024-03-01", "retraction_watch"),
                               ("Reinstatement", "2024-04-01", "retraction_watch"),
                               (None, None, "openalex")]:
        store.mark_retracted(conn, [{"id": "W1", "nature": kind, "date": date, "source": source,
                                     "notice_id": kind, "notice_doi": None, "reasons": []}])
    row = conn.execute("MATCH (p:Paper {id:'W1'}) RETURN p.nature AS kind, p:Retracted AS active").single()
    assert dict(row) == {"kind": "Reinstatement", "active": False}
    conn.close()

