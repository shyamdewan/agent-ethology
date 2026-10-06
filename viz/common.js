// Shared helpers for every Agent Ethology tab.
const TABS = [
  ["histomap.html", "Who runs it"],
  ["ideas.html", "Where ideas come from"],
  ["deference.html", "Who defers to whom"],
  ["contagion.html", "Mood contagion"],
  ["happiness.html", "Power vs happiness"],
  ["dissent.html", "Dissent"],
  ["backstage.html", "Public vs private"],
  ["agency.html", "What they work on"],
];
const LAB_COLORS = {
  Anthropic: "#e0917c", OpenAI: "#faed8f", Google: "#b5d1cc", xAI: "#7f9a92",
  DeepSeek: "#5fa8a0", Moonshot: "#c4705c", Zhipu: "#d9c26a", Meta: "#3f6b5f", Other: "#566b5e", all: "#b5d1cc",
};
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const labOfName = n => {
  const s = n.toLowerCase().replace("[temporary] ", "");
  if (/claude|opus|sonnet|haiku|fable/.test(s)) return "Anthropic";
  if (/^gpt|^o\d/.test(s)) return "OpenAI";
  if (s.startsWith("gemini")) return "Google";
  if (s.startsWith("grok")) return "xAI";
  if (s.startsWith("deepseek")) return "DeepSeek";
  if (s.startsWith("kimi") || s.includes("fine-tuned leader")) return "Moonshot";
  if (s.startsWith("glm")) return "Zhipu";
  if (s.startsWith("muse")) return "Meta";
  return "Other";
};
const labColor = n => LAB_COLORS[LAB_COLORS[n] ? n : labOfName(n)];
// logos keep each company's own brand color, whatever the site palette is
const BRAND_COLOR = { Anthropic: "#d97757", OpenAI: "#ffffff", Google: "#4796e3", xAI: "#ffffff", DeepSeek: "#4d6bfe", Moonshot: "#ffffff", Zhipu: "#3859ff", Meta: "#0866ff" };
const BRAND = { Anthropic: "claude", OpenAI: "openai", Google: "gemini", xAI: "grok", DeepSeek: "deepseek", Moonshot: "kimi", Zhipu: "zhipu", Meta: "meta" };
function logo(name, color, size = 14) {
  const lab = LAB_COLORS[name] ? name : labOfName(name);
  const b = BRAND[lab];
  color = color || BRAND_COLOR[lab];
  const ds = window.LOGOS && window.LOGOS[b];
  return ds ? `<svg viewBox="0 0 24 24" width="${size}" height="${size}" aria-hidden="true" style="flex:none;vertical-align:-2px"><path fill="${color || labColor(name)}" fill-rule="evenodd" d="${ds.join(" ")}"/></svg>` : "";
}

function renderTabs() {
  if (!document.body || document.body.dataset.tabs === "off" || document.querySelector("nav.tabs")) return;
  const here = location.pathname.split("/").pop() || "histomap.html";
  const nav = document.createElement("nav");
  nav.className = "tabs";
  nav.setAttribute("aria-label", "Swarm dynamics");
  nav.innerHTML = `<div class="tabs-in"><a class="brand" href="histomap.html" style="color:inherit;text-decoration:none">Agent <span>Ethology</span></a>${TABS.map(([href, label], i) =>
    `<a class="tab" href="${href}"${href === here ? ' aria-current="page"' : ""}><b>${String(i + 1).padStart(2, "0")}</b>${label}</a>`).join("")}</div>`;
  document.body.prepend(nav);
  // keep the tab strip where the reader left it across page loads, and never hide the current tab
  const strip = nav.querySelector(".tabs-in");
  try { strip.scrollLeft = +sessionStorage.getItem("tabs-x") || 0; } catch (e) {}
  const cur = strip.querySelector('[aria-current="page"]');
  if (cur && (cur.offsetLeft < strip.scrollLeft || cur.offsetLeft + cur.offsetWidth > strip.scrollLeft + strip.clientWidth)) strip.scrollLeft = cur.offsetLeft - 24;
  const save = () => { try { sessionStorage.setItem("tabs-x", strip.scrollLeft); } catch (e) {} };
  strip.addEventListener("scroll", save, { passive: true });
  addEventListener("pagehide", save);
}

const tipEl = () => document.getElementById("tip") || Object.assign(document.body.appendChild(document.createElement("div")), { id: "tip", className: "tip" });
function showTip(ev, html) {
  const t = tipEl();
  t.innerHTML = html;
  t.style.opacity = 1;
  const x = Math.min(ev.clientX + 16, innerWidth - t.offsetWidth - 12);
  const y = Math.min(ev.clientY + 16, innerHeight - t.offsetHeight - 12);
  t.style.left = x + "px"; t.style.top = y + "px";
}
const hideTip = () => { tipEl().style.opacity = 0; };
const pct = (v, d = 0) => (v * 100).toFixed(d) + "%";
const signed = (v, d = 2) => (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(d);
const SOURCE_NOTE = "Source: AI Village dataset (AI Digest), agent chat only. Every message scored by Jev (TypeSafe) with the six previous messages in its room as context: dominance (submissive → commanding), mood (distressed → delighted), whom it addresses, and whether it directs, defers, supports, opposes or proposes.";
// build the tab bar as soon as <body> is parsed, so it is there on first paint instead of pushing the page down later
if (document.body) renderTabs();
else new MutationObserver((_, mo) => { if (document.body) { mo.disconnect(); renderTabs(); } }).observe(document.documentElement, { childList: true });
document.addEventListener("DOMContentLoaded", renderTabs);

// ---------------------------------------------------------------- shared time range
// One range for every tab: a weekly activity strip you can brush, plus presets.
// Pages call TimeRange.mount(fn); fn(range) runs on load and on every change.
// range.from / range.to are inclusive indexes into WK.weeks; range.has(isoWeek) tests a week.
const TimeRange = (() => {
  const KEY = "swarm-range";
  let range, listeners = [];
  const weeks = () => window.WK.weeks;
  const make = (from, to) => {
    const ws = weeks();
    from = Math.max(0, Math.min(from, ws.length - 1)); to = Math.max(from, Math.min(to, ws.length - 1));
    const a = ws[from], b = ws[to];
    return { from, to, fromWeek: a, toWeek: b, all: from === 0 && to === ws.length - 1,
      has: iso => { const w = iso.slice(0, 10); return w >= a && w <= addDays(b, 6); },
      hasIdx: i => i >= from && i <= to };
  };
  const addDays = (iso, n) => { const t = new Date(iso + "T12:00:00Z"); t.setUTCDate(t.getUTCDate() + n); return t.toISOString().slice(0, 10); };
  const fmt = iso => new Date(iso + "T12:00:00Z").toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
  function load() {
    try { const s = JSON.parse(localStorage.getItem(KEY) || "null"); if (s) { const ws = weeks(); const f = ws.indexOf(s[0]), t = ws.indexOf(s[1]); if (f >= 0 && t >= f) return make(f, t); } } catch (e) {}
    // first visit: open on the last 3 months, the same span as the "Last 3 months" preset
    const last = weeks().length - 1;
    return make(Math.max(0, last - 12), last);
  }
  function save() { try { localStorage.setItem(KEY, JSON.stringify([range.fromWeek, range.toWeek])); } catch (e) {} }
  function presets() {
    const ws = weeks(), last = ws.length - 1, idx = y => [ws.findIndex(w => w >= `${y}-01-01`), ws.length - 1 - [...ws].reverse().findIndex(w => w < `${y + 1}-01-01`)];
    return [["All", 0, last], ["2025", ...idx(2025)], ["2026", ...idx(2026)], ["Last 3 months", Math.max(0, last - 12), last], ["Last month", Math.max(0, last - 4), last]];
  }
  function set(r, from) { range = r; save(); paint(from); listeners.forEach(fn => fn(range)); }
  let brush, gBrush, x;
  function label(f, t) {
    const lab = document.getElementById("range-label");
    if (!lab) return;
    const ws = weeks(), n = d3.sum(window.WK.strip.slice(f, t + 1));
    lab.innerHTML = `<b>${fmt(ws[f])} – ${fmt(addDays(ws[t], 6))}</b> · ${t - f + 1} weeks · ${n.toLocaleString()} messages`;
    d3.selectAll(".range-strip rect.wk").attr("fill", (d, i) => i >= f && i <= t ? "#faed8f" : "#262d24");
  }
  function paint(from) {
    const lab = document.getElementById("range-label");
    if (!lab) return;
    label(range.from, range.to);
    document.querySelectorAll(".range-presets button").forEach(b => b.setAttribute("aria-pressed", +b.dataset.f === range.from && +b.dataset.t === range.to));
    if (from !== "brush" && gBrush) gBrush.call(brush.move, [x(range.from), x(range.to + 1)]);
  }
  function build() {
    const nav = document.querySelector(".tabs");
    const bar = document.createElement("div");
    bar.className = "range";
    bar.innerHTML = `<div class="range-in"><span class="label">Time frame</span><div class="range-presets">${presets().map(([l, f, t]) => `<button class="btn" data-f="${f}" data-t="${t}">${l}</button>`).join("")}</div><div class="range-strip" id="range-strip"></div><span class="range-label" id="range-label"></span></div>`;
    nav.appendChild(bar);
    bar.querySelectorAll(".range-presets button").forEach(b => b.onclick = () => set(make(+b.dataset.f, +b.dataset.t)));
    const el = document.getElementById("range-strip"), W = Math.max(160, el.clientWidth), H = 26, ws = weeks();
    x = d3.scaleLinear().domain([0, ws.length]).range([0, W]);
    const y = d3.scaleSqrt().domain([0, d3.max(window.WK.strip)]).range([0, H - 4]);
    const svg = d3.select(el).append("svg").attr("viewBox", `0 0 ${W} ${H}`).attr("preserveAspectRatio", "none").attr("aria-label", "Messages per week; drag to choose a time frame");
    svg.selectAll("rect.wk").data(window.WK.strip).join("rect").attr("class", "wk").attr("x", (d, i) => x(i) + 0.5).attr("width", Math.max(1, x(1) - x(0) - 1)).attr("y", d => H - y(d)).attr("height", d => y(d));
    const span = sel => { const f = Math.max(0, Math.round(x.invert(sel[0]))), t = Math.min(ws.length - 1, Math.max(f, Math.round(x.invert(sel[1])) - 1)); return [f, t]; };
    brush = d3.brushX().extent([[0, 0], [W, H]]).on("brush", ev => {
      if (!ev.sourceEvent || !ev.selection) return;
      label(...span(ev.selection));
    }).on("end", ev => {
      if (!ev.sourceEvent) return;
      if (!ev.selection) { set(make(0, ws.length - 1)); return; }
      const f = Math.round(x.invert(ev.selection[0])), t = Math.round(x.invert(ev.selection[1])) - 1;
      set(make(f, Math.max(f, t)), "brush");
      gBrush.call(brush.move, [x(range.from), x(range.to + 1)]);
    });
    gBrush = svg.append("g").attr("class", "brush").call(brush);
    paint();
  }
  return {
    mount(fn) {
      if (!range) { range = load(); if (document.querySelector(".tabs")) build(); else document.addEventListener("DOMContentLoaded", build); }
      listeners.push(fn); fn(range);
    },
    get: () => range,
  };
})();

// ---------------------------------------------------------------- conversation explorer
// Any element with data-ref="<room>/<day>#<id>" opens the full conversation around that message.
const DOM_WORD = ["submissive", "deferential", "peer", "assertive", "commanding"];
const CONV = (() => {
  const cache = {}, waiting = {};
  return {
    loaded(key, rows) { cache[key] = rows; (waiting[key] || []).forEach(fn => fn(rows)); delete waiting[key]; },
    get(room, day) {
      const key = room + "/" + day;
      if (cache[key]) return Promise.resolve(cache[key]);
      return new Promise((res, rej) => {
        (waiting[key] ||= []).push(res);
        if (waiting[key].length > 1) return;
        const s = document.createElement("script");
        s.src = `data/conv/${encodeURIComponent(room)}/${day}.js`;
        s.onerror = () => { delete waiting[key]; rej(new Error("missing")); };
        document.head.appendChild(s);
      });
    },
  };
})();
const Conversation = (() => {
  let el, state = {};
  const villageDay = iso => Math.floor((Date.parse(iso + "T00:00:00Z") - Date.UTC(2025, 3, 2)) / 864e5) + 1;
  const longDate = iso => new Date(iso + "T12:00:00Z").toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
  function ensureIndex() {
    if (window.CONV_INDEX) return Promise.resolve();
    return new Promise(res => { const s = document.createElement("script"); s.src = "data/conv/index.js"; s.onload = res; s.onerror = res; document.head.appendChild(s); });
  }
  function build() {
    el = document.createElement("aside");
    el.className = "convo"; el.setAttribute("role", "dialog"); el.setAttribute("aria-label", "Conversation"); el.hidden = true;
    el.innerHTML = `<header class="convo-head"><div><p class="eyebrow" id="cv-eyebrow"></p><h3 id="cv-title"></h3></div>
      <button class="btn convo-x" id="cv-close" aria-label="Close conversation">Close ✕</button></header>
      <div class="convo-nav"><button class="btn" id="cv-prev">← Previous day</button><button class="btn" id="cv-focus">Back to message</button><button class="btn" id="cv-next">Next day →</button></div>
      <div class="convo-body" id="cv-body" tabindex="-1"></div>`;
    document.body.appendChild(el);
    const scrim = document.createElement("div"); scrim.className = "convo-scrim"; scrim.hidden = true; scrim.id = "cv-scrim";
    document.body.appendChild(scrim);
    scrim.onclick = close;
    el.querySelector("#cv-close").onclick = close;
    el.querySelector("#cv-prev").onclick = () => step(-1);
    el.querySelector("#cv-next").onclick = () => step(1);
    el.querySelector("#cv-focus").onclick = () => focusMsg(true);
    addEventListener("keydown", ev => { if (ev.key === "Escape" && !el.hidden) close(); });
  }
  function close() { el.hidden = true; document.getElementById("cv-scrim").hidden = true; document.body.style.overflow = ""; state.opener?.focus?.(); }
  function days() { return (window.CONV_INDEX || {})[state.room] || []; }
  function step(dir) { const ds = days(), i = ds.indexOf(state.day) + dir; if (i >= 0 && i < ds.length) show(state.room, ds[i], null); }
  function chip(r) {
    if (r[4] == null) return "";
    const dom = r[4], mood = r[5], rel = r[6], tgt = r[7];
    const domCol = dom >= 2.5 ? "#e0573f" : dom < 1.75 ? "#b5d1cc" : "#566b5e";
    return `<span class="cv-chips"><span class="cv-chip" style="border-color:${domCol};color:${dom >= 2.5 || dom < 1.75 ? domCol : "var(--ash)"}">${DOM_WORD[Math.round(dom)]} ${dom.toFixed(1)}</span><span class="cv-chip">mood ${mood.toFixed(1)}</span>${rel ? `<span class="cv-chip">${esc(rel)}${tgt && tgt !== "everyone" ? ` → ${esc(tgt)}` : ""}</span>` : ""}</span>`;
  }
  function focusMsg(smooth) {
    const f = el.querySelector(".cv-msg.focus");
    if (f) f.scrollIntoView({ block: "center", behavior: smooth && !matchMedia("(prefers-reduced-motion: reduce)").matches ? "smooth" : "auto" });
  }
  async function show(room, day, id) {
    state = { ...state, room, day, id: id ?? state.id };
    const body = el.querySelector("#cv-body");
    el.querySelector("#cv-eyebrow").textContent = `#${room} · Day ${villageDay(day)}`;
    el.querySelector("#cv-title").textContent = longDate(day);
    const ds = days(), i = ds.indexOf(day);
    el.querySelector("#cv-prev").disabled = i <= 0;
    el.querySelector("#cv-next").disabled = i < 0 || i >= ds.length - 1;
    body.innerHTML = `<p class="hint" style="padding:16px">Loading the conversation…</p>`;
    let rows;
    try { rows = await CONV.get(room, day); }
    catch (e) { body.innerHTML = `<p class="hint" style="padding:16px">This conversation isn't available.</p>`; return; }
    const hasFocus = rows.some(r => r[0] === state.id);
    el.querySelector("#cv-focus").disabled = !hasFocus;
    body.innerHTML = `<p class="cv-count">${rows.length} messages in #${esc(room)} this day</p>` + rows.map(r => {
      const human = r[2] === "Human";
      const long = r[3].length > 520;
      return `<article class="cv-msg${r[0] === state.id ? " focus" : ""}${human ? " human" : ""}">
        <div class="cv-meta"><span class="cv-who">${human ? "" : logo(r[2], undefined, 13)}${esc(r[2])}</span><span class="cv-time">${r[1]}</span>${chip(r)}</div>
        <div class="cv-text${long ? " clamp" : ""}">${esc(r[3])}</div>${long ? `<button class="cv-more">Show more</button>` : ""}</article>`;
    }).join("");
    body.querySelectorAll(".cv-more").forEach(b => b.onclick = () => { const t = b.previousElementSibling; t.classList.toggle("clamp"); b.textContent = t.classList.contains("clamp") ? "Show more" : "Show less"; });
    if (hasFocus) focusMsg(false); else body.scrollTop = 0;
  }
  async function open(ref, opener) {
    if (!ref) return;
    if (!el) build();
    const [path, id] = ref.split("#"), cut = path.lastIndexOf("/");
    state = { opener: opener || document.activeElement };
    el.hidden = false; document.getElementById("cv-scrim").hidden = false; document.body.style.overflow = "hidden";
    hideTip();
    await ensureIndex();
    await show(path.slice(0, cut), path.slice(cut + 1), id);
    el.querySelector("#cv-close").focus({ preventScroll: true });
  }
  document.addEventListener("click", ev => {
    const t = ev.target.closest("[data-ref]");
    if (t && !ev.target.closest(".convo")) { ev.preventDefault(); open(t.getAttribute("data-ref"), t); }
  });
  document.addEventListener("keydown", ev => {
    const t = ev.target.closest && ev.target.closest("[data-ref]");
    if (t && (ev.key === "Enter" || ev.key === " ")) { ev.preventDefault(); open(t.getAttribute("data-ref"), t); }
  });
  return { open };
})();

// ---------------------------------------------------------------- private note reader
// Any element with data-note="<memory note id>" opens that agent's whole private note;
// data-hl="<agent name>" highlights every mention of that agent and scrolls to the first.
const NOTES = (() => {
  const cache = {}, waiting = {};
  return {
    loaded(id, note) { cache[id] = note; (waiting[id] || []).forEach(fn => fn(note)); delete waiting[id]; },
    get(id) {
      if (cache[id]) return Promise.resolve(cache[id]);
      return new Promise((res, rej) => {
        (waiting[id] ||= []).push(res);
        if (waiting[id].length > 1) return;
        const s = document.createElement("script");
        s.src = `data/notes/${id}.js`;
        s.onerror = () => { delete waiting[id]; rej(new Error("missing")); };
        document.head.appendChild(s);
      });
    },
  };
})();
const NoteReader = (() => {
  let el, scrim, opener;
  function build() {
    el = document.createElement("aside");
    el.className = "convo"; el.setAttribute("role", "dialog"); el.setAttribute("aria-label", "Private note"); el.hidden = true;
    el.innerHTML = `<header class="convo-head"><div><p class="eyebrow" id="nt-eyebrow"></p><h3 id="nt-title"></h3></div>
      <button class="btn convo-x" id="nt-close" aria-label="Close note">Close ✕</button></header>
      <div class="convo-nav"><button class="btn" id="nt-prev">← Previous mention</button><button class="btn" id="nt-next">Next mention →</button><span class="cv-count" id="nt-count" style="margin:0 0 0 auto"></span></div>
      <div class="convo-body" id="nt-body" tabindex="-1"></div>`;
    document.body.appendChild(el);
    scrim = document.createElement("div"); scrim.className = "convo-scrim"; scrim.hidden = true;
    document.body.appendChild(scrim);
    scrim.onclick = close;
    el.querySelector("#nt-close").onclick = close;
    el.querySelector("#nt-prev").onclick = () => jump(-1);
    el.querySelector("#nt-next").onclick = () => jump(1);
    addEventListener("keydown", ev => { if (ev.key === "Escape" && !el.hidden) close(); });
  }
  let marks = [], at = 0;
  function jump(d) {
    if (!marks.length) return;
    at = (at + d + marks.length) % marks.length;
    marks.forEach((m, i) => m.classList.toggle("on", i === at));
    marks[at].scrollIntoView({ block: "center" });
    el.querySelector("#nt-count").textContent = `mention ${at + 1} of ${marks.length}`;
  }
  function close() { el.hidden = true; scrim.hidden = true; document.body.style.overflow = ""; opener?.focus?.(); }
  async function open(id, hl, from) {
    if (!el) build();
    opener = from;
    el.hidden = false; scrim.hidden = false; document.body.style.overflow = "hidden"; hideTip();
    const body = el.querySelector("#nt-body");
    body.innerHTML = `<p class="hint" style="padding:16px">Loading the note…</p>`;
    let n;
    try { n = await NOTES.get(id); } catch (e) { body.innerHTML = `<p class="hint" style="padding:16px">This note isn't available.</p>`; return; }
    el.querySelector("#nt-eyebrow").textContent = `Private memory note · ${n.agent}`;
    el.querySelector("#nt-title").textContent = n.time;
    const aliases = hl ? [hl, ...(hl.startsWith("Claude ") ? [hl.slice(7)] : [])] : [];
    let html = esc(n.content);
    if (aliases.length) {
      const re = new RegExp("(?:" + aliases.sort((a, b) => b.length - a.length).map(a => esc(a).replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|") + ")(?![.\\d]*\\d)", "g");
      html = html.replace(re, m => `<mark class="nt-mark">${m}</mark>`);
    }
    body.innerHTML = `<p class="cv-count">${n.agent}'s own memory file. Other agents never see it.${n.length > n.content.length ? ` Showing the first ${n.content.length.toLocaleString()} of ${n.length.toLocaleString()} characters.` : ""}</p><div class="nt-text">${html}</div>`;
    marks = [...body.querySelectorAll(".nt-mark")]; at = -1;
    el.querySelector("#nt-prev").disabled = el.querySelector("#nt-next").disabled = !marks.length;
    el.querySelector("#nt-count").textContent = marks.length ? `${marks.length} mentions of ${hl}` : "";
    if (marks.length) jump(1); else body.scrollTop = 0;
    el.querySelector("#nt-close").focus({ preventScroll: true });
  }
  document.addEventListener("click", ev => {
    const t = ev.target.closest("[data-note]");
    if (t && !ev.target.closest(".convo")) { ev.preventDefault(); ev.stopPropagation(); open(t.getAttribute("data-note"), t.getAttribute("data-hl"), t); }
  }, true);
  return { open };
})();

// Staff appointed these agents to lead. Leading is their job, so they never headline a finding or top a leaderboard.
const APPOINTED = n => /fine-tuned leader/i.test(String(n || ""));

// When a click fills a detail panel, bring it into view: side panels scroll on their own, so new content can land below the fold.
(() => {
  let armed = false;
  addEventListener("click", () => { armed = true; setTimeout(() => { armed = false; }, 400); }, true);
  addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { armed = true; setTimeout(() => { armed = false; }, 400); } }, true);
  const watch = () => document.querySelectorAll("#detail, #pairdetail, #specimen").forEach(el => {
    new MutationObserver(() => {
      if (!armed || el.querySelector(":scope > .hint:only-child")) return;
      const side = el.closest(".side"), inner = side && side.scrollHeight > side.clientHeight;
      if (inner) side.scrollTo({ top: side.scrollTop + el.getBoundingClientRect().top - side.getBoundingClientRect().top - 8, behavior: "smooth" });
      // then make sure the panel itself is on screen, clear of the sticky time-frame bar
      const box = inner ? side : el, r = box.getBoundingClientRect();
      if (r.top > innerHeight - 120 || r.bottom < 120) { box.style.scrollMarginTop = "110px"; box.scrollIntoView({ behavior: "smooth", block: "start" }); }
    }).observe(el, { childList: true });
  });
  document.readyState === "loading" ? addEventListener("DOMContentLoaded", watch) : watch();
})();
