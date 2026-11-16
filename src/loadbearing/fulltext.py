"""Citation contexts from open-access full text (Europe PMC JATS XML).

For a citing paper and a set of cited DOIs/titles, return the sentence(s) where
each is cited and the section they sit in. Handles Nature-style ranges like
"3-5" where only the first and last reference carry an <xref>.
"""

from __future__ import annotations

import re
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from . import http

EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
XLINK_HREF = "{http://www.w3.org/1999/xlink}href"
DOI_IN_TEXT = re.compile(r"10\.\d{4,9}/[^\s\"<>]+", re.I)
SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\[])")
RANGE_SEP = re.compile(r"^\s*[–—-]\s*$")


@dataclass
class Context:
    section: str      # raw section title
    section_type: str  # intro | methods | results | discussion | other
    sentence: str


def pmcid_for_doi(doi: str) -> str | None:
    q = urllib.parse.quote(f'DOI:"{doi}"')
    data = http.get(f"{EPMC}/search?query={q}&format=json&resultType=lite")
    for r in data.get("resultList", {}).get("result", []):
        if r.get("pmcid") and r.get("isOpenAccess") == "Y":
            return r["pmcid"]
    return None


def fetch_jats(pmcid: str) -> ET.Element | None:
    try:
        xml = http.get(f"{EPMC}/{pmcid}/fullTextXML", as_json=False)
        return ET.fromstring(xml)
    except (http.HttpError, ET.ParseError):
        return None


RETRACTION_PREFIX = re.compile(r"^\s*(?:retracted(?: article)?|retraction|withdrawn|expression of concern)\s*[:.\-]\s*", re.I)


def _norm_title(t: str) -> str:
    """Comparable title key. OpenAlex prefixes retracted titles ('RETRACTED ARTICLE: …');
    the citing paper's reference list does not, so strip it before comparing."""
    t = RETRACTION_PREFIX.sub("", t or "")
    return re.sub(r"[^a-z0-9]", "", t.lower())[:60]


def _tokens(t: str) -> set[str]:
    t = RETRACTION_PREFIX.sub("", t or "").lower()
    return {w for w in re.findall(r"[a-z0-9]+", t) if len(w) > 2}


def _title_match(a: str, b_tokens: set[str]) -> bool:
    """True when (nearly) every word of title `a` appears in the reference text.
    Containment, not Jaccard: the reference may be a whole citation string."""
    ta = _tokens(a)
    if len(ta) < 4 or not b_tokens:
        return False
    return len(ta & b_tokens) / len(ta) >= 0.9


def _section_type(title: str, sec_type: str) -> str:
    s = f"{sec_type} {title}".lower()
    if any(k in s for k in ("method", "material", "procedure", "experimental")):
        return "methods"
    if "result" in s:
        return "results"
    if any(k in s for k in ("discussion", "conclusion")):
        return "discussion"
    if any(k in s for k in ("intro", "background")):
        return "intro"
    return "other"


def _refs(root: ET.Element) -> tuple[dict[str, tuple[str | None, str, set[str]]], list[str]]:
    refs: dict[str, tuple[str | None, str, set[str]]] = {}
    order: list[str] = []
    for ref in root.iter("ref"):
        rid = ref.get("id")
        if not rid:
            continue
        doi = None
        for pid in ref.iter("pub-id"):
            if pid.get("pub-id-type") == "doi" and pid.text:
                doi = pid.text.strip().lower()
        if not doi:  # Elsevier-style: <ext-link ext-link-type="doi" xlink:href="10.…"/>
            for link in ref.iter("ext-link"):
                if link.get("ext-link-type") == "doi" and link.get(XLINK_HREF):
                    doi = link.get(XLINK_HREF).strip().lower().removeprefix("https://doi.org/")
        full_text = "".join(ref.itertext())
        if not doi:
            m = DOI_IN_TEXT.search(full_text)
            doi = m.group(0).rstrip(".,;)").lower() if m else None
        title_el = next(ref.iter("article-title"), None)
        title = "".join(title_el.itertext()) if title_el is not None else full_text
        refs[rid] = (doi, _norm_title(title), _tokens(title))
        order.append(rid)
    return refs, order


def _paragraph_hits(p: ET.Element, order_index: dict[str, int], order: list[str]):
    """Yield (char_offset, rid) for every reference cited in a paragraph, expanding ranges."""
    text_parts: list[str] = []
    hits: list[tuple[int, str]] = []
    prev_xref: tuple[int, str] | None = None
    between = ""

    def visit(el: ET.Element):
        nonlocal prev_xref, between
        if el.tag == "xref" and el.get("ref-type") == "bibr":
            offset = sum(len(t) for t in text_parts)
            rids = (el.get("rid") or "").split()
            if prev_xref and RANGE_SEP.match(between) and rids:
                a, b = order_index.get(prev_xref[1]), order_index.get(rids[0])
                if a is not None and b is not None and b > a + 1:
                    hits.extend((offset, order[i]) for i in range(a + 1, b))
            hits.extend((offset, r) for r in rids)
            text_parts.append("".join(el.itertext()))
            prev_xref = (offset, rids[-1]) if rids else None
            between = ""
        else:
            if el.text:
                text_parts.append(el.text)
                between += el.text
            for child in el:
                visit(child)
                if child.tail:
                    text_parts.append(child.tail)
                    between += child.tail
            return
        # tail handled by parent

    visit(p)
    return "".join(text_parts), hits


def contexts_for(citing_doi: str, targets: dict[str, tuple[str | None, str]]) -> tuple[str, dict[str, list[Context]]]:
    """targets: key -> (doi, title). Returns (status, key -> contexts).

    status is 'fulltext' when an open full text was parsed, else 'no_fulltext'.
    A target with an empty list was not found in the text (metadata-only edge).
    """
    pmcid = pmcid_for_doi(citing_doi)
    root = fetch_jats(pmcid) if pmcid else None
    if root is None:
        return "no_fulltext", {}
    refs, order = _refs(root)
    order_index = {rid: i for i, rid in enumerate(order)}
    rid_to_keys: dict[str, list[str]] = {}
    for key, (doi, title) in targets.items():
        nt = _norm_title(title)
        for rid, (rdoi, rtitle, rtokens) in refs.items():
            if ((doi and rdoi and doi == rdoi) or (nt and len(nt) > 25 and nt == rtitle)
                    or ((not rdoi or not doi) and _title_match(title, rtokens))):
                rid_to_keys.setdefault(rid, []).append(key)
    found: dict[str, list[Context]] = {k: [] for k in targets}
    body = root.find(".//body")
    if body is None or not rid_to_keys:
        return "fulltext", found

    def walk(el: ET.Element, sec_title: str, sec_type: str):
        if el.tag == "sec":
            t = el.find("title")
            sec_title = "".join(t.itertext()).strip() if t is not None else sec_title
            sec_type = el.get("sec-type") or sec_type
        if el.tag == "p":
            text, hits = _paragraph_hits(el, order_index, order)
            for offset, rid in hits:
                for key in rid_to_keys.get(rid, []):
                    sentence = _sentence_at(text, offset)
                    ctx = Context(sec_title, _section_type(sec_title, sec_type), sentence)
                    if all(c.sentence != sentence for c in found[key]):
                        found[key].append(ctx)
            return
        for child in el:
            walk(child, sec_title, sec_type)

    walk(body, "", "")
    return "fulltext", found


def _sentence_at(text: str, offset: int) -> str:
    start = 0
    for m in SENTENCE_END.finditer(text):
        if m.start() >= offset:
            return re.sub(r"\s+", " ", text[start:m.start()]).strip()[:600]
        start = m.end()
    return re.sub(r"\s+", " ", text[start:]).strip()[:600]
