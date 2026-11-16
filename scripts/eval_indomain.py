"""Score intent classifiers on the in-domain sample (sentences from our own evidence graph).

  uv run python scripts/eval_indomain.py [--model PATH]

Gold = expert_label when filled in, else the blind first-pass label. The sample is stratified by the
rules' prediction, so per-label precision is estimated directly; recall and accuracy are reweighted to
the population of 606 read citations.
"""

import argparse
import csv
import json
from collections import Counter

from loadbearing import intent
from loadbearing.evaluate import binary, scores, wilson
from loadbearing.fulltext import _section_type

LABELS = ["background", "method", "result", "critical"]


def load(name: str):
    sample = {r["id"]: r for r in csv.DictReader(open(f"data/eval/{name}_sample.csv"))}
    gold = {}
    for r in csv.DictReader(open(f"data/eval/{name}_labels.csv")):
        gold[r["id"]] = r["expert_label"].strip() or r["label"]
    meta = json.load(open(f"data/eval/{name}_predictions.json"))
    return sample, gold, meta


def weighted(rows, gold, pred, strata, pool):
    """Population estimate: each stratum (rules prediction) weighted by its pool size."""
    n_s = Counter(strata[i] for i in rows)
    w = {i: pool[strata[i]] / n_s[strata[i]] for i in rows}
    acc = sum(w[i] for i in rows if gold[i] == pred[i]) / sum(w.values())
    rel = {"method", "result"}
    tp = sum(w[i] for i in rows if gold[i] in rel and pred[i] in rel)
    fn = sum(w[i] for i in rows if gold[i] in rel and pred[i] not in rel)
    fp = sum(w[i] for i in rows if gold[i] not in rel and pred[i] in rel)
    return {"accuracy": round(acc, 3), "reliance_precision": round(tp / (tp + fp), 3) if tp + fp else 0,
            "reliance_recall": round(tp / (tp + fn), 3) if tp + fn else 0,
            "gold_reliance_share": round(sum(w[i] for i in rows if gold[i] in rel) / sum(w.values()), 3)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", help="path to a trained classifier (see scripts/train_intent.py)")
    ap.add_argument("--set", default="indomain", choices=["indomain", "heldout"],
                    help="indomain: stratified tuning sample (160); heldout: simple random sample (60), never tuned on")
    args = ap.parse_args()
    sample, gold, meta = load(args.set)
    ids = sorted(sample)
    if args.set == "heldout":  # simple random sample: one stratum, no reweighting
        strata, pool = {i: "all" for i in ids}, {"all": meta["pool"]}
    else:
        strata, pool = {i: meta["items"][i]["pred"] for i in ids}, meta["pool_sizes"]

    sec = {i: _section_type(sample[i]["section"], "") for i in ids}
    if args.set == "heldout":
        types = {i: {"type": meta["items"][i]["cited_type"]} for i in ids}
    else:
        types = json.load(open("data/eval/indomain_cited_types.json"))  # OpenAlex work type of each cited paper
    preds = {"rules-v0": {i: intent.classify(sample[i]["sentence"], sec[i])[0] for i in ids},
             "v1-rules": {i: intent.classify_v1(sample[i]["sentence"], sec[i], types[i]["type"])[0] for i in ids}}
    if args.model:
        from loadbearing.intent_model import IntentModel
        m = IntentModel(args.model)
        probs = dict(zip(ids, m.predict_proba([sample[i]["sentence"] for i in ids], [sample[i]["section"] for i in ids])))
        preds["scicite-model-alone"] = {i: max(probs[i], key=probs[i].get) for i in ids}
        preds["v1+model"] = {i: intent.classify_v1(sample[i]["sentence"], sec[i], types[i]["type"], probs[i]["method"])[0] for i in ids}

    out = {"n": len(ids), "gold_distribution": Counter(gold[i] for i in ids),
           "gold_source": Counter("expert" if r["expert_label"].strip() else r["annotator"]
                                  for r in csv.DictReader(open(f"data/eval/{args.set}_labels.csv")))}
    for name, p in preds.items():
        g = [gold[i] for i in ids]
        q = [p[i] for i in ids]
        by_pred = {}
        for lab in LABELS:
            hits = [i for i in ids if p[i] == lab]
            k = sum(1 for i in hits if gold[i] == lab)
            by_pred[lab] = {"n": len(hits), "precision": round(k / len(hits), 3) if hits else None, "ci95": wilson(k, len(hits))}
        out[name] = {"sample_scores": scores(g, q, LABELS), "reliance_binary_sample": binary(g, q),
                     "precision_by_predicted_label": by_pred,
                     "population_estimate": weighted(ids, gold, p, strata, pool)}
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
