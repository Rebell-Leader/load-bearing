"""Offline tests: citation-context extraction, intent rules, and the Relate exposure query."""

import xml.etree.ElementTree as ET

import relate

from loadbearing import bib, fulltext, intent, store

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
                                 "notice_id": "RW1", "notice_doi": None}])
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
    from loadbearing import check, openalex

    def no_network(*a, **k):
        raise AssertionError("offline check touched the network")

    monkeypatch.setattr(openalex, "work", no_network)
    res = check.run_check("data/demo.rl", doi="https://doi.org/10.1016/J.REDOX.2025.103611", depth=3, offline=True)
    assert res.root_id == "W4408770418" and res.title.startswith("Absence of astrocytic ceruloplasmin")
    assert res.summary["counts"]["load_bearing"] == 23
    try:
        check.run_check("data/demo.rl", doi="10.1000/not-in-store", offline=True)
    except LookupError as e:
        assert "not a checked manuscript" in str(e)
    else:
        raise AssertionError("missing manuscript should raise")
