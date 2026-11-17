"""Tiny cached HTTP GET. Every response is stored under data/raw/cache so re-runs
spend no API budget and the demo works offline once warmed."""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CACHE = Path("data/raw/cache") if Path("data/raw/cache").exists() else (_ROOT / "data/raw/cache")
CACHE_DIR = Path(os.environ.get("LOADBEARING_CACHE", str(_DEFAULT_CACHE)))
USER_AGENT = "load-bearing/0.1 (relate hackathon spike)"
stats = {"network": 0, "cached": 0}


class HttpError(RuntimeError):
    def __init__(self, code: int, url: str, body: str):
        super().__init__(f"HTTP {code} for {url.split('api_key=')[0]}: {body[:300]}")
        self.code = code


def _cache_path(url: str) -> Path:
    clean = url.split("&api_key=")[0].split("?api_key=")[0]
    return CACHE_DIR / hashlib.sha256(clean.encode()).hexdigest()[:32]


def get(url: str, *, as_json: bool = True, retries: int = 5):
    path = _cache_path(url)
    if path.exists():
        stats["cached"] += 1
        raw = path.read_bytes()
        return json.loads(raw) if as_json else raw.decode("utf-8", "replace")
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
            stats["network"] += 1
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            return json.loads(raw) if as_json else raw.decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            if exc.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise HttpError(exc.code, url, body) from exc
        except urllib.error.URLError:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise
    raise RuntimeError("unreachable")
