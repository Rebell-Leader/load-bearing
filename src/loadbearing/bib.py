"""Read references from BibTeX or from any text with one DOI per line.

The BibTeX reader is brace-aware, so single-line entries ("@article{k, title={…}, doi={…}}"),
nested braces and quoted values all parse. Agents often emit BibTeX on one line.
"""

from __future__ import annotations

import re
from pathlib import Path

ENTRY_START = re.compile(r"@(\w+)\s*[{(]", re.I)
FIELD_NAME = re.compile(r"\s*([A-Za-z][\w\-]*)\s*=\s*")
DOI_IN_TEXT = re.compile(r"10\.\d{4,9}/[^\s\"<>{}]+", re.I)


def read_references(path: str | Path) -> list[dict]:
    """Return [{key, doi, title}] in file order. Entries without a DOI keep doi=None."""
    return parse_references(Path(path).read_text(encoding="utf-8", errors="replace"))


def parse_references(text: str) -> list[dict]:
    """Parse BibTeX text, or any text with one DOI per line."""
    entries = list(_bibtex_entries(text))
    if entries:
        refs = []
        for etype, key, fields in entries:
            if etype.lower() in ("comment", "string", "preamble"):
                continue
            doi = fields.get("doi")
            if not doi:
                m = DOI_IN_TEXT.search(fields.get("url", "") + " " + fields.get("note", ""))
                doi = m.group(0) if m else None
            refs.append({"key": key, "doi": _clean(doi), "title": _strip_braces(fields.get("title", ""))})
        return refs
    refs = []
    for i, line in enumerate(text.splitlines(), 1):
        m = DOI_IN_TEXT.search(line)
        if m:
            refs.append({"key": f"ref{i}", "doi": _clean(m.group(0)), "title": ""})
    return refs


def _bibtex_entries(text: str):
    pos = 0
    while (m := ENTRY_START.search(text, pos)):
        start = m.end()
        end = _matching_close(text, start - 1)
        if end is None:
            return
        body = text[start:end]
        pos = end + 1
        key, _, rest = body.partition(",")
        yield m.group(1), key.strip(), _fields(rest)


def _matching_close(text: str, open_idx: int) -> int | None:
    opener = text[open_idx]
    closer = "}" if opener == "{" else ")"
    depth = 0
    for i in range(open_idx, len(text)):
        ch = text[i]
        if ch == "{" or (opener == "(" and ch == "("):
            depth += 1
        elif ch == "}" or (opener == "(" and ch == ")"):
            depth -= 1
            if depth == 0 and ch == closer:
                return i
    return None


def _fields(body: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    i = 0
    while (m := FIELD_NAME.match(body, i)):
        name, i = m.group(1).lower(), m.end()
        if i < len(body) and body[i] == "{":
            end = _matching_close(body, i)
            end = len(body) if end is None else end
            value, i = body[i + 1:end], end + 1
        elif i < len(body) and body[i] == '"':
            end = body.find('"', i + 1)
            end = len(body) if end == -1 else end
            value, i = body[i + 1:end], end + 1
        else:
            end = body.find(",", i)
            end = len(body) if end == -1 else end
            value, i = body[i:end], end
        fields[name] = value.strip()
        comma = body.find(",", i)
        if comma == -1:
            break
        i = comma + 1
    return fields


def _strip_braces(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("{", "").replace("}", "")).strip()


def _clean(doi: str | None) -> str | None:
    if not doi:
        return None
    doi = doi.strip().rstrip(".,;").lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "http://dx.doi.org/", "https://dx.doi.org/", "doi:"):
        doi = doi.removeprefix(prefix)
    return doi or None
