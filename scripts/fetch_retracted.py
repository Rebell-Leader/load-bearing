"""Download the set of works OpenAlex marks as retracted (~105k, ~525 requests). Needs OPENALEX_API_KEY:
OpenAlex refuses cursor paging without one. The pipeline does not need this file (it asks OpenAlex
server-side with filter=is_retracted:true,cited_by:...); it is here for anyone who wants the full set.

Writes data/raw/openalex_retracted.jsonl, one {id, doi, title, year} per line.
Resumable: if the file is complete (has the count marker), it does nothing.
"""

import json
import sys
from pathlib import Path

from loadbearing import openalex

OUT = Path("data/raw/openalex_retracted.jsonl")
DONE = OUT.with_suffix(".done")


def main() -> int:
    if DONE.exists():
        print(f"already complete: {OUT} ({DONE.read_text().strip()} works)")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with OUT.open("w") as fh:
        for w in openalex.iter_filter("is_retracted:true", "id,doi,title,publication_year"):
            fh.write(json.dumps({
                "id": openalex.short_id(w["id"]),
                "doi": openalex.norm_doi(w.get("doi")),
                "title": w.get("title"),
                "year": w.get("publication_year"),
            }) + "\n")
            n += 1
            if n % 10000 == 0:
                print(f"{n} works, {openalex.requests_made} requests", flush=True)
    DONE.write_text(str(n))
    print(f"done: {n} retracted works in {openalex.requests_made} requests -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
