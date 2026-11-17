# Devpost submission draft

## Project name

Load-Bearing

## Elevator pitch

Find which claims in a draft depend on a retracted study, even when the cited review has no notice. Load-Bearing traces each affected outcome to the study and notice in Relate.

## Links

- [Public repository](https://github.com/Rebell-Leader/load-bearing) with topics `relate` and `relate-neo4j-hackathon`
- [Interactive claim audit](https://rebell-leader.github.io/load-bearing/viewer/claims.html)
- [Citation explorer](https://rebell-leader.github.io/load-bearing/viewer/)
- Demo video URL to attach after hosting. The 1:46 captioned cut is built at `demo/build/load-bearing-claim-first.mp4`.

## About the project

### Inspiration

The bibliography of a draft can pass a direct retraction check even when a published review behind one of its sentences used a study that was later retracted. The VITALITY study found 847 systematic reviews that quantitatively incorporated retracted trials. A reviewer needs to know which estimate to reassess and where to find the inclusion evidence. [VITALITY study](https://pmc.ncbi.nlm.nih.gov/articles/PMC12015725/)

### What it does

Two draft sentences cite one published meta-analysis. Figure 3b pooled the results of eight rat studies and included reference 44, which was later retracted. Figure 3a pools mouse studies and uses a different set of references. The direct DOI check finds no notice on the shared review. Load-Bearing shows the exact figure and publisher notice behind each decision. It recommends reassessing the rat estimate and shows why the mouse claim is outside the scope of that notice. [Review, Figures 3a and 3b](https://link.springer.com/article/10.1186/s13287-022-03231-1#Fig3) · [Publisher notice](https://doi.org/10.1007/s11011-023-01282-8)

Open [the interactive audit](https://rebell-leader.github.io/load-bearing/viewer/claims.html) and toggle between direct DOI and claim paths. Change the cutoff to see the report before the notice. The second case checks two claims that cite the same recommender-systems overview. [Case and sources](CLAIM_PILOT.md)

### How we built it

- **Embedded Relate and a single-file claim store.** The graph connects a cited review to a reported outcome, its included or excluded study, and the study's dated publication notice. Cypher retrieves the path, including the recorded figure or section. The file at `data/claims.rl` is inspectable. The browser displays results exported from the same file.
- **Offline audit and review workflow.** `uv run loadbearing audit` runs the featured example. The CSV importer previews study DOIs, evidence locators, and notice links before a reviewer confirms the write. An unmapped or ambiguous claim produces an abstention.
- **Agent integration.** The `audit_claims` MCP tool returns the disposition and links. In the recorded PaperOrchestra and Claude pilot, the agent qualified the rat sentence, gave the source links, and kept the mouse sentence verbatim. The PaperOrchestra metadata search was replayed from public fixtures after hitting rate limits.
- **Citation discovery.** The separate bibliography audit uses a Relate directory store with a live read-only MCP follower. The portable exposure graph and WebAssembly explorer support deeper investigation of candidate paths.

### What the comparison showed

| Method | Exact actions on 17 curated claims | Indirect cases found | False alerts on six controls |
| --- | ---: | ---: | ---: |
| Direct DOI notices | 6 | 0 | 1 |
| Untyped two-hop paths | 12 | 6 | 5 |
| Claim-scoped Relate paths | 17 | 6 | 0 |

The pilot uses curated outcome links. A second comparison imported 11 reviewed links across five previously unseen reviews, covering 29 draft inputs and controlled variants. The audit detected 10 of 15 affected variants and raised zero false alerts. The five affected paraphrases with no confirmed outcome ID produced abstentions. [Reproduction and limits](CLAIM_PILOT.md#evaluation-on-new-reviews)

### Significant AI use and source material

Codex and Gemini assisted with design, code, tests, and submission material. The saved transcript includes Claude Haiku 5.5 for the claim pilot and Claude Opus 5.5 for the literature graph demo. The offline audit uses stored evidence and deterministic queries. The broader citation triage optionally uses a SciCite-trained BiomedBERT model. Google PaperOrchestra is a separately attributed open-source dependency of the optional replay. Scholarly metadata and publication notices are attributed in the README and evidence files. [Code license](../LICENSE) · [Data sources](../README.md#data-sources)

## Submission checklist

- [x] Public repository with setup instructions and topic `relate`
- [x] Inspectable single-file Relate store and an offline judge command
- [x] Claim report, curated comparison, and new-source evaluation
- [x] Local captioned video under two minutes
- [ ] Attach a login-free link to the video and submit by Dec 11 at 6:00 p.m. PST
