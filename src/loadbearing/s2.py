"""Semantic Scholar fallback: citation contexts and intents for a citing paper's references."""

from __future__ import annotations

import os
import time
import urllib.parse

from . import http

BASE = "https://api.semanticscholar.org/graph/v1"
_last_call = 0.0


def references(citing_doi: str) -> list[dict]:
    """[{doi, title, contexts, intents, influential}] or [] if unavailable."""
    global _last_call
    key = os.environ.get("S2_API_KEY")
    url = (f"{BASE}/paper/DOI:{urllib.parse.quote(citing_doi)}/references"
           "?fields=title,externalIds,contexts,intents,isInfluential&limit=1000")
    if key:
        url += f"&api_key={key}"  # stripped from the cache key; S2 also accepts the x-api-key header
    wait = 1.1 - (time.time() - _last_call)
    if wait > 0:
        time.sleep(wait)
    try:
        # Unauthenticated S2 shares one rate pool; on 429 give up fast instead of backing off for minutes.
        data = http.get(url, retries=2)
    except (http.HttpError, OSError):
        return []
    finally:
        _last_call = time.time()
    out = []
    for item in data.get("data") or []:
        cited = item.get("citedPaper") or {}
        ext = cited.get("externalIds") or {}
        out.append({
            "doi": (ext.get("DOI") or "").lower() or None,
            "title": cited.get("title") or "",
            "contexts": item.get("contexts") or [],
            "intents": item.get("intents") or [],
            "influential": bool(item.get("isInfluential")),
        })
    return out
