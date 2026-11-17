import json
from pathlib import Path

import pytest
import relate

from loadbearing.claim_audit import audit, audit_claims, build_snapshot
from loadbearing.cli import main


@pytest.fixture
def snapshot(tmp_path):
    facts = json.loads((Path(__file__).parents[1] / "data/comparison/claim_facts.json").read_text())
    path = tmp_path / "claim.rl"
    build_snapshot(path, facts)
    conn = relate.connect(str(path), read_only=True)
    try:
        yield conn
    finally:
        conn.close()


def test_same_reference_yields_distinct_claim_actions(snapshot):
    ref = ["https://doi.org/10.30574/WJAETS.2025.15.1.0276"]
    positive = audit(snapshot, claim="Improved K-means can segment users.", reference_dois=ref, as_of="2026-11-16")
    control = audit(snapshot, claim="The system separates candidate generation and ranking.",
                    reference_dois=ref, as_of="2026-11-16")
    assert positive["action"] == "review_indirect"
    assert control["action"] == "retain_for_this_notice"
    assert positive["findings"][0]["path"] == control["findings"][0]["path"]
    assert "reference 5" in control["findings"][0]["evidence"]["locator"]


def test_missing_and_ambiguous_outcome_evidence_abstain(snapshot):
    args = {"reference_dois": ["10.1186/s13287-022-03231-1"], "as_of": "2026-11-16"}
    hidden = audit(snapshot, claim="Rat cognitive function", fixture_condition="withhold_outcome_evidence", **args)
    ambiguous = audit(snapshot, claim="Rat and mouse cognitive function", **args)
    assert hidden["action"] == ambiguous["action"] == "insufficient_evidence"
    assert "evidence" not in hidden["findings"][0]
    unresolved = audit(snapshot, claim="A claim", reference_dois=["10.1000/unknown"], as_of="2026-11-16")
    assert unresolved["action"] == "insufficient_evidence"


def test_historical_notice_cutoff(snapshot):
    args = {"claim": "Use the results.", "reference_dois": ["10.1038/nature04533"]}
    historical = audit(snapshot, as_of="2023-01-01", **args)
    current = audit(snapshot, as_of="2026-11-16", **args)
    assert historical["action"] == "review_notice"
    assert historical["findings"][0]["notice"]["kind"] == "expression_of_concern"
    assert current["action"] == "review_direct"
    assert current["findings"][0]["notice"]["kind"] == "retraction"
    with pytest.raises(ValueError, match="later than snapshot"):
        audit(snapshot, as_of="2026-11-17", **args)


def test_unrelated_retraction_wording_cannot_clear_a_direct_citation(snapshot):
    args = {"reference_dois": ["10.1038/nature04533"], "as_of": "2026-11-16"}
    assert audit(snapshot, claim="Document that the cited paper was retracted.", **args)["action"] == "retain_with_notice"
    assert audit(snapshot, claim="Discuss the retracted earlier report, then base the conclusion on this paper.",
                 **args)["action"] == "review_direct"


def test_import_preview_confirm_retry_and_audit(tmp_path, capsys):
    data = Path(__file__).parents[1] / "data/claim_eval"
    db = tmp_path / "imported.rl"
    args = ["import-outcomes", str(data / "outcomes.csv"), "--notices", str(data / "notices.csv"),
            "--as-of", "2026-11-16", "--store", str(db)]
    assert main(args) == 0
    assert "Preview only" in capsys.readouterr().out
    assert not db.exists()
    assert main([*args, "--confirm"]) == 0
    assert main([*args, "--confirm"]) == 0

    claims = [row for row in json.loads((data / "claims.json").read_text()) if row["id"] in {
        "gillespie-mapped", "gillespie-outside-scope", "gillespie-paraphrase-unmapped",
    }]
    results = audit_claims(db, claims)
    assert [row["action"] for row in results] == ["review_indirect", "insufficient_evidence", "retain_for_this_notice"]
    positive = results[0]["findings"]
    assert len(positive) == 1
    assert "Analysis 10.3" in positive[0]["evidence"]["locator"]
    assert positive[0]["notice"]["url"] == "https://doi.org/10.1016/j.bone.2017.10.007"

    malformed = tmp_path / "invalid.csv"
    malformed.write_text("review_doi\n10.1234/incorrect\n")
    assert main(["import-outcomes", str(malformed), "--as-of", "2026-11-16",
                 "--store", str(db), "--confirm"]) == 2
    assert audit_claims(db, claims) == results
