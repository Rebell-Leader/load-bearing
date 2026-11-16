"""Scoring helpers for citation-intent classifiers (no sklearn needed)."""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

from .fulltext import _section_type

SCICITE_DIR = Path("data/raw/scicite/scicite")
RELIANCE = {"method", "result"}


def load_scicite(split: str) -> list[dict]:
    rows = []
    for line in (SCICITE_DIR / f"{split}.jsonl").open():
        r = json.loads(line)
        section = r.get("sectionName")
        section = section if isinstance(section, str) else ""
        rows.append({"text": r["string"], "section": section, "section_type": _section_type(section, ""),
                     "label": r["label"], "id": r["unique_id"]})
    return rows


def scores(gold: list[str], pred: list[str], labels: list[str]) -> dict:
    cm = Counter(zip(gold, pred))
    per = {}
    for lab in labels:
        tp = cm[(lab, lab)]
        fp = sum(cm[(g, lab)] for g in labels if g != lab) + sum(v for (g, p), v in cm.items() if p == lab and g not in labels)
        fn = sum(cm[(lab, p)] for p in set(pred) if p != lab)
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        f = 2 * p * r / (p + r) if p + r else 0.0
        per[lab] = {"precision": round(p, 3), "recall": round(r, 3), "f1": round(f, 3), "support": sum(1 for g in gold if g == lab)}
    acc = sum(1 for g, p in zip(gold, pred) if g == p) / len(gold)
    return {"accuracy": round(acc, 3), "macro_f1": round(sum(v["f1"] for v in per.values()) / len(labels), 3),
            "per_class": per, "confusion": {f"{g}->{p}": n for (g, p), n in sorted(cm.items())}}


def binary(gold: list[str], pred: list[str], positive: set[str] = RELIANCE) -> dict:
    """Load-bearing view: is the citation relied on (method/result) or not?"""
    g = [x in positive for x in gold]
    p = [x in positive for x in pred]
    tp = sum(a and b for a, b in zip(g, p))
    fp = sum((not a) and b for a, b in zip(g, p))
    fn = sum(a and (not b) for a, b in zip(g, p))
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": round(prec, 3), "recall": round(rec, 3),
            "f1": round(2 * prec * rec / (prec + rec), 3) if prec + rec else 0.0,
            "precision_95ci": wilson(tp, tp + fp), "n_predicted": tp + fp, "n_gold": tp + fn}


def wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    """95% Wilson interval for a proportion; small samples need honest error bars."""
    if n == 0:
        return [0.0, 0.0]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 3), round(c + h, 3)]
