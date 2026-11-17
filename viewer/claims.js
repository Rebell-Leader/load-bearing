"use strict";

const byId = (id) => document.getElementById(id);
const demo = window.claimDemo;
const example = byId("example");
const cutoff = byId("cutoff");
let mode = "claim";

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function sourceLink(text, url) {
  const link = element("a", text);
  link.href = url;
  link.target = "_blank";
  link.rel = "noopener";
  return link;
}

function claimCard(result, caseData) {
  const flagged = result.action === "review_indirect";
  const outsideScope = result.action === "retain_for_this_notice";
  const card = element("article", null, "claim-card");
  if (flagged) card.classList.add("review");
  if (outsideScope) card.classList.add("retain");
  card.append(element("span", demo.actions[result.action], "status"), element("h3", result.claim));
  const finding = result.findings[0];
  if (!finding?.evidence) {
    card.append(element("p", "The shared reference has no applicable notice in this snapshot at this cutoff.", "finding"));
    return card;
  }

  const { evidence, notice } = finding;
  const path = element("ol", null, "path");
  path.setAttribute("aria-label", flagged ? "Evidence path to notice" : "Scope of the notice");
  const locator = element("li");
  locator.append(sourceLink(evidence.locator, evidence.url));
  path.append(locator);
  path.append(element("li", flagged ? `Includes ${caseData.study}` : `${caseData.study} is outside this outcome`));
  const noticeStep = element("li");
  noticeStep.append(sourceLink(`Publisher retraction · ${notice.date}`, notice.url));
  path.append(noticeStep);
  card.append(path, element("p", evidence.finding, "finding"));
  const action = flagged
    ? example.value === "rodents"
      ? "Reassess the rat estimate without study 44."
      : "Verify the segmentation claim against an independent source."
    : "Keep this sentence for this notice.";
  card.append(element("p", action, "next"));
  const details = element("details");
  details.append(element("summary", flagged ? "Recorded agent revision" : "Recorded agent decision"),
                 element("p", result.recorded_revision),
                 element("p", `${demo.agent} · saved MCP comparison`));
  card.append(details);
  return card;
}

function render(resetDate = false) {
  const data = demo.examples[example.value];
  const currentDate = data.current[0].as_of;
  if (resetDate) {
    cutoff.replaceChildren(new Option(`After notice · ${currentDate}`, "current"));
    if (data.before) cutoff.add(new Option(`Before notice · ${data.before}`, "historical"));
  }
  byId("date-field").hidden = !data.before || mode === "direct";
  byId("direct").setAttribute("aria-pressed", String(mode === "direct"));
  byId("claim").setAttribute("aria-pressed", String(mode === "claim"));
  byId("case-title").textContent = data.title;
  byId("shared-source").textContent = data.reference;
  byId("shared-source").href = data.source_url;
  byId("shared-doi").textContent = data.current[0].resolved_references[0];
  const rows = mode === "direct" ? data.direct : data[cutoff.value];
  const banner = byId("direct-result");
  banner.hidden = mode !== "direct";
  const count = new Set(rows.flatMap((row) => row.findings.map((finding) => finding.notice.doi))).size;
  banner.textContent = `${count} direct notices on the shared DOI`;
  byId("cards").replaceChildren(...rows.map((row) => claimCard(row, data)));
  byId("command").textContent = "uv run loadbearing audit"
    + (example.value === "rodents" ? "" : " --example recommender")
    + (mode === "direct" ? " --mode direct" : cutoff.value === "historical" ? ` --as-of ${data.before}` : "");
}

if (!demo) {
  byId("boot-error").hidden = false;
} else {
  example.addEventListener("change", () => render(true));
  cutoff.addEventListener("change", () => render());
  for (const method of ["direct", "claim"]) {
    byId(method).addEventListener("click", () => { mode = method; render(); });
  }
  byId("copy").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(byId("command").textContent);
      byId("copy").textContent = "Copied";
      setTimeout(() => { byId("copy").textContent = "Copy"; }, 1800);
    } catch {
      const range = document.createRange();
      range.selectNodeContents(byId("command"));
      window.getSelection().removeAllRanges();
      window.getSelection().addRange(range);
    }
  });
  for (const [key, title] of [["direct", "Direct DOI"], ["untyped", "Two-hop paths"], ["claim_aware", "Claim-scoped paths"]]) {
    const row = element("tr");
    const stats = demo.pilot[key];
    const heading = element("th", title);
    heading.scope = "row";
    row.append(heading, element("td", `${stats.indirect_detected}/${stats.indirect_total}`),
               element("td", `${stats.false_alerts_on_controls}/${stats.cases - stats.required_review_actions}`));
    byId("metrics").append(row);
  }
  byId("snapshot-id").textContent = `Snapshot SHA-256 ${demo.snapshot_sha256.slice(0, 16)}…`;
  byId("audit").hidden = false;
  byId("reproduce").hidden = false;
  render(true);
}
