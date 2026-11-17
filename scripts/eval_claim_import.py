"""Reproduce the held-out comparison by importing published inclusion decisions."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from loadbearing import claim_audit, claim_import
from run_claim_comparison import score

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/claim_eval"
SOURCE = "https://doi.org/10.1136/bmjopen-2019-031909"


def evaluate() -> dict:
    inputs = json.loads((DATA / "claims.json").read_text())
    labels = json.loads((DATA / "labels.json").read_text())
    if {row["id"] for row in inputs} != labels.keys():
        raise ValueError("Claims and separately stored labels must match by ID.")
    cases = [{"id": key, "expected": {"action": label["action"]}} for key, label in labels.items()]
    facts = claim_import.read_tables(DATA / "outcomes.csv", DATA / "notices.csv", "2026-11-16")
    studies_in_pilot = json.loads((ROOT / "data/comparison/claim_facts.json").read_text())
    pilot_dois = {p["doi"] for p in studies_in_pilot["publications"]}
    if any(p["doi"] in pilot_dois for p in facts["publications"]):
        raise ValueError("A review in the evaluation is also in the original pilot.")

    with TemporaryDirectory(prefix="loadbearing-claim-eval-") as tmp:
        store = Path(tmp) / "new.rl"
        claim_audit.write_snapshot(store, facts)
        arms = {}
        for mode in claim_audit.MODES:
            rows = claim_audit.audit_claims(store, inputs, mode)
            metrics = score(cases, rows)
            metrics["abstentions"] = sum(row["action"] == "insufficient_evidence" for row in rows)
            metrics["matched_controls_flagged"] = sum(
                row["action"].startswith("review_") and labels[row["id"]]["condition"] == "outside-scope"
                for row in rows
            )
            arms[mode] = {"metrics": metrics,
                          "actions_by_case": {row["id"]: row["action"] for row in rows}}
    scoped = arms["claim_aware"]["actions_by_case"]
    mapped = [row["id"] for row in inputs if labels[row["id"]]["condition"] in {"mapped", "paraphrase-mapped", "outside-scope"}]
    return {
        "source": SOURCE,
        "inputs_sha256": {p.name: sha256(p.read_bytes()).hexdigest() for p in sorted(DATA.iterdir()) if p.is_file()},
        "reviews_outside_original_pilot": len(facts["publications"]),
        "conditions": dict(Counter(label["condition"] for label in labels.values())),
        "mapped_claims_with_disposition": {
            "returned": sum(scoped[key] != "insufficient_evidence" for key in mapped), "total": len(mapped)
        },
        "arms": arms,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate()
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({mode: arm["metrics"] for mode, arm in result["arms"].items()}, indent=2))
