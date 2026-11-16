# Week-1 spike notes (2026-11-16)

Goal: prove the core loop on real data. Read a bibliography, build the citation graph out to three hops in
Relate, read the citing sentences on paths that reach retracted papers, and report.

## Relate 1.0.1: verified

`scripts/probe_dialect.py` ran 8 of 8 checks OK against a single-file store:

| Check | Result |
|---|---|
| Single-file store, `CREATE`, reopen and query | OK; a 20k-node graph is a 6.5 MB `.rl` file |
| Uniqueness constraint | OK |
| Quantified path pattern with inline relationship `WHERE` | OK; background-only paths are excluded |
| `date()` values and comparison (citations made after a retraction) | OK |
| Full-text index and `SEARCH` | OK |
| Vector index and `SEARCH` | OK |
| `UNWIND` bulk writes | 20k relationships in 0.33 s |

Gotchas worth remembering:

- `duration.between(a, b).days` returns only the days *component* (5 for 2024-06-24 → 2025-03-01).
  Use `duration.inDays(a, b).days` for a day count.
- `MERGE (p:Paper {id: …, title: …, year: …})` with a full property map took 9.5 s for 20k nodes.
  Merge on the key alone, then `SET` the rest (as `store.upsert_papers` does).

## Data sources: verified

| Source | What we use | Constraint found |
|---|---|---|
| OpenAlex | works, `referenced_works`, `is_retracted` (104,657 retracted works) | Without a key: a shared daily budget per IP (about 1,000 requests at $0.0001 each), and cursor paging is refused |
| OpenAlex filter `is_retracted:true,cited_by:A\|B\|…` | Server-side intersection: the retracted works among the references of up to 100 papers, in one request | — |
| Retraction Watch (Crossref GitLab CSV, 68 MB) | notice nature, date, reasons; 73,822 records | Joined by DOI |
| Europe PMC JATS | citing sentence and section for open-access papers | Only the open-access subset |
| Semantic Scholar | fallback contexts and intents | Partial: 33 of 89 references had contexts in the test paper |

Data-quality finding: OpenAlex and Semantic Scholar both list Lesné 2006 as a reference of
10.1038/s41467-024-49028-z, but the PMC full text (80 references) never cites it. Metadata edges can be
wrong, which is why every citation carries an `evidence` label (`fulltext`, `s2`, `metadata_only`,
`no_fulltext`) and unread paths are reported as **unverified**, not as exposure.

## Budget lesson

The first live run used ~630 OpenAlex requests. Hop 3 issued one `cites:` lookup per (retracted work,
batch) pair. It now asks for the batch's reference lists once, so hop 3 costs at most 2 requests per 100
papers. All responses are cached in `data/raw/cache/`, so re-runs are free and work offline.

## First live result

Input: the 72 references of a 2025 *Redox Biology* paper on astrocytic ceruloplasmin and memory
(10.1016/j.redox.2025.103611), which is in PMC. The same run on the reference list as a `.bib`
(`examples/redox2025.bib`) gives the same paths. Full report: [`runs/redox2025.txt`](../runs/redox2025.txt).

| Measure | Value |
|---|---|
| References resolved | 72 / 72 |
| References that reach a retracted paper within 3 hops | 56 |
| Retracted papers reached | 349 (277 matched to a Retraction Watch notice) |
| Citations on those paths | 1,289 |
| Citing sentence read | 606 (47%): 577 from Europe PMC full text, 29 from Semantic Scholar |
| Made after the retraction | 60 |
| Status per retracted paper | 10 load-bearing, 117 unverified, 222 mention-only |
| Store | `data/demo.rl`, 926 papers, 1,305 citations, 2.8 MB |
| Time | ~6 min cold, ~2 min from cache, 0.16 s `--offline` |

Findings worth showing:

- **Lesné 2006 (Aβ*56, retracted 2024)** is reached through 25 of the 72 references. One path is
  load-bearing: a 2011 review used the oligomer detection it reported.
- **A meta-analysis pooled a later-retracted study.** A systematic review and meta-analysis of neural
  stem-cell therapy in rodent Alzheimer's models (Stem Cell Res Ther, Jan 2023,
  10.1186/s13287-022-03231-1) includes in its pooled studies ("22 mice trials … and 8 rat trials … were
  selected") a rat study retracted in August 2023 for image duplication and manipulation. The
  meta-analysis predates the retraction; its pooled estimate now includes retracted data.
- **Retractions cascade.** Two papers in this graph were retracted in 2026 with the reason
  "Cites Retracted Work".

## Bugs found and fixed during the spike

1. Elsevier-style JATS stores reference DOIs in `<ext-link ext-link-type="doi" xlink:href>`, not
   `<pub-id>`. Reading it raised coverage from 21% to 47% and lit up the first hop.
2. OpenAlex prefixes retracted titles ("RETRACTED ARTICLE: …"); title matching now strips it, and the
   fallback uses word containment instead of exact prefix equality.
3. Intent v0 first defaulted every cue-less Discussion sentence to "result", which put generic framing
   on load-bearing paths. Now only the Results section, or an explicit cue, implies reliance.

## Known weaknesses (honest list)

- Intent rules are unevaluated. Several load-bearing "result" labels are still generic statements.
  Week 2 needs a hand-labelled sample (~150 citations) and a precision number.
- 53% of on-path citations are unread: 49% have no open full text, 4% weren't found in the text that
  was read (metadata edges can be wrong; see the Lesné / s41467 case above).
- 72 of 349 retracted works have no Retraction Watch match by DOI, so no date or reasons are shown.
- Without an OpenAlex key the daily budget allows about one cold check per day. This spike used
  ~700 of ~1,000 free requests today.

## Week 2, step 1: MCP server and skill (2026-11-16)

- `loadbearing-mcp` (mcp 2.3 `MCPServer`, stdio) exposes six tools: `retraction_status`,
  `check_references`, `check_paper`, `explain_exposure`, `graph_schema`, `query_graph`.
  `query_graph` opens the store with `relate.connect(path, read_only=True)`, so Relate itself refuses
  writes (`WriteOnReadOnlyAccessDatabase`).
- `scripts/mcp_smoke.py` drives the server over real stdio with the MCP client. All 7 checks pass.
  `check_references` at depth 2 on a 3-entry `.bib` takes 5 s, and the direct finding comes back with
  the author's own key (`lesne2006`).
- `skills/load-bearing/SKILL.md` ("check before you cite"), linked into `.claude/skills/`, and a
  project `.mcp.json`.
- Bug found by the smoke test: the BibTeX reader assumed one field per line, so single-line entries
  (common in agent output) lost their DOI. Replaced with a brace-aware parser and tests.
## Week 2, step 2: Relate's own MCP server (2026-11-16, Relate CLI v1.0.2)

- `relate serve --mcp stdio --read-only` lists exactly `read_cypher` and `get_schema`. On the demo graph
  the pitch query takes 1.5 ms (15 paths) and the full exposure query 30 ms (740 paths), with the same
  statuses the Python check computes. Writes are refused (`Only MATCH queries are allowed`).
- **Finding: a `.rl` store can't be shared with a running reader.** While `relate serve --read-only`
  holds `demo.rl`, a Python writer fails with `storage locked` (the docs describe the reverse direction).
  The first `.mcp.json`, with both servers on `demo.rl`, would have broken every agent check.
- **Fix: a directory store with a live follower.** `relate clone data/demo.rl data/evidence`, then
  `relate serve --mcp stdio --database data/evidence --read-only=live`. A Python 1.0.1 writer commits
  beside it, and the follower sees the commit within about 0.25 s. The Load-Bearing server serializes its
  own writes with a lock, since tool calls run in worker threads.
- `scripts/mcp_smoke.py` now runs both servers side by side on a temporary clone. All 12 checks pass,
  including "Relate sees the agent's new check live". Shipped stores stay byte-identical.
- **Quirk for the Relate team:** an agent can't `EXPLAIN` through `read_cypher`. The server prepends
  `EXPLAIN` to classify each call, so the statement becomes `EXPLAIN EXPLAIN …` (parse error).
- `--offline` checks now open the store with `read_only=True`; before, the schema statements and the
  checkpoint on close rewrote `demo.rl`.

## Week 2, step 3: citation-intent evaluation (2026-11-16)

Full report: [EVAL.md](EVAL.md). In brief:

- SciCite test: rules v0 0.603 macro-F1; BiomedBERT fine-tuned on SciCite **0.856** (1.2 min on the GPU).
- In-domain (Claude labels, blind): v0 found 27% of reliance. The SciCite model alone found 12%,
  because SciCite files "X was shown to Y" under background.
- v1 = strong critical cues + method model + cited-work type (review vs primary) + two guards. On the
  tuning sample it estimates P 0.82 / R 0.87. On a held-out random sample it gets **P 0.33 / R 0.69**.
  The guards were tuned in-sample and the tuning sample was stratified, so the held-out number is the
  honest one.
- Negative result: NLI claim alignment between sentence and cited title has no signal (AUC 0.50).
- Demo after the v1 rebuild: 23 load-bearing, 155 unverified, 171 mention-only (v0: 10 / 117 / 222).
  `:Review` label on 209 cited works; `CITES.classifier` records the classifier.
- Next for precision: expert labels (CSV and guideline ready), then fine-tune on our own definition.

## Week 2, step 4: agent demo (2026-11-16)

- `scripts/agent_demo.py`: the Claude Agent SDK, Claude Opus 5.5, two stdio MCP servers (`load-bearing`
  and `relate --read-only=live`), `tools=[]`, `dontAsk`, a budget cap, and a temporary store clone.
  Recorded run: `runs/agent_demo.md`. See [DEMO.md](DEMO.md) for the video script.
- The first run exposed missing notices for papers Retraction Watch hasn't recorded yet.
  `crossref.py` now looks them up through Crossref (`filter=updates:<doi>`). On the demo pack:
  277 notices from Retraction Watch, 44 from Crossref, 28 with only the OpenAlex flag.
- The agent found an impossible upstream citation (2008 → 2012). Done: `store.flag_citation_dates`
  marks a citation `anachronistic` when the cited paper is dated more than a year after the citing one
  (the slack covers "in press" references), and every path query excludes it. When the cited paper is
  retracted, the edge is marked `year_conflict` instead: it is kept, because OpenAlex sometimes dates a
  retracted paper by its notice, but the path can only be `unverified`. Demo graph: 1 excluded
  (Shankar 2008 → a 2012 paper), 1 conflict (a 2011 cancer review → a 2020 retracted cloud-computing
  paper, plainly a mis-linked reference). Reports list both.

## Week 2, step 5: browser viewer (2026-11-16)

- `viewer/index.html`: one static page on `@relate/relate-wasm@1.0.2` from jsDelivr. The WASM build can't
  open `.rl` files, so `scripts/export_viewer.py` writes `viewer/evidence.json` (0.9 MB, two
  manuscripts), loaded into an in-memory `RelateDb` with `UNWIND … CREATE`.
- The page runs the Cypher statements from `store.py`, embedded in the pack, so the CLI, the MCP server
  and the browser share one query. Its numbers match the CLI (56/72 references, 349 retracted,
  23 load-bearing; grant draft: 2 direct + 1 load-bearing).
- Measured in the browser pane: engine ready in ~60 ms after download, pack loaded in 260–380 ms,
  exposure query 741 paths in ~100 ms, console queries 2–6 ms. No horizontal scroll at 375 px.
- Not published as a claude.ai Artifact: artifact pages may load CDN scripts only at versions at least
  two weeks old, and relate-wasm 1.0.x is from 2026-11-11/12. Vendoring the three engine files would
  get around this if a hosted link is wanted before then; GitHub Pages works as is.

## Next (week 2)

1. ~~MCP: serve the store read-only for agents, plus a skill ("check before you cite").~~ Done, see above.
2. Intent v1: evaluate the rules on a hand-labelled sample, then try an LLM or SciBERT classifier.
3. Get an OpenAlex key, ship a pre-built Alzheimer's evidence pack, and add a `.tex` reader so a
   manuscript's own citation sentences are classified too.
4. Browser viewer (Relate WASM) for the evidence pack.
