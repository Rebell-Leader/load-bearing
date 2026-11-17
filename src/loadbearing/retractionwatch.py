"""Retraction Watch database (open via Crossref): DOI -> retraction notice facts.

Source CSV: https://gitlab.com/crossref/retraction-watch-data (retraction_watch.csv).
We only ever report what a notice says (nature, date, reasons); we never infer misconduct.
"""

from __future__ import annotations

import csv
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from . import crossref

_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CSV = Path("data/raw/retraction_watch.csv") if Path("data/raw/retraction_watch.csv").exists() else (_ROOT / "data/raw/retraction_watch.csv")


def _iso(us_date: str) -> str | None:
    """'12/1/2020 0:00' -> '2020-12-01'."""
    us_date = (us_date or "").strip()
    if not us_date:
        return None
    try:
        return datetime.strptime(us_date.split(" ")[0], "%m/%d/%Y").date().isoformat()
    except ValueError:
        return None


def _doi(value: str) -> str | None:
    value = (value or "").strip().lower()
    if not value or value in {"unavailable", "0"}:
        return None
    return value.removeprefix("https://doi.org/")


@lru_cache(maxsize=1)
def load(path: Path = DEFAULT_CSV) -> dict[str, dict]:
    """Map original-paper DOI -> notice. A retraction outranks an expression of concern."""
    rank = {"Retraction": 3, "Expression of concern": 2, "Correction": 1, "Reinstatement": 0}
    notices: dict[str, dict] = {}
    if not path.exists():
        return notices
    with path.open(encoding="utf-8", errors="replace", newline="") as fh:
        for row in csv.DictReader(fh):
            doi = _doi(row.get("OriginalPaperDOI", ""))
            if not doi:
                continue
            nature = (row.get("RetractionNature") or "").strip()
            notice = {
                "record_id": int(row["Record ID"]) if row.get("Record ID", "").isdigit() else None,
                "nature": nature,
                "date": _iso(row.get("RetractionDate", "")),
                "notice_doi": _doi(row.get("RetractionDOI", "")),
                "reasons": [r.strip().lstrip("+") for r in (row.get("Reason") or "").split(";") if r.strip()],
                "journal": (row.get("Journal") or "").strip(),
            }
            prev = notices.get(doi)
            if prev is None or rank.get(nature, 0) > rank.get(prev["nature"], 0):
                notices[doi] = notice
    return notices


def resolve(doi: str | None, marked_retracted: bool) -> tuple[dict | None, str | None]:
    """Look for a notice and identify its source. Check Crossref when the flag lacks a retraction notice."""
    recorded = load().get(doi) if doi else None
    if doi and marked_retracted and (not recorded or recorded["nature"] != "Retraction"):
        fallback = crossref.notice(doi)
        if fallback and (not recorded or fallback["nature"] == "Retraction"):
            return fallback, "crossref"
    return recorded, "retraction_watch" if recorded else None
