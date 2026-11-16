"""Fine-tune BiomedBERT on SciCite for citation intent (background / method / result).

  HF_HUB_OFFLINE=1 uv run --group train python scripts/train_intent.py [--epochs 3] [--seed 13]

Input pairs are (section title, citing sentence). The best epoch by dev macro-F1 is saved to
models/intent-biomedbert-scicite/ with metrics.json (dev and test scores).
"""

import argparse
import json
import random
import time
from pathlib import Path

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer, get_linear_schedule_with_warmup

from loadbearing.evaluate import binary, load_scicite, scores

BASE = "microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext"
LABELS = ["background", "method", "result"]
OUT = Path("models/intent-biomedbert-scicite")


def batches(rows, tok, size, max_len, shuffle, rng):
    idx = list(range(len(rows)))
    if shuffle:
        rng.shuffle(idx)
    for i in range(0, len(idx), size):
        chunk = [rows[j] for j in idx[i:i + size]]
        enc = tok([r["section"] for r in chunk], [r["text"] for r in chunk], truncation="only_second",
                  max_length=max_len, padding=True, return_tensors="pt")
        enc["labels"] = torch.tensor([LABELS.index(r["label"]) for r in chunk])
        yield enc


def evaluate(model, rows, tok, device, max_len):
    model.eval()
    preds = []
    with torch.no_grad():
        for enc in batches(rows, tok, 128, max_len, False, None):
            enc = {k: v.to(device) for k, v in enc.items() if k != "labels"}
            with torch.autocast("cuda", dtype=torch.bfloat16, enabled=device == "cuda"):
                logits = model(**enc).logits
            preds += [LABELS[i] for i in logits.argmax(-1).tolist()]
    gold = [r["label"] for r in rows]
    return {"three_way": scores(gold, preds, LABELS), "load_bearing_binary": binary(gold, preds)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--max-len", type=int, default=192)
    ap.add_argument("--seed", type=int, default=13)
    args = ap.parse_args()
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    rng = random.Random(args.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"

    train, dev, test = (load_scicite(s) for s in ("train", "dev", "test"))
    tok = AutoTokenizer.from_pretrained(BASE)
    model = AutoModelForSequenceClassification.from_pretrained(
        BASE, num_labels=3, id2label=dict(enumerate(LABELS)), label2id={l: i for i, l in enumerate(LABELS)}).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    steps = args.epochs * ((len(train) + args.batch - 1) // args.batch)
    sched = get_linear_schedule_with_warmup(opt, int(0.06 * steps), steps)

    best, history = -1.0, []
    t0 = time.time()
    for epoch in range(1, args.epochs + 1):
        model.train()
        total = 0.0
        for enc in batches(train, tok, args.batch, args.max_len, True, rng):
            enc = {k: v.to(device) for k, v in enc.items()}
            with torch.autocast("cuda", dtype=torch.bfloat16, enabled=device == "cuda"):
                loss = model(**enc).loss
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            opt.zero_grad()
            total += loss.item()
        dev_res = evaluate(model, dev, tok, device, args.max_len)
        f1 = dev_res["three_way"]["macro_f1"]
        history.append({"epoch": epoch, "train_loss": round(total, 2), "dev_macro_f1": f1, "minutes": round((time.time() - t0) / 60, 1)})
        print(history[-1], flush=True)
        if f1 > best:
            best = f1
            OUT.mkdir(parents=True, exist_ok=True)
            model.save_pretrained(OUT)
            tok.save_pretrained(OUT)

    model = AutoModelForSequenceClassification.from_pretrained(OUT).to(device)
    metrics = {"base_model": BASE, "data": "SciCite (Cohan et al., NAACL 2019), train split", "args": vars(args),
               "history": history, "dev": evaluate(model, dev, tok, device, args.max_len),
               "test": evaluate(model, test, tok, device, args.max_len)}
    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=2))
    t = metrics["test"]
    print(f"test: acc {t['three_way']['accuracy']} macro-F1 {t['three_way']['macro_f1']} "
          f"-> {OUT}")
    print({k: v["f1"] for k, v in t["three_way"]["per_class"].items()})


if __name__ == "__main__":
    main()
