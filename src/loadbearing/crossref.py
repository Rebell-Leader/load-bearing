"""Crossref fallback for retraction notices that Retraction Watch hasn't recorded yet.

Publishers register a notice that "updates" the original DOI; Crossref's filter=updates:<doi>
finds it. Crossref carries the notice DOI, type and date, but not the reasons.
"""

from __future__ import annotations

import urllib.parse

from . import http

API = "https://api.crossref.org/works"
RANK = {"retraction": 4, "withdrawal": 3, "removal": 3, "expression_of_concern": 2, "correction": 1, "erratum": 1}


def notice(doi: str) -> dict | None:
    """{nature, date, notice_doi, title, source} for the strongest notice updating `doi`, or None."""
    url = f"{API}?filter=updates:{urllib.parse.quote(doi)}&select=DOI,title,update-to&rows=20"
    try:
        items = http.get(url).get("message", {}).get("items", [])
    except (http.HttpError, OSError, ValueError):
        return None
    best = None
    for item in items:
        notice_doi = (item.get("DOI") or "").lower()
        if notice_doi == doi.lower():  # a record pointing at itself is not a notice
            continue
        title = (item.get("title") or [""])[0]
        for upd in item.get("update-to") or []:
            if (upd.get("DOI") or "").lower() != doi.lower():
                continue
            kind = upd.get("type", "")
            if "retract" in title.lower():  # e.g. Elsevier "Retraction notice to …" typed as erratum
                kind = "retraction"
            parts = (upd.get("updated") or {}).get("date-parts", [[None]])[0]
            date = "-".join(f"{p:02d}" if i else str(p) for i, p in enumerate(parts)) if parts and parts[0] else None
            cand = {"kind": kind, "date": date if date and len(parts) == 3 else None, "notice_doi": notice_doi, "title": title}
            if best is None or RANK.get(kind, 0) > RANK.get(best["kind"], 0):
                best = cand
    if not best:
        return None
    nature = {"retraction": "Retraction", "withdrawal": "Retraction", "removal": "Retraction",
              "expression_of_concern": "Expression of concern"}.get(best["kind"], "Correction")
    return {"nature": nature, "date": best["date"], "notice_doi": best["notice_doi"], "title": best["title"],
            "source": "crossref", "reasons": []}
