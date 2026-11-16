"""Record the demo video with headless Chromium. Silent: the voice-over is added afterwards.

Scenes live in demo/scenes/. Scenes 1-4 and 6 are deterministic timelines: for every frame the recorder
calls render(t) and takes a screenshot, so motion is smooth whatever the machine's load. Scene 5 drives
the live viewer (the hosted GitHub Pages copy by default) with a visible cursor, in synthetic time.

Before recording it runs the commands the video shows (the offline check, the Relate CLI query) and
reads the recorded agent transcript and the store, so the numbers on screen come from the repository.

    uv run --with playwright python scripts/record_demo.py                 # everything -> demo/build/
    uv run --with playwright python scripts/record_demo.py --scenes 2,4    # re-record some scenes
    uv run --with playwright python scripts/record_demo.py --local-viewer  # scene 5 from this checkout

Outputs in demo/build/: load-bearing-demo.mp4 (1920x1080, 30 fps, no audio), sNN.mp4 per scene,
load-bearing-demo.srt (the voice-over script at its time codes) and timing.md.
Needs ffmpeg, and a Chromium: Playwright's cached build, or CHROMIUM=/path/to/chrome.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import difflib
import functools
import glob
import http.server
import json
import math
import os
import re
import subprocess
import sys
import threading
from datetime import date
from pathlib import Path
from urllib.parse import quote

import relate

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from loadbearing import store  # noqa: E402

BUILD = ROOT / "demo" / "build"
FPS = 30
DEMO_DOI = "10.1016/j.redox.2025.103611"
DEMO_ROOT = "W4408770418"
LESNE_DOI = "10.1038/nature04533"
VIEWER_URL = "https://rebell-leader.github.io/load-bearing/viewer/"
LINKS = {"repo": "github.com/Rebell-Leader/load-bearing", "viewer": "rebell-leader.github.io/load-bearing/viewer/"}
BG = "0x0e0f11"

# Scene lengths (s), sized so the voice-over below fits at about 160 words per minute.
TIMING = {"s1": 17.0, "s2": 18.5, "s3": 23.0, "s4": 22.5, "s5": 16.5, "s6": 16.5}
SCENES = [("s1", "s1_hook.html", "The problem"), ("s2", "s2_cli.html", "Command line"),
          ("s3", "s3_agent.html", "For agents"), ("s4", "s4_relate.html", "Inside Relate"),
          ("s5", "s5_browser.html", "In the browser"), ("s6", "s6_eval.html", "Measured, not assumed")]
VOICE_OVER = {
    "s1": "This Nature paper was retracted in 2024, after OpenAlex had counted 2,840 citations. In a 2026 study, "
          "none of nine AI research tools reliably caught retracted papers. Flagging a direct citation is easy. "
          "The hard part is what your sources relied on.",
    "s2": "Load-Bearing follows citations three hops out into a Relate graph, and reads the sentence where each one "
          "appears. This 2025 Alzheimer's paper has 72 references. 56 of them lead to retracted work, and 23 "
          "retracted papers are reached only through method or result citations.",
    "s3": "For agents, Load-Bearing is an MCP server, next to Relate's own. Here Claude audits a research "
          "assistant's draft. It finds two retracted papers, reads the evidence before acting, keeps one review "
          "for its general claim, queries the graph in Cypher, and rewrites the paragraph without inventing a "
          "single reference.",
    "s4": "The core is one Cypher statement: paths from the manuscript to a retracted paper where every hop is a "
          "method or result citation. Relate answers it in a few milliseconds. The evidence pack is a single "
          "file you can hand to an editor, and the working graph is a directory store that Relate's MCP server "
          "follows live.",
    "s5": "The same graph runs in the browser, on Relate's WebAssembly build. Pick a retracted paper, see every path "
          "and the sentence behind each citation, and query it in Cypher. Nothing to install, and nothing leaves "
          "the page.",
    "s6": "We measured it honestly. On SciCite, the intent model reaches 0.856 macro-F1. On held-out sentences, it "
          "finds 69 percent of real reliance at 33 percent precision. So every finding shows its sentence, and a "
          "person decides.",
}


# ---------------------------------------------------------------- data from the repository

def _env() -> dict:
    """The environment a user's shell would have: no agent-mode variables, C.UTF-8 locale."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE") and k != "VIRTUAL_ENV"}
    env["LC_ALL"] = "C.UTF-8"
    return env


def _run(args: list[str]) -> str:
    r = subprocess.run(args, cwd=ROOT, env=_env(), capture_output=True, text=True)
    return r.stdout + r.stderr


def _long_date(d: str) -> str:
    y, m, dd = (int(x) for x in d.split("-"))
    return date(y, m, dd).strftime("%-d %B %Y")


def _strip_retracted(title: str) -> str:
    return re.sub(r"^(RETRACTED( ARTICLE)?:\s*)", "", title or "")


def _short(title: str, n: int) -> str:
    title = _strip_retracted(title)
    return title if len(title) <= n else title[: n - 1].rstrip() + "…"


def lesne_data(conn) -> dict:
    row = list(conn.execute(
        "MATCH (p:Paper {doi: $doi}) OPTIONAL MATCH (p)-[:RETRACTED_BY]->(n:Notice) "
        "RETURN p.title AS title, p.year AS year, toString(p.retraction_date) AS rdate, p.reasons AS reasons, "
        "n.notice_doi AS notice LIMIT 1", {"doi": LESNE_DOI}))[0]
    cited = 2840  # OpenAlex cited_by_count on 2026-11-16; refreshed from the local cache when it exists
    for f in glob.glob(str(ROOT / "data/raw/cache/*")):
        try:
            text = Path(f).read_text()
        except (OSError, UnicodeDecodeError):
            continue
        m = re.search(r'"id": "https://openalex.org/W2075481535"[^{}]*?"cited_by_count": (\d+)', text)
        if m:
            cited = int(m.group(1))
            break
    reasons = sorted(row["reasons"] or [], key=lambda r: ("Manipulation" not in r and "Duplication" not in r, r))
    return {"title": _strip_retracted(row["title"]), "year": row["year"], "venue": "Nature", "authors": "Lesné et al.",
            "doi": LESNE_DOI, "retraction_date_long": _long_date(row["rdate"]), "reasons": reasons,
            "notice_doi": row["notice"], "cited_by_count": cited}


def cli_data() -> dict:
    cmd = f"uv run loadbearing check --doi {DEMO_DOI} --store data/demo.rl --offline"
    out = _run(cmd.split())
    assert "of your references reach" in out, out[:500]
    return {"cmd": cmd, "output": out}


def relate_data(conn) -> dict:
    query = store.LOAD_BEARING_ONLY.strip()
    out = _run(["relate", "-d", "data/demo.rl", "--read-only", "--mode", "toon", "--param", f"root={DEMO_ROOT}",
                store.LOAD_BEARING_ONLY])
    m = re.search(r'"elapsed_ms":([0-9.]+)', out)
    assert m, out[:500]
    rows = list(conn.execute(store.LOAD_BEARING_ONLY, {"root": DEMO_ROOT}))
    st = store.stats(conn)
    return {
        "query": query,
        "cmds": ['Q=$(uv run python -c "from loadbearing.store import LOAD_BEARING_ONLY as q; print(q)")',
                 f'relate -d data/demo.rl --read-only --mode toon --param root={DEMO_ROOT} "$Q"'],
        "output": out, "elapsed_ms": f"{float(m.group(1)):.1f}", "rows": len(rows),
        "retracted": len({r["retracted"] for r in rows}),
        "size": f"{(ROOT / 'data/demo.rl').stat().st_size / 1e6:.1f} MB",
        "stats": f"{st['papers']:,} papers · {st['cites']:,} citations · {st['retracted']:,} retracted",
    }


def _final_answer(md: str) -> str:
    return md.split("## Final answer", 1)[1]


def agent_data(conn) -> dict:
    md = (ROOT / "runs/agent_demo.md").read_text()
    final = _final_answer(md)
    draft_md = (ROOT / "examples/draft_background.md").read_text()
    keys = dict(re.findall(r"@article\{(\w+),.*?doi=\{([^}]+)\}", draft_md))
    by_doi = {v.lower(): k for k, v in keys.items()}

    cyphers = re.findall(r"```cypher\n(.*?)\n```", final, re.S)
    comments = [c.splitlines()[0].lstrip("/ ").strip() for c in cyphers]
    steps, n_cypher = [], 0
    for server, tool, args, result in re.findall(
            r"\*\*→ `([\w-]+)` · `(\w+)`\*\*\n\n```json\n(.*?)\n```.*?```json\n(.*?)\n```", md, re.S):
        if tool == "retraction_status":
            dois = json.loads(args)["dois"]
            bad = re.findall(r'\\"doi\\": \\"([^\\]+)\\", \\"status\\": \\"retracted\\"', result)
            a, res = f"({len(dois)} DOIs)", f"{len(bad)} retracted: " + ", ".join(by_doi.get(d, d) for d in bad)
        elif tool == "check_references":
            st = dict(re.findall(r'\\"(direct|load_bearing|unverified|mention_only)\\": (\d+)', result.split("guidance")[0]))
            a = "(label grant-draft, depth 2)"
            res = " · ".join(f"{v} {k.replace('_', '-')}" for k, v in st.items())
        elif tool == "explain_exposure":
            rid = json.loads(args)["retracted"]
            r = list(conn.execute("MATCH (p:Paper {id: $id}) RETURN p.title AS t, p.year AS y", {"id": rid}))[0]
            a = f"({_short(r['t'], 24)} {r['y']})"
            tp = re.search(r'\\"total_paths\\": (\d+)', result)
            res = (f"{tp.group(1)} path{'' if tp.group(1) == '1' else 's'}, each with its citing sentences" if tp
                   else "every path, with its citing sentences")
        elif tool == "get_schema":
            labels = re.findall(r'"(\w+)":\{"count"', result)
            a, res = "", "labels: " + ", ".join(labels)
        else:  # read_cypher
            cols = json.loads(re.search(r'"columns":(\[[^\]]*\])', result).group(1))
            ms = float(re.search(r'"elapsed_ms":([0-9.]+)', result).group(1))
            a = f"({comments[n_cypher]})" if n_cypher < len(comments) else ""
            n_cypher += 1
            res = f"{', '.join(cols)} · {ms:.1f} ms"
        steps.append({"server": server, "tool": tool, "args": a, "result": res})

    cline = re.search(r'"(One specific type 1 AβO[^"]+)"', final).group(1)
    reed = re.search(r'"(Forebrains were lysed[^"]+)"', final).group(1)
    larson_full = re.search(r'"(…apparent trimers[^"]+)"', final).group(1)
    for frag in ("dodecamers (56 kDa) were detected using antibodies", "(Kayed et al. 2003; Lesne et al. 2006)"):
        assert frag in larson_full, frag
    larson = "“…dodecamers (56 kDa) were detected using antibodies… (Kayed et al. 2003; Lesne et al. 2006)”"

    # The agent's graph-check table, condensed.
    rows = {}
    for line in final.split("## Graph check", 1)[1].splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 3 and cells[0] in keys:
            rows[cells[0]] = cells
    def describe(k):
        _, direct, via = rows[k]
        intent = re.search(r"\((?:\*\*)?([\w ,:]+?)(?:\*\*)?(?:,|\))", direct)
        d = "cites it directly"
        if intent:
            word = intent.group(1)
            if word in ("method", "result"):
                d += f' for a <b class="i-rel">{word}</b>'
            else:
                d += " (intent unknown: no full text)" if "no full text" in direct else f" ({word})"
        n = re.match(r"(\d+) papers?", via)
        return d + (f" · reaches it through {n.group(1)} more paper{'s' if n.group(1) != '1' else ''}" if n else "")
    graph_rows = [[k, describe(k)] for k in ("reed2011", "cline2018", "larson2012", "shankar2008")]
    graph_rows.append(["walsh2002 · selkoe2016", '<span class="muted">no path within two hops</span>'])

    # The rewrite, as a word diff against the original draft.
    draft = " ".join(draft_md.split("```")[0].split("\n\n", 1)[1].split())
    revised = re.search(r"\n> (Soluble amyloid.*?)\n", final).group(1).replace("**", "")
    a, b = re.findall(r"\S+|\s+", draft), re.findall(r"\S+|\s+", revised)
    diff = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            diff.append(["=", "".join(a[i1:i2])])
        if op in ("delete", "replace"):
            diff.append(["-", "".join(a[i1:i2])])
        if op in ("insert", "replace"):
            diff.append(["+", "".join(b[j1:j2])])
    for k in re.findall(r"\[([\w; ]+)\]", revised):
        for key in re.split(r";\s*", k):
            assert key in keys or key.startswith("NEW"), key  # no invented references

    run = final.split("## Run", 1)[1]
    turns, calls, secs = re.search(r"turns: (\d+), tool calls: (\d+), wall time: (\d+) s", run).groups()
    cost = re.search(r"cost: (\$[0-9.]+)", run).group(1)
    return {"steps": steps, "cline_sentence": cline, "cline_section": "A multitude of AβO species or just two?",
            "cypher": cyphers[0], "graph_rows": graph_rows, "diff": diff, "reed_sentence": reed,
            "larson_quote": larson, "stats": f"Claude Opus 5.5, {turns} turns, {calls} tool calls, {secs} s, {cost}"}


def eval_data() -> dict:
    ev = (ROOT / "docs/EVAL.md").read_text()
    rules = float(re.search(r"\| Rules v0 \| [0-9.]+ \| ([0-9.]+) \|", ev).group(1))
    f1 = float(re.search(r"\*\*BiomedBERT \+ SciCite\*\*.*?\| \*\*[0-9.]+\*\* \| \*\*([0-9.]+)\*\*", ev).group(1))
    m = re.search(r"\*\*v1 \+ model\*\*.*?\| ([0-9.]+) \[([0-9.]+)–([0-9.]+)\] \((\d+) predicted\) / ([0-9.]+) \|", ev)
    p, lo, hi, n, r = m.groups()
    return {"scicite_f1": f1, "rules_f1": rules, "heldout_precision": float(p), "precision_ci": [float(lo), float(hi)],
            "predicted": int(n), "heldout_recall": float(r),
            "footnote": "In-domain labels: Claude, blind to predictions, following data/eval/GUIDELINES.md; "
                        "expert labels are pending. Details in docs/EVAL.md."}


def build_data() -> dict:
    conn = relate.connect(str(ROOT / "data/demo.rl"), read_only=True)
    try:
        data = {"lesne": lesne_data(conn), "cli": cli_data(), "relate": relate_data(conn),
                "agent": agent_data(conn), "eval": eval_data(), "links": LINKS, "timing": TIMING}
    finally:
        conn.close()
    BUILD.mkdir(parents=True, exist_ok=True)
    (BUILD / "data.js").write_text("window.DATA = " + json.dumps(data, ensure_ascii=False, indent=1) + ";\n")
    return data


# ---------------------------------------------------------------- recording

class Encoder:
    """JPEG frames in, H.264 out (high quality; the final pass re-encodes)."""

    def __init__(self, path: Path):
        self.path, self.frames = path, 0
        self.p = subprocess.Popen(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(FPS), "-c:v", "mjpeg",
             "-i", "-", "-vf", "scale=1920:1080:flags=lanczos,format=yuv420p", "-c:v", "libx264", "-preset", "medium",
             "-crf", "12", "-r", str(FPS), str(path)], stdin=subprocess.PIPE)

    def write(self, jpeg: bytes, times: int = 1):
        for _ in range(times):
            self.p.stdin.write(jpeg)
            self.frames += 1

    def close(self) -> float:
        self.p.stdin.close()
        if self.p.wait() != 0:
            raise RuntimeError(f"ffmpeg failed for {self.path}")
        return self.frames / FPS


async def _shot(cdp) -> bytes:
    r = await cdp.send("Page.captureScreenshot", {"format": "jpeg", "quality": 93, "optimizeForSpeed": True})
    return base64.b64decode(r["data"])


async def record_timeline(ctx, base: str, sid: str, page_name: str) -> float:
    page = await ctx.new_page()
    await page.goto(f"{base}/demo/scenes/{page_name}", wait_until="networkidle")
    await page.wait_for_function("window.READY === true", timeout=60_000)
    duration = await page.evaluate("window.DURATION")
    cdp = await ctx.new_cdp_session(page)
    enc = Encoder(BUILD / f"{sid}.mp4")
    for i in range(round(duration * FPS)):
        await page.evaluate(f"render({i / FPS})")
        enc.write(await _shot(cdp))
    await page.close()
    return enc.close()


async def record_viewer(ctx, base: str, sid: str, viewer_url: str) -> float:
    page = await ctx.new_page()
    await page.goto(f"{base}/demo/scenes/s5_browser.html?src={quote(viewer_url, safe='')}&show={quote(VIEWER_URL, safe='')}",
                    wait_until="load")
    frame = None
    for _ in range(200):
        frame = next((f for f in page.frames if "/viewer/" in f.url), None)
        if frame:
            break
        await asyncio.sleep(0.1)
    await frame.wait_for_function(
        "() => /paths in/.test((document.getElementById('status') || {}).textContent || '')", timeout=120_000)
    await page.evaluate("document.fonts.ready")
    await asyncio.sleep(0.6)
    cdp = await ctx.new_cdp_session(page)
    enc = Encoder(BUILD / f"{sid}.mp4")
    cur = [900.0, 330.0]

    async def hold(sec):
        enc.write(await _shot(cdp), round(sec * FPS))

    async def move(x, y, sec):
        x0, y0 = cur
        n = max(1, round(sec * FPS))
        for k in range(1, n + 1):
            e = 0.5 - 0.5 * math.cos(math.pi * k / n)
            await page.evaluate(f"cursor({x0 + (x - x0) * e}, {y0 + (y - y0) * e})")
            enc.write(await _shot(cdp))
        cur[:] = [x, y]

    async def center(js_find: str):
        r = await frame.evaluate(f"() => {{ const e = {js_find}; const r = e.getBoundingClientRect(); "
                                 f"return [r.left + Math.min(r.width / 2, 120), r.top + r.height / 2]; }}")
        ox, oy = await page.evaluate("frameOrigin()")
        return ox + r[0], oy + r[1]

    async def click(js_find: str, glide=0.6):
        x, y = await center(js_find)
        await move(x, y, glide)
        for k in range(4):
            await page.evaluate(f"cursor({x}, {y}, {[0.5, 1, 1, 0.6][k]})")
            enc.write(await _shot(cdp))
        await frame.evaluate(f"() => ({js_find}).click()")
        await asyncio.sleep(0.4)
        for k in range(3):
            await page.evaluate(f"cursor({x}, {y}, {[0.4, 0.15, 0][k]})")
            enc.write(await _shot(cdp))

    async def scroll(y_js: str, sec):
        y0 = await frame.evaluate("() => window.scrollY")
        y1 = await frame.evaluate(f"() => Math.max(0, {y_js})")
        n = max(1, round(sec * FPS))
        for k in range(1, n + 1):
            e = 0.5 - 0.5 * math.cos(math.pi * k / n)
            await frame.evaluate(f"() => window.scrollTo(0, {y0 + (y1 - y0) * e})")
            enc.write(await _shot(cdp))

    chip = "[...document.querySelectorAll('#chips button')].find((b) => b.textContent.startsWith('Load-bearing'))"
    first = "document.querySelector('#list li button.item')"
    evidence = "document.getElementById('detail').closest('section')"
    console_card = "document.querySelector('section.console')"
    await hold(1.8)
    await click(chip, 0.7)
    await hold(0.5)
    await click(first, 0.6)
    await hold(1.0)
    await scroll(f"window.scrollY + {evidence}.getBoundingClientRect().top - 10", 1.0)
    await hold(2.4)
    await scroll("window.scrollY + 230", 0.8)
    await hold(1.5)
    await scroll(f"window.scrollY + {console_card}.getBoundingClientRect().top - 10", 1.0)
    await frame.evaluate("""() => { const s = document.getElementById('preset');
        const o = [...s.options].find((o) => o.textContent.startsWith('Retracted for citing'));
        s.value = o.value; s.onchange(); }""")
    await click("document.getElementById('run')", 0.6)
    await hold(0.3)
    await move(cur[0] + 90, cur[1] + 70, 0.5)
    await hold(TIMING["s5"] - enc.frames / FPS)
    await page.close()
    return enc.close()


async def stills(args) -> int:
    """PNG stills of the timeline scenes at given times, for checking layout without recording."""
    from playwright.async_api import async_playwright

    build_data()
    base, srv = _serve()
    out = BUILD / "stills"
    out.mkdir(parents=True, exist_ok=True)
    times = [float(t) for t in args.stills.split(",")]
    wanted = {f"s{n.strip()}" for n in args.scenes.split(",")} if args.scenes else {sid for sid, _, _ in SCENES}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(executable_path=_chromium(), headless=True, args=["--hide-scrollbars"])
        ctx = await browser.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1, color_scheme="dark")
        for sid, page_name, _ in SCENES:
            if sid not in wanted or sid == "s5":
                continue
            page = await ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            await page.goto(f"{base}/demo/scenes/{page_name}", wait_until="networkidle")
            try:
                await page.wait_for_function("window.READY === true", timeout=30_000)
            except Exception:
                print(f"{sid}: not ready; errors: {errors}")
                continue
            for t in times:
                await page.evaluate(f"render({t})")
                await page.screenshot(path=str(out / f"{sid}_{t:05.1f}.png"))
            print(f"{sid}: {len(times)} stills{'; errors: ' + '; '.join(errors) if errors else ''}")
            await page.close()
        await browser.close()
    srv.shutdown()
    return 0


def assemble(durations: dict[str, float]) -> Path:
    order = [sid for sid, _, _ in SCENES]
    inputs, filters = [], []
    for i, sid in enumerate(order):
        d = durations[sid]
        inputs += ["-i", str(BUILD / f"{sid}.mp4")]
        out = 0.6 if i == len(order) - 1 else 0.25
        filters.append(f"[{i}:v]fade=t=in:st=0:d=0.2:c={BG},fade=t=out:st={d - out:.3f}:d={out}:c={BG}[v{i}]")
    filters.append("".join(f"[v{i}]" for i in range(len(order))) + f"concat=n={len(order)}:v=1:a=0[out]")
    final = BUILD / "load-bearing-demo.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(filters), "-map", "[out]",
                    "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p", "-r", str(FPS),
                    "-movflags", "+faststart", str(final)], check=True)
    return final


def _ts(t: float, srt: bool = True) -> str:
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}".replace(".", ",") if srt else f"{int(m)}:{s:04.1f}"


def write_script(durations: dict[str, float], data: dict) -> None:
    vo = VOICE_OVER
    srt, md, t0, n = [], ["# Demo video timing", "",
                          "Silent video: `load-bearing-demo.mp4`. Record each voice-over line to fit its scene; "
                          "`load-bearing-demo.srt` has the same text split by sentence at its time codes.", "",
                          "| # | Scene | Time | Length | Voice-over | Words |", "|---|---|---|---|---|---|"], 0.0, 1
    for i, (sid, _, title) in enumerate(SCENES, 1):
        d = durations[sid]
        text = vo[sid]
        md.append(f"| {i} | {title} | {_ts(t0, False)}–{_ts(t0 + d, False)} | {d:.1f} s | {text} | {len(text.split())} |")
        sentences = re.split(r"(?<=[.!?])\s+", text)
        start, end = t0 + 0.4, t0 + d - 0.3
        total = sum(len(s) for s in sentences)
        for s in sentences:
            seg = (end - start) * len(s) / total
            srt += [str(n), f"{_ts(start)} --> {_ts(start + seg - 0.05)}", s, ""]
            start += seg
            n += 1
        t0 += d
    md += ["", f"Total: {_ts(t0, False)} ({t0:.1f} s)."]
    (BUILD / "load-bearing-demo.srt").write_text("\n".join(srt))
    (BUILD / "timing.md").write_text("\n".join(md) + "\n")


def _chromium() -> str:
    if os.environ.get("CHROMIUM"):
        return os.environ["CHROMIUM"]
    found = sorted(glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome")),
                   key=lambda p: int(re.search(r"chromium-(\d+)", p).group(1)))
    if not found:
        raise SystemExit("no Chromium found: run `uv run --with playwright playwright install chromium` or set CHROMIUM")
    return found[-1]


def _serve() -> tuple[str, http.server.ThreadingHTTPServer]:
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(ROOT)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_address[1]}", srv


async def main_async(args) -> int:
    from playwright.async_api import async_playwright

    data = build_data()
    print(f"data: {DEMO_DOI}, Relate query {data['relate']['elapsed_ms']} ms, {len(data['agent']['steps'])} agent steps")
    base, srv = _serve()
    wanted = {f"s{n.strip()}" for n in args.scenes.split(",")} if args.scenes else {sid for sid, _, _ in SCENES}
    viewer = f"{base}/viewer/" if args.local_viewer else VIEWER_URL
    durations_file = BUILD / "durations.json"
    durations = json.loads(durations_file.read_text()) if durations_file.exists() else {}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(executable_path=_chromium(), headless=True,
                                           # In-process iframes: an out-of-process (cross-origin) iframe is
                                           # captured at 1/device-scale size in headless screenshots.
                                           args=["--force-color-profile=srgb", "--hide-scrollbars",
                                                 "--disable-site-isolation-trials",
                                                 "--disable-features=IsolateOrigins,site-per-process"])
        ctx = await browser.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1.5,
                                        color_scheme="dark")
        sem = asyncio.Semaphore(args.jobs)

        async def one(sid, page_name, title):
            async with sem:
                if sid == "s5":
                    d = await record_viewer(ctx, base, sid, viewer)
                else:
                    d = await record_timeline(ctx, base, sid, page_name)
                durations[sid] = d
                print(f"  {sid} {title}: {d:.1f} s", flush=True)

        results = await asyncio.gather(*(one(*s) for s in SCENES if s[0] in wanted), return_exceptions=True)
        failed = [r for r in results if isinstance(r, BaseException)]
        for r in failed:
            print(f"scene failed: {r!r}")
        await browser.close()
    srv.shutdown()
    durations_file.write_text(json.dumps(durations, indent=1))
    if failed:
        return 1
    missing = [sid for sid, _, _ in SCENES if not (BUILD / f"{sid}.mp4").exists()]
    if missing:
        print(f"not assembling: missing {missing}")
        return 1
    final = assemble(durations)
    write_script(durations, data)
    print(f"video: {final.relative_to(ROOT)} ({sum(durations.values()):.1f} s); script: demo/build/timing.md, .srt")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--scenes", help="comma-separated scene numbers to (re)record, e.g. 2,4")
    ap.add_argument("--local-viewer", action="store_true", help="scene 5 from this checkout instead of GitHub Pages")
    ap.add_argument("--jobs", type=int, default=3, help="scenes recorded in parallel")
    ap.add_argument("--data-only", action="store_true", help="write demo/build/data.js and stop")
    ap.add_argument("--stills", help="comma-separated times (s): save PNG stills of the timeline scenes instead")
    args = ap.parse_args()
    if args.data_only:
        build_data()
        print("wrote demo/build/data.js")
        return 0
    return asyncio.run(stills(args) if args.stills else main_async(args))


if __name__ == "__main__":
    sys.exit(main())
