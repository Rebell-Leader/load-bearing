# Load-Bearing viewer

A static page that runs [Relate](https://relatedb.ai)'s WebAssembly build in the browser and explores an
evidence pack: which references reach retracted papers, through which citations, with the citing
sentences. It has no server-side code and nothing to install.

Hosted copy: https://rebell-leader.github.io/load-bearing/viewer/ (GitHub Pages). To run it locally:

```bash
python3 -m http.server 8765        # from the repository root
# open http://localhost:8765/viewer/
```

## How it works

- `index.html` loads `@relate/relate-wasm@1.0.2` from jsDelivr and opens an in-memory `RelateDb`.
- The browser build can't open a `.rl` file, so `evidence.json` (0.9 MB) carries the pack's nodes and
  relationships. The page loads them with parameterized `UNWIND … CREATE` statements, then converts
  date strings back to Relate `date` values.
  Measured in Chrome: 1,250 nodes and 1,634 relationships load in about 260–380 ms.
- The findings come from the **same Cypher** the CLI and the MCP server run. `scripts/export_viewer.py`
  copies `EXPOSURE_QUERY`, `LOAD_BEARING_ONLY` and `IGNORED_QUERY` from `src/loadbearing/store.py` into
  the pack; the page doesn't keep its own copy. On the demo paper the exposure query returns 741 paths
  in about 100 ms.
- The console runs any Cypher against the tab's copy, with `$root` bound to the selected manuscript.
- Data from the pack (titles, sentences) is only ever inserted as text, never as HTML.

## The pack

`uv run python scripts/export_viewer.py` rebuilds `evidence.json` from `data/demo.rl` and adds the grant
draft from the agent demo (checked at depth 2 on a temporary copy). Both manuscripts share one graph, so
a citation found by one check can extend paths for the other. That's why the demo paper shows one more
read citation here (607/1,289) than in the CLI report (606/1,288).
