"""Minimal OpenAlex client: batched lookups and server-side retraction filtering.

Without OPENALEX_API_KEY every request draws on a small shared daily budget
(~1,000 requests per IP) and cursor paging is refused. Set the env var to use
your own free key. Responses are cached on disk (see http.py).
"""

from __future__ import annotations

import os
import urllib.parse
from collections.abc import Iterable, Iterator

from . import http

BASE = "https://api.openalex.org"
WORK_FIELDS = "id,doi,title,publication_year,publication_date,is_retracted,referenced_works,authorships"
SLIM_FIELDS = "id,doi,title,publication_year,publication_date,is_retracted"


def short_id(openalex_id: str) -> str:
    """'https://openalex.org/W123' -> 'W123'."""
    return openalex_id.rsplit("/", 1)[-1]


def norm_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    doi = doi.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "http://dx.doi.org/", "https://dx.doi.org/", "doi:"):
        if doi.startswith(prefix):
            doi = doi[len(prefix):]
    return doi or None


def _get(path: str, params: dict[str, str]) -> dict:
    key = os.environ.get("OPENALEX_API_KEY")
    if key:
        params = {**params, "api_key": key}
    return http.get(f"{BASE}{path}?{urllib.parse.urlencode(params, safe=':|,*')}")


def _batched(items: list[str], size: int) -> Iterator[list[str]]:
    for i in range(0, len(items), size):
        yield items[i:i + size]


def works_by_ids(ids: Iterable[str], select: str = WORK_FIELDS) -> list[dict]:
    """Fetch works by OpenAlex short ids, 100 per request."""
    unique = sorted({short_id(i) for i in ids})
    out: list[dict] = []
    for batch in _batched(unique, 100):
        data = _get("/works", {"filter": "openalex_id:" + "|".join(batch), "per-page": "100", "select": select})
        out.extend(data["results"])
    return out


def works_by_dois(dois: Iterable[str], select: str = WORK_FIELDS) -> list[dict]:
    """Fetch works by DOI, 50 per request (DOIs make long URLs)."""
    unique = sorted({d for d in (norm_doi(x) for x in dois) if d})
    out: list[dict] = []
    for batch in _batched(unique, 50):
        data = _get("/works", {"filter": "doi:" + "|".join(batch), "per-page": "50", "select": select})
        out.extend(data["results"])
    return out


def retracted_cited_by(citing_ids: Iterable[str]) -> list[dict]:
    """Retracted works referenced by any of the given works.

    OpenAlex intersects server-side: filter=is_retracted:true,cited_by:A|B|C.
    One request covers 100 citing works, so we never download whole reference lists
    just to learn which entries are retracted.
    """
    unique = sorted({short_id(i) for i in citing_ids})
    out: dict[str, dict] = {}
    for batch in _batched(unique, 100):
        data = _get("/works", {
            "filter": "is_retracted:true,cited_by:" + "|".join(batch),
            "per-page": "200",
            "select": SLIM_FIELDS,
        })
        for w in data["results"]:
            out[short_id(w["id"])] = w
    return list(out.values())


def work(id_or_doi: str, select: str = WORK_FIELDS) -> dict:
    key = id_or_doi if id_or_doi.upper().startswith("W") else "doi:" + norm_doi(id_or_doi)
    return _get(f"/works/{key}", {"select": select})


def iter_filter(filter_expr: str, select: str, per_page: int = 200) -> Iterator[dict]:
    """Cursor-page through every work matching a filter (needs OPENALEX_API_KEY)."""
    cursor = "*"
    while cursor:
        data = _get("/works", {"filter": filter_expr, "per-page": str(per_page), "cursor": cursor, "select": select})
        yield from data["results"]
        cursor = data["meta"].get("next_cursor")
        if not data["results"]:
            break
