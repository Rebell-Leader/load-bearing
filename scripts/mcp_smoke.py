"""Smoke-test both MCP servers over real stdio, the way `.mcp.json` runs them.

  uv run python scripts/mcp_smoke.py [store.rl]

Clones the store (default data/demo.rl) into a temporary directory store, then runs the
Load-Bearing server (the single writer) and Relate's own server (`--read-only=live`, following
the writer) side by side. The shipped files are never modified. Without the Relate CLI on PATH,
only the Load-Bearing half runs, on a temporary copy of the .rl file.
"""

import asyncio
import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

from mcp import Client
from mcp.client.stdio import StdioServerParameters

from loadbearing.claim_audit import DEMO_CLAIMS
from loadbearing import store as lb_store

SRC = sys.argv[1] if len(sys.argv) > 1 else "data/demo.rl"
ROOT = "W4408770418"  # the demo paper (Redox Biology 2025)
LESNE = "10.1038/nature04533"
QUIET_ENV = {**os.environ, "DO_NOT_TRACK": "1"}

SMALL_BIB = """@article{lesne2006, title={A specific amyloid-beta protein assembly in the brain impairs memory}, doi={10.1038/nature04533}}
@article{cline2018, title={The Amyloid-beta Oligomer Hypothesis}, doi={10.3233/jad-179941}}
@article{xie2013, title={Sleep drives metabolite clearance from the adult brain}, doi={10.1126/science.1241224}}
"""

ok = True


def report(name, passed, detail=""):
    global ok
    ok &= bool(passed)
    print(f"{'OK  ' if passed else 'FAIL'} {name:<40} {detail}")


def text(result) -> dict:
    return json.loads(result.content[0].text)


async def main() -> int:
    tmp = tempfile.mkdtemp()
    has_relate = shutil.which("relate") is not None
    if has_relate:
        store = os.path.join(tmp, "evidence")
        subprocess.run(["relate", "clone", SRC, store], check=True, capture_output=True, env=QUIET_ENV)
    else:
        store = os.path.join(tmp, "smoke.rl")
        shutil.copy(SRC, store)
        print("relate CLI not on PATH: testing the Load-Bearing server only")

    lb_params = StdioServerParameters(command="uv", args=["run", "--quiet", "loadbearing-mcp"],
                                      env={**QUIET_ENV, "LOADBEARING_STORE": store}, cwd=os.getcwd())
    relate_params = StdioServerParameters(
        command="relate", args=["serve", "--mcp", "stdio", "--database", store, "--read-only=live"],
        env=QUIET_ENV, cwd=os.getcwd())

    async with contextlib.AsyncExitStack() as stack:
        lb = await stack.enter_async_context(Client(lb_params, read_timeout_seconds=600))
        rl = await stack.enter_async_context(Client(relate_params, read_timeout_seconds=120)) if has_relate else None

        # Load-Bearing server
        tools = {t.name for t in (await lb.list_tools()).tools}
        report("load-bearing: list_tools", len(tools) == 7 and "audit_claims" in tools, ", ".join(sorted(tools)))
        featured = json.loads(DEMO_CLAIMS.read_text())["rodents"]["claims"]
        audit = await lb.call_tool("audit_claims", {"claims": featured})
        actions = [row["action"] for row in audit.structured_content["result"]]
        report("load-bearing: audit_claims", actions == ["review_indirect", "retain_for_this_notice"], str(actions))
        r = text(await lb.call_tool("retraction_status", {"dois": [LESNE, "10.1126/science.1241224"]}))
        report("load-bearing: retraction_status", r[0]["status"] == "retracted" and r[1]["status"] == "no_notice_found",
               f"{r[0]['status']} ({r[0]['notice']['date'] if r[0]['notice'] else '-'}), {r[1]['status']}")
        s = text(await lb.call_tool("graph_schema", {}))
        report("load-bearing: graph_schema", s["node_counts"].get("Retracted", 0) > 0, f"{s['node_counts']}")
        q = text(await lb.call_tool("query_graph", {"cypher": s["examples"]["most_reached_retracted"], "parameters": {"root": ROOT}}))
        report("load-bearing: query_graph", bool(q.get("rows")), f"top: {q['rows'][0]['title'][:45]}… via {q['rows'][0]['via']}")
        w = text(await lb.call_tool("query_graph", {"cypher": "CREATE (:Paper {id: 'evil'})"}))
        report("load-bearing: query_graph refuses writes", "error" in w, (w.get("error") or "")[:60])
        e = text(await lb.call_tool("explain_exposure", {"manuscript_id": ROOT, "retracted": LESNE}))
        report("load-bearing: explain_exposure", e.get("total_paths", 0) > 0,
               f"{e.get('total_paths')} paths, statuses {sorted({p['status'] for p in e.get('paths', [])})}")

        # Relate's own server, live on the same store
        if rl:
            rtools = {t.name for t in (await rl.list_tools()).tools}
            report("relate: list_tools (read-only)", rtools == {"read_cypher", "get_schema"}, ", ".join(sorted(rtools)))
            schema = text(await rl.call_tool("get_schema", {"sample_size": -1}))
            report("relate: get_schema", schema.get("Retracted", {}).get("count", 0) > 0,
                   ", ".join(f"{k}={v['count']}" for k, v in schema.items()))
            env = text(await rl.call_tool("read_cypher", {"statement": lb_store.LOAD_BEARING_ONLY, "parameters": {"root": ROOT}}))
            report("relate: read_cypher (pitch query)", bool(env.get("rows")) and not env.get("error"),
                   f"{len(env['rows'])} load-bearing paths in {env.get('elapsed_ms', 0):.1f} ms")
            refused = await rl.call_tool("read_cypher", {"statement": "CREATE (:Paper {id: 'evil'})"})
            report("relate: read_cypher refuses writes", refused.is_error, refused.content[0].text[:60])

        # An agent checks a draft while Relate's server is up: one writer, one live follower.
        t0 = time.time()
        raw = await lb.call_tool("check_references", {"references": SMALL_BIB, "label": "smoke", "depth": 2})
        c = text(raw)
        if "findings" not in c:
            report("load-bearing: check_references", False, raw.content[0].text[:200])
        else:
            direct = [f for f in c["findings"] if f["status"] == "direct"]
            key = direct[0]["via_your_references"][0].get("bib_key") if direct else None
            report("load-bearing: check_references (depth 2)", key == "lesne2006",
                   f"{c['summary']['by_status']} in {time.time() - t0:.0f}s; direct via bib key {key}")
        if rl:
            stmt = ("MATCH (m:Manuscript {id: 'M:smoke'})-[:CITES]->(:Paper)-[:CITES]->{0,2}(bad:Retracted) "
                    "RETURN count(DISTINCT bad) AS retracted")
            for attempt in range(20):
                rows = text(await rl.call_tool("read_cypher", {"statement": stmt}))["rows"]
                if rows and rows[0]["retracted"] > 0:
                    break
                await asyncio.sleep(0.25)
            report("relate: sees the new check live", rows and rows[0]["retracted"] > 0,
                   f"M:smoke reaches {rows[0]['retracted'] if rows else 0} retracted papers, visible after ~{attempt * 0.25:.2f}s")

    shutil.rmtree(tmp)
    print("all passed" if ok else "SOME CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
