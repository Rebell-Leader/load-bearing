# Claim-level audit and PaperOrchestra pilot

A bibliography check tells you that one of your references cites a retracted paper. When your reference is a review or a meta-analysis, that still leaves a practical question: **did the specific result you are citing actually use the retracted study?**

Two sentences in the same draft can cite the same review:
- One cites a pooled estimate that included a later-retracted trial (**needs review**).
- The next sentence cites a different outcome from the same review—for example, a mouse meta-analysis where the retracted study was a rat trial—or cites the review only for general background (**safe to keep**).

A direct DOI check misses the first sentence because the review itself is not retracted. An untyped citation-path check flags both sentences because both cite the same review.

This pilot tests a claim-scoped Relate graph on 17 draft sentences across six real retraction cases, and pairs it with Google's [PaperOrchestra](https://github.com/google-research/paper-orchestra) literature-review pipeline.

## How the claim graph works

For the six reviews in the test set, [`data/comparison/claim_facts.json`](../data/comparison/claim_facts.json) records which reported outcomes included which underlying studies, along with the dated retraction and expression-of-concern notices. [`src/loadbearing/claim_audit.py`](../src/loadbearing/claim_audit.py) loads those facts into a Relate store:

```text
(:ClaimWork)-[:REPORTS]->(:Outcome)-[:STUDY_USE {role: 'uses' | 'outside_scope'}]->(:ClaimWork)-[:HAS_NOTICE]->(:PublicationNotice)
```

When auditing a sentence (`claim`, `reference_dois`, `as_of` date):
1. Direct citations to a paper with a notice on or before `as_of` are flagged (`review_direct` or `review_notice`), unless the sentence is explicitly documenting that the paper was retracted (`retain_with_notice`).
2. Indirect citations through a review match the claim against the review's recorded outcomes:
   - If the outcome used the retracted study (`role = 'uses'`), it returns `review_indirect` with the exact figure/section locator and notice link.
   - If the retracted study was outside that outcome (`role = 'outside_scope'`), it returns `retain_for_this_notice`.
   - If outcome evidence is missing or ambiguous, it abstains (`insufficient_evidence`) instead of guessing.

## Results on the 17-case benchmark

We compared three graph queries on the same Relate snapshot (`as_of = 2026-11-16`):

| Method | Exact decisions (`17` cases) | Indirect retractions caught (`6` cases) | False alarms on unaffected controls (`6` cases) |
| --- | ---: | ---: | ---: |
| Direct DOI notices only | 6 / 17 | 0 / 6 | 1 |
| Untyped citation paths (2 hops) | 12 / 17 | 6 / 6 | 5 |
| **Claim-scoped Relate graph** | **17 / 17** | **6 / 6** | **0** |

On the 9-case pilot split alone, exact decisions are `2/9` (direct), `7/9` (untyped), and `9/9` (claim-scoped).

## Pairing with PaperOrchestra and Claude

PaperOrchestra's literature-review stage (`HybridLiteratureAgent.run`) searches Semantic Scholar for candidate papers, checks titles and publication cutoffs, deduplicates, and writes a LaTeX draft (`updated_template.tex`) and a `.bib` file (`references.bib`). Because Semantic Scholar's public search endpoint rate-limited live queries (`HTTP 429`), we replayed the search responses using verified publication metadata for the 11 cited works.

One practical finding from running PaperOrchestra's code directly: **it accepted all 11 references and wrote 0 DOIs into `references.bib`.** Our adapter matched the generated BibTeX keys back to their DOIs by title and year (`runs/claim_pilot/paper-orchestra/citation_dois.json`) before running the audit.

We then ran four fresh Claude Haiku 5.5 sessions (`claude -p`, no web search, capped at $0.15) to revise the 17 LaTeX sentences under four levels of evidence:

| Evidence given to Claude | Exact decisions | Affected claims revised with source & notice links | Unaffected control claims kept verbatim | Time |
| --- | ---: | ---: | ---: | ---: |
| PaperOrchestra verified bibliography only | 6 / 17 | 0 / 11 | 6 / 6 | 29.7 s |
| Direct DOI notice lookup | 6 / 17 | 5 / 11 | 5 / 6 | 14.6 s |
| Claim-scoped Relate report (static JSON) | **17 / 17** | **11 / 11** | **6 / 6** | 25.3 s |
| Claim-scoped Relate MCP tool (`audit_claims`) | **17 / 17** | **11 / 11** | **6 / 6** | 28.5 s |

All four runs together cost $0.02; full outputs are in [`runs/claim_pilot/report.json`](../runs/claim_pilot/report.json).

**Concrete example from the run:** Two test sentences cite the same 2025 recommender-systems overview ([WJAETS 2025, p. 983](https://wjaets.com/sites/default/files/fulltext_pdf/WJAETS-2025-0276.pdf#page=5)):
- Sentence 1 uses the overview's claim that improved K-means segments users from behavioral and social data—a finding the overview took from Shen et al. 2023 ([retracted March 2024](https://link.springer.com/article/10.1007/s44196-024-00476-x)).
- Sentence 2 cites the next paragraph of the same overview on separating candidate generation from ranking (attributed to Loukili et al., an unrelated reference).

With only PaperOrchestra's verified bibliography, Claude kept the K-means claim and even suggested citing the retracted Shen paper directly because its DOI resolved. With the claim-scoped Relate graph (either as a static report or through MCP), Claude flagged and qualified the K-means sentence with links to both the overview section and the retraction notice, while leaving the candidate-generation sentence untouched.

## Limitations

- **Curated outcome links:** For this 17-case pilot, the mapping from each review outcome to its included studies (`claim_facts.json`) was curated from the published papers, forest plots, and VITALITY reanalyses. The main Load-Bearing CLI (`loadbearing check`) narrows citation paths automatically using sentence-level citation intent; narrowing further to specific pooled outcomes in a meta-analysis currently requires those outcome links.
- **Static vs. MCP:** Because the agent audited all 17 claims in one batch, the static report and the `audit_claims` MCP tool gave the exact same `17/17` result. MCP's advantage here is giving a live drafting agent on-demand access to the graph without pre-bundling reports into its prompt.

## Reproduce

Run the deterministic Relate comparison (no API keys or network):

```bash
uv run python scripts/run_claim_comparison.py --output /tmp/loadbearing-graph-pilot
```

To also run the pinned PaperOrchestra literature stage (`d9bae997e793a015ed38bb1605be9eb58c00284f`), clone PaperOrchestra into a temporary directory and install its lightweight dependencies:

```bash
pilot_dir=$(mktemp -d)
git clone https://github.com/google-research/paper-orchestra.git "$pilot_dir/upstream"
git -C "$pilot_dir/upstream" checkout --detach d9bae997e793a015ed38bb1605be9eb58c00284f
uv pip install --python .venv/bin/python --target "$pilot_dir/deps" \
  google-genai==3.3.0 python-dotenv==1.2.4 requests==2.34.2 thefuzz==0.22.1
PYTHONPATH="$pilot_dir/deps" uv run python scripts/run_claim_comparison.py \
  --paper-orchestra "$pilot_dir/upstream" --output "$pilot_dir/results"
```

Add `--claude` to that command to re-run the four live Claude Haiku sessions.
