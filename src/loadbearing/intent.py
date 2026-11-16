"""Citation intent. v0: transparent rules. v1 (classify_v1): strong critical cues, a BiomedBERT
model fine-tuned on SciCite for methods, and the cited work's type (review vs primary research).
Evaluation: docs/EVAL.md.

Labels:
  method      the citing paper uses a method, reagent or protocol from the cited work
  result      the citing paper builds on or compares with a finding of the cited work
  background  a general mention (introduction, history, "reviewed in")
  critical    the citing paper already flags the cited work (retraction, failed replication)
  unknown     no citing sentence available

Only method/result count as load-bearing. 'critical' defuses a path: the citing
authors already know.
"""

from __future__ import annotations

import re

CRITICAL = re.compile(
    r"retract|withdrawn|fabricat|falsif|misconduct|manipulat|irreproducib|could not (?:be )?(?:replicat|reproduc)"
    r"|fail(?:ed|ure) to (?:replicat|reproduc)|not (?:be )?reproduc|controvers|called into question|questioned|disputed",
    re.I,
)
METHOD = re.compile(
    r"as (?:previously )?described|as reported (?:previously|before)|according to|adapted from|following (?:the )?(?:protocol|method|procedure)"
    r"|using (?:the )?(?:method|protocol|procedure|approach|assay|model|antibod)|protocol|were (?:generated|obtained|prepared|purified) as"
    r"|was (?:performed|carried out|done) as|kindly provided|modified (?:from|version)",
    re.I,
)
RESULT = re.compile(
    r"consistent with|in (?:agreement|line|accordance) with|similar(?:ly)? to|confirm|corroborat|support(?:s|ed|ing)? (?:the|our|this|these)"
    r"|(?:has|have) been (?:shown|demonstrated|reported)|(?:showed|shown|demonstrated|reported|found|revealed) that|evidence (?:that|for)"
    r"|in contrast|contrary to|unlike|inconsistent with|whereas",
    re.I,
)
BACKGROUND = re.compile(r"reviewed in|for (?:a )?review|for reviews?|see (?:also )?ref|e\.g\.|such as", re.I)

S2_MAP = {"methodology": "method", "result": "result", "background": "background"}


def classify(sentence: str | None, section_type: str = "other") -> tuple[str, str]:
    """Return (label, rule) so every label can be explained."""
    if not sentence:
        return "unknown", "no citing sentence"
    if CRITICAL.search(sentence):
        return "critical", "cue: " + CRITICAL.search(sentence).group(0)
    if section_type == "methods":
        return "method", "section: methods"
    if METHOD.search(sentence):
        return "method", "cue: " + METHOD.search(sentence).group(0)
    if BACKGROUND.search(sentence):
        return "background", "cue: " + BACKGROUND.search(sentence).group(0)
    if RESULT.search(sentence):
        return "result", "cue: " + RESULT.search(sentence).group(0)
    # Without a cue, only the Results section implies reliance. A bare Discussion sentence is
    # usually framing ("Iron deficiency is the most common…"), so it stays background:
    # load-bearing must be earned by evidence, never by default.
    if section_type == "results":
        return "result", "section: results"
    return "background", f"section: {section_type or 'other'}"


# ---- v1 (2026-11-16): evaluated in docs/EVAL.md -------------------------------------------------
# v0 flagged "controversial"/"questioned" as critical (precision 0.25 in-domain); v1 keeps only cues
# that point at the cited work itself.
STRONG_CRITICAL = re.compile(
    r"retract|withdrawn|fabricat|falsif|misconduct|manipulat|irreproducib|could not (?:be )?(?:replicat|reproduc)"
    r"|fail(?:ed|ure) to (?:replicat|reproduc)|not (?:be )?reproduc|\balleged",
    re.I,
)


def classify_v1(sentence: str | None, section_type: str = "other", cited_type: str | None = None,
                method_prob: float | None = None) -> tuple[str, str]:
    """Intent v1: critical cue > method > primary-research finding > background.

    cited_type is the OpenAlex work type of the cited paper ('review', 'article', …).
    method_prob comes from the BiomedBERT/SciCite model when it is available; without it,
    the v0 method cues stand in.
    """
    if not sentence:
        return "unknown", "no citing sentence"
    m = STRONG_CRITICAL.search(sentence)
    if m:
        return "critical", "cue: " + m.group(0)
    if section_type == "methods":
        return "method", "section: methods"
    if method_prob is not None:
        if method_prob > 0.5:
            return "method", f"model: method p={method_prob:.2f}"
    elif METHOD.search(sentence):
        return "method", "cue: " + METHOD.search(sentence).group(0)
    if cited_type == "review":
        return "background", "cited work is a review"
    if cited_type is None:  # type unknown: fall back to v0's evidence-earned rules
        return classify(sentence, section_type)
    # Precision guards: generic evidence-talk, or a long reference group with no specific detail,
    # leans on no single finding even when the cited works are primary research.
    m = VAGUE.search(sentence)
    if m:
        return "background", "vague: " + m.group(0)
    n = citation_group_size(sentence)
    if n >= 3 and not SPECIFIC.search(sentence):
        return "background", f"group of {n} refs, no specific finding"
    return "result", f"cites primary research ({cited_type})"


VAGUE = re.compile(
    r"\b(accumulating|growing|increasing|ample|mounting|robust|emerging|several lines of|various|many|numerous|other|previous|recent)"
    r"\s+(evidence|studies|reports|works|lines)\b|\bstudies have\b|\bhas been (implicated|suggested|proposed)\b",
    re.I,
)
SPECIFIC = re.compile(
    r"\b(\d+(\.\d+)?\s?(%|µ?[mnµ]?M|mg|kDa|fold|months?|weeks?|days?)|mice|rats?|patients|cells?|in vitro|in vivo|knock\w*"
    r"|transgenic|overexpress\w*|deletion|inhibit\w*|increase\w*|decrease\w*|reduc\w*)\b",
    re.I,
)
_GROUP = re.compile(r"[\[(]\s*\[?(\d[\d,\s–\-–\[\]]*)\]?\s*[\])]|(?<=[A-Za-z.,)])(\d{1,3}(?:[–\-–,]\d{1,3})+)(?=[\s.,;]|$)")


def citation_group_size(sentence: str) -> int:
    """Count numbered references in a sentence: '[3,5–8]' → 5, 'disease13–18.' → 6."""
    n = 0
    for m in _GROUP.finditer(sentence):
        for part in (m.group(1) or m.group(2) or "").replace("[", "").replace("]", "").split(","):
            part = part.strip()
            r = re.split(r"\s*[–\-–]\s*", part)
            if len(r) == 2 and r[0].isdigit() and r[1].isdigit():
                n += max(1, int(r[1]) - int(r[0]) + 1)
            elif part.isdigit():
                n += 1
    return n


RANK = {"critical": 4, "method": 3, "result": 2, "background": 1, "unknown": 0}


def combine(labels: list[str]) -> str:
    """A reference cited several times takes its strongest role."""
    return max(labels, key=lambda lab: RANK[lab]) if labels else "unknown"
