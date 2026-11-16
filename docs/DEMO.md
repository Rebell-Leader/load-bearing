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

## Video (about 1:55)

The silent video is recorded with headless Chromium by [`scripts/record_demo.py`](../scripts/record_demo.py) from the
scene pages in [`demo/scenes/`](../demo/scenes/). Every number on screen comes from the repository: the script runs the
offline check and the Relate CLI query, reads the store and the recorded agent transcript, and drives the hosted
viewer. Scenes 1–4 and 6 are timelines rendered frame by frame; scene 5 is the live viewer with a visible cursor.

```bash
uv run --with playwright python scripts/record_demo.py                # demo/build/load-bearing-demo.mp4
uv run --with playwright python scripts/record_demo.py --scenes 3     # re-record one scene, then reassemble
```

It writes `demo/build/load-bearing-demo.mp4` (1920×1080, 30 fps, no audio), one clip per scene,
`load-bearing-demo.srt` with the voice-over below split by sentence at its time codes, and `timing.md`.
Each scene ends on a still frame, so a scene can be held longer if a voice-over line runs long.

| Time | Screen | Voice-over |
|---|---|---|
| 0:00–0:17 | **The problem.** Lesné 2006: the paper, its 2,840 OpenAlex citations, the retraction stamp and notice reasons; then a two-hop path (your draft → Larson & Lesné 2012 → Lesné 2006) with the method sentence | "This Nature paper was retracted in 2024, after OpenAlex had counted 2,840 citations. In a 2026 study, none of nine AI research tools reliably caught retracted papers. Flagging a direct citation is easy. The hard part is what your sources relied on." |
| 0:17–0:35.5 | **Command line.** `loadbearing check --doi 10.1016/j.redox.2025.103611 --store data/demo.rl --offline` typed and run; the report scrolls to the load-bearing findings and the summary | "Load-Bearing follows citations three hops out into a Relate graph, and reads the sentence where each one appears. This 2025 Alzheimer's paper has 72 references. 56 of them lead to papers marked retracted, and 23 of those papers are reached only through method or result citations." |
| 0:35.5–0:58.5 | **For agents.** The recorded agent run replayed: eight tool calls across both MCP servers, the Cline 2018 sentence and the decisions, the agent's own Cypher with its result, and the rewrite as a word diff | "For agents, Load-Bearing is an MCP server, next to Relate's own. Here Claude audits a research assistant's draft. It finds two retracted papers, reads the evidence before acting, keeps one review for its general claim, queries the graph in Cypher, and rewrites the paragraph without inventing a single reference." |
| 0:58.5–1:21 | **Inside Relate.** `LOAD_BEARING_ONLY` from `store.py` with its two key clauses highlighted; the Relate CLI running it on `data/demo.rl` with the measured time; the single-file pack and the live directory store | "The core is one Cypher statement: paths from the manuscript to a retracted paper where every hop is a method or result citation. Relate answers it in a few milliseconds. The evidence pack is a single file you can hand to an editor, and the working graph is a directory store that Relate's MCP server follows live." |
| 1:21–1:37.5 | **In the browser.** The live viewer on GitHub Pages: filter to load-bearing, open Lesné 2006, scroll the path diagram and sentences, run a Cypher preset in the console | "The same graph runs in the browser, on Relate's WebAssembly build. Pick a retracted paper, see every path and the sentence behind each citation, and query it in Cypher. Nothing to install, and nothing leaves the page." |
| 1:37.5–1:55 | **Measured, not assumed.** SciCite macro-F1 against the rules, held-out recall and precision with its confidence interval, an example sentence, and the end card with links | "We measured it honestly. On SciCite, the intent model reaches 0.856 macro-F1. On our held-out sentences, the rules alone do as well: 69 percent of real reliance found, at 33 percent precision. So every finding shows its sentence, and a person decides." |
