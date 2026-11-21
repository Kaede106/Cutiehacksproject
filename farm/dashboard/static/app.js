"use strict";
// CutieFarm control room: polls /api/state and updates the page in place. Values from the data
// files are only ever put on the page as text (textContent), never as HTML.

const POLL_MS = 2500;
const SVG_NS = "http://www.w3.org/2000/svg";
const CHIP_TEXT = { ripe: "Ready", ripening: "Ripening", unripe: "Unripe" };
const TONE = { ripe: "var(--cf-ripe)", ripening: "var(--cf-ripening)", unripe: "var(--cf-unripe)" };
const KIND_TEXT = { scan: "Scan", ready: "Ready", picked: "Picked", watered: "Watered", sensors: "Sensors" };
const FLAG_TEXT = { demo: "Demo", simulated: "Simulated" };
const $ = (id) => document.getElementById(id);

function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value == null || value === false) continue;
    if (key === "class") el.className = value;
    else if (key === "style") el.style.cssText = value;
    else el.setAttribute(key, value);
  }
  for (const kid of kids.flat()) {
    if (kid == null || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

function svg(tag, attrs) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (key === "style") el.style.cssText = value; // the CSP blocks style attributes, not the CSSOM
    else el.setAttribute(key, value);
  }
  return el;
}

function ago(seconds) {
  if (seconds < 10) return "just now";
  if (seconds < 90) return `${Math.round(seconds)} s ago`;
  if (seconds < 5400) return `${Math.round(seconds / 60)} min ago`;
  if (seconds < 172800) return `${Math.round(seconds / 3600)} h ago`;
  return `${Math.round(seconds / 86400)} days ago`;
}

function signed(n) {
  return n > 0 ? `+${n}` : n < 0 ? `−${-n}` : "no change";
}

function empty(title, detail) {
  return h("div", { class: "empty" }, h("strong", null, title), detail && h("span", null, detail));
}

// --- camera frame -------------------------------------------------------------------

let cameraKey = null;

function bracket(x, y, w, hh) {
  const l = Math.max(4, Math.min(w, hh) * 0.28);
  return `M${x} ${y + l}V${y}H${x + l}M${x + w - l} ${y}H${x + w}V${y + l}` +
         `M${x + w} ${y + hh - l}V${y + hh}H${x + w - l}M${x + l} ${y + hh}H${x}V${y + hh - l}`;
}

function drawBoxes(stage, fruits, width, height) {
  stage.style.setProperty("--ratio", String(width / height));
  stage.querySelectorAll(".boxes, .chip").forEach((el) => el.remove());
  const layer = svg("svg", { class: "boxes", viewBox: `0 0 ${width} ${height}`, preserveAspectRatio: "none", "aria-hidden": "true" });
  const chips = [];
  for (const fruit of fruits) {
    if (!fruit.bbox) continue;
    const [x, y, w, hh] = fruit.bbox;
    const d = bracket(x, y, w, hh);
    layer.append(svg("path", { class: "halo", d }), svg("path", { class: "mark", d, style: `stroke:${TONE[fruit.label]}` }));
    const inside = y / height < 0.1;
    chips.push(h("span", {
      class: inside ? "chip inside" : "chip",
      style: `left:${(x / width) * 100}%;top:${(y / height) * 100}%;--tone:${TONE[fruit.label]}`,
    }, CHIP_TEXT[fruit.label]));
  }
  stage.append(layer, ...chips);
}

function renderCamera(state) {
  const frame = $("frame");
  const scan = state.scan;
  const key = JSON.stringify([state.data_folder, scan && [scan.id, scan.image, scan.fruits, scan.frame]]);
  if (key === cameraKey) return;
  cameraKey = key;
  frame.replaceChildren();
  if (!state.data_folder) {
    frame.append(empty("No data folder yet", "Start the hub with python -m farm, or set CUTIEFARM_DATA."));
    return;
  }
  if (!scan) {
    frame.append(empty("No scan yet", "The camera program saves a scan when it sees oranges."));
    return;
  }
  const stage = h("div", { class: "stage" });
  stage.style.setProperty("--ratio", String(scan.frame.w / scan.frame.h));
  frame.append(stage);
  const placeholder = (note) => {
    stage.querySelector("img")?.remove();
    drawBoxes(stage, scan.fruits, scan.frame.w, scan.frame.h);
    stage.append(h("p", { class: "stage-note" }, note));
  };
  if (!scan.image) {
    placeholder("No photo was saved with this scan");
    return;
  }
  const img = h("img", { alt: "Latest camera frame with the oranges marked" });
  img.addEventListener("load", () => drawBoxes(stage, scan.fruits, img.naturalWidth, img.naturalHeight));
  img.addEventListener("error", () => placeholder("The photo could not be loaded"));
  img.src = scan.image;
  stage.prepend(img);
}

function renderCameraMeta(state) {
  const scan = state.scan;
  const meta = $("camera-meta");
  if (!scan) {
    meta.replaceChildren();
    return;
  }
  const item = (cls, name, value) => h("div", { class: cls }, h("dt", null, name), h("dd", null, value));
  meta.replaceChildren(
    item(scan.age_s > 3600 ? "when old" : "when", "Scanned", `${scan.clock}, ${ago(scan.age_s)}`),
    item("", "Model", scan.model || "not recorded"),
    item("", "Source", scan.source || "not recorded"),
  );
}

// --- ready to pick ----------------------------------------------------------------------

function changeNode(n) {
  return h("span", { class: n > 0 ? "up" : n < 0 ? "down" : "" }, signed(n));
}

function renderReady(state) {
  const scan = state.scan;
  const root = $("ready");
  if (!scan) {
    root.replaceChildren(h("p", { class: "delta quiet" }, "No scan yet", h("small", null, "Counts appear after the first scan")));
    return;
  }
  const c = scan.counts;
  const ch = scan.change;
  const delta = ch
    ? h("p", { class: "delta" }, changeNode(ch.ripe), h("small", null, "since the previous scan"))
    : h("p", { class: "delta" }, "First scan", h("small", null, "nothing to compare yet"));
  const other = (label) => h("div", { class: "other", style: `--tone:${TONE[label]}` },
    h("span", { class: "num" }, c[label]),
    h("div", null,
      h("p", { class: "name" }, h("span", { class: "swatch" }), label === "ripening" ? "Ripening" : "Unripe"),
      ch && h("p", { class: "chg" }, changeNode(ch[label]))));
  root.replaceChildren(
    h("div", { class: "ready-main" }, h("div", { class: "big" }, c.ripe), delta),
    h("div", { class: "others" }, other("ripening"), other("unripe")),
  );
}

// --- watering -----------------------------------------------------------------------------

function sparkline(metric, window) {
  const wrap = h("div", { class: "spark-wrap" });
  const pts = metric.series;
  if (!pts.length) {
    return h("p", { class: "spark-none" }, metric.value == null ? "No readings yet" : "No readings in the last 24 h");
  }
  const [t0, t1] = window;
  const values = pts.map((p) => p[1]);
  let lo = Math.min(...values);
  let hi = Math.max(...values);
  const th = metric.threshold;
  if (th != null && th >= lo - 12 && th <= hi + 12) {
    lo = Math.min(lo, th);
    hi = Math.max(hi, th);
  }
  if (hi - lo < 2) {
    lo -= 1;
    hi += 1;
  }
  const W = 300;
  const H = 100;
  const x = (t) => ((t - t0) / (t1 - t0)) * W;
  const y = (v) => H - 6 - ((v - lo) / (hi - lo)) * (H - 12);
  const d = pts.map(([t, v], i) => `${i ? "L" : "M"}${x(t).toFixed(1)} ${y(v).toFixed(1)}`).join("");
  const root = svg("svg", { class: "spark", viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "none", "aria-hidden": "true" });
  root.append(svg("line", { class: "base", x1: 0, x2: W, y1: H, y2: H }));
  const showTh = th != null && th >= lo && th <= hi;
  if (showTh) root.append(svg("line", { class: "thresh", x1: 0, x2: W, y1: y(th), y2: y(th) }));
  root.append(svg("path", { class: "line", d }));
  const last = pts[pts.length - 1];
  wrap.append(root, h("span", { class: "dot", style: `left:${(x(last[0]) / W) * 100}%;top:${(y(last[1]) / H) * 100}%` }));
  if (showTh) wrap.append(h("span", { class: "thresh-label", style: `top:${(y(th) / H) * 100}%` }, `Water below ${th}${metric.unit}`));
  return wrap;
}

function renderWater(state) {
  const root = $("water");
  const advice = state.watering;
  const sensors = state.sensors;
  const adviceNode = advice
    ? h("div", { class: "advice" },
        h("div", { class: "headline" },
          h("span", { class: `title ${advice.tone}` }, advice.title),
          advice.next_label && h("span", { class: "next" }, h("span", null, "Next "), advice.next_label),
          advice.simulated && h("span", { class: "tag" }, "Simulated sensors")),
        h("p", { class: "reason" }, advice.reason))
    : h("div", { class: "advice" }, h("span", { class: "title unknown" }, "No advice yet"),
        h("p", { class: "reason" }, state.data_folder ? "The advice could not be worked out." : "There is no data folder yet."));
  const rows = sensors.metrics.map((m) => {
    const known = m.value != null;
    const info = h("div", null,
      h("p", { class: "label" }, m.label),
      h("p", { class: "value" }, known ? m.value : "—", known && h("small", null, m.unit)),
      m.stale
        ? h("p", { class: "stale" }, `Last reading ${ago(m.age_s)}`)
        : m.low != null && h("p", { class: "range" }, `Last 24 h: ${m.low}–${m.high} ${m.unit}`));
    return h("div", { class: "metric" }, info, sparkline(m, sensors.window));
  });
  root.replaceChildren(adviceNode, h("div", { class: "metrics" }, rows));
}

// --- activity feed ---------------------------------------------------------------------------

const seen = new Set();
let firstFeed = true;

function fitFeed() {
  const list = $("feed");
  const items = [...list.children];
  items.forEach((li) => (li.hidden = false));
  const limit = list.getBoundingClientRect().bottom;
  items.forEach((li) => {
    if (li.getBoundingClientRect().bottom > limit + 1) li.hidden = true;
  });
}

function renderFeed(state) {
  const list = $("feed");
  if (!state.feed.length) {
    list.replaceChildren(h("li", { class: "none" }, "Nothing has happened yet."));
    return;
  }
  list.replaceChildren(...state.feed.map((e) => {
    const key = `${e.kind}|${e.t}|${e.text}`;
    const fresh = !firstFeed && !seen.has(key);
    seen.add(key);
    return h("li", { class: fresh ? "fresh" : "" },
      h("span", { class: "t" }, e.clock),
      h("span", { class: `k k-${e.kind}` }, KIND_TEXT[e.kind] || e.kind),
      h("span", null, e.text),
      e.flag ? h("span", { class: "tag" }, FLAG_TEXT[e.flag] || e.flag) : h("span"));
  }));
  firstFeed = false;
  fitFeed();
}

// --- header, loop ------------------------------------------------------------------------------

function renderHeader(state) {
  $("notices").replaceChildren(...state.notices.map((n) => h("span", { class: "notice" }, n.text)));
  const updated = $("updated");
  updated.className = "updated";
  updated.textContent = `Updated ${state.clock}`;
}

function render(state) {
  renderHeader(state);
  renderCamera(state);
  renderCameraMeta(state);
  renderReady(state);
  renderWater(state);
  renderFeed(state);
}

async function tick() {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 4000);
  try {
    const response = await fetch("/api/state", { cache: "no-store", signal: controller.signal });
    if (!response.ok) throw new Error(String(response.status));
    render(await response.json());
  } catch (error) {
    const updated = $("updated");
    updated.className = "updated lost";
    updated.textContent = "Connection lost, retrying";
  } finally {
    clearTimeout(timer);
    setTimeout(tick, POLL_MS);
  }
}

window.addEventListener("resize", fitFeed);
tick();
