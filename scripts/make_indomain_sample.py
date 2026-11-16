"""Draw a stratified, blind sample of citing sentences from the evidence graph for labelling.

  uv run python scripts/make_indomain_sample.py [store] [--seed 7]

Writes
  data/eval/indomain_sample.csv        id, citing/cited titles, section, sentence  (no predictions: label blind)
  data/eval/indomain_predictions.json  id -> rules-v0 label and stratum (kept apart until scoring)
"""

import argparse
import csv
import json
import random
from pathlib import Path

import relate

QUOTA = {"critical": 999, "method": 999, "result": 60, "background": 67}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("store", nargs="?", default="data/demo.rl")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    conn = relate.connect(args.store, read_only=True)
    rows = [dict(r) for r in conn.execute(
        """MATCH (a:Paper)-[c:CITES]->(b:Paper) WHERE c.context IS NOT NULL
           RETURN a.id AS src, b.id AS dst, a.title AS citing, b.title AS cited, c.section AS section,
                  c.context AS sentence, c.intent AS pred, c.evidence AS evidence, b:Retracted AS cited_retracted
           ORDER BY src, dst""")]
    conn.close()
    rng = random.Random(args.seed)
    sample = []
    for label, quota in QUOTA.items():
        pool = [r for r in rows if r["pred"] == label]
        rng.shuffle(pool)
        sample += pool[:quota]
    rng.shuffle(sample)
    out = Path("data/eval")
    out.mkdir(parents=True, exist_ok=True)
    with (out / "indomain_sample.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "citing", "cited", "section", "sentence"])
        for i, r in enumerate(sample, 1):
            r["id"] = f"s{i:03d}"
            cited = (r["cited"] or "").replace("RETRACTED ARTICLE: ", "").replace("RETRACTED: ", "")
            w.writerow([r["id"], r["citing"], cited, r["section"] or "", r["sentence"]])
    pred = {r["id"]: {"pred": r["pred"], "src": r["src"], "dst": r["dst"], "evidence": r["evidence"],
                      "cited_retracted": r["cited_retracted"]} for r in sample}
    (out / "indomain_predictions.json").write_text(json.dumps({"seed": args.seed, "pool_sizes": {
        k: sum(1 for r in rows if r["pred"] == k) for k in QUOTA}, "items": pred}, indent=1))
    print(f"{len(sample)} sentences from {len(rows)} read citations -> {out}/indomain_sample.csv")


if __name__ == "__main__":
    main()
