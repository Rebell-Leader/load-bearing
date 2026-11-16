"""Score the rule-based intent classifier (v0) on the SciCite test split.

  uv run python scripts/eval_scicite.py [--split test]

SciCite (Cohan et al., NAACL 2019; AI2, Apache-2.0): background / method / result(comparison).
Our 'critical' label has no SciCite counterpart and is scored as background.
"""

import argparse
import json
from collections import Counter

from loadbearing import intent
from loadbearing.evaluate import binary, load_scicite, scores

LABELS = ["background", "method", "result"]


def predict_rules(rows):
    out = []
    for r in rows:
        label, _ = intent.classify(r["text"], r["section_type"])
        out.append({"critical": "background", "unknown": "background"}.get(label, label))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="test")
    args = ap.parse_args()
    rows = load_scicite(args.split)
    gold = [r["label"] for r in rows]
    pred = predict_rules(rows)
    res = {"split": args.split, "n": len(rows), "classifier": "rules-v0",
           "three_way": scores(gold, pred, LABELS), "load_bearing_binary": binary(gold, pred),
           "predicted_distribution": Counter(pred), "majority_baseline_accuracy": round(Counter(gold).most_common(1)[0][1] / len(gold), 3)}
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
