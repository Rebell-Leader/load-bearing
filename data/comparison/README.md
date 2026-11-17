# Claim-level comparison dataset

This directory holds the 17 test cases and curated outcome links used in [`docs/CLAIM_PILOT.md`](../../docs/CLAIM_PILOT.md) and [`scripts/run_claim_comparison.py`](../../scripts/run_claim_comparison.py).

## Files

| File | What it holds |
| --- | --- |
| [`cases.jsonl`](cases.jsonl) | 17 test claims across 6 case families (`8` development, `9` pilot), with expected actions and source evidence links |
| [`claim_facts.json`](claim_facts.json) | Publication notices (with dates) and outcome-to-study links (`uses` vs. `outside_scope`) loaded into the pilot Relate store |
| [`paper_orchestra_metadata.json`](paper_orchestra_metadata.json) | Public metadata for the 11 cited works, used to replay Semantic Scholar search responses in PaperOrchestra's literature stage |

## The six case families

| Family | What it tests | Primary sources |
| --- | --- | --- |
| **Rodent Alzheimer's meta-analysis** (`rodent-*`, 6 cases) | A Jan 2023 meta-analysis pooled 8 rat cognitive-function studies, including Rezk et al. 2022 (ref. 44, retracted Aug 2023 for image manipulation). Tests the affected rat outcome (`review_indirect`), two unaffected mouse outcomes from the same review (`retain_for_this_notice`), direct citation of the rat study (`review_direct`), missing outcome evidence (`insufficient_evidence`), and a pre-retraction audit date (`no_notice_as_of`). | [Synthesis, Results & Figs. 3–4](https://link.springer.com/article/10.1186/s13287-022-03231-1), [retraction notice](https://link.springer.com/article/10.1007/s11011-023-01282-8) |
| **Infertility systematic reviews** (`infertility-*`, 3 cases) | Two meta-analyses (Liu 2014, Qin 2020) that pooled a retracted clomiphene/letrozole trial (Badawy 2009, retracted 2020), plus a direct citation. Removing Badawy changed the pooled result in the published VITALITY reanalysis. | [Liu 2014](https://doi.org/10.1111/jog.12393), [Qin 2020](https://pmc.ncbi.nlm.nih.gov/articles/PMC7402796/), [VITALITY study](https://pmc.ncbi.nlm.nih.gov/articles/PMC12015725/), [retraction notice](https://pubmed.ncbi.nlm.nih.gov/32912617/) |
| **Vascular reviews** (`vascular-*`, 2 cases) | Two reviews (Barrons 2014, Shahin 2013) that pooled two retracted ramipril trials (Ahimastos 2006 and 2013, both retracted in 2015). | [VITALITY Case 3](https://pmc.ncbi.nlm.nih.gov/articles/PMC12015725/), [2006 trial notice](https://doi.org/10.7326/M15-2625), [2013 trial notice](https://doi.org/10.1001/jama.2015.10811) |
| **AI recommender overview** (`cs-shen-*`, 3 cases) | A 2025 overview relies on a retracted K-means paper (Shen 2023, ref. 6) in section 3.2 (`review_indirect`), cites an unrelated paper (Loukili, ref. 5) for candidate generation vs. ranking in section 3.3 (`retain_for_this_notice`), plus a control sentence that cites Shen specifically to note its retraction (`retain_with_notice`). | [Overview PDF, p. 983](https://wjaets.com/sites/default/files/fulltext_pdf/WJAETS-2025-0276.pdf), [retraction notice](https://link.springer.com/article/10.1007/s44196-024-00476-x) |
| **Tabular transformer** (`cs-transformer-direct`, 1 case) | Direct citation of a retracted computer-science benchmark paper (`review_direct`). | [Retraction notice](https://link.springer.com/article/10.1007/s44196-024-00493-w) |
| **Amyloid assembly** (`lesne-*`, 2 cases) | Direct citation of Lesné et al. 2006 audited after its June 2024 retraction (`review_direct`) vs. audited in Jan 2023 when it carried a July 2022 expression of concern (`review_notice`). | [Retraction notice](https://pubmed.ncbi.nlm.nih.gov/38914864/), [Retraction Watch](https://www.crossref.org/documentation/retrieve-metadata/retraction-watch/) |

## Action labels

| Action | Meaning |
| --- | --- |
| `review_direct` | The sentence relies directly on a retracted paper. |
| `review_indirect` | The sentence relies on a review outcome that included a retracted paper. |
| `review_notice` | The cited work had a non-retraction notice (such as an expression of concern) as of the audit date. |
| `retain_for_this_notice` | The cited review reaches a retracted paper, but the specific outcome cited here did not use it. |
| `retain_with_notice` | The sentence cites a retracted paper only to discuss its retraction. |
| `no_notice_as_of` | No notice existed on or before the requested `as_of` audit date. |
| `insufficient_evidence` | A reference could not be resolved, or the graph lacks outcome-level evidence to tell whether the cited claim used the retracted study. |

## Discovery funnel on the shipped demo store (`data/demo.rl`)

For context, here is how sentence-level citation intent (`loadbearing check`) narrows candidate paths on the 72-reference *Redox Biology* 2025 paper in `data/demo.rl` (SHA-256 `3df85813f7fcd6129a5c94773f2db7e4aca18b5082b9c9635d71b8d20bef802e`):

| Query | Flagged works reached | Total paths |
| --- | ---: | ---: |
| Direct (1 hop) | 0 of 72 references | 0 |
| Untyped paths (up to 2 hops) | 10 | 15 |
| Load-bearing paths (up to 2 hops) | 4 | 4 |
| Untyped paths (up to 3 hops) | 349 | 739 |
| Load-bearing paths (up to 3 hops) | 23 (21 with a retraction notice) | 30 |
