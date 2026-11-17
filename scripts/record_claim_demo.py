"""Record the claim-first, captioned submission video from the offline app."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from record_demo import _chromium, _ts

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "demo/build"
FPS = 30
BEATS = [
    (13, "Two sentences cite the same systematic review.\nWhich one depends on a study that was later retracted?"),
    (11, "The direct DOI check finds no notice on the review itself."),
    (13, "Relate follows the rat outcome to Figure 3b and study 44,\nthen to the publisher's retraction notice."),
    (12, "Figure 3a uses a different set of studies.\nThe mouse sentence is outside the scope of this notice."),
    (10, "Move the cutoff before the notice.\nThe audit reports what was in the record at that date."),
    (13, "In the recorded MCP run, the agent qualified the rat claim,\nlinked the evidence, and kept the mouse claim verbatim."),
    (12, "The same check works on this recommender overview.\nThe clustering claim and the ranking claim rely on different references."),
    (12, "On the curated pilot, claim paths found all six indirect cases\nand raised zero alerts on the six controls."),
    (10, "Run the same audit offline from the published Relate store.\nNo model, API key, or database server is needed."),
]


def capture(directory: Path) -> None:
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=_chromium(), headless=True, args=["--disable-dev-shm-usage"],
        )
        page = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=1.5)
        page.goto((ROOT / "viewer/claims.html").as_uri())
        expect(page.locator(".claim-card")).to_have_count(2)
        page.add_style_tag(content="""
            main { padding-bottom: 700px; }
            .demo-focus { outline: 3px solid #25745d; outline-offset: 3px; border-radius: 5px; }
        """)

        def frame(number: int, scroll: str | None = None, focus: str | None = None) -> None:
            page.locator(".demo-focus").evaluate_all("(nodes) => nodes.forEach(n => n.classList.remove('demo-focus'))")
            if scroll:
                page.locator(scroll).evaluate("(node) => window.scrollTo(0, node.getBoundingClientRect().top + scrollY - 44)")
            else:
                page.evaluate("window.scrollTo(0, 0)")
            if focus:
                page.locator(focus).first.evaluate("(node) => node.classList.add('demo-focus')")
            page.screenshot(path=directory / f"{number}.png", animations="disabled")

        page.locator("#direct").click()
        frame(1)
        expect(page.locator("#direct-result")).to_have_text("0 direct notices on the shared DOI")
        frame(2, "#audit", "#direct-result")
        page.locator("#claim").click()
        expect(page.locator(".review .path")).to_contain_text("Figure 3b")
        frame(3, "#audit", ".review .path")
        expect(page.locator(".retain .path")).to_contain_text("Figure 3a")
        frame(4, "#audit", ".retain .path")
        page.locator("#cutoff").select_option("historical")
        expect(page.locator(".status").first).to_contain_text("No applicable notice")
        frame(5, "#audit", "#cutoff")
        page.locator("#cutoff").select_option("current")
        page.locator(".review summary").click()
        page.locator(".retain summary").click()
        expect(page.locator(".review details[open]")).to_contain_text("Claude Haiku 5.5")
        frame(6, ".claims", ".review details")
        page.locator("#example").select_option("recommender")
        expect(page.locator(".review .path")).to_contain_text("section 3.2")
        frame(7, "#audit")
        page.locator("#example").select_option("rodents")
        frame(8, "#reproduce", ".comparison")
        terminal_frame(page, directory / "9.png")
        browser.close()


def terminal_frame(page, output: Path) -> None:
    command = "uv run loadbearing audit"
    report = subprocess.run([sys.executable, "-m", "loadbearing.cli", "audit", "--json"], cwd=ROOT,
                            capture_output=True, text=True, check=True)
    rows = json.loads(report.stdout)
    cards = [
        (row["findings"][0]["evidence"]["locator"], row["action"], row["findings"][0]["notice"]["url"])
        for row in rows
    ]
    page.set_content("""
    <!doctype html><html lang="en"><meta charset="utf-8"><title>Offline claim audit</title>
    <style>
      * { box-sizing: border-box; }
      body { margin: 0; background: #f8f6ef; color: #202b28; font: 18px system-ui, sans-serif; }
      main { width: 1100px; margin: 70px auto; }
      h1 { font: 50px Georgia, serif; margin: 6px 0 23px; }
      .tag { color: #174e41; font: 700 13px monospace; letter-spacing: 2px; }
      pre { background: #1b352d; color: #e8f4e7; padding: 28px 32px; font: 17px/1.8 monospace;
            white-space: pre-wrap; border-radius: 12px; }
      a { color: #174e41; }
    </style>
    <main>
      <div class="tag">LOAD-BEARING</div><h1>Run the claim audit offline</h1>
      <pre id="terminal"></pre>
      <a href="https://github.com/Rebell-Leader/load-bearing">github.com/Rebell-Leader/load-bearing</a>
    </main>
    """)
    lines = [f"$ {command}", "", "data/claims.rl · cutoff 2026-11-16", ""]
    for locator, action, notice in cards:
        lines.extend((action, f"  {locator}", f"  {notice}", ""))
    page.locator("#terminal").evaluate("(node, text) => { node.textContent = text; }", "\n".join(lines).rstrip())
    page.screenshot(path=output, animations="disabled")


def subtitles() -> str:
    start, cues = 0, []
    for index, (duration, caption) in enumerate(BEATS, start=1):
        cues.extend((str(index), f"{_ts(start + 0.15)} --> {_ts(start + duration - 0.15)}", caption, ""))
        start += duration
    return "\n".join(cues)


def assemble(directory: Path, audio: Path | None) -> None:
    captions = OUTPUT / "load-bearing-claim-first.srt"
    captions.write_text(subtitles(), encoding="utf-8")
    command = ["ffmpeg", "-y", "-loglevel", "error"]
    for index, (seconds, _) in enumerate(BEATS, start=1):
        command.extend(("-loop", "1", "-framerate", str(FPS), "-t", str(seconds), "-i", str(directory / f"{index}.png")))
    if audio:
        command.extend(("-i", str(audio)))
    joined = "".join(f"[{i}:v]" for i in range(len(BEATS)))
    style = "Fontname=DejaVu Sans,FontSize=17,PrimaryColour=&H00FFFFFF,BackColour=&H001A3229,BorderStyle=3,Outline=3,Shadow=0,MarginV=18"
    command.extend(("-filter_complex_threads", "2", "-filter_complex",
                    f"{joined}concat=n={len(BEATS)}:v=1:a=0[raw];"
                    f"[raw]subtitles={captions.name}:force_style='{style}'[out]", "-map", "[out]"))
    command.extend(("-c:v", "libx264", "-threads", "3", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p"))
    if audio:
        command.extend(("-map", f"{len(BEATS)}:a:0", "-af", "apad", "-c:a", "aac", "-shortest"))
    command.extend(("-movflags", "+faststart", "load-bearing-claim-first.mp4"))
    subprocess.run(command, cwd=OUTPUT, check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", type=Path, help="optional narration track; a short track is padded")
    options = parser.parse_args()
    audio = options.audio.resolve(strict=True) if options.audio else None
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="loadbearing-capture-") as directory:
        capture(Path(directory))
        assemble(Path(directory), audio)
    print(f"Created {(OUTPUT / 'load-bearing-claim-first.mp4').relative_to(ROOT)} ({sum(x[0] for x in BEATS)} seconds)")
