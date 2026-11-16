# Citation-intent labelling guidelines (Load-Bearing)

The question for every citing sentence: **does the citing paper lean on the cited work?**

| Label | Use when | Examples |
|---|---|---|
| `method` | The citing paper reuses a method, protocol, assay, model organism or line, dose choice, dataset or code from the cited work | "as previously described [12]", "dose selection was based on [23,24]", "data from GSE36980 [27]" |
| `result` | The sentence uses a specific empirical finding of the cited **primary** study as evidence for a claim, compares results with it, or pools its data | "X was shown to reduce Y in mice [14]", "consistent with [7]", a meta-analysis listing included trials |
| `background` | General or textbook knowledge, framing, prevalence, a claim sourced to a **review**, long lists of examples, figure-source credits, or a description of what a study did without using its finding | "AD is a common disease [1]", "reviewed in [5]", "Adapted from [70, 71]" |
| `critical` | The sentence questions the specific cited work: retraction, failed replication, a methodological flaw, or skeptical wording ("alleged") | "the alleged requirement of PrPc (Lauren 2009)", "obtained using unphysiologically high concentrations" |

Decision order: critical > method > result > background. A neutral "remains controversial" is background.

`indomain_labels.csv`: `label` is the first pass by Claude, made blind to the rule predictions.
`expert_label` is for a domain expert's correction; scoring uses it whenever it is filled in.
