"""Run the claim audit and a pinned PaperOrchestra literature-stage replay."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import contextlib
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import relate

from loadbearing import bib, claim_audit

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/comparison"
PIN = "d9bae997e793a015ed38bb1605be9eb58c00284f"
FINDINGS = {"review_direct", "review_indirect", "review_notice"}


def read_json(path: Path):
    return json.loads(path.read_text())


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def replay_literature_stage(upstream: Path, output: Path, records: list[dict], cases: list[dict]) -> dict:
    """Run upstream discovery scheduling, title verification, enrichment and artifact writing on a replay."""
    revision = subprocess.check_output(["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True).strip()
    if revision != PIN or (upstream / ".env").exists():
        raise ValueError(f"Use a clean PaperOrchestra checkout at {PIN} without a .env")
    sys.path.insert(0, str(upstream))
    with contextlib.redirect_stdout(io.StringIO()):
        from methods.agents.literature_review_agent import CandidatePaper, HybridLiteratureAgent
        from utils import scholar_utils

    output.mkdir(parents=True, exist_ok=True)
    by_title = {r["title"]: r for r in records}
    by_doi = {r["doi"]: r for r in records}
    requests = []

    def search_response(url, *, headers, params, timeout):
        if url != "https://api.semanticscholar.org/graph/v1/paper/search":
            raise ValueError(f"Unexpected replay endpoint: {url}")
        r = by_title[params["query"]]
        requests.append(r["doi"])
        metadata = {"title": r["title"], "year": r["year"], "authors": [{"name": r["first_author"]}],
                    "venue": r["journal"], "journal": {"name": r["journal"]}, "abstract": r["scope"]}
        return SimpleNamespace(status_code=200, json=lambda: {"data": [metadata]})

    def fixed_draft(outline, papers, cutoff):
        keys = {by_title[p.title]["doi"]: p.citation_key for p in papers}
        lines = [r"\documentclass{article}", r"\usepackage{natbib}", r"\begin{document}"]
        for row in cases:
            source = row["input"]
            cite = ",".join(keys[d] for d in source["reference_dois"])
            lines += [f"% claim {row['id']}", source["claim"] + rf" \citep{{{cite}}}", ""]
        return "\n".join(lines + [r"\bibliographystyle{plainnat}", r"\bibliography{references}", r"\end{document}", ""])

    with TemporaryDirectory(prefix="loadbearing-po-") as temp:
        outline = Path(temp) / "outline.json"
        write_json(outline, {"intro_related_work_plan": {"introduction_strategy": {"search_directions": ["fixed fixtures"]}}})
        empty = str(Path(temp) / "absent")
        agent = HybridLiteratureAgent(empty, empty, empty, empty, str(output))
        candidates = [CandidatePaper(title=r["title"], year=r["year"], reason="Public comparison fixture") for r in records]
        agent._discover_candidates = lambda *_: candidates
        agent._synthesize_content = fixed_draft
        actual_requests = scholar_utils.requests
        scholar_utils.requests = SimpleNamespace(get=search_response)
        try:
            agent.run(str(outline), cutoff_date="2026-11")
        finally:
            scholar_utils.requests = actual_requests

    citation_map = read_json(output / "citation_map.json")
    refs = bib.read_references(output / "references.bib")
    manifest = {r["key"]: by_title[citation_map[r["key"]]["title"]]["doi"] for r in refs
                if r["key"] in citation_map and r["title"] == citation_map[r["key"]]["title"]
                and citation_map[r["key"]]["title"] in by_title
                and citation_map[r["key"]]["year"] == by_title[r["title"]]["year"]}
    write_json(output / "citation_dois.json", manifest)
    draft = (output / "updated_template.tex").read_text()
    matched_claims = {i: (s, keys.split(",")) for i, s, keys in
                      re.findall(r"^% claim ([\w-]+)\n(.+) \\citep\{([^}]+)\}$", draft, flags=re.M)}
    inputs = {}
    for case in cases:
        text, keys = matched_claims[case["id"]]
        inputs[case["id"]] = {**case["input"], "claim": text, "reference_dois": [manifest[key] for key in keys]}
    return {"commit": revision, "metadata_mode": "public metadata replay with paraphrased abstracts",
            "requested": len(requests), "accepted": len(refs),
            "bibtex_dois": sum(bool(r["doi"]) for r in refs), "bridged_dois": len(manifest),
            "accepted_dois": sorted(manifest.values()), "input_claims": inputs,
            "identities": [{"doi": doi, "title": by_doi[doi]["title"], "source": by_doi[doi]["source"]}
                           for doi in sorted(manifest.values())]}


def score(cases: list[dict], results: list[dict]) -> dict:
    by_id = {r["id"]: r for r in results}
    checked = [(r["expected"]["action"], by_id.get(r["id"], {}).get("action")) for r in cases]
    required = sum(e in FINDINGS for e, _ in checked)
    exact_findings = sum(e == a and e in FINDINGS for e, a in checked)
    false_alerts = sum(a in FINDINGS and e not in FINDINGS for e, a in checked)
    return {"cases": len(cases), "returned": sum(a is not None for _, a in checked),
            "exact_actions": sum(e == a for e, a in checked), "required_review_actions": required,
            "correct_review_actions": exact_findings, "false_alerts_on_controls": false_alerts,
            "indirect_detected": sum(e == a == "review_indirect" for e, a in checked),
            "indirect_total": sum(e == "review_indirect" for e, _ in checked)}


def score_revisions(cases: list[dict], results: list[dict], audit_rows: list[dict]) -> dict:
    """Count unchanged controls and label-matched revisions that cite all audited source URLs."""
    references = {r["id"]: r for r in audit_rows}
    by_id = {r["id"]: r for r in results}
    controls_preserved = grounded_revisions = 0
    for case in cases:
        submitted = by_id.get(case["id"])
        if not submitted:
            continue
        expected = case["expected"]["action"]
        unchanged = submitted["revision"] == case["input"]["claim"]
        if expected not in FINDINGS:
            controls_preserved += unchanged
        elif submitted["action"] == expected and not unchanged:
            links = {item["notice"]["url"] for item in references[case["id"]]["findings"] if item["action"] == expected}
            links.update(item["evidence"]["url"] for item in references[case["id"]]["findings"]
                         if item["action"] == expected and "evidence" in item)
            grounded_revisions += bool(links and links.issubset(submitted["source_urls"]))
    return {"controls_preserved_verbatim": controls_preserved,
            "controls_total": sum(case["expected"]["action"] not in FINDINGS for case in cases),
            "grounded_review_revisions": grounded_revisions}


_OUTPUT_SCHEMA = {
    "type": "object", "required": ["cases"], "additionalProperties": False,
    "properties": {"cases": {"type": "array", "items": {
        "type": "object", "required": ["id", "action", "revision", "source_urls"], "additionalProperties": False,
        "properties": {"id": {"type": "string"}, "action": {"type": "string"}, "revision": {"type": "string"},
                       "source_urls": {"type": "array", "items": {"type": "string"}}},
    }}},
}
_SYSTEM = """Audit fixed research draft spans. Rely only on evidence available in this run. A matched citation identity
establishes that a reference exists. Scope every decision to the exact claim and notice. Allowed actions:
review_direct, review_indirect, review_notice, retain_for_this_notice, retain_with_notice, no_notice_as_of,
insufficient_evidence. For a review action, give a scoped replacement or a qualification in revision. For any other
action, copy the original span verbatim as revision. Keep existing references and add no citations. Put supporting
URLs from the supplied evidence in source_urls. Preserve any fixture_condition. For the MCP arm use audit_claims
once with the whole array of claim objects, then revise. Return one decision for each supplied ID."""


def run_agent(arm: str, inputs: list[dict], evidence, config: dict, cwd: Path) -> dict:
    prompt = json.dumps({"arm": arm, "claims": inputs, "evidence": evidence}, ensure_ascii=False)
    command = ["claude", "-p", "--model", "haiku", "--tools", "", "--strict-mcp-config", "--mcp-config",
               json.dumps(config), "--setting-sources", "", "--no-session-persistence", "--permission-mode",
               "dontAsk", "--max-turns", "5", "--max-budget-usd", "0.15", "--output-format", "stream-json",
               "--verbose", "--json-schema", json.dumps(_OUTPUT_SCHEMA), "--system-prompt", _SYSTEM]
    if arm == "mcp_graph":
        command += ["--allowedTools", "mcp__claim_pilot__audit_claims"]
    proc = subprocess.run(command, input=prompt, text=True, capture_output=True, cwd=cwd, timeout=145,
                          env={**os.environ, "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"})
    events = [json.loads(line) for line in proc.stdout.splitlines() if line.startswith("{")]
    final = next((e for e in reversed(events) if e.get("type") == "result"), {})
    responses = final.get("structured_output", {})
    tool_calls = [c["name"] for event in events if event.get("type") == "assistant"
                  for c in event.get("message", {}).get("content", []) if c.get("type") == "tool_use"]
    if proc.returncode or final.get("is_error") or not responses.get("cases"):
        raise RuntimeError(f"{arm}: exit {proc.returncode}, {final.get('subtype')}, tools {tool_calls}")
    return {"rows": responses["cases"], "tools": tool_calls, "usage": final.get("usage"),
            "model_usage": final.get("modelUsage"), "cost_usd": final.get("total_cost_usd"),
            "duration_ms": final.get("duration_ms")}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paper-orchestra", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "runs/claim_pilot")
    parser.add_argument("--claude", action="store_true", help="Run four matched public-fixture trials using the local Claude login")
    parser.add_argument("--serve", type=Path, help="Serve a prepared claim snapshot over MCP stdio")
    args = parser.parse_args()
    if args.serve:
        claim_audit.serve(args.serve)
        return
    if args.claude and not args.paper_orchestra:
        parser.error("--claude compares identical PaperOrchestra artifacts and requires --paper-orchestra")
    args.output.mkdir(parents=True, exist_ok=True)
    cases = [json.loads(line) for line in (DATA / "cases.jsonl").read_text().splitlines()]
    pilot_cases = [case for case in cases if case["split"] == "pilot"]
    data_files = [DATA / f for f in ("cases.jsonl", "claim_facts.json", "paper_orchestra_metadata.json")]
    report = {"inputs_sha256": {p.name: sha256(p.read_bytes()).hexdigest() for p in data_files}}
    if args.paper_orchestra:
        identity = replay_literature_stage(args.paper_orchestra, args.output / "paper-orchestra",
                                           read_json(data_files[2]), cases)
        selected = identity.pop("input_claims")
        if any(selected[r["id"]] != r["input"] for r in cases):
            raise ValueError("The PaperOrchestra adapter changed benchmark inputs")
        report["paper_orchestra"] = identity
    else:
        selected = {r["id"]: r["input"] for r in cases}

    with TemporaryDirectory(prefix="loadbearing-claim-pilot-") as temp:
        snapshot = Path(temp) / "claim.rl"
        claim_audit.build_snapshot(snapshot, read_json(data_files[1]))
        conn = relate.connect(str(snapshot), read_only=True)
        try:
            arms = {mode: [{"id": id, **claim_audit.audit(conn, **source, mode=mode)} for id, source in selected.items()]
                    for mode in ("direct", "untyped", "claim_aware")}
        finally:
            conn.close()
        report["graph_arms"] = {name: {"metrics": score(cases, rows), "pilot_split_metrics": score(pilot_cases, rows),
                                      "rows": rows} for name, rows in arms.items()}
        report_path = args.output / "report.json"
        write_json(report_path, report)
        print({name: results["metrics"] for name, results in report["graph_arms"].items()}, flush=True)

        if args.claude:
            empty = {"mcpServers": {}}
            mcp = {"mcpServers": {"claim_pilot": {"command": sys.executable,
                   "args": [str(Path(__file__).resolve()), "--serve", str(snapshot)]}}}
            inputs = [{"id": id, **source} for id, source in selected.items()]
            treatment = {"identity": (report.get("paper_orchestra", {}).get("identities", []), empty),
                         "direct": (arms["direct"], empty), "static_graph": (arms["claim_aware"], empty),
                         "mcp_graph": (None, mcp)}
            report["agent_arms"] = {}
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = {name: pool.submit(run_agent, name, inputs, evidence, config, Path(temp))
                           for name, (evidence, config) in treatment.items()}
                for name, future in futures.items():
                    try:
                        arm = future.result()
                        arm["metrics"] = score(cases, arm["rows"])
                        arm["metrics"].update(score_revisions(cases, arm["rows"], arms["claim_aware"]))
                        arm["pilot_split_metrics"] = {**score(pilot_cases, arm["rows"]),
                                                      **score_revisions(pilot_cases, arm["rows"], arms["claim_aware"])}
                    except (RuntimeError, subprocess.TimeoutExpired) as error:
                        arm = {"error": str(error)}
                    report["agent_arms"][name] = arm
                    write_json(report_path, report)
                    print(name, arm.get("metrics", arm.get("error")), flush=True)


if __name__ == "__main__":
    main()
