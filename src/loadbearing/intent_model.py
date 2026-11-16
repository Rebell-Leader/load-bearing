"""Learned citation-intent classifier (BiomedBERT fine-tuned on SciCite).

Optional: needs the `train` dependency group (torch, transformers) and a trained model directory.
Input is the pair (section title, citing sentence), the same way it was trained.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

DEFAULT_MODEL = Path("models/intent-biomedbert-scicite")
_loaded: "IntentModel | None | bool" = False


def load_default() -> "IntentModel | None":
    """The model if torch, transformers and the weights are present; otherwise None (rules take over).

    LOADBEARING_INTENT_MODEL overrides the path; set it to 'none' to force the rules.
    """
    global _loaded
    if _loaded is not False:
        return _loaded
    path = os.environ.get("LOADBEARING_INTENT_MODEL", str(DEFAULT_MODEL))
    _loaded = None
    if path.lower() != "none" and (Path(path) / "config.json").exists():
        try:
            _loaded = IntentModel(path)
        except ImportError:
            print("intent model found but torch/transformers missing (uv sync --group train); using rules", file=sys.stderr)
    return _loaded


class IntentModel:
    def __init__(self, path: str | Path = DEFAULT_MODEL, device: str | None = None, max_len: int = 192):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self.torch = torch
        self.path = Path(path)
        self.tok = AutoTokenizer.from_pretrained(self.path)
        self.model = AutoModelForSequenceClassification.from_pretrained(self.path)
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device).eval()
        self.labels = [self.model.config.id2label[i] for i in range(self.model.config.num_labels)]
        self.max_len = max_len

    def predict_proba(self, sentences: list[str], sections: list[str] | None = None, batch: int = 64) -> list[dict]:
        sections = sections or [""] * len(sentences)
        out = []
        for i in range(0, len(sentences), batch):
            enc = self.tok([s or "" for s in sections[i:i + batch]], [t or "" for t in sentences[i:i + batch]],
                           truncation="only_second", max_length=self.max_len, padding=True, return_tensors="pt").to(self.device)
            with self.torch.no_grad():
                probs = self.torch.softmax(self.model(**enc).logits.float(), dim=-1).cpu().tolist()
            out += [dict(zip(self.labels, p)) for p in probs]
        return out

    def predict(self, sentences: list[str], sections: list[str] | None = None) -> list[str]:
        return [max(p, key=p.get) for p in self.predict_proba(sentences, sections)]

    def card(self) -> dict:
        f = self.path / "metrics.json"
        return json.loads(f.read_text()) if f.exists() else {}
