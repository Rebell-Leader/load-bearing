# Agent demo and video script

## What the agent demo shows

An AI research assistant wrote a grant background paragraph with seven real references
([`examples/draft_background.md`](../examples/draft_background.md)). A Claude agent audits it before
submission and rewrites it. The agent has two MCP servers and no other tools: no shell and no file
access.

| Server | Tools | Role |
|---|---|---|
| `load-bearing` | `retraction_status`, `check_references`, `check_paper`, `explain_exposure`, `graph_schema`, `query_graph` | Builds the evidence graph and is the store's single writer |
| `relate` | `read_cypher`, `get_schema` | Relate's own server (`relate serve --mcp stdio --read-only=live`), following that writer |

Recorded run: [`runs/agent_demo.md`](../runs/agent_demo.md). It took 9 turns, 8 tool calls, 111 s and
$0.50 on Claude Opus 5.5. What the agent did:

- **Called `retraction_status` on all 7 DOIs**, then `check_references` at depth 2. Two citations are
  direct hits: `lesne2006` (retracted 2024-06-24, with notice reasons) and `reed2011` (retracted
  2026-07-01, notice found through Crossref).
- **Read every flagged sentence instead of trusting the label**, citing the classifier's measured 33%
  precision. It dropped `larson2012`, whose 56-kDa detection relies on Lesné 2006. It kept `cline2018`
  only for the general oligomer claim, because its reliance is confined to one Aβ*56 subsection.
- **Asked the graph a follow-up through Relate's `read_cypher`**: which references reach Lesné 2006
  within two hops, and through which papers. It wrote and showed its own Cypher.
- **Noticed two things about the graph itself**:
  - It stores only citations that lie on paths to retracted work, so "no path" doesn't mean "clean".
  - One upstream citation is impossible (a 2008 paper "citing" a 2012 one), so it discounted that path.
    That catch became a feature after this run: such citations are now flagged `anachronistic` and
    excluded from every path, and each report lists what it ignored.
- **Rewrote the paragraph without inventing references.** It removed the Aβ*56 and assembly-specific
  claims and marked `[NEW CITATION NEEDED]` where the closing claim lost its support.

Reproduce (about 2 minutes and $0.50; needs the Relate CLI and a Claude credential, either
`ANTHROPIC_API_KEY` or a Claude Code login):

```bash
uv sync --group demo
uv run --group demo python scripts/agent_demo.py --budget 3
```

The run works on a temporary clone of `data/demo.rl`, so the shipped files never change.

## Video script (about 1:45)

| Time | Screen | Voice-over |
|---|---|---|
| 0:00–0:12 | The Lesné 2006 retraction notice next to its citation count | "This *Nature* paper was retracted in 2024 after OpenAlex had counted 2,840 citations. In a 2026 study, none of nine AI research tools reliably caught retracted papers. Flagging a direct citation is easy. The hard part is the papers you rely on that relied on it." |
| 0:12–0:30 | `loadbearing check --doi 10.1016/j.redox.2025.103611 --offline`, scrolling the report | "Load-Bearing follows citations three hops out in Relate and reads the sentence where each one appears. This 2025 Alzheimer's paper has 72 references: 56 lead to retracted work, and 23 of those paths run through method or result citations." |
| 0:30–1:05 | `scripts/agent_demo.py` running, then the transcript: tool calls, the Cline sentence, the Cypher, the rewrite | "For agents, Load-Bearing is an MCP server, alongside Relate's own. Claude audits a research assistant's draft. It finds two retracted papers, reads the evidence before acting, keeps one review for its general claim, queries the graph in Cypher, and rewrites the paragraph without inventing a single reference." |
| 1:05–1:25 | `store.py` with the quantified path query; `relate serve --read-only=live`; `data/demo.rl` | "The core is one Cypher statement: paths from the manuscript to a retracted paper where every hop is a method or result citation. It runs in 1.5 ms. The evidence pack is a single `.rl` file you can hand to an editor. The working graph is a directory store that Relate's MCP server follows live." |
| 1:25–1:45 | [`docs/EVAL.md`](EVAL.md) table | "We measured it honestly: BiomedBERT on SciCite reaches 0.856 macro-F1, and on held-out sentences our classifier finds 69% of real reliance at 33% precision. So every finding shows its sentence, and a person decides." |
