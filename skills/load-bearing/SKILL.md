---
name: load-bearing
description: Audit draft claims and bibliographies for reliance on retracted research. Use when writing or reviewing a manuscript, evidence synthesis, grant, or report with a list of references. Finds dated publication notices and traces a claim to study inclusion evidence for a specific review outcome when available.
---

# Load-Bearing: check before you cite

AI research tools routinely cite retracted papers without noticing (a 2026 JMIR study found none of nine
tools reliably caught them). Load-Bearing checks a bibliography against retraction notices and follows
citations up to three hops, separating papers that *used* a retracted result or method from papers that
only *mentioned* it. The evidence lives in a Relate graph (a single `.rl` file).

## Which interface

1. **MCP tools** (preferred, if the `load-bearing` server is connected):
   `audit_claims`, `retraction_status`, `check_references`, `check_paper`, `explain_exposure`, `graph_schema`, `query_graph`.
2. **CLI** (from the repository root):
   ```bash
   uv run loadbearing audit claims.json --json      # draft claims against the local outcome store
   uv run loadbearing check refs.bib --json          # a bibliography (BibTeX or one DOI per line)
   uv run loadbearing check --doi 10.xxxx/yyyy --json # a published paper
   ```
   Exit code 1 means at least one `direct` or `load_bearing` finding.

## Workflow

**To audit a draft outcome** use `audit_claims` with the draft sentence, cited DOI, and notice cutoff. Supply an outcome ID only after confirming its source figure or section. If evidence is missing or the match is ambiguous, keep the abstention in the review. When a claim is flagged, give the locator, notice link, and what a reviewer should reassess. An outcome outside the scope of a notice can be retained for that notice.

**While drafting**: before adding a citation, call `retraction_status(dois=[...])` on the candidates. It is
instant and builds no graph. Drop or replace anything `retracted`; mention an `expression_of_concern`
explicitly if you keep it.

**Before handing over a draft**: run `check_references(references=<BibTeX or DOIs>, label=<short name>, depth=2)`.
Depth 2 takes seconds. Use `depth=3` for a final audit; it can take minutes on a cold cache.

**To audit a published paper**: `check_paper(doi=..., depth=2)`.

**To see why**: `explain_exposure(manuscript_id=..., retracted=<retracted_id or DOI>)` shows up to 30 paths
with the available citing sentences and the total path count.

## Acting on findings

| Status | What it means | What to do |
|---|---|---|
| `direct` | You cite a paper flagged for review | Check the notice and why the draft cites the paper before suggesting a change |
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
