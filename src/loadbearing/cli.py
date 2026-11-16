"""loadbearing check — which of your references rest on retracted science?

  loadbearing check refs.bib            a manuscript's bibliography (or a DOI list)
  loadbearing check --doi 10.xxxx/yyy   a published paper, read from its open full text
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from collections import defaultdict
from pathlib import Path

from . import expand, http
from .check import ORDER, run_check

HEADINGS = {
    "direct": "DIRECT: you cite a retracted paper",
    "load_bearing": "LOAD-BEARING: reached only through method or result citations",
    "unverified": "UNVERIFIED: reached through citations we could not read",
    "mention_only": "MENTION-ONLY: reached through a background mention (low concern)",
    "defused": "DEFUSED: a paper on the way already flags the problem",
}
MARK = {"direct": "✗", "load_bearing": "!", "unverified": "?", "mention_only": "·", "defused": "✓"}
DETAILED = {"direct", "load_bearing"}


def _short(title: str | None, n: int = 70) -> str:
    title = (title or "untitled")
    for prefix in ("RETRACTED ARTICLE: ", "RETRACTED: ", "Retracted: "):
        title = title.removeprefix(prefix)
    return title if len(title) <= n else title[: n - 1] + "…"


def _path_lines(path: dict) -> list[str]:
    lines = []
    n = len(path["edges"])
    for i, (node, edge) in enumerate(zip(path["chain"][1:], path["edges"])):
        role = "cites" if i == 0 and edge["intent"] == "unknown" else edge["intent"]
        zombie = "  [cited after retraction]" if edge["zombie"] else ""
        zombie += "  [date conflict: likely a metadata error]" if edge.get("year_conflict") else ""
        lines.append(f"      {'└─' if i == n - 1 else '├─'} {role:<10} → {_short(node['title'], 60)} ({node['year']}){zombie}")
        if edge["context"]:
            where = f" [{_short(edge['section'], 40)}]" if edge["section"] else ""
            lines.append(f"           “{textwrap.shorten(edge['context'], 200, placeholder='…')}”{where}")
    return lines


def render(summary: dict, ex: expand.Expansion | None, st: dict, store_path: str, depth: int,
           title: str | None = None) -> str:
    out = []
    groups = summary["retracted"]
    if ex:
        out.append(f"Load-Bearing check: {ex.root_title}")
        out.append(f"  {ex.refs_resolved}/{ex.refs_total or ex.refs_resolved} references resolved"
                   + (f" ({len(ex.unresolved)} without a DOI match)" if ex.unresolved else ""))
    else:
        out.append(f"Load-Bearing check: {title or 'manuscript'}")
        out.append(f"  offline: read from {store_path}, no network")
    out.append(f"  {summary['refs_exposed']} of your references reach {len(groups)} retracted papers within {depth} citation hops")
    if summary["citations_on_paths"]:
        pct = 100 * summary["citations_read"] / summary["citations_on_paths"]
        out.append(f"  evidence: read the citing sentence for {summary['citations_read']} of {summary['citations_on_paths']} "
                   f"citations on those paths ({pct:.0f}%); {summary['zombies']} were made after the retraction")
    out.append(f"  store {store_path}: {st['papers']:,} papers, {st['cites']:,} citations, {st['retracted']:,} retracted")
    for ig in summary.get("ignored_impossible") or []:
        out.append(f"  ignored an impossible citation: {_short(ig['citing'], 45)} ({ig['citing_year']}) → "
                   f"{_short(ig['cited'], 45)} ({ig['cited_year']}), cited paper is newer")
    if summary.get("date_conflicts"):
        out.append(f"  {summary['date_conflicts']} citation(s) to retracted papers have conflicting dates; "
                   "those paths are reported as unverified")
    by_status: dict[str, list[dict]] = defaultdict(list)
    for g in groups:
        by_status[g["status"]].append(g)
    for status in ORDER:
        items = by_status[status]
        if not items:
            continue
        out.append("")
        out.append(f"{HEADINGS[status]} ({len(items)})")
        limit = 10 if status in DETAILED else 8
        for g in items[:limit]:
            date = g["retraction_date"] or "date unknown"
            via = f"via {len(g['via'])} of your references"
            out.append(f"  {MARK[status]} {_short(g['title'])} ({g['year']}): {g['nature'] or 'Retraction'} {date}, {via}")
            if status in DETAILED:
                if g["reasons"]:
                    out.append(f"      notice: {'; '.join(g['reasons'][:3])}")
                elif g.get("notice_doi"):
                    out.append(f"      notice: doi:{g['notice_doi']} ({g.get('notice_source')}; reasons not recorded)")
                out.extend(_path_lines(g["best_path"]))
        if len(items) > limit:
            out.append(f"  … {len(items) - limit} more (use --json)")
    counts = ", ".join(f"{summary['counts'][s]} {s.replace('_', '-')}" for s in ORDER if summary["counts"][s])
    out.append("")
    out.append(f"Summary: {counts or 'no paths to retracted papers found'}.")
    out.append("Paths are evidence for a person to review, not verdicts about any paper or author.")
    return "\n".join(out)


def cmd_check(args) -> int:
    try:
        res = run_check(args.store, bib_path=args.bib, doi=args.doi, depth=args.depth,
                        offline=args.offline, s2_limit=args.s2_limit)
    except LookupError as e:
        print(f"loadbearing: {e}", file=sys.stderr)
        return 2
    summary = res.summary
    if args.json:
        print(json.dumps({"root": res.root_id, "depth": res.depth, "store": res.store_stats,
                          **{k: v for k, v in summary.items() if k != "retracted"},
                          "retracted": [{k: v for k, v in g.items() if k != "paths"} for g in summary["retracted"]]},
                         indent=2, default=str))
    else:
        print(render(summary, res.expansion, res.store_stats, args.store, args.depth, res.title), flush=True)
    print(f"(http: {http.stats['network']} network, {http.stats['cached']} cached)", file=sys.stderr)
    return 1 if summary["counts"]["direct"] or summary["counts"]["load_bearing"] else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="loadbearing", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="check a bibliography or a published paper")
    c.add_argument("bib", nargs="?", help=".bib file or a text file with one DOI per line")
    c.add_argument("--doi", help="check a published paper by DOI instead of a .bib")
    c.add_argument("--store", default="data/evidence", help="Relate store: a directory or a .rl file (default: %(default)s)")
    c.add_argument("--depth", type=int, default=3, choices=[1, 2, 3], help="citation hops from the manuscript")
    c.add_argument("--offline", action="store_true", help="query the existing store only; no network")
    c.add_argument("--s2-limit", type=int, default=40, help="max Semantic Scholar fallback calls (default: %(default)s)")
    c.add_argument("--json", action="store_true", help="machine-readable output for agents")
    args = p.parse_args(argv)
    if args.cmd == "check" and not (args.bib or args.doi):
        p.error("give a .bib file or --doi")
    return cmd_check(args)


if __name__ == "__main__":
    sys.exit(main())
