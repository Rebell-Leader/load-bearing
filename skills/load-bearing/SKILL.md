---
name: load-bearing
description: Check citations for retracted science before you cite them. Use when writing or reviewing anything with references (a literature review, a paper, a grant, a report from a research agent), when given a .bib file or a list of DOIs, or when asked whether a paper or claim rests on retracted work. Finds direct citations of retracted papers and second-order reliance through method or result citations, with the citing sentence as evidence.
---

# Load-Bearing: check before you cite

AI research tools routinely cite retracted papers without noticing (a 2026 JMIR study found none of nine
tools reliably caught them). Load-Bearing checks a bibliography against retraction notices and follows
citations up to three hops, separating papers that *used* a retracted result or method from papers that
only *mentioned* it. The evidence lives in a Relate graph (a single `.rl` file).

## Which interface

1. **MCP tools** (preferred, if the `load-bearing` server is connected):
   `retraction_status`, `check_references`, `check_paper`, `explain_exposure`, `graph_schema`, `query_graph`.
2. **CLI** (from the repository root):
   ```bash
   uv run loadbearing check refs.bib --json          # a bibliography (BibTeX or one DOI per line)
   uv run loadbearing check --doi 10.xxxx/yyyy --json # a published paper
   ```
   Exit code 1 means at least one `direct` or `load_bearing` finding.

## Workflow

**While drafting**: before adding a citation, call `retraction_status(dois=[...])` on the candidates. It is
instant and builds no graph. Drop or replace anything `retracted`; mention an `expression_of_concern`
explicitly if you keep it.

**Before handing over a draft**: run `check_references(references=<BibTeX or DOIs>, label=<short name>, depth=2)`.
Depth 2 takes seconds. Use `depth=3` for a final audit; it can take minutes on a cold cache.

**To audit a published paper**: `check_paper(doi=..., depth=2)`.

**To see why**: `explain_exposure(manuscript_id=..., retracted=<retracted_id or DOI>)` lists every path
with the citing sentences.

## Acting on findings

| Status | What it means | What to do |
|---|---|---|
| `direct` | You cite a retracted paper | Remove it, or cite it only to discuss the retraction |
| `load_bearing` | A reference relied on retracted work for a method or result | Read the quoted sentence. If your claim depends on that result, find independent support or say so |
| `unverified` | A path exists, but a citation on it could not be read | Low priority unless the retracted paper is central to the topic |
| `mention_only` | Reached only through background mentions | Usually ignore |
| `defused` | A paper on the path already flags the problem | Usually ignore |

`via_your_references` tells you *which of the user's citations* lead there (with `bib_key` when the input
was BibTeX). Point at those, not at the retracted paper alone.

## How to report

- Quote the evidence sentence and the notice reasons, and give the retraction date.
- When a finding has `notice_on_record: false`, OpenAlex flags the paper but no retraction notice was
  found (or only a correction or expression of concern). Say "marked retracted, no notice found", not
  "retracted".
- Report what retraction notices say. Never call a paper or an author fraudulent; say "retracted (reason
  per notice: …)".
- A path is evidence for a person to review, not a verdict. Say how much was read
  (`citing_sentences_read` of `citations_on_paths`).

## Ad-hoc questions about the graph

Call `graph_schema` for the model and example Cypher, then `query_graph` (read-only). Useful ones: the most
reached retracted papers for a manuscript, citations made after a retraction, and papers retracted for
citing retracted work. If the `relate` MCP server is connected (`relate serve --mcp stdio --database data/evidence
--read-only=live`), its `read_cypher` and `get_schema` tools query the same graph and see each new check as soon
as it commits.
