// Deterministic timeline for the demo scenes. Every visual is a pure function of t (seconds): the
// recorder calls render(t) once per frame and screenshots the result, so motion never depends on how
// fast the machine is. No CSS transitions or animations are used anywhere.
(() => {
  const tracks = [];
  const clamp = (x) => Math.max(0, Math.min(1, x));
  const ease = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
  const p = (t, t0, d) => (d <= 0 ? (t >= t0 ? 1 : 0) : ease(clamp((t - t0) / d)));
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  const TL = {
    p, ease, clamp, esc,
    on(fn) { tracks.push(fn); return fn; },
    // Visible from tIn to tOut, fading (and sliding/scaling) in and out.
    show(el, tIn, tOut = Infinity, { d = 0.5, dy = 14, dx = 0, scale = 0, dOut = d } = {}) {
      TL.on((t) => {
        const a = p(t, tIn, d), b = tOut === Infinity ? 0 : p(t, tOut, dOut), o = a * (1 - b), k = 1 - a;
        el.style.opacity = o.toFixed(3);
        el.style.visibility = o < 0.002 ? "hidden" : "visible";
        el.style.transform = `translate(${dx * k}px, ${dy * k}px) scale(${1 + scale * k})`;
      });
    },
    // Types text into el; returns the time typing ends.
    type(el, text, t0, cps = 40) {
      TL.on((t) => { const n = Math.max(0, Math.min(text.length, Math.floor((t - t0) * cps))); el.textContent = text.slice(0, n); });
      return t0 + text.length / cps;
    },
    caret(el, tFrom, tTo) {
      TL.on((t) => { el.style.visibility = t >= tFrom && t < tTo && Math.floor(t * 2.2) % 2 === 0 ? "visible" : "hidden"; });
    },
    count(el, to, t0, d, fmt = (v) => Math.round(v).toLocaleString("en-US")) {
      TL.on((t) => { el.textContent = fmt(to * p(t, t0, d)); });
    },
    // Piecewise eased scrolling: keys = [[t, y], ...].
    scroll(el, keys) {
      TL.on((t) => {
        let y = keys[0][1];
        for (let i = 1; i < keys.length; i++) {
          const [t0, y0] = keys[i - 1], [t1, y1] = keys[i];
          if (t >= t1) { y = y1; continue; }
          if (t > t0) y = y0 + (y1 - y0) * ease((t - t0) / (t1 - t0));
          break;
        }
        el.scrollTop = y;
      });
    },
    // Background highlight between tIn and tOut. rgb like "245,165,36".
    hl(el, tIn, tOut = Infinity, rgb = "245,165,36", alpha = 0.2) {
      TL.on((t) => {
        const o = p(t, tIn, 0.35) * (tOut === Infinity ? 1 : 1 - p(t, tOut, 0.35));
        el.style.background = o > 0.002 ? `rgba(${rgb},${(alpha * o).toFixed(3)})` : "";
        el.style.boxShadow = o > 0.002 ? `inset 3px 0 0 rgba(${rgb},${o.toFixed(3)})` : "";
      });
    },
    // Draws an SVG path from 0 to full length between t0 and t0 + d.
    draw(pathEl, t0, d) {
      const len = pathEl.getTotalLength();
      pathEl.style.strokeDasharray = `${len}`;
      TL.on((t) => { pathEl.style.strokeDashoffset = `${len * (1 - p(t, t0, d))}`; });
    },
    cypher(src) {
      const KW = /\b(MATCH|OPTIONAL|WHERE|RETURN|WITH|ORDER|BY|AND|OR|NOT|IN|AS|DISTINCT|CASE|WHEN|THEN|ELSE|END|UNWIND|LIMIT|DESC|count|coalesce|nodes|relationships|length|labels|toString)\b/g;
      return src.split("\n").map((line) => {
        const cm = line.indexOf("//");
        const code = cm >= 0 ? line.slice(0, cm) : line, comment = cm >= 0 ? line.slice(cm) : "";
        const out = [];
        const re = /('[^']*')|(\$\w+)|(:[A-Z]\w*)|(\b\d+\b)|([{}]|->|-\[|\]-|\[|\]|\(|\))|([^'$:{}\[\]()\d-]+|[\s\S])/g;
        let m;
        while ((m = re.exec(code))) {
          if (m[1]) out.push(`<span class="k-str">${esc(m[1])}</span>`);
          else if (m[2]) out.push(`<span class="k-par">${esc(m[2])}</span>`);
          else if (m[3]) out.push(`<span class="k-lbl">${esc(m[3])}</span>`);
          else if (m[4]) out.push(`<span class="k-num">${esc(m[4])}</span>`);
          else if (m[5]) out.push(`<span class="k-op">${esc(m[5])}</span>`);
          else out.push(esc(m[6]).replace(KW, '<span class="k-kw">$1</span>'));
        }
        return out.join("") + (comment ? `<span class="k-cm">${esc(comment)}</span>` : "");
      }).join("\n");
    },
    el(tag, attrs = {}, html = "") {
      const e = document.createElement(tag);
      for (const [k, v] of Object.entries(attrs)) {
        if (k === "style" && typeof v === "object") Object.assign(e.style, v); else e.setAttribute(k, v);
      }
      if (html) e.innerHTML = html;
      return e;
    },
    // Load the web fonts before any layout is measured (scroll targets, callout positions).
    async fonts() {
      const faces = ["400 16px Inter", "500 16px Inter", "600 16px Inter", "700 16px Inter", "800 16px Inter",
        "italic 400 16px Inter", '400 13px "JetBrains Mono"', '600 13px "JetBrains Mono"'];
      await Promise.all(faces.map((f) => document.fonts.load(f).catch(() => null)));
      await document.fonts.ready;
    },
    async ready(duration) {
      await document.fonts.ready;
      window.DURATION = duration;
      window.render(0);
      window.READY = true;
    },
  };
  window.TL = TL;
  window.render = (t) => { for (const f of tracks) f(t); };
})();
