"""HTML viz template — single-file interactive graph (vis-network).

Output of `serialize.write_graph_html`. Loads `vis-network` from
jsdelivr CDN, inlines the graph data, and ships with dark theme, search,
filter sidebar, click-to-expand, animated path mode, mini-map, and
keyboard shortcuts (`/` search · `f` filters · `esc` clear · `p` path
mode).

Inspired by Graphify (https://graphify.net/) — noc-native equivalent
that derives the graph from AST + authored prose only (no LLM-inferred
edges in v1).
"""

from __future__ import annotations

HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>noc-graph — knowledge graph</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<script src="https://cdn.jsdelivr.net/npm/vis-network@9.1.9/standalone/umd/vis-network.min.js"></script>
<style>
  :root {
    --bg: #0b1020;
    --bg-elev-1: #131a33;
    --bg-elev-2: #1c2547;
    --fg: #e6ecff;
    --fg-dim: #95a3c8;
    --accent: #7c9eff;
    --accent-hot: #ff5ea8;
    --halo: rgba(124, 158, 255, .35);
    --border: #2a3360;
    --shadow: 0 8px 28px rgba(0,0,0,.55);
    --radius: 10px;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; height: 100%; background: var(--bg); color: var(--fg);
               font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
  body { display: grid; grid-template-rows: 56px 1fr 28px; grid-template-columns: 280px 1fr 320px; }
  header {
    grid-row: 1; grid-column: 1 / span 3;
    display: flex; align-items: center; padding: 0 16px; gap: 14px;
    background: linear-gradient(90deg, var(--bg-elev-1), var(--bg-elev-2));
    border-bottom: 1px solid var(--border);
  }
  header h1 { margin: 0; font-size: 14px; letter-spacing: .04em; color: var(--fg); }
  header h1 .accent { color: var(--accent); }
  #search-wrap { flex: 1; max-width: 600px; position: relative; }
  #search {
    width: 100%; padding: 8px 36px 8px 12px;
    background: var(--bg-elev-2); color: var(--fg);
    border: 1px solid var(--border); border-radius: var(--radius);
    font-size: 13px; outline: none;
    transition: border-color .15s, box-shadow .15s;
  }
  #search:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--halo); }
  #search-hint { position: absolute; right: 10px; top: 50%; transform: translateY(-50%);
                 color: var(--fg-dim); font-size: 11px; pointer-events: none; }
  #results { position: absolute; top: 100%; left: 0; right: 0; max-height: 60vh; overflow: auto;
             background: var(--bg-elev-2); border: 1px solid var(--border);
             border-radius: var(--radius); margin-top: 6px; box-shadow: var(--shadow); display: none; z-index: 5; }
  #results.show { display: block; }
  .result-row { padding: 8px 12px; cursor: pointer; border-bottom: 1px solid var(--border); }
  .result-row:hover { background: rgba(124,158,255,.08); }
  .result-row .label { font-size: 13px; color: var(--fg); }
  .result-row .meta { font-size: 11px; color: var(--fg-dim); }
  .kind-chip { display: inline-block; padding: 1px 6px; border-radius: 4px;
               font-size: 10px; margin-right: 6px; background: var(--bg-elev-1); }
  #status-pill { margin-left: auto; font-size: 11px; color: var(--fg-dim); }

  aside.left {
    grid-row: 2; grid-column: 1;
    background: var(--bg-elev-1); border-right: 1px solid var(--border);
    overflow: auto; padding: 14px;
  }
  aside.right {
    grid-row: 2; grid-column: 3;
    background: var(--bg-elev-1); border-left: 1px solid var(--border);
    overflow: auto; padding: 14px; transition: transform .2s ease;
  }
  aside.right.collapsed { transform: translateX(100%); }
  .section-title { font-size: 11px; text-transform: uppercase; letter-spacing: .08em;
                   color: var(--fg-dim); margin: 10px 0 6px; }
  .chip-row { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 12px; }
  .chip {
    display: inline-flex; align-items: center;
    padding: 3px 10px; border-radius: 999px;
    background: var(--bg-elev-2); border: 1px solid var(--border);
    font-size: 11px; cursor: pointer; user-select: none;
    transition: background .15s, border-color .15s, transform .1s;
  }
  .chip:hover { background: rgba(124,158,255,.1); border-color: var(--accent); }
  .chip.on { background: var(--accent); color: #0b1020; border-color: var(--accent); }
  .chip.product.on { background: #67d391; color: #0b1020; border-color: #67d391; }
  .stat-row { display: flex; justify-content: space-between; font-size: 12px;
              color: var(--fg-dim); padding: 3px 0; }
  .stat-row .val { color: var(--fg); }

  main {
    grid-row: 2; grid-column: 2;
    position: relative; overflow: hidden;
  }
  #net { position: absolute; inset: 0; }
  #minimap {
    position: absolute; bottom: 12px; right: 12px; width: 180px; height: 120px;
    background: rgba(11,16,32,.85); border: 1px solid var(--border); border-radius: 8px;
    pointer-events: none; opacity: .8; display: none;
  }
  #toast {
    position: absolute; top: 16px; left: 50%; transform: translateX(-50%);
    background: var(--bg-elev-2); color: var(--fg); padding: 8px 14px;
    border: 1px solid var(--accent); border-radius: var(--radius); font-size: 12px;
    box-shadow: var(--shadow); opacity: 0; transition: opacity .25s; pointer-events: none;
  }
  #toast.show { opacity: 1; }

  /* Right side panel */
  .panel-header { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
  .panel-header .close { margin-left: auto; cursor: pointer; color: var(--fg-dim);
                         font-size: 16px; padding: 2px 8px; border-radius: 4px; }
  .panel-header .close:hover { background: var(--bg-elev-2); color: var(--fg); }
  .node-label { font-size: 14px; color: var(--fg); }
  .node-path { font-size: 11px; color: var(--fg-dim); word-break: break-all;
               background: var(--bg-elev-2); padding: 4px 8px; border-radius: 6px; }
  .neighbor-group { margin-top: 12px; }
  .neighbor-group h4 { font-size: 11px; text-transform: uppercase;
                       letter-spacing: .08em; color: var(--accent); margin: 0 0 6px; }
  .neighbor-row { padding: 4px 6px; font-size: 12px; cursor: pointer;
                  border-radius: 4px; color: var(--fg); }
  .neighbor-row:hover { background: var(--bg-elev-2); }
  .neighbor-row .kind { font-size: 10px; color: var(--fg-dim); margin-right: 6px; }

  footer {
    grid-row: 3; grid-column: 1 / span 3;
    background: var(--bg-elev-1); border-top: 1px solid var(--border);
    padding: 0 14px; display: flex; align-items: center; gap: 14px;
    font-size: 11px; color: var(--fg-dim);
  }
  footer a { color: var(--accent); text-decoration: none; }
  footer a:hover { text-decoration: underline; }
  .pill { padding: 2px 8px; border-radius: 4px; background: var(--bg-elev-2); }

  /* Pulse animation for selected node halo */
  @keyframes pulse {
    0% { box-shadow: 0 0 0 0 var(--halo); }
    100% { box-shadow: 0 0 0 24px rgba(124,158,255,0); }
  }

  /* Confidence slider */
  input[type=range] { width: 100%; accent-color: var(--accent); }

  /* Empty-state */
  .empty { color: var(--fg-dim); font-size: 12px; padding: 8px; text-align: center; }
</style>
</head>
<body>

<header>
  <h1>noc-<span class="accent">graph</span></h1>
  <div id="search-wrap">
    <input id="search" placeholder="search nodes — label, path, or symbol…" autocomplete="off" />
    <span id="search-hint">press / to focus · esc to clear</span>
    <div id="results"></div>
  </div>
  <div id="status-pill"></div>
</header>

<aside class="left">
  <div class="section-title">Node kinds</div>
  <div class="chip-row" id="kind-chips"></div>

  <div class="section-title">Products / anchors</div>
  <div class="chip-row" id="product-chips"></div>

  <div class="section-title">Confidence ≥ <span id="conf-val">0.0</span></div>
  <input type="range" id="conf-slider" min="0" max="100" value="0" />

  <div class="section-title">Stats</div>
  <div class="stat-row"><span>Nodes shown</span><span class="val" id="stat-nodes">0</span></div>
  <div class="stat-row"><span>Edges shown</span><span class="val" id="stat-edges">0</span></div>
  <div class="stat-row"><span>Clusters</span><span class="val" id="stat-clusters">0</span></div>

  <div class="section-title">Path mode</div>
  <div style="font-size:11px;color:var(--fg-dim);margin-bottom:6px;">
    Press <b>p</b>, click source, then target.
  </div>
  <button id="path-btn" class="chip">enter path mode</button>
  <button id="clear-btn" class="chip" style="margin-top:6px;">reset view</button>
</aside>

<main>
  <div id="net"></div>
  <canvas id="minimap"></canvas>
  <div id="toast"></div>
</main>

<aside class="right collapsed" id="panel">
  <div class="panel-header">
    <span class="kind-chip" id="panel-kind">·</span>
    <span class="node-label" id="panel-label">·</span>
    <span class="close" id="panel-close">×</span>
  </div>
  <div class="node-path" id="panel-path">·</div>
  <div id="panel-body"></div>
</aside>

<footer>
  <span class="pill" id="footer-meta">{{BUILD_META}}</span>
  <span>vis-network · force-directed · Louvain clustering</span>
  <span style="margin-left:auto;">
    inspired by <a href="https://graphify.net/" target="_blank" rel="noopener">graphify.net</a> ·
    noc-native, AST + authored-prose only
  </span>
</footer>

<script>
const GRAPH_DATA = {{GRAPH_JSON_INLINE}};

/* ── palette ───────────────────────────────────────────────────────────── */
const KIND_COLORS = {
  module:                "#7c9eff",
  class:                 "#a78bfa",
  function:              "#60c1ff",
  method:                "#67e0ff",
  route:                 "#4ad6a8",
  mcp_tool:              "#ffd166",
  component:             "#ef6f6c",
  hook:                  "#f29e4c",
  migration:             "#b08bff",
  kb_pattern:            "#c66cff",
  kb_guide:              "#d896ff",
  kb_integration:        "#9d8aff",
  kb_backend_spec:       "#8aa9ff",
  kb_frontend_spec:      "#8ad4ff",
  memory:                "#5ad7c4",
  master_prompt_section: "#aec6ff",
  finding:               "#ff97c6",
  project:               "#ffa86b",
  proposal:              "#ffc987",
  product:               "#67d391",
  seed:                  "#ffd166",
};
const KIND_SHAPES = {
  product: "diamond", seed: "diamond",
  kb_pattern: "box", kb_guide: "box", kb_integration: "box",
  kb_backend_spec: "box", kb_frontend_spec: "box",
  memory: "box", master_prompt_section: "box",
  finding: "box", project: "box", proposal: "box",
};
function colorOf(k){ return KIND_COLORS[k] || "#95a3c8"; }
function shapeOf(k){ return KIND_SHAPES[k] || "dot"; }

/* ── state ─────────────────────────────────────────────────────────────── */
const state = {
  kindEnabled: new Set(Object.keys(KIND_COLORS)),
  productEnabled: null,            // null = all
  minConfidence: 0.0,
  selectedNode: null,
  pathMode: false,
  pathPick: [],
};

/* ── filters UI ───────────────────────────────────────────────────────── */
const kindChips = document.getElementById("kind-chips");
const presentKinds = new Set(GRAPH_DATA.nodes.map(n => n.kind));
[...presentKinds].sort().forEach(k => {
  const el = document.createElement("span");
  el.className = "chip on";
  el.style.borderColor = colorOf(k);
  el.style.color = colorOf(k);
  el.dataset.kind = k;
  el.textContent = k;
  el.onclick = () => {
    el.classList.toggle("on");
    if (state.kindEnabled.has(k)) state.kindEnabled.delete(k);
    else state.kindEnabled.add(k);
    applyFilters();
  };
  kindChips.appendChild(el);
});

const productChips = document.getElementById("product-chips");
const presentProducts = new Set(
  GRAPH_DATA.nodes.filter(n => n.product).map(n => n.product)
);
const allChip = document.createElement("span");
allChip.className = "chip product on";
allChip.textContent = "all";
allChip.onclick = () => {
  state.productEnabled = null;
  productChips.querySelectorAll(".chip").forEach(c =>
    c.classList.toggle("on", c === allChip)
  );
  applyFilters();
};
productChips.appendChild(allChip);
[...presentProducts].sort().forEach(p => {
  const el = document.createElement("span");
  el.className = "chip product";
  el.dataset.product = p;
  el.textContent = p;
  el.onclick = () => {
    state.productEnabled = new Set([p]);
    productChips.querySelectorAll(".chip").forEach(c =>
      c.classList.toggle("on", c === el)
    );
    applyFilters();
  };
  productChips.appendChild(el);
});

const confSlider = document.getElementById("conf-slider");
const confVal = document.getElementById("conf-val");
confSlider.oninput = () => {
  state.minConfidence = confSlider.value / 100;
  confVal.textContent = state.minConfidence.toFixed(2);
  applyFilters();
};

/* ── network setup ─────────────────────────────────────────────────────── */
const allNodes = new vis.DataSet(GRAPH_DATA.nodes.map(n => ({
  id: n.id,
  label: n.label,
  title: nodeTooltip(n),
  color: { background: colorOf(n.kind), border: confidenceBorder(n) },
  shape: shapeOf(n.kind),
  borderWidth: n.confidence >= 1.0 ? 2 : 1,
  borderWidthSelected: 4,
  group: n.cluster != null ? String(n.cluster) : "default",
  font: { color: "#e6ecff", size: 13, face: "system-ui" },
  size: 14 + Math.min(20, (n.meta && n.meta.degree) || 0),
  _kind: n.kind,
  _product: n.product,
  _confidence: n.confidence,
  _path: n.path,
  _line: n.line,
  _id: n.id,
})));
const allEdges = new vis.DataSet(GRAPH_DATA.edges.map((e, idx) => ({
  id: `e${idx}`,
  from: e.source,
  to: e.target,
  arrows: "to",
  color: { color: edgeColor(e), opacity: 0.4 + 0.6 * (e.confidence || 1) },
  width: 0.6 + (e.weight || 1) * 0.6,
  smooth: { type: "dynamic" },
  _kind: e.kind,
  _confidence: e.confidence,
})));

function confidenceBorder(n){
  return n.confidence >= 1.0 ? "#ffffff44" : "#ff5ea8";
}
function edgeColor(e){
  switch(e.kind){
    case "calls":         return "#7c9eff";
    case "imports":       return "#5ad7c4";
    case "consumes_seed": return "#ffd166";
    case "kb_pointer":    return "#c66cff";
    case "memory_link":   return "#5ad7c4";
    case "documents":     return "#ff97c6";
    case "defined_in":    return "#3d4870";
    case "contains":      return "#3d4870";
    case "inherits":      return "#a78bfa";
    case "mounts":        return "#67e0ff";
    default:              return "#3d4870";
  }
}
function nodeTooltip(n){
  const lines = [
    `<b>${escapeHtml(n.label)}</b>`,
    `<span style="color:#95a3c8">${escapeHtml(n.kind)}</span>`,
  ];
  if (n.path) lines.push(`<code>${escapeHtml(n.path)}</code>`);
  if (n.product) lines.push(`product · ${escapeHtml(n.product)}`);
  if (n.meta && n.meta.docstring) lines.push(`<i>${escapeHtml(n.meta.docstring)}</i>`);
  if (n.meta && n.meta.first_line) lines.push(`<i>${escapeHtml(n.meta.first_line)}</i>`);
  if (n.meta && n.meta.description) lines.push(`<i>${escapeHtml(n.meta.description)}</i>`);
  return lines.join("<br>");
}
function escapeHtml(s){ return String(s).replace(/[&<>"]/g, c =>
  ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"})[c]); }

/* Compute degree -> size */
const degree = {};
GRAPH_DATA.edges.forEach(e => {
  degree[e.source] = (degree[e.source] || 0) + 1;
  degree[e.target] = (degree[e.target] || 0) + 1;
});
allNodes.forEach(n => {
  const d = degree[n.id] || 0;
  allNodes.update({ id: n.id, size: 12 + Math.min(28, Math.sqrt(d) * 4) });
});

const network = new vis.Network(
  document.getElementById("net"),
  { nodes: allNodes, edges: allEdges },
  {
    physics: {
      solver: "barnesHut",
      barnesHut: { gravitationalConstant: -8000, springLength: 110, springConstant: 0.04, damping: 0.5 },
      stabilization: { iterations: 200, updateInterval: 25, fit: true },
    },
    interaction: { hover: true, tooltipDelay: 120, multiselect: false, navigationButtons: true,
                   keyboard: { enabled: true, speed: { x:8, y:8, zoom:0.02 } } },
    nodes: { scaling: { min: 10, max: 50 } },
    edges: { selectionWidth: 2.5 },
  }
);

document.getElementById("status-pill").textContent =
  `${GRAPH_DATA.nodes.length} nodes · ${GRAPH_DATA.edges.length} edges`;
document.getElementById("stat-nodes").textContent = GRAPH_DATA.nodes.length;
document.getElementById("stat-edges").textContent = GRAPH_DATA.edges.length;
const uniqueClusters = new Set(GRAPH_DATA.nodes.map(n => n.cluster).filter(c => c != null));
document.getElementById("stat-clusters").textContent = uniqueClusters.size;

/* ── filtering ─────────────────────────────────────────────────────────── */
function applyFilters(){
  const visibleIds = new Set();
  GRAPH_DATA.nodes.forEach(n => {
    if (!state.kindEnabled.has(n.kind)) return;
    if (state.productEnabled && !state.productEnabled.has(n.product)) {
      // also keep KB / memory / cross-cutting nodes visible
      if (n.product) return;
    }
    if ((n.confidence || 1) < state.minConfidence) return;
    visibleIds.add(n.id);
  });
  allNodes.forEach(n => {
    allNodes.update({ id: n.id, hidden: !visibleIds.has(n.id) });
  });
  let edgeCount = 0;
  allEdges.forEach(e => {
    const visible = visibleIds.has(e.from) && visibleIds.has(e.to);
    allEdges.update({ id: e.id, hidden: !visible });
    if (visible) edgeCount++;
  });
  document.getElementById("stat-nodes").textContent = visibleIds.size;
  document.getElementById("stat-edges").textContent = edgeCount;
}

/* ── interactions ─────────────────────────────────────────────────────── */
network.on("selectNode", (params) => {
  const id = params.nodes[0];
  state.selectedNode = id;
  highlightNeighborhood(id);
  if (state.pathMode) {
    state.pathPick.push(id);
    showToast(state.pathPick.length === 1 ? "Now pick TARGET node" : "Computing path…");
    if (state.pathPick.length === 2) {
      animatePath(state.pathPick[0], state.pathPick[1]);
      state.pathMode = false;
      state.pathPick = [];
      document.getElementById("path-btn").classList.remove("on");
    }
  }
});
network.on("deselectNode", () => {
  clearHighlight();
  state.selectedNode = null;
});
network.on("doubleClick", (params) => {
  if (!params.nodes.length) return;
  openPanel(params.nodes[0]);
});
network.on("hoverNode", (params) => {
  // visualised via vis-network's title tooltip; could add side-effects here later
});

function highlightNeighborhood(id){
  const neighborIds = new Set([id]);
  GRAPH_DATA.edges.forEach(e => {
    if (e.source === id) neighborIds.add(e.target);
    if (e.target === id) neighborIds.add(e.source);
  });
  allNodes.forEach(n => {
    const inHood = neighborIds.has(n.id);
    allNodes.update({
      id: n.id,
      color: {
        background: inHood ? colorOf(n._kind) : "#1c2547",
        border: inHood ? "#ffffff" : "#2a3360",
      },
      font: { color: inHood ? "#e6ecff" : "#404a70" },
    });
  });
  allEdges.forEach(e => {
    const involved = e.from === id || e.to === id;
    allEdges.update({
      id: e.id,
      color: { color: involved ? "#7c9eff" : "#283057", opacity: involved ? 1.0 : 0.15 },
      width: involved ? 2.4 : 0.4,
    });
  });
}
function clearHighlight(){
  allNodes.forEach(n => {
    allNodes.update({
      id: n.id,
      color: { background: colorOf(n._kind), border: confidenceBorder({confidence: n._confidence}) },
      font: { color: "#e6ecff" },
    });
  });
  allEdges.forEach(e => {
    allEdges.update({
      id: e.id,
      color: { color: edgeColor({kind: e._kind}), opacity: 0.4 + 0.6 * (e._confidence || 1) },
      width: 0.6 + 0.6,
    });
  });
}

function animatePath(src, dst){
  const path = bfsPath(src, dst);
  if (!path) { showToast("no path within 8 hops"); return; }
  showToast(`path: ${path.length - 1} hops`);
  clearHighlight();
  const ids = new Set(path);
  allNodes.forEach(n => {
    const on = ids.has(n.id);
    allNodes.update({
      id: n.id,
      color: { background: on ? "#ff5ea8" : "#1c2547", border: on ? "#ffffff" : "#2a3360" },
      font: { color: on ? "#0b1020" : "#404a70" },
    });
  });
  // sequence: emphasize each hop briefly
  let i = 0;
  const tick = () => {
    if (i >= path.length - 1) return;
    const eid = findEdgeId(path[i], path[i+1]);
    if (eid) allEdges.update({ id: eid, color: { color: "#ff5ea8", opacity: 1 }, width: 4 });
    i++;
    setTimeout(tick, 180);
  };
  tick();
  network.fit({ nodes: path, animation: { duration: 600, easingFunction: "easeInOutQuad" } });
}
function bfsPath(src, dst){
  const adj = {};
  GRAPH_DATA.edges.forEach(e => {
    (adj[e.source] ||= []).push(e.target);
    (adj[e.target] ||= []).push(e.source);
  });
  const parent = { [src]: null };
  const q = [src];
  while (q.length) {
    const cur = q.shift();
    if (cur === dst) break;
    for (const next of (adj[cur] || [])) {
      if (next in parent) continue;
      parent[next] = cur;
      q.push(next);
    }
  }
  if (!(dst in parent)) return null;
  const out = [];
  let cur = dst;
  while (cur != null) { out.push(cur); cur = parent[cur]; }
  return out.reverse();
}
function findEdgeId(a, b){
  let found = null;
  allEdges.forEach(e => {
    if ((e.from === a && e.to === b) || (e.from === b && e.to === a)) found = e.id;
  });
  return found;
}

/* ── side panel ───────────────────────────────────────────────────────── */
function openPanel(id){
  const n = GRAPH_DATA.nodes.find(x => x.id === id);
  if (!n) return;
  document.getElementById("panel-kind").textContent = n.kind;
  document.getElementById("panel-kind").style.background = colorOf(n.kind);
  document.getElementById("panel-kind").style.color = "#0b1020";
  document.getElementById("panel-label").textContent = n.label;
  document.getElementById("panel-path").textContent = n.path || n.id;

  const body = document.getElementById("panel-body");
  body.innerHTML = "";
  if (n.meta) {
    if (n.meta.docstring) {
      const d = document.createElement("p");
      d.style.cssText = "font-size:12px;color:var(--fg);font-style:italic;";
      d.textContent = n.meta.docstring;
      body.appendChild(d);
    }
    if (n.meta.first_line) {
      const d = document.createElement("p");
      d.style.cssText = "font-size:12px;color:var(--fg);font-style:italic;";
      d.textContent = n.meta.first_line;
      body.appendChild(d);
    }
  }
  const out = {}, inc = {};
  GRAPH_DATA.edges.forEach(e => {
    if (e.source === id) (out[e.kind] ||= []).push(e.target);
    if (e.target === id) (inc[e.kind] ||= []).push(e.source);
  });
  appendGroup(body, "out →", out);
  appendGroup(body, "← in", inc);
  document.getElementById("panel").classList.remove("collapsed");
}
function appendGroup(parent, title, map){
  if (!Object.keys(map).length) return;
  Object.entries(map).forEach(([k, ids]) => {
    const grp = document.createElement("div");
    grp.className = "neighbor-group";
    const h = document.createElement("h4");
    h.textContent = `${title} ${k} (${ids.length})`;
    grp.appendChild(h);
    ids.slice(0, 15).forEach(targetId => {
      const tn = GRAPH_DATA.nodes.find(x => x.id === targetId);
      const row = document.createElement("div");
      row.className = "neighbor-row";
      row.innerHTML = `<span class="kind">${tn ? tn.kind : "?"}</span>${escapeHtml(tn ? tn.label : targetId)}`;
      row.onclick = () => {
        network.selectNodes([targetId]);
        network.focus(targetId, { animation: { duration: 400, easingFunction: "easeInOutQuad" }, scale: 1.4 });
        highlightNeighborhood(targetId);
      };
      grp.appendChild(row);
    });
    if (ids.length > 15) {
      const more = document.createElement("div");
      more.className = "empty";
      more.textContent = `+${ids.length - 15} more`;
      grp.appendChild(more);
    }
    parent.appendChild(grp);
  });
}
document.getElementById("panel-close").onclick = () =>
  document.getElementById("panel").classList.add("collapsed");

/* ── search ───────────────────────────────────────────────────────────── */
const searchInput = document.getElementById("search");
const resultsEl = document.getElementById("results");
let searchDebounce;
searchInput.addEventListener("input", () => {
  clearTimeout(searchDebounce);
  searchDebounce = setTimeout(() => runSearch(searchInput.value), 80);
});
function runSearch(q){
  if (!q.trim()) { resultsEl.classList.remove("show"); return; }
  const ql = q.toLowerCase();
  const ranked = [];
  GRAPH_DATA.nodes.forEach(n => {
    const lbl = n.label.toLowerCase();
    let score = 0;
    if (lbl === ql) score = 100;
    else if (lbl.startsWith(ql)) score = 50;
    else if (lbl.includes(ql)) score = 25;
    else if (n.id.toLowerCase().includes(ql)) score = 10;
    else if (n.path && n.path.toLowerCase().includes(ql)) score = 5;
    if (score) ranked.push([score, n]);
  });
  ranked.sort((a, b) => b[0] - a[0]);
  resultsEl.innerHTML = "";
  ranked.slice(0, 20).forEach(([_, n]) => {
    const row = document.createElement("div");
    row.className = "result-row";
    row.innerHTML = `
      <div class="label">
        <span class="kind-chip" style="background:${colorOf(n.kind)};color:#0b1020;">${n.kind}</span>
        ${escapeHtml(n.label)}
      </div>
      <div class="meta">${escapeHtml(n.path || n.id)}</div>
    `;
    row.onclick = () => {
      resultsEl.classList.remove("show");
      searchInput.value = "";
      network.selectNodes([n.id]);
      network.focus(n.id, { animation: { duration: 500, easingFunction: "easeInOutQuad" }, scale: 1.6 });
      highlightNeighborhood(n.id);
      openPanel(n.id);
    };
    resultsEl.appendChild(row);
  });
  if (ranked.length === 0) {
    resultsEl.innerHTML = `<div class="empty">no matches</div>`;
  }
  resultsEl.classList.add("show");
}
document.addEventListener("click", (ev) => {
  if (!document.getElementById("search-wrap").contains(ev.target)) {
    resultsEl.classList.remove("show");
  }
});

/* ── keyboard ─────────────────────────────────────────────────────────── */
document.addEventListener("keydown", (ev) => {
  if (document.activeElement === searchInput) {
    if (ev.key === "Escape") { searchInput.value = ""; resultsEl.classList.remove("show"); searchInput.blur(); }
    return;
  }
  if (ev.key === "/") { ev.preventDefault(); searchInput.focus(); }
  if (ev.key === "p") togglePathMode();
  if (ev.key === "Escape") {
    network.unselectAll();
    clearHighlight();
    document.getElementById("panel").classList.add("collapsed");
    state.pathMode = false;
    state.pathPick = [];
    document.getElementById("path-btn").classList.remove("on");
  }
});

document.getElementById("path-btn").onclick = togglePathMode;
function togglePathMode(){
  state.pathMode = !state.pathMode;
  state.pathPick = [];
  document.getElementById("path-btn").classList.toggle("on", state.pathMode);
  showToast(state.pathMode ? "Path mode: click SOURCE node" : "Path mode off");
}
document.getElementById("clear-btn").onclick = () => {
  network.fit({ animation: { duration: 500, easingFunction: "easeInOutQuad" } });
  network.unselectAll();
  clearHighlight();
};

/* ── toast ────────────────────────────────────────────────────────────── */
let toastTimer;
function showToast(msg){
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 2200);
}

network.once("stabilizationIterationsDone", () => {
  showToast("ready — press / to search, p for path mode");
});
</script>
</body>
</html>
"""
