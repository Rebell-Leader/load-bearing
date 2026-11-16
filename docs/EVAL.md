# Citation-intent evaluation (2026-11-16)

Load-Bearing calls a path *load-bearing* when every citation after the author's own is a **method** or
**result** citation, meaning the citing paper leans on the cited work. This page measures how well that
label is assigned. Short version:

- The original rules (v0) missed most real reliance (held-out recall 0.08).
- A BiomedBERT model fine-tuned on SciCite reaches **0.856 macro-F1 on SciCite**, but SciCite defines
  "result" narrowly, so on its own it finds almost none of our reliance.
- Intent **v1**, the shipped default, combines that model (for methods) with the cited work's type
  (review or primary research) and two precision guards. Held-out reliance recall rises to **0.69**,
  but precision is only **0.33**. A load-bearing finding is a lead to check, and the report always shows
  the sentence.
- More in-domain labels are the way to raise precision (see the end of this page).

## Data

| Set | Size | What it is | Labels |
|---|---|---|---|
| SciCite test | 1,861 | Citing sentences from Semantic Scholar (CS and biomedicine). Cohan et al., NAACL 2019; AI2, Apache-2.0 | Crowd and expert: background / method / result (= result *comparison*) |
| In-domain tuning sample | 160 | Sentences from the demo graph, stratified by the v0 prediction (all critical and method, 60 result, 67 background) | Claude, blind to predictions, per [`data/eval/GUIDELINES.md`](../data/eval/GUIDELINES.md) |
| In-domain held-out | 60 | Simple random sample from the 446 read citations *not* in the tuning sample. Labelled after v1 was frozen | Same as above |

Gold labels come from Claude, not a domain expert. The CSVs have an empty `expert_label` column; any
value filled in there replaces the first pass the next time the scripts run.

## Results

### SciCite test (n = 1,861)

| Classifier | Accuracy | Macro-F1 | F1 background | F1 method | F1 result |
|---|---|---|---|---|---|
| Majority class | 0.536 | — | — | — | — |
| Rules v0 | 0.638 | 0.603 | 0.680 | 0.775 | 0.354 |
| **BiomedBERT + SciCite** (3 epochs, 1.2 min on an RTX 4080) | **0.870** | **0.856** | 0.884 | 0.881 | 0.803 |

The fine-tuned model is on par with published SciCite results. Reproduce with
`HF_HUB_OFFLINE=1 uv run --group train python scripts/train_intent.py`; metrics go to
`models/intent-biomedbert-scicite/metrics.json`.

### In-domain: reliance (method or result) vs. not

| Classifier | Tuning sample (160): population-weighted P / R | **Held-out (60): P [95% CI] / R** |
|---|---|---|
| Rules v0 | 0.67 / 0.27 | 0.17 [0.03–0.56] (6 predicted) / 0.08 |
| SciCite model alone | 1.00 / 0.12 | — (0 predicted) / 0.00 |
| v1, rules only (no PyTorch) | 0.80 / 0.85 | 0.33 [0.19–0.52] (27 predicted) / 0.69 |
| **v1 + model** (default when installed) | 0.82 / 0.87 | 0.33 [0.19–0.52] (27 predicted) / 0.69 |

The held-out base rate is 13 reliance out of 60. Accuracy is a poor guide on this background-heavy set,
since predicting "background" everywhere already scores 0.78. Full outputs: `runs/eval_indomain.json`,
`runs/eval_heldout.json`.

## Why the tuning number and the held-out number differ

1. **Stratification.** The tuning sample over-represents sentences v0 called result or method, where
   reliance is common. The held-out pool is mostly ordinary background sentences.
2. **Tuning on the test.** The two v1 guards (vague evidence-talk; three or more references with no
   specific detail) were written after reading tuning-sample errors. They raised tuning precision from
   0.77 to 0.86, and that gain didn't carry over.
3. **The guideline and the classifier share a rule.** "A claim sourced to a review is background" is
   both a labelling rule and a v1 feature, so in-domain agreement partly measures self-consistency.

## What v1 still gets wrong

All 18 held-out false positives are **textbook statements cited to primary research**. Examples: "AD is
a major cause of dementia [2,3]" cited to an ipriflavone mouse study; "There are two central pathways
involved in apoptosis [183]"; "The diameters of such liposome particles vary from 25 nm to 2.5 μm [6]"
(a review that OpenAlex types as an article).

## A tested idea that didn't work: claim alignment

Hypothesis: real reliance restates the cited paper's own claim ("H2S levels are lowered in AD" against
the cited title "Brain hydrogen sulfide is severely decreased in AD").

Test: an NLI model (DeBERTa-xlarge-MNLI) scored entailment between each sentence and its cited title,
in both directions, alongside title-word overlap. The best feature reached AUC 0.50 over all 220 labels
and 0.45 on the held-out set: no signal. Titles are too short, and textbook claims often share words
with the cited title. Abstract-level alignment hasn't been tested.

## What would move precision

1. **Expert labels.** About 300 to 500 in-domain sentences labelled by a biomedical NLP researcher would
   give independent gold and enough data to fine-tune the SciCite model on our own definition. The
   label CSVs and guideline are ready for that.
2. **Better review detection.** OpenAlex misses some reviews. Title cues ("overview", "advances",
   "classification") or the cited paper's reference count could catch them.
3. **Path scores instead of hard labels.** Per-edge reliance probabilities, multiplied along each path,
   would rank load-bearing findings instead of filtering them.

## How the product handles this today

- Every load-bearing finding carries its evidence sentence and the rule that fired (`CITES.rule`, for
  example "cites primary research (article)" or "model: method p=0.97"). The MCP guidance tells agents
  to read the sentence before acting.
- Each edge records which classifier labelled it (`CITES.classifier`: `v1+biomedbert-scicite` or `v1-rules`).
- On the demo paper, v1 reports 23 load-bearing papers marked retracted, 21 of them with a retraction notice (v0: 10), 155 unverified and 171
  mention-only. Given held-out precision, treat the 23 as candidates. Lesné 2006, the hepcidin-motif
  case and the meta-analysis pooling the retracted rodent study all hold up on manual reading.
