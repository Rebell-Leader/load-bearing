"""Write examples/<name>.bib from a published paper's reference list (uses the HTTP cache).

  uv run python scripts/make_example_bib.py 10.1016/j.redox.2025.103611 examples/redox2025.bib
"""

import sys
from pathlib import Path

from loadbearing import openalex


def bibtex(w: dict, key: str) -> str:
    authors = " and ".join(a["author"]["display_name"] for a in (w.get("authorships") or [])[:6])
    fields = {
        "title": (w.get("title") or "").replace("{", "").replace("}", ""),
        "author": authors,
        "year": str(w.get("publication_year") or ""),
        "doi": openalex.norm_doi(w.get("doi")) or "",
    }
    body = ",\n".join(f"  {k} = {{{v}}}" for k, v in fields.items() if v)
    return f"@article{{{key},\n{body}\n}}\n"


def main(doi: str, out: str) -> int:
    root = openalex.work(doi)
    refs = openalex.works_by_ids(root["referenced_works"])
    entries = []
    for i, w in enumerate(sorted(refs, key=lambda w: w.get("publication_year") or 0), 1):
        last = ((w.get("authorships") or [{}])[0].get("author", {}).get("display_name", "anon").split() or ["anon"])[-1]
        entries.append(bibtex(w, f"{last.lower()}{w.get('publication_year')}_{i}"))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(f"% References of {root.get('title')} (doi:{doi}), from OpenAlex\n\n" + "\n".join(entries))
    print(f"wrote {len(entries)} entries to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
