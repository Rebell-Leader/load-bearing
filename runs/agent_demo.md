# Agent demo transcript (2026-11-16 13:26)

Claude Opus 5.5 (Claude Agent SDK) with two MCP servers and no built-in tools:
`load-bearing` (6 tools, the store's single writer) and `relate` (`relate serve --mcp stdio --read-only=live`, following that writer).

## Task

```text
A PI is finalizing the background section of a grant application. An AI research assistant produced
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
```

Draft: [`examples/draft_background.md`](../examples/draft_background.md)

## Steps

**→ `load-bearing` · `retraction_status`**

```json
{"dois": ["10.3233/JAD-179941", "10.15252/emmm.201606210", "10.1038/416535a", "10.1038/nm1782", "10.1038/nature04533", "10.1016/j.neurobiolaging.2009.11.007", "10.1111/j.1471-4159.2011.07478.x"]}
```

<details><summary>result (1,992 chars)</summary>

```json
{"result":"[{\"doi\": \"10.3233/jad-179941\", \"status\": \"no_notice_found\", \"title\": \"The Amyloid-β Oligomer Hypothesis: Beginning of the Third Decade\", \"year\": 2018, \"openalex_id\": \"W2809078375\", \"notice\": null}, {\"doi\": \"10.15252/emmm.201606210\", \"status\": \"no_notice_found\", \"title\": \"The amyloid hypothesis of Alzheimer's disease at 25 years\", \"year\": 2016, \"openalex_id\": \"W2329336071\", \"notice\": null}, {\"doi\": \"10.1038/416535a\", \"status\": \"no_notice_found\", \"title\": \"Naturally secreted oligomers of amyloid β protein potently inhibit hippocampal long-term potentiation in vivo\", \"year\": 2002, \"openalex_id\": \"W2150999725\", \"notice\": null}, {\"doi\": \"10.1038/nm1782\", \"status\": \"no_notice_found\", \"title\": \"Amyloid-β protein dimers isolated directly from Alzheimer's brains impair synaptic plasticity and memory\", \"year\": 2008, \"openalex_id\": \"W2109727228\", \"notice\": null}, {\"doi\": \"10.1038/nature04533\", \"status\": \"retracted\", \"title\": \"RETRACTED ARTICLE: A specific amyloid-β protein assembly in the brain impairs memory\", \"year\": 2006, \"openalex_id\": \"W2075481535\", \"notice\": {\"nature\": \"Retraction\", \"date\": \"2024-06-24\", \"reasons\": [\"Concerns/Issues about Image\", \"Duplication of/in Image\", \"Investigation by Journal/Publisher\", \"Investigation by Third Party\", \"Manipulation of Images\", \"Objections by Author(s)\", \"Upgrade/Update of Prior Notice(s)\"], \"notice_doi\": \"10.1038/s41586-024-07691-8\"}}, {\"doi\": \"10.1016/j.neurobiolaging.2009.11.007\", \"status\": \"retracted\", \"title\": \"RETRACTED: Cognitive effects of cell-derived and synthetically derived Aβ oligomers\", \"year\": 2010, \"openalex_id\": \"W2021740213\", \"notice\": null}, {\"doi\": \"10.1111/j.1471-4159.2011.07478.x\", \"status\": \"no_notice_found\", \"title\": \"Soluble Aβ oligomer production and toxicity\", \"year\": 2011, \"openalex_id\": \"W1553011341\", \"notice\": null}]"}
```
</details>

**→ `load-bearing` · `check_references`**

```json
{"references": "@article{cline2018, title={The Amyloid-β Oligomer Hypothesis: Beginning of the Third Decade}, author={Cline, Erika N. and Bicca, Maíra A. and Viola, Kirsten L. and Klein, William L.}, journal={Journal of Alzheimer's Disease}, year={2018}, doi={10.3233/JAD-179941}}\n@article{selkoe2016, title={The amyloid hypothesis of Alzheimer's disease at 25 years}, author={Selkoe, Dennis J. and Hardy, John}, journal={EMBO Molecular Medicine}, year={2016}, doi={10.15252/emmm.201606210}}\n@article{walsh2002, title={Naturally secreted oligomers of amyloid β protein potently inhibit hippocampal long-term potentiation in vivo}, author={Walsh, Dominic M. and Klyubin, Igor and others}, journal={Nature}, year={2002}, doi={10.1038/416535a}}\n@article{shankar2008, title={Amyloid-β protein dimers isolated directly from Alzheimer's brains impair synaptic plasticity and memory}, author={Shankar, Ganesh M. and others}, journal={Nature Medicine}, year={2008}, doi={10.1038/nm1782}}\n@article{lesne2006, title={A specific amyloid-β protein assembly in the brain impairs memory}, author={Lesné, Sylvain and others}, journal={Nature}, year={2006}, doi={10.1038/nature04533}}\n@article{reed2011, title={Cognitive effects of cell-derived and synthetically derived Aβ oligomers}, author={Reed, Miranda N. and others}, journal={Neurobiology of Aging}, year={2011}, doi={10.1016/j.neurobiolaging.2009.11.007}}\n@article{larson2012, title={Soluble Aβ oligomer production and toxicity}, author={Larson, Megan…
```

<details><summary>result (6,662 chars)</summary>

```json
{"result":"{\"manuscript_id\": \"M:grant-draft\", \"title\": \"grant-draft\", \"depth\": 2, \"summary\": {\"retracted_papers_reached\": 4, \"your_references_exposed\": 5, \"by_status\": {\"direct\": 2, \"load_bearing\": 1, \"unverified\": 1}, \"citations_on_paths\": 13, \"citing_sentences_read\": 4, \"cited_after_retraction\": 0}, \"guidance\": {\"direct\": \"You cite a retracted paper. Remove it, or cite it only to discuss the retraction.\", \"load_bearing\": \"A paper you cite may rely on retracted work for a method or result. Read the quoted sentence first: intent v1 finds most real reliance but has ~33% precision on held-out sentences (docs/EVAL.md). If your claim depends on that result, find independent support.\", \"unverified\": \"A path exists but at least one citation on it could not be read. Low priority unless the retracted paper is central to your topic.\"}, \"intent_classifier\": \"v1 (held-out reliance recall 0.69, precision 0.33; see docs/EVAL.md)\", \"findings\": [{\"status\": \"direct\", \"retracted_id\": \"W2075481535\", \"title\": \"RETRACTED ARTICLE: A specific amyloid-β protein assembly in the brain impairs memory\", \"year\": 2006, \"doi\": \"10.1038/nature04533\", \"notice\": {\"nature\": \"Retraction\", \"date\": \"2024-06-24\", \"reasons\": [\"Concerns/Issues about Image\", \"Duplication of/in Image\", \"Investigation by Journal/Publisher\", \"Investigation by Third Party\", \"Manipulation of Images\", \"Objections by Author(s)\", \"Upgrade/Update of Prior Notice(s)\"], \"notice_doi\": \"10.1038/s41586-024-07691-8\", \"source\": \"retraction_watch\"}, \"via_your_references\": [{\"id\": \"W1553011341\", \"doi\": \"10.1111/j.1471-4159.2011.07478.x\", \"title\": \"Soluble Aβ oligomer production and toxicity\", \"year\": 2011, \"bib_key\": \"larson2012\"}, {\"id\": \"W2021740213\", \"doi\": \"10.1016/j.neurobiolaging.2009.11.007\", \"title\": \"RETRACTED: Cognitive effects of cell-derived and synthetically derived Aβ oligomers\", \"year\": 2010, \"bib_key\": \"reed2011\"}, {\"id\": \"W2075481535\", \"doi\": \"10.1038/nature04533\", \"title\": \"RETRACTED ARTICLE: A specific amyloid-β protein assembly in the brain impairs memory\", \"year\": 2006, \"bib_key\": \"lesne2006\"}, {\"id\": \"W2109727228\", \"doi\": \"10.1038/nm1782\", \"title\": \"Amyloid-β protein dimers isolated directly from Alzheimer's brains impair synaptic plasticity and memory\", \"year\": 2008, \"bib_key\": \"shankar2008\"}, {\"id\": \"W2809078375\", \"doi\": \"10.3…
```
</details>

**→ `load-bearing` · `explain_exposure`**

```json
{"manuscript_id": "M:grant-draft", "retracted": "W2075481535"}
```

<details><summary>result (34,295 chars)</summary>

```json
{"result":"{\"retracted\": {\"id\": \"W2075481535\", \"title\": \"RETRACTED ARTICLE: A specific amyloid-β protein assembly in the brain impairs memory\", \"doi\": \"10.1038/nature04533\", \"notice\": {\"nature\": \"Retraction\", \"date\": \"2024-06-24\", \"reasons\": [\"Concerns/Issues about Image\", \"Duplication of/in Image\", \"Investigation by Journal/Publisher\", \"Investigation by Third Party\", \"Manipulation of Images\", \"Objections by Author(s)\", \"Upgrade/Update of Prior Notice(s)\"]}}, \"paths\": [{\"status\": \"direct\", \"hops\": [{\"from\": \"grant-draft\", \"to\": \"RETRACTED ARTICLE: A specific amyloid-β protein assembly in the brain impairs memory\", \"to_doi\": \"10.1038/nature04533\", \"intent\": \"unknown\", \"evidence\": null, \"section\": null, \"sentence\": null, \"cited_after_retraction\": false}]}, {\"status\": \"load_bearing\", \"hops\": [{\"from\": \"grant-draft\", \"to\": \"RETRACTED: Cognitive effects of cell-derived and synthetically derived Aβ oligomers\", \"to_doi\": \"10.1016/j.neurobiolaging.2009.11.007\", \"intent\": \"unknown\", \"evidence\": null, \"section\": null, \"sentence\": null, \"cited_after_retraction\": false}, {\"from\": \"RETRACTED: Cognitive effects of cell-derived and synthetically derived Aβ oligomers\", \"to\": \"RETRACTED ARTICLE: A specific amyloid-β protein assembly in the brain impairs memory\", \"to_doi\": \"10.1038/nature04533\", \"intent\": \"method\", \"evidence\": \"s2\", \"section\": \"\", \"sentence\": \"Immunoaffinity chromatography Forebrains were lysed in RIPA buffer and ultraentrifuged as previously described (Lesné et al., 2006). roteins were incubated overnight with columns packed with y crosslinking antibodies to the Affi-Prep protein A resin Bio-Rad Laboratories).\", \"cited_after_retraction\": false}]}, {\"status\": \"load_bearing\", \"hops\": [{\"from\": \"grant-draft\", \"to\": \"The Amyloid-β Oligomer Hypothesis: Beginning of the Third Decade\", \"to_doi\": \"10.3233/jad-179941\", \"intent\": \"unknown\", \"evidence\": null, \"section\": null, \"sentence\": null, \"cited_after_retraction\": false}, {\"from\": \"The Amyloid-β Oligomer Hypothesis: Beginning of the Third Decade\", \"to\": \"RETRACTED ARTICLE: A specific amyloid-β protein assembly in the brain impairs memory\", \"to_doi\": \"10.1038/nature04533\", \"intent\": \"result\", \"evidence\": \"fulltext\", \"section\": \"A multitude of AβO species or just two?\", \"sentence\": \"One specific type 1 AβO has been identified, …
```
</details>

**→ `load-bearing` · `explain_exposure`**

```json
{"manuscript_id": "M:grant-draft", "retracted": "W2021740213"}
```

<details><summary>result (1,969 chars)</summary>

```json
{"result":"{\"retracted\": {\"id\": \"W2021740213\", \"title\": \"RETRACTED: Cognitive effects of cell-derived and synthetically derived Aβ oligomers\", \"doi\": \"10.1016/j.neurobiolaging.2009.11.007\", \"notice\": {\"nature\": \"Retraction\", \"date\": \"2026-07-01\", \"reasons\": []}}, \"paths\": [{\"status\": \"direct\", \"hops\": [{\"from\": \"grant-draft\", \"to\": \"RETRACTED: Cognitive effects of cell-derived and synthetically derived Aβ oligomers\", \"to_doi\": \"10.1016/j.neurobiolaging.2009.11.007\", \"intent\": \"unknown\", \"evidence\": null, \"section\": null, \"sentence\": null, \"cited_after_retraction\": false}]}, {\"status\": \"unverified\", \"hops\": [{\"from\": \"grant-draft\", \"to\": \"The Amyloid-β Oligomer Hypothesis: Beginning of the Third Decade\", \"to_doi\": \"10.3233/jad-179941\", \"intent\": \"unknown\", \"evidence\": null, \"section\": null, \"sentence\": null, \"cited_after_retraction\": false}, {\"from\": \"The Amyloid-β Oligomer Hypothesis: Beginning of the Third Decade\", \"to\": \"RETRACTED: Cognitive effects of cell-derived and synthetically derived Aβ oligomers\", \"to_doi\": \"10.1016/j.neurobiolaging.2009.11.007\", \"intent\": \"unknown\", \"evidence\": \"metadata_only\", \"section\": null, \"sentence\": null, \"cited_after_retraction\": false}]}, {\"status\": \"unverified\", \"hops\": [{\"from\": \"grant-draft\", \"to\": \"Soluble Aβ oligomer production and toxicity\", \"to_doi\": \"10.1111/j.1471-4159.2011.07478.x\", \"intent\": \"unknown\", \"evidence\": null, \"section\": null, \"sentence\": null, \"cited_after_retraction\": false}, {\"from\": \"Soluble Aβ oligomer production and toxicity\", \"to\": \"RETRACTED: Cognitive effects of cell-derived and synthetically derived Aβ oligomers\", \"to_doi\": \"10.1016/j.neurobiolaging.2009.11.007\", \"intent\": \"unknown\", \"evidence\": \"no_fulltext\", \"section\": null, \"sentence\": null, \"cited_after_retraction\": false}]}], \"total_paths\": 3}"}
```
</details>

**→ `load-bearing` · `explain_exposure`**

```json
{"manuscript_id": "M:grant-draft", "retracted": "W2155049938"}
```

<details><summary>result (1,168 chars)</summary>

```json
{"result":"{\"retracted\": {\"id\": \"W2155049938\", \"title\": \"RETRACTED: The Complex PrPc-Fyn Couples Human Oligomeric Aβ with Pathological Tau Changes in Alzheimer's Disease\", \"doi\": \"10.1523/jneurosci.1858-12.2012\", \"notice\": {\"nature\": \"Retraction\", \"date\": \"2025-03-12\", \"reasons\": [\"Concerns/Issues about Image\", \"Investigation by Company/Institution\", \"Investigation by Third Party\", \"Unreliable Image\"]}}, \"paths\": [{\"status\": \"unverified\", \"hops\": [{\"from\": \"grant-draft\", \"to\": \"The Amyloid-β Oligomer Hypothesis: Beginning of the Third Decade\", \"to_doi\": \"10.3233/jad-179941\", \"intent\": \"unknown\", \"evidence\": null, \"section\": null, \"sentence\": null, \"cited_after_retraction\": false}, {\"from\": \"The Amyloid-β Oligomer Hypothesis: Beginning of the Third Decade\", \"to\": \"RETRACTED: The Complex PrPc-Fyn Couples Human Oligomeric Aβ with Pathological Tau Changes in Alzheimer's Disease\", \"to_doi\": \"10.1523/jneurosci.1858-12.2012\", \"intent\": \"unknown\", \"evidence\": \"metadata_only\", \"section\": null, \"sentence\": null, \"cited_after_retraction\": false}]}], \"total_paths\": 1}"}
```
</details>

**→ `relate` · `get_schema`**

```json
{}
```

<details><summary>result (2,703 chars)</summary>

```json
{"Manuscript":{"count":2,"properties":{"doi":{"type":"String"},"id":{"type":"String"},"pub_date":{"type":"Temporal"},"title":{"type":"String"},"year":{"type":"Integer"}},"relationships":{"CITES":{"direction":"out","labels":["Paper","Retracted","Review"],"properties":{"classifier":{"type":"String"},"context":{"type":"String"},"evidence":{"type":"String"},"intent":{"type":"String"},"n_contexts":{"type":"Integer"},"rule":{"type":"String"},"section":{"type":"String"},"zombie":{"type":"Boolean"}}}},"type":"node"},"Notice":{"count":321,"properties":{"date":{"type":"Temporal"},"id":{"type":"String"},"nature":{"type":"String"},"notice_doi":{"type":"String"},"reasons":{"type":"List"},"source":{"type":"String"}},"type":"node"},"Paper":{"count":929,"properties":{"doi":{"type":"String"},"id":{"type":"String"},"nature":{"type":"String"},"notice_source":{"type":"String"},"pub_date":{"type":"Temporal"},"reasons":{"type":"List"},"retraction_date":{"type":"Temporal"},"title":{"type":"String"},"work_type":{"type":"String"},"year":{"type":"Integer"}},"relationships":{"CITES":{"direction":"out","labels":["Paper","Retracted","Review"],"properties":{"classifier":{"type":"String"},"context":{"type":"String"},"evidence":{"type":"String"},"intent":{"type":"String"},"n_contexts":{"type":"Integer"},"rule":{"type":"String"},"section":{"type":"String"},"zombie":{"type":"Boolean"}}},"RETRACTED_BY":{"direction":"out","labels":["Notice"]}},"type":"node"},"Retracted":{"count":349,"properties":{"doi":{"type":"String"},"id":{"type":"String"},"nature":{"type":"String"},"notice_source":{"type":"String"},"pub_date":{"type":"Temporal"},"reasons":{"type":"List"},"retraction_date":{"type":"Temporal"},"title":{"type":"String"},"work_type":{"type":"String"},"year":{"type":"Integer"}},"relationships":{"CITES":{"direction":"out","labels":["Paper","Retracted"],"properties":{"classifier":{"type":"String"},"context":{"type":"String"},"evidence":{"type":"String"},"intent":{"type":"String"},"n_contexts":{"type":"Integer"},"rule":{"type":"String"},"section":{"type":"String"},"zombie":{"type":"Boolean"}}},"RETRACTED_BY":{"direction":"out","labels":["Notice"]}},"type":"node"},"Review":{"count":209,"properties":{"doi":{"type":"String"},"id":{"type":"String"},"pub_date":{"type":"Temporal"},"title":{"type":"String"},"work_type":{"type":"String"},"year":{"type":"Integer"}},"relationships":{"CITES":{"direction":"out","labels":["Paper","Retracted","Review"],"properties":{"classifier":{"type":"String"},"context":{…
```
</details>

**→ `relate` · `read_cypher`**

```json
{"statement": "MATCH (m:Manuscript {id: $mid})-[:CITES]->(ref)\nMATCH p = (ref)-[:CITES*1..2]->(l {doi: $doi})\nWITH ref, p, [n IN nodes(p)[1..-1] | coalesce(n.doi, n.id)] AS via, [r IN relationships(p) | r.intent] AS intents\nRETURN ref.doi AS reference, length(p) AS hops, via, intents\nORDER BY reference, hops", "parameters": {"mid": "M:grant-draft", "doi": "10.1038/nature04533"}}
```

<details><summary>result (6,367 chars)</summary>

```json
{"columnTypes":["STRING","INTEGER","LIST","LIST"],"columns":["reference","hops","via","intents"],"elapsed_ms":1.2026999999999999,"error":null,"execute_ms":0.970997,"lex_parse_ms":0.032833999999999995,"lower_ms":0.06208,"notifications":[{"category":"PERFORMANCE","code":"Relate.Notification.Statement.MissingIndex","description":"the equality predicate on id filters :Manuscript without a range index on (:Manuscript {id})","gql_status":"03C91","operator_id":3,"remedy":"CREATE INDEX relate_Manuscript__id FOR (n:Manuscript) ON (n.id)","severity":"INFORMATION","title":"Missing index"}],"parse_ms":0.137328,"plan":{"profiled":false,"root":{"actual":null,"children":[{"actual":null,"children":[{"actual":null,"children":[{"actual":null,"children":[],"details":"(m:Manuscript)-[:CITES]->(ref)","estimated_rows":null,"identifiers":[],"operator":"Expand","warnings":[{"category":"PERFORMANCE","code":"Relate.Notification.Statement.MissingIndex","description":"the equality predicate on id filters :Manuscript without a range index on (:Manuscript {id})","gql_status":"03C91","remedy":"CREATE INDEX relate_Manuscript__id FOR (n:Manuscript) ON (n.id)","severity":"INFORMATION","title":"Missing index"}]}],"details":"p = (ref)-[:CITES*1..2]->(l)","estimated_rows":null,"identifiers":[],"operator":"Expand","warnings":[]}],"details":"4 item(s)","estimated_rows":null,"identifiers":[],"operator":"Projection","warnings":[]}],"details":"4 item(s), ordered","estimated_rows":null,"identifiers":[],"operator":"ProduceResults","warnings":[]},"schema":"relate.plan/v1","statement":"MATCH (m:Manuscript {id: $mid})-[:CITES]->(ref) MATCH p = (ref)-[:CITES*1..2]->(l {doi: $doi}) WITH ref, p, [n IN nodes(p)[1..-1] | coalesce(n.doi, n.id)] AS via, [r IN relationships(p) | r.intent] AS intents RETURN ref.doi AS reference, length(p) AS hops, via, intents ORDER BY reference, hops"},"plan_cache":"miss","plan_ms":0.077578,"result_generation_ms":0.000471,"rewrite_ms":0.004652,"rows":[{"hops":1,"intents":["method"],"reference":"10.1016/j.neurobiolaging.2009.11.007","via":[]},{"hops":1,"intents":["unknown"],"reference":"10.1038/nm1782","via":[]},{"hops":2,"intents":["unknown","unknown"],"reference":"10.1038/nm1782","via":["10.1523/jneurosci.3501-06.2007"]},{"hops":2,"intents":["unknown","result"],"reference":"10.1038/nm1782","via":["10.1038/sj.emboj.7601953"]},{"hops":2,"intents":["unknown","unknown"],"reference":"10.1038/nm1782","via":["10.1159/000337230"]},{"hops":2,"intents":["unknown","unknown"],"reference…
```
</details>

**→ `relate` · `read_cypher`**

```json
{"statement": "MATCH (m:Manuscript {id: $mid})-[:CITES]->(ref)\nOPTIONAL MATCH (ref)-[:CITES]->(x)\nWITH ref, count(DISTINCT x) AS refs_in_graph\nOPTIONAL MATCH p = (ref)-[:CITES*1..2]->(l {doi: $doi})\nRETURN ref.doi AS reference, refs_in_graph,\n       count(DISTINCT CASE WHEN length(p)=1 THEN p END) AS direct_cites,\n       count(DISTINCT CASE WHEN length(p)=2 THEN nodes(p)[1] END) AS two_hop_intermediates\nORDER BY reference", "parameters": {"mid": "M:grant-draft", "doi": "10.1038/nature04533"}}
```

<details><summary>result (3,334 chars)</summary>

```json
{"columnTypes":["STRING","INTEGER","INTEGER","INTEGER"],"columns":["reference","refs_in_graph","direct_cites","two_hop_intermediates"],"elapsed_ms":1.096931,"error":null,"execute_ms":0.8476370000000001,"lex_parse_ms":0.013431,"lower_ms":0.06918300000000001,"notifications":[{"category":"PERFORMANCE","code":"Relate.Notification.Statement.MissingIndex","description":"the equality predicate on id filters :Manuscript without a range index on (:Manuscript {id})","gql_status":"03C91","operator_id":4,"remedy":"CREATE INDEX relate_Manuscript__id FOR (n:Manuscript) ON (n.id)","severity":"INFORMATION","title":"Missing index"}],"parse_ms":0.17146699999999998,"plan":{"profiled":false,"root":{"actual":null,"children":[{"actual":null,"children":[{"actual":null,"children":[{"actual":null,"children":[{"actual":null,"children":[],"details":"(m:Manuscript)-[:CITES]->(ref)","estimated_rows":null,"identifiers":[],"operator":"Expand","warnings":[{"category":"PERFORMANCE","code":"Relate.Notification.Statement.MissingIndex","description":"the equality predicate on id filters :Manuscript without a range index on (:Manuscript {id})","gql_status":"03C91","remedy":"CREATE INDEX relate_Manuscript__id FOR (n:Manuscript) ON (n.id)","severity":"INFORMATION","title":"Missing index"}]}],"details":"(ref)-[:CITES]->(x), optional","estimated_rows":1313,"identifiers":[],"operator":"Optional(Expand)","warnings":[]}],"details":"2 item(s), keys: ref, aggregation","estimated_rows":null,"identifiers":[],"operator":"EagerAggregation","warnings":[]}],"details":"p = (ref)-[:CITES*1..2]->(l), optional","estimated_rows":null,"identifiers":[],"operator":"Optional(Expand)","warnings":[]}],"details":"4 item(s), keys: reference, refs_in_graph, aggregation, ordered","estimated_rows":null,"identifiers":[],"operator":"EagerAggregation","warnings":[]},"schema":"relate.plan/v1","statement":"MATCH (m:Manuscript {id: $mid})-[:CITES]->(ref) OPTIONAL MATCH (ref)-[:CITES]->(x) WITH ref, count(DISTINCT x) AS refs_in_graph OPTIONAL MATCH p = (ref)-[:CITES*1..2]->(l {doi: $doi}) RETURN ref.doi AS reference, refs_in_graph, count(DISTINCT CASE WHEN length(p)=1 THEN p END) AS direct_cites, count(DISTINCT CASE WHEN length(p)=2 THEN nodes(p)[1] END) AS two_hop_intermediates ORDER BY reference"},"plan_cache":"miss","plan_ms":0.07144199999999999,"result_generation_ms":0.000366,"rewrite_ms":0.0043950000000000005,"rows":[{"direct_cites":1,"reference":"10.1016/j.neurobiolaging.2009.11.007","refs_in_graph":1,"two_hop_intermediate…
```
</details>

_(final answer below)_

## Final answer

# Audit of the grant background draft (label `M:grant-draft`)

Two of the seven references are retracted papers: **lesne2006** and **reed2011**. Two more lean on retracted Aβ*56 work at the point where they cite it: **cline2018** and **larson2012**. I recommend dropping lesne2006, reed2011 and larson2012, and keeping cline2018 only for the general oligomer claim. No paths turned up for walsh2002, selkoe2016 or shankar2008, apart from unreadable ones for shankar2008.

## Findings

I ran `retraction_status` on all 7 DOIs, then `check_references` (label `grant-draft`, depth 2). The check found 4 retracted papers, reachable from 5 of your 7 references: 2 `direct`, 1 `load_bearing`, 1 `unverified`. **The tool read only 4 of the 13 citing sentences on these paths.** The rest had no full text or metadata only. Treat what follows as evidence for a person to review, not a verdict. The citation-intent classifier is also imprecise (about 33% precision on held-out sentences), so I quote every sentence so you can judge it yourself.

### 1. `lesne2006`: you cite a retracted paper (direct)
- **Paper:** Lesné et al. 2006, *Nature*, "A specific amyloid-β protein assembly in the brain impairs memory" (10.1038/nature04533).
- **Retracted 2024-06-24.** Notice: 10.1038/s41586-024-07691-8.
- **Reasons per notice:** Concerns/Issues about Image; Duplication of/in Image; Manipulation of Images; Investigation by Journal/Publisher; Investigation by Third Party; Objections by Author(s); Upgrade/Update of Prior Notice(s).
- **Affected claim:** the whole Aβ*56 sentence. Memory impairment in Tg2576 mice and deficits after injection into young rats rest only on this paper.
- **Action:** remove it.

### 2. `reed2011`: you cite a retracted paper (direct)
- **Paper:** Reed et al., *Neurobiology of Aging* (10.1016/j.neurobiolaging.2009.11.007). OpenAlex dates it 2010; your BibTeX says 2011.
- **Retracted 2026-07-01** (from Crossref). Notice: 10.1016/j.neurobiolaging.2026.03.001.
- **Reasons:** none recorded in the notice data I have, so I can't quote any. `retraction_status` marks the paper retracted but returned no notice details.
- **It also relied on Lesné 2006 for a method:** "Forebrains were lysed in RIPA buffer and ultraentrifuged as previously described (Lesné et al., 2006)."
- **Affected claim:** "comparisons of cell-derived and synthetic oligomers revealed assembly-specific cognitive effects."
- **Action:** remove it.

### 3. `larson2012`: relies on retracted work (load-bearing)
- **Paper:** Larson & Lesné, *Journal of Neurochemistry*, "Soluble Aβ oligomer production and toxicity". It is not retracted itself.
- **It cites Lesné 2006 for a method (the 56-kDa detection):** "…apparent trimers (13 kDa), hexamers (27 kDa), nonamers (40 kDa) and dodecamers (56 kDa) were detected using antibodies targeting the N-terminus and central domain of Ab, such as 6E10, and using the A11 antibody… (Kayed et al. 2003; Lesne et al. 2006)."
- **It also cites `reed2011`.** That link is unverified: no full text.
- **Affected claim:** "these findings motivate therapies that target defined oligomeric species." In the draft, "defined species" refers back to the Aβ*56 and assembly-specific results that are now retracted.
- **Action:** drop it. The sentence needs a new, independent citation.

### 4. `cline2018`: relies on retracted work in one section (load-bearing)
Cline et al. 2018, *J Alzheimer's Disease*. All of the sentences below are in its section "A multitude of AβO species or just two?":
- **Relies on Lesné 2006 for a result:** "One specific type 1 AβO has been identified, the 56 kDa SDS-stable species sometimes referred to as Aβ*56 [44]."
- **Relies on a second retracted paper for a result:** 10.1126/scisignal.aal2021, "The amyloid-β oligomer Aβ*56 induces specific alterations in neuronal signaling…" (2017). Retracted 2025-12-23 (notice 10.1126/scisignal.aee6619). Reasons: none recorded in the notice data I have. Citing sentence: "A recent study by Lesné and colleagues compared the in vitro toxicity of Aβ*56 to two LMW species, dimers and trimers [127]."
- **Unverified (metadata only, no sentence available):**
  - It cites `reed2011`.
  - It cites 10.1523/jneurosci.1858-12.2012, "The Complex PrPc-Fyn Couples Human Oligomeric Aβ with Pathological Tau Changes…". Retracted 2025-03-12. Reasons per notice: Concerns/Issues about Image; Unreliable Image; Investigation by Company/Institution; Investigation by Third Party.
- Cline 2018 was published before all of these retractions, so it can't flag them.
- **Action:** the draft cites Cline only for the general claim that oligomers rather than plaques cause synaptic failure. Its reliance on retracted work is limited to the Aβ*56 material, so it can stay for that general claim, ideally listed after selkoe2016. Don't cite it for anything about Aβ*56.

### 5. `shankar2008`: no reliance shown (unverified only)
- Shankar 2008 cites Lesné 2006 directly and through 4 intermediate papers. None of those citations could be read (no full text).
- Its central result is independent: dimers taken from human Alzheimer's brain tissue.
- **Action:** keep it. This is low priority.

### No findings
- **walsh2002:** published before Lesné 2006, so it can't cite it.
- **selkoe2016:** no path to any retracted paper at depth 2. That means nothing was found, not that it was proven clean.

**None** of the citations on these paths were made after the retraction date (`cited_after_retraction`: 0).

## Graph check

**Question:** which references reach Lesné 2006 (10.1038/nature04533) within two citation hops, and through which papers?

```cypher
// paths of 1–2 hops from each reference to Lesné 2006
MATCH (m:Manuscript {id: $mid})-[:CITES]->(ref)
MATCH p = (ref)-[:CITES*1..2]->(l {doi: $doi})
WITH ref, p, [n IN nodes(p)[1..-1] | coalesce(n.doi, n.id)] AS via,
     [r IN relationships(p) | r.intent] AS intents
RETURN ref.doi AS reference, length(p) AS hops, via, intents
ORDER BY reference, hops
// $mid = 'M:grant-draft', $doi = '10.1038/nature04533'
```

```cypher
// per-reference summary, including references with no path
MATCH (m:Manuscript {id: $mid})-[:CITES]->(ref)
OPTIONAL MATCH (ref)-[:CITES]->(x)
WITH ref, count(DISTINCT x) AS refs_in_graph
OPTIONAL MATCH p = (ref)-[:CITES*1..2]->(l {doi: $doi})
RETURN ref.doi AS reference, refs_in_graph,
       count(DISTINCT CASE WHEN length(p)=1 THEN p END) AS direct_cites,
       count(DISTINCT CASE WHEN length(p)=2 THEN nodes(p)[1] END) AS two_hop_intermediates
ORDER BY reference
```

| Bib key | Cites Lesné 2006 directly (intent) | Reaches it in 2 hops via |
|---|---|---|
| lesne2006 | n/a (it *is* the retracted paper; 0 hops) | n/a |
| reed2011 | yes (**method**) | none |
| cline2018 | yes (**result**) | 1 paper: reed2011 (10.1016/j.neurobiolaging.2009.11.007), which cites Lesné for a **method** |
| shankar2008 | yes (unknown, no full text) | 4 papers: 10.1523/jneurosci.3501-06.2007; 10.1038/sj.emboj.7601953 (that paper cites Lesné for a result: "56* kDa oligomer assemblies from transgenic mouse brains (Lesne et al, 2006)"); 10.1523/jneurosci.5161-07.2008; 10.1159/000337230 ⚠️ |
| larson2012 | yes (**method**) | 26 papers: 10.1523/jneurosci.1189-06.2006, 10.1523/jneurosci.2984-08.2009, 10.1159/000261723, 10.1074/jbc.r800016200, 10.1523/jneurosci.2357-10.2010, 10.1016/j.neurobiolaging.2007.06.011, 10.1007/s10571-011-9691-4, 10.1038/nature07761, 10.1038/nature09217, 10.1073/pnas.0911829107, 10.1523/jneurosci.0204-08.2008, 10.1016/j.neuroscience.2007.10.054, 10.1002/ana.21321, 10.1074/jbc.m701078200, 10.1038/nm1782 (= shankar2008), 10.1016/j.nbd.2009.07.021, 10.3233/jad-2009-1096, 10.1523/jneurosci.5825-09.2010, 10.1016/j.neurobiolaging.2009.11.007 (= reed2011), 10.1002/emmm.201000082, 10.1111/j.1471-4159.2006.04157.x, 10.1523/jneurosci.5721-09.2010, 10.1073/pnas.0609521104, 10.4061/2009/689285, 10.1523/jneurosci.4878-07.2008, 10.1523/jneurosci.3501-06.2007 |
| walsh2002 | no | no |
| selkoe2016 | no | no |

**Reading this table:**
- **The graph seems to store only citations that lie on a path to retracted work.** Shankar has 5 citing edges stored and Cline 4, far fewer than their full reference lists. So "no" for selkoe2016 means no path was found, not that its reference list was confirmed clean.
- ⚠️ **One edge looks like a data error.** The graph has Shankar 2008 citing 10.1159/000337230, a paper from 2012. A 2008 paper can't cite a 2012 one, so this is probably wrong upstream citation data. Ignore that path.
- **Most 2-hop paths aren't evidence that your references relied on Lesné.** Many of larson2012's paths go through papers that only cite Lesné in passing, and the tool classed two of them as `defused` (10.1038/nature07761 and 10.1038/nature09217).

## Revised paragraph

> Soluble amyloid-β (Aβ) oligomers, rather than plaques, are widely proposed to be a proximate cause of synaptic failure in Alzheimer's disease [selkoe2016; cline2018]. Naturally secreted oligomers inhibit hippocampal long-term potentiation in vivo [walsh2002], and Aβ dimers isolated directly from Alzheimer's brains impair synaptic plasticity and memory [shankar2008]. Together, these findings motivate therapies that target soluble, synaptotoxic Aβ oligomers [**NEW CITATION NEEDED**: an independent source for the therapeutic rationale; larson2012 was removed].

**What changed:**
- **Removed:** the Aβ*56 sentence. Its only support was lesne2006 (retracted 2024-06-24). I couldn't find independent support in the given references, so I dropped it rather than re-citing it.
- **Removed:** the assembly-specific cognitive effects claim. Its only support was reed2011 (retracted 2026-07-01).
- **Narrowed:** "defined oligomeric species" became "soluble, synaptotoxic Aβ oligomers". The claim now rests only on walsh2002 and shankar2008. If you want to keep the species-specific framing, you need a new primary source that doesn't depend on Aβ*56.
- **Toned down:** "now widely considered *the* proximate cause" became "widely proposed to be *a* proximate cause". This is optional, but the review evidence supports a hypothesis rather than a consensus.
- **Reordered:** selkoe2016 now comes first, because cline2018 relies on retracted Aβ*56 work in one section.

## Revised BibTeX

```bibtex
@article{selkoe2016, title={The amyloid hypothesis of Alzheimer's disease at 25 years}, author={Selkoe, Dennis J. and Hardy, John}, journal={EMBO Molecular Medicine}, year={2016}, doi={10.15252/emmm.201606210}}
@article{cline2018, title={The Amyloid-β Oligomer Hypothesis: Beginning of the Third Decade}, author={Cline, Erika N. and Bicca, Maíra A. and Viola, Kirsten L. and Klein, William L.}, journal={Journal of Alzheimer's Disease}, year={2018}, doi={10.3233/JAD-179941}}
@article{walsh2002, title={Naturally secreted oligomers of amyloid β protein potently inhibit hippocampal long-term potentiation in vivo}, author={Walsh, Dominic M. and Klyubin, Igor and others}, journal={Nature}, year={2002}, doi={10.1038/416535a}}
@article{shankar2008, title={Amyloid-β protein dimers isolated directly from Alzheimer's brains impair synaptic plasticity and memory}, author={Shankar, Ganesh M. and others}, journal={Nature Medicine}, year={2008}, doi={10.1038/nm1782}}
```

Before submitting, run `retraction_status` on whatever new citation you add for the therapy sentence. For the final version, a `depth=3` `check_references` run gives a fuller audit.

## Run

- turns: 9, tool calls: 8, wall time: 111 s
- cost: $0.50 (budget cap $3.00), stop: success
- store: a clone of `data/demo.rl` (temporary)
