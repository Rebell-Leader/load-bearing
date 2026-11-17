import json
from pathlib import Path

import pytest
import relate

from loadbearing.claim_audit import audit, build_snapshot


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
