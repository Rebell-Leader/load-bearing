"""Build the offline claim demo pack and its browsable, read-only report."""

from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from loadbearing import claim_audit

ROOT = Path(__file__).resolve().parents[1]
FACTS = ROOT / "data/comparison/claim_facts.json"
SNAPSHOT = ROOT / "data/claims.rl"
REPORT = ROOT / "viewer/claim-demo.js"


def read(path: Path):
    return json.loads(path.read_text())


def export(snapshot: Path) -> dict:
    pilot = read(ROOT / "runs/claim_pilot/report.json")
    agent = pilot["agent_arms"]["mcp_graph"]
    revisions = {row["id"]: row["revision"] for row in agent["rows"]}
    demos = read(claim_audit.DEMO_CLAIMS)
    for demo in demos.values():
        claims = demo.pop("claims")
        demo["direct"] = claim_audit.audit_claims(snapshot, claims, "direct")
        demo["current"] = claim_audit.audit_claims(snapshot, claims)
        if "before" in demo:
            earlier = [{**claim, "as_of": demo["before"]} for claim in claims]
            demo["historical"] = claim_audit.audit_claims(snapshot, earlier)
        for result in demo["current"]:
            result["recorded_revision"] = revisions[result["id"]]

    # Recompute the three comparison arms on the same snapshot as the featured cases.
    from run_claim_comparison import score

    cases = [json.loads(line) for line in (ROOT / "data/comparison/cases.jsonl").read_text().splitlines()]
    inputs = [{"id": case["id"], **case["input"]} for case in cases]
    arms = {mode: score(cases, claim_audit.audit_claims(snapshot, inputs, mode)) for mode in claim_audit.MODES}
    return {"examples": demos, "actions": claim_audit.ACTIONS, "pilot": arms, "agent": "Claude Haiku 5.5",
            "source_sha256": sha256(FACTS.read_bytes()).hexdigest(),
            "snapshot_sha256": sha256(snapshot.read_bytes()).hexdigest()}


if __name__ == "__main__":
    with TemporaryDirectory(dir=SNAPSHOT.parent) as directory:
        path = Path(directory) / SNAPSHOT.name
        claim_audit.build_snapshot(path, read(FACTS))
        payload = export(path)
        path.chmod(0o644)
        path.replace(SNAPSHOT)
    REPORT.write_text("window.claimDemo = " + json.dumps(payload, ensure_ascii=False, indent=2) + ";\n")
    print(f"{SNAPSHOT.relative_to(ROOT)} → {REPORT.relative_to(ROOT)}")
