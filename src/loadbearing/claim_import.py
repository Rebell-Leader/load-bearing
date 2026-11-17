"""Import source-checked outcome-to-study links from a structured inclusion table."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
import re
from urllib.parse import urlsplit

from .openalex import norm_doi

OUTCOME_COLUMNS = (
    "review_doi", "outcome_id", "outcome_label", "study_doi", "role", "source_url",
    "locator", "evidence_summary", "reviewed_by",
)
NOTICE_COLUMNS = ("study_doi", "kind", "date", "url")
NOTICE_KINDS = {"retraction", "expression_of_concern", "correction", "reinstatement"}


def _load_rows(path: Path, required: tuple[str, ...]):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        missing = set(required) - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path.name}: missing columns {', '.join(sorted(missing))}")
        for number, row in enumerate(reader, start=2):
            if None in row or any(not (row.get(key) or "").strip() for key in required):
                raise ValueError(f"{path.name}:{number}: provide all required fields and quote cells containing commas")
            yield f"{path.name}:{number}", {key: value.strip() for key, value in row.items() if value is not None}


def _doi(value: str, where: str) -> str:
    doi = norm_doi(value)
    if not doi or not re.fullmatch(r"10\.\d{4,}/\S+", doi):
        raise ValueError(f"{where}: invalid DOI {value!r}")
    return doi


def _url(value: str, where: str) -> str:
    url = urlsplit(value)
    if url.scheme not in {"https", "http"} or not url.hostname:
        raise ValueError(f"{where}: use a public HTTP(S) source URL")
    return value


def read_tables(outcomes_path: Path, notices_path: Path | None, as_of: str) -> dict:
    """Validate both tables before any graph is opened for writing."""
    as_of = date.fromisoformat(as_of).isoformat()
    publications = {}
    for where, row in _load_rows(outcomes_path, OUTCOME_COLUMNS):
        review = _doi(row["review_doi"], where)
        study = _doi(row["study_doi"], where)
        outcome_id, role = row["outcome_id"], row["role"]
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", outcome_id):
            raise ValueError(f"{where}: use letters, digits, dots, hyphens or underscores in outcome_id")
        if review == study or role not in {"uses", "outside_scope"}:
            raise ValueError(f"{where}: give distinct DOIs and a role of uses or outside_scope")
        pub = publications.setdefault(review, {"doi": review, "citations": set(), "outcomes": {}})
        outcome = pub["outcomes"].setdefault(outcome_id, {
            "id": outcome_id, "label": row["outcome_label"], "uses": [], "outside_scope": [],
            "study_evidence": {},
        })
        if outcome["label"] != row["outcome_label"]:
            raise ValueError(f"{where}: conflicting labels for {outcome_id}")
        if study in outcome["study_evidence"]:
            raise ValueError(f"{where}: duplicate review, outcome and study")
        outcome[role].append(study)
        outcome["study_evidence"][study] = {
            "url": _url(row["source_url"], where), "locator": row["locator"],
            "finding": row["evidence_summary"], "reviewed_by": row["reviewed_by"],
        }
        pub["citations"].add(study)
    if not publications:
        raise ValueError("The inclusion table has no outcome rows.")

    notices = []
    if notices_path is not None:
        for where, row in _load_rows(notices_path, NOTICE_COLUMNS):
            published = date.fromisoformat(row["date"]).isoformat()
            if row["kind"] not in NOTICE_KINDS or published > as_of:
                raise ValueError(f"{where}: invalid notice type or date after the snapshot cutoff")
            notices.append({"doi": _doi(row["study_doi"], where), "kind": row["kind"],
                            "date": published, "url": _url(row["url"], where)})
    return {
        "as_of": as_of,
        "publications": [
            {"doi": p["doi"], "citations": sorted(p["citations"]), "outcomes": list(p["outcomes"].values())}
            for p in publications.values()
        ],
        "notices": notices,
    }
