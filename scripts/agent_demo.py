"""Agent demo: a Claude agent audits a research assistant's draft before it goes out.

  uv run --group demo python scripts/agent_demo.py [--store DIR] [--budget 3.0]

The agent (Claude Agent SDK, Claude Opus 5.5) gets exactly two MCP servers and no built-in tools:
  load-bearing  the six Load-Bearing tools (the single writer of the store)
  relate        Relate's own read_cypher / get_schema, following the writer with --read-only=live
It runs on a temporary clone of data/demo.rl unless --store is given, and writes a Markdown
transcript to runs/agent_demo.md. Credentials: ANTHROPIC_API_KEY, or your Claude Code login.
"""

import argparse
import asyncio
import json
import os
import re
import shutil
import subprocess
import tempfile
import textwrap
import time
from pathlib import Path

from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock, ToolResultBlock,
                              ToolUseBlock, UserMessage, query)

ROOT = Path(__file__).resolve().parents[1]
DRAFT = ROOT / "examples" / "draft_background.md"
OUT = ROOT / "runs" / "agent_demo.md"

LB_TOOLS = ["retraction_status", "check_references", "check_paper", "explain_exposure", "graph_schema", "query_graph"]
RELATE_TOOLS = ["read_cypher", "get_schema"]

TASK = """A PI is finalizing the background section of a grant application. An AI research assistant produced
the draft below. Before it is submitted:

1. Audit the references with the Load-Bearing tools: call retraction_status on every DOI, then
   check_references on the BibTeX (label "grant-draft", depth 2).
2. For each problem, give the bib key it affects and quote the evidence: the notice's reasons and date,
   and for a load-bearing finding the citing sentence.
3. Answer one follow-up from the evidence graph itself with the relate tools (get_schema, read_cypher):
   which of the draft's references reach Lesné 2006 (doi 10.1038/nature04533) within two citation hops,
   and through which papers. Show the Cypher you ran.
4. Rewrite the paragraph so that no claim rests on retracted work, and keep the claims that have
   independent support. Do not invent references: you may only keep or drop the ones given, and you
   must say where a claim now needs a new citation. Return the revised BibTeX.

Answer in Markdown with the sections: Findings, Graph check, Revised paragraph, Revised BibTeX.

--- DRAFT ---
"""


def system_prompt() -> str:
    skill = (ROOT / "skills" / "load-bearing" / "SKILL.md").read_text()
    skill = re.sub(r"^---.*?---\s*", "", skill, flags=re.S)  # drop the frontmatter
    return ("You audit scholarly citations for reliance on retracted science. You have two MCP servers: "
            "load-bearing (checks) and relate (read-only Cypher over the same evidence graph; the manuscript you "
            "check is stored as (:Manuscript {id: 'M:<label>'})). Follow this skill:\n\n" + skill)


def clip(text: str, n: int) -> str:
    text = text if isinstance(text, str) else json.dumps(text, ensure_ascii=False)
    return text if len(text) <= n else text[: n - 1] + "…"


def result_text(block: ToolResultBlock) -> str:
    c = block.content
    if isinstance(c, list):
        return "\n".join(part.get("text", "") for part in c if isinstance(part, dict))
    return c or ""


async def run(store: str, budget: float) -> int:
    env = {**os.environ, "LOADBEARING_STORE": store, "DO_NOT_TRACK": "1"}
    options = ClaudeAgentOptions(
        model="claude-opus-5-5",
        effort="high",
        system_prompt=system_prompt(),
        mcp_servers={
            "load-bearing": {"type": "stdio", "command": "uv",
                             "args": ["run", "--quiet", "--directory", str(ROOT), "loadbearing-mcp"],
                             "env": {"LOADBEARING_STORE": store}},
            "relate": {"type": "stdio", "command": "relate",
                       "args": ["serve", "--mcp", "stdio", "--database", store, "--read-only=live"],
                       "env": {"DO_NOT_TRACK": "1"}},
        },
        tools=[],  # no shell, no file access: only the two MCP servers
        allowed_tools=[f"mcp__load-bearing__{t}" for t in LB_TOOLS] + [f"mcp__relate__{t}" for t in RELATE_TOOLS],
        permission_mode="dontAsk",
        strict_mcp_config=True,
        max_budget_usd=budget,
        cwd=str(ROOT),
        env=env,
    )
    prompt = TASK + DRAFT.read_text()
    lines = [f"# Agent demo transcript ({time.strftime('%Y-%m-%d %H:%M')})", "",
             "Claude Opus 5.5 (Claude Agent SDK) with two MCP servers and no built-in tools:",
             "`load-bearing` (6 tools, the store's single writer) and `relate` "
             "(`relate serve --mcp stdio --read-only=live`, following that writer).", "",
             "## Task", "", "```text", TASK.strip(), "```", "", f"Draft: [`examples/draft_background.md`](../examples/draft_background.md)", "",
             "## Steps", ""]
    calls: dict[str, str] = {}
    final = None
    t0 = time.time()
    async for msg in query(prompt=prompt, options=options):
        if isinstance(msg, AssistantMessage):
            for b in msg.content:
                if isinstance(b, ToolUseBlock):
                    server, _, tool = b.name.removeprefix("mcp__").partition("__")
                    calls[b.id] = b.name
                    args = json.dumps(b.input, ensure_ascii=False)
                    lines += [f"**→ `{server}` · `{tool}`**", "", "```json", clip(args, 1500), "```", ""]
                    print(f"[{time.time() - t0:5.0f}s] call {server}.{tool}", flush=True)
                elif isinstance(b, TextBlock) and b.text.strip():
                    lines += [textwrap.indent(b.text.strip(), "> ") if len(b.text) < 600 else b.text.strip(), ""]
        elif isinstance(msg, UserMessage) and isinstance(msg.content, list):
            for b in msg.content:
                if isinstance(b, ToolResultBlock):
                    text = result_text(b)
                    status = "error" if b.is_error else "result"
                    lines += [f"<details><summary>{status} ({len(text):,} chars)</summary>", "", "```json",
                              clip(text, 2500), "```", "</details>", ""]
        elif isinstance(msg, ResultMessage):
            final = msg
    if final is None:
        print("no result message")
        return 1
    if final.result and final.result.strip() in lines:  # the last assistant turn is the final answer itself
        lines[lines.index(final.result.strip())] = "_(final answer below)_"
    lines += ["## Final answer", "", final.result or "(empty)", "", "## Run", "",
              f"- turns: {final.num_turns}, tool calls: {len(calls)}, wall time: {final.duration_ms / 1000:.0f} s",
              f"- cost: ${final.total_cost_usd or 0:.2f} (budget cap ${budget:.2f}), stop: {final.subtype}",
              f"- store: a clone of `data/demo.rl` ({'temporary' if 'tmp' in store else store})", ""]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines))
    print(f"\n{final.subtype}: {final.num_turns} turns, {len(calls)} tool calls, "
          f"{final.duration_ms / 1000:.0f}s, ${final.total_cost_usd or 0:.2f} -> {OUT}")
    return 0 if not final.is_error else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", help="directory store to use (default: a temporary clone of data/demo.rl)")
    ap.add_argument("--budget", type=float, default=3.0, help="max spend in USD for this run")
    args = ap.parse_args()
    tmp = None
    store = args.store
    if not store:
        tmp = tempfile.mkdtemp(prefix="lb-agent-")
        store = os.path.join(tmp, "evidence")
        subprocess.run(["relate", "clone", str(ROOT / "data" / "demo.rl"), store], check=True,
                       capture_output=True, env={**os.environ, "DO_NOT_TRACK": "1"})
    try:
        return asyncio.run(run(store, args.budget))
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
