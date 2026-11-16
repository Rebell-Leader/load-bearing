# Devpost submission draft

Paste each block into the matching Devpost field. Items in `[[ ]]` need your input.

## Project name

Load-Bearing

## Elevator pitch (under 200 characters)

Not every citation matters. Load-Bearing finds the ones carrying the weight, and tells you when one has
collapsed: retracted science, traced through citation paths in Relate.

## Links

- Repository: https://github.com/Rebell-Leader/load-bearing (topics `relate`, `relate-neo4j-hackathon`)
- Demo video: `[[YouTube link]]`
- Browser viewer: `[[https://<you>.github.io/load-bearing/viewer/]]` (GitHub Pages), or run it locally
  with `python3 -m http.server 8765`

## About the project

### Inspiration

Lesné et al. 2006, the *Nature* paper on the Aβ*56 assembly in Alzheimer's disease, was retracted in 2024
after OpenAlex had counted 2,840 citations. In a 2026 study, none of nine AI research tools reliably caught
retracted papers. Reference managers flag a retracted paper you cite directly. The harder problem is
second-order: a paper you rely on got its key result from a retracted study. That is a property of a
path through the citation graph, and only some edges on the path count.

### What it does

Load-Bearing checks a bibliography or a published paper:

1. **Builds the graph.** It follows citations up to three hops out into a Relate graph.
2. **Reads the citations.** For every citation on a path to a retracted paper, it reads the citing
   sentence from open-access full text and classifies it. Method and result citations mean reliance;
   background mentions don't; critical citations already flag the problem.
3. **Reports by retracted paper.** One statement in Relate finds every path from the manuscript to a
   retracted paper and computes its status: direct, load-bearing, unverified, mention-only or defused.
   Each finding comes with the notice (date, reasons) and the quoted sentences.

What connects to what: `(:Manuscript)-[:CITES]->(:Paper)-[:CITES {intent, sentence, evidence}]->…->(:Paper:Retracted)-[:RETRACTED_BY]->(:Notice)`,
plus `:Review` labels and data-quality flags on citations.

It works in three places:

- **Command line:** `loadbearing check refs.bib`, or `--doi`. Offline against a shipped store, or live.
- **For agents:** an MCP server with six tools ("check before you cite"), next to Relate's own MCP server
  on the same graph, plus an agent skill. In the recorded demo, Claude audits a research assistant's
  grant paragraph. It finds two retracted references, reads the evidence before acting, queries the
  graph in Cypher, spots an impossible upstream citation, and rewrites the paragraph without inventing a
  single reference.
- **In the browser:** a static page that runs Relate's WebAssembly build and the same Cypher, with path
  diagrams and a query console.

On a real 2025 Alzheimer's paper, 56 of its 72 references reach a retracted paper within three hops, and
23 retracted papers are reached through method or result citations only. Two findings stand out:

- A 2023 meta-analysis pooled a study that was retracted months later for image manipulation.
- Two papers in the graph were retracted with the reason "Cites Retracted Work".

### How we built it

- **Relate, used deliberately in four modes:**
  - embedded from Python (`relate-db`);
  - a single-file `.rl` evidence pack;
  - a directory store that `relate serve --mcp stdio --read-only=live` follows while Load-Bearing writes;
  - the WebAssembly build in the browser.

  The core query is a quantified path pattern with inline relationship predicates. On the demo graph,
  Relate classifies all 741 paths in 30 ms.
- **Data:** OpenAlex (references; a server-side `is_retracted:true,cited_by:` filter means a
  three-hop check costs at most two requests per 100 papers scanned, about 120 for the demo paper), the Retraction Watch database via Crossref, Crossref notice links, Europe
  PMC full text (JATS), and Semantic Scholar as a fallback.
- **Citation intent:** BiomedBERT fine-tuned on SciCite (0.856 macro-F1) for method citations, plus the
  cited work's type (review or primary research) and precision guards. It was evaluated on labelled
  in-domain sentences with a separate held-out set.
- **Agents:** an MCP server built on the MCP Python SDK, an agent skill, and a Claude Agent SDK demo
  agent limited to the two MCP servers.

### Challenges we ran into

- **A served `.rl` file locks out writers.** While `relate serve --read-only` holds a `.rl` store, a
  writer gets `storage locked`. Our first MCP setup would have broken every agent check. Relate's answer,
  a directory store with a `--read-only=live` follower, became a design feature.
- **Being honest about citation intent.** On the tuning sample, our classifier looked like 0.86 precision.
  On a held-out sample it was 0.33. We kept the held-out number, show every sentence, and document a
  negative result (NLI claim alignment had no signal).
- **Messy metadata.** Reference DOIs hide in different XML tags, OpenAlex prefixes retracted titles, and
  some citation links are impossible. The agent found one (a 2008 paper "citing" a 2012 one), and that
  catch became a filter.

### Accomplishments that we're proud of

- **One Cypher statement serves every surface.** The CLI, the MCP server, Relate's MCP server and the
  browser run the same statement on the same graph, and their numbers match.
- **An agent with judgment.** It reads the evidence instead of trusting labels, and it doesn't invent
  citations.
- **A measured, reproducible evaluation** with its weaknesses stated.

### What we learned

- Graph paths are the right unit for research integrity: exposure is a property of a path, not of a
  paper.
- An embedded database changes the privacy story. Peer reviewers can check confidential manuscripts
  without any server.

### What's next

- Expert labels from biomedical NLP researchers, to train intent on our own definition.
- Abstract-level claim matching.
- Path scores instead of hard labels.
- A larger evidence pack (OpenAlex key) shared through `relate push` to Neo4j.

## Built with

relate · relatedb · cypher · webassembly · python · mcp · claude · claude-agent-sdk · openalex · crossref ·
europe-pmc · semantic-scholar · pytorch · transformers · biomedbert

## Submission checklist (from the hackathon page)

- [x] Project description: the use case, and what connects to what (above)
- [x] Public GitHub repo with a README on how to set up and use it: README follows the template
- [x] GitHub topic `relate` (required) and `relate-neo4j-hackathon` (recommended)
- [x] Persistent Relate store judges can inspect: `data/demo.rl` (single file) and `data/evidence/` (directory)
- [x] Working code with Relate running: the offline check, 12 tests, MCP smoke test, viewer
- [ ] Demo video, 1–2 minutes: script in [DEMO.md](DEMO.md)
- [ ] Submit on Devpost by **Dec 11, 6:00 PM PST**
