/* =========================================================
   Varela Digital — Social Network (Cytoscape)
   File: network.js
   Source: ../data/network/network_people.json
   ========================================================= */

console.log("network.js loaded");

const DATA_PATH = "../data/network/network_people.json";
const VIEWER_PATTERN = "viewer.html?file={cv}.xml";

let NETWORK = null;
let cy = null;

// focus state
let FOCUS_NODE_ID = null;

// Track what "fit" is showing (largest vs all)
let LAST_FIT_SCOPE = "all"; // "largest" | "all"

// keep one observer (desktop layout changes / sidebar scrollbars, etc.)
let RESIZE_OBSERVER = null;

// caches to avoid rebuilding arrays repeatedly
let EDGES_BY_MODE = { correspondence: [], comention: [] };
let NODES_BY_ID = new Map(); // id -> {id,label}
let LAST_ELEMENTS_KEY = ""; // mode|minWeight
let LAST_ELEMENTS = null;

function debounce(fn, wait = 160) {
  let t = null;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), wait);
  };
}

function runWhenIdle(fn, timeout = 250) {
  if (typeof requestIdleCallback === "function") {
    requestIdleCallback(fn, { timeout });
  } else {
    setTimeout(fn, 0);
  }
}

const UI = {
  mode: document.getElementById("networkMode"),
  minWeight: document.getElementById("minWeight"),
  weightValue: document.getElementById("weightValue"),
  weightValueInline: document.getElementById("weightValueInline"),
  fitBtn: document.getElementById("fitNetworkBtn"),
  container: document.getElementById("network"),

  personSelect: document.getElementById("personSelect"),
  egoDepth: document.getElementById("egoDepth"),
  focusBtn: document.getElementById("focusBtn"),
  resetBtn: document.getElementById("resetBtn"),
};

function viewerUrl(cvId) {
  return VIEWER_PATTERN.replace("{cv}", cvId);
}

function setWeightBadges(v) {
  if (UI.weightValue) UI.weightValue.textContent = String(v);
  if (UI.weightValueInline) UI.weightValueInline.textContent = String(v);
}

function normalizeType(t) {
  const s = String(t || "").toLowerCase().trim();
  if (s === "correspondence" || s === "corresp") return "correspondence";
  if (
    s === "comention" ||
    s === "co-mention" ||
    s === "co_mention" ||
    s === "comentions" ||
    s === "co-mentions" ||
    s === "co_mentions"
  )
    return "comention";
  return s;
}

// make xml:id readable when label is missing
function humanizeId(id) {
  const raw = String(id || "").trim();
  if (!raw) return "—";
  const s = raw.replaceAll("_", " ").replaceAll("-", " ").trim();
  return s
    .split(/\s+/)
    .map((w) => {
      const lw = w.toLowerCase();
      if (["da", "de", "do", "das", "dos", "e"].includes(lw)) return lw;
      return lw.charAt(0).toUpperCase() + lw.slice(1);
    })
    .join(" ");
}

function nodeLabel(n) {
  const label = (n.label || "").trim();
  return label ? label : humanizeId(n.id);
}

/* =========================================================
   LABEL POLICY — hidden by default
   - Only show labels when node has class "vd-labels"
   - In focus: keep labels only on focused node + selected nodes
   ========================================================= */

function clearAllNodeLabels() {
  if (!cy) return;
  cy.nodes().removeClass("vd-labels");
}

function showLabelForNode(node) {
  if (!node || node.empty()) return;
  node.addClass("vd-labels");
}

function hideLabelForNode(node) {
  if (!node || node.empty()) return;
  if (node.hasClass("vd-focus")) return;
  node.removeClass("vd-labels");
}

function enforceFocusLabelPolicy() {
  if (!cy) return;
  cy.nodes().forEach((n) => {
    if (n.hasClass("vd-focus") || n.selected()) n.addClass("vd-labels");
    else n.removeClass("vd-labels");
  });
}

/* -----------------------------
   Overlay + empty state
----------------------------- */

function ensureOverlay() {
  let ov = document.getElementById("vd-network-overlay");
  if (!ov) {
    ov = document.createElement("div");
    ov.id = "vd-network-overlay";
    ov.className = "vd-network-overlay";
    ov.innerHTML = `
      <div class="vd-network-overlay-inner">
        <div class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></div>
        <div class="vd-network-overlay-text">Building network…</div>
      </div>
    `;
    const parent = UI.container?.parentElement;
    if (parent) {
      parent.style.position = "relative";
      parent.appendChild(ov);
    } else if (UI.container) {
      UI.container.style.position = "relative";
      UI.container.appendChild(ov);
    }
  }
  return ov;
}

function setLoading(isLoading) {
  const ov = ensureOverlay();
  if (ov) ov.style.display = isLoading ? "flex" : "none";
}

function showEmptyState() {
  let empty = document.getElementById("vd-network-empty");
  if (!empty) {
    empty = document.createElement("div");
    empty.id = "vd-network-empty";
    empty.className = "vd-network-empty";
    empty.innerHTML = `
      <div>
        <div class="vd-network-empty-title">No edges match the current filters.</div>
        <div class="vd-network-empty-text">Try lowering “Minimum documents” or switching mode.</div>
      </div>
    `;
    const parent = UI.container?.parentElement;
    (parent || UI.container).appendChild(empty);
  }
  empty.style.display = "flex";
}

function hideEmptyState() {
  const empty = document.getElementById("vd-network-empty");
  if (empty) empty.style.display = "none";
}

/* -----------------------------
   Helpers: evidence union + formatting
----------------------------- */

function dedupeEvidence(arr) {
  const seen = new Set();
  const out = [];
  (arr || []).forEach((x) => {
    const s = String(x || "").trim();
    if (!s) return;
    if (seen.has(s)) return;
    seen.add(s);
    out.push(s);
  });
  return out;
}

function safeArray(v) {
  return Array.isArray(v) ? v : [];
}

function evidenceToLinks(evidence, limit = 40) {
  const ev = safeArray(evidence);
  if (!ev.length) return "<span style='opacity:.8'>No evidence</span>";

  const links = ev
    .slice(0, limit)
    .map((cv) => {
      const id = String(cv || "").trim();
      if (!id) return "";
      const url = viewerUrl(id);
      return `<a href="${url}" target="_blank" rel="noopener">${escapeHtml(id)}</a>`;
    })
    .filter(Boolean)
    .join(" ");

  const more = ev.length > limit ? ` <span style="opacity:.75">(+${ev.length - limit} more)</span>` : "";
  return links + more;
}

/* -----------------------------
   Data indexing (fast) + evidence for nodes
   - Merge/aggregate edges to avoid duplicates
   - Build NODE_EVIDENCE_BY_MODE[id] = Set(cvId)
----------------------------- */

let NODE_EVIDENCE_BY_MODE = {
  correspondence: new Map(), // id -> Set(cv)
  comention: new Map(), // id -> Set(cv)
};

function addNodeEvidence(mode, nodeId, evidenceArr) {
  if (!nodeId) return;
  const m = NODE_EVIDENCE_BY_MODE[mode];
  if (!m) return;
  let set = m.get(nodeId);
  if (!set) {
    set = new Set();
    m.set(nodeId, set);
  }
  safeArray(evidenceArr).forEach((cv) => {
    const s = String(cv || "").trim();
    if (s) set.add(s);
  });
}

function indexNetworkData() {
  // nodes map
  NODES_BY_ID = new Map();
  (NETWORK.nodes || []).forEach((n) => {
    NODES_BY_ID.set(n.id, { id: n.id, label: nodeLabel(n) });
  });

  // reset node evidence maps
  NODE_EVIDENCE_BY_MODE = {
    correspondence: new Map(),
    comention: new Map(),
  };

  // buckets to merge duplicates
  const buckets = {
    correspondence: new Map(),
    comention: new Map(),
  };

  (NETWORK.edges || []).forEach((e) => {
    const type = normalizeType(e.type);
    if (type !== "correspondence" && type !== "comention") return;

    const source = String(e.source || "").trim();
    const target = String(e.target || "").trim();
    if (!source || !target) return;

    const directed = !!e.directed;
    const weight = typeof e.weight === "number" ? e.weight : parseInt(e.weight || "1", 10) || 1;
    const evidence = Array.isArray(e.evidence) ? e.evidence : [];

    // track node evidence
    addNodeEvidence(type, source, evidence);
    addNodeEvidence(type, target, evidence);

    // canonical pair for co-mention (undirected)
    let s = source;
    let t = target;
    let dirFlag = directed ? "1" : "0";
    if (type === "comention") {
      dirFlag = "0";
      if (s > t) {
        const tmp = s;
        s = t;
        t = tmp;
      }
    }

    const key = `${type}|${dirFlag}|${s}|${t}`;
    const map = buckets[type];
    const existing = map.get(key);

    if (!existing) {
      map.set(key, {
        id: e.id || key,
        type,
        source: s,
        target: t,
        directed: type === "comention" ? false : directed,
        weight: Math.max(1, weight),
        evidence: [...evidence],
      });
    } else {
      existing.weight += Math.max(1, weight);
      existing.evidence.push(...evidence);
    }
  });

  EDGES_BY_MODE = { correspondence: [], comention: [] };

  for (const mode of ["correspondence", "comention"]) {
    const arr = Array.from(buckets[mode].values()).map((x) => {
      const w = Math.max(1, x.weight);
      return {
        ...x,
        evidence: dedupeEvidence(x.evidence),
        weight: w,
        wlog: Math.log2(w + 1),
      };
    });

    arr.sort((a, b) => b.weight - a.weight);
    EDGES_BY_MODE[mode] = arr;
  }
}

/* -----------------------------
   Build elements (with node "strength" for sizing + node evidence count)
   - strength = sum of incident edge weights in filtered graph
   - nodeEvidence = list of CV ids for the node in current mode (from index)
----------------------------- */

function buildElementsFast(mode, minWeight) {
  const wanted = normalizeType(mode);
  const key = `${wanted}|${minWeight}`;
  if (key === LAST_ELEMENTS_KEY && LAST_ELEMENTS) return LAST_ELEMENTS;

  const edgesSrc = EDGES_BY_MODE[wanted] || [];

  const used = new Set();
  const strength = new Map(); // nodeId -> sum weights

  const edges = [];
  for (const e of edgesSrc) {
    if (e.weight < minWeight) break;

    used.add(e.source);
    used.add(e.target);

    strength.set(e.source, (strength.get(e.source) || 0) + e.weight);
    strength.set(e.target, (strength.get(e.target) || 0) + e.weight);

    edges.push({
      data: {
        id: e.id,
        type: e.type,
        source: e.source,
        target: e.target,
        weight: e.weight,
        wlog: e.wlog,
        directed: e.directed,
        evidence: e.evidence,
      },
    });
  }

  const nodeEvMap = NODE_EVIDENCE_BY_MODE[wanted] || new Map();

  const nodes = [];
  for (const id of used) {
    const n = NODES_BY_ID.get(id);

    const s = Math.max(1, strength.get(id) || 1);
    const slog = Math.log2(s + 1);

    const evSet = nodeEvMap.get(id);
    const evArr = evSet ? Array.from(evSet) : [];

    nodes.push({
      data: {
        id,
        label: n?.label || humanizeId(id),

        // node sizing driver
        strength: s,
        slog,

        // evidence for tooltips (node click)
        evidence: evArr,
        evidenceCount: evArr.length,

        // colors are fixed/neutral (you said colors didn't work well)
        color: "#4e7a5a",
      },
    });
  }

  const out = { nodes, edges };
  LAST_ELEMENTS_KEY = key;
  LAST_ELEMENTS = out;
  return out;
}

/* =========================================================
   Layout tuning
   Goal: more separation INSIDE clusters, without pushing components far apart.
   ========================================================= */

function layoutFor(mode, nodeCount, edgeCount) {
  const isCo = normalizeType(mode) === "comention";
  const dense = nodeCount > 220 || edgeCount > 800;
  const veryDense = nodeCount > 380 || edgeCount > 1600;

  const baseRepulsion = isCo ? 98000 : 52000;
  const repulsion = veryDense ? baseRepulsion * 1.18 : dense ? baseRepulsion * 1.08 : baseRepulsion;

  const baseEdge = isCo ? 260 : 220;
  const edgeLen = veryDense ? baseEdge * 1.06 : baseEdge;

  const componentSpacing = isCo ? 260 : 170;
  const spacingFactor = isCo ? 1.10 : 1.06;

  const iter = veryDense ? 360 : dense ? 500 : 700;

  return {
    name: "cose",
    animate: false,
    randomize: true,

    nodeRepulsion: repulsion,
    nodeOverlap: 60,
    idealEdgeLength: edgeLen,
    edgeElasticity: isCo ? 0.16 : 0.14,

    gravity: isCo ? 0.040 : 0.055,
    componentSpacing,
    spacingFactor,

    avoidOverlap: true,
    nodeDimensionsIncludeLabels: false,
    numIter: iter,

    initialTemp: 1800,
    coolingFactor: 0.985,
    minTemp: 1.0,
  };
}

/* =========================================================
   Local ego layout (focus)
   ========================================================= */

function egoLayoutFor(mode, nodeCount) {
  const isCo = normalizeType(mode) === "comention";
  const dense = nodeCount > 90;
  const veryDense = nodeCount > 170;

  const baseRep = isCo ? 125000 : 90000;
  const rep = veryDense ? baseRep * 1.18 : dense ? baseRep * 1.08 : baseRep;

  const edgeLen = isCo ? 260 : 220;
  const iter = veryDense ? 260 : dense ? 320 : 420;

  return {
    name: "cose",
    animate: false,
    randomize: false,

    nodeRepulsion: rep,
    nodeOverlap: 70,
    idealEdgeLength: edgeLen,
    edgeElasticity: 0.14,
    gravity: 0.03,

    componentSpacing: 180,
    spacingFactor: 1.08,

    avoidOverlap: true,
    nodeDimensionsIncludeLabels: false,
    numIter: iter,

    initialTemp: 1200,
    coolingFactor: 0.99,
    minTemp: 1.0,
  };
}

/* =========================================================
   Style
   - thin edges (log weight)
   - node size by "slog" (sum of incident weights)
   - labels only via class vd-labels
   ========================================================= */

const STYLE = [
  {
    selector: "node",
    style: {
      label: "",

      "font-size": 10,
      "text-wrap": "wrap",
      "text-max-width": 180,
      color: "#1f1f1f",

      "text-background-color": "rgba(248,245,239,0.92)",
      "text-background-opacity": 1,
      "text-background-padding": "2px",
      "text-background-shape": "roundrectangle",

      "background-color": "data(color)",
      "border-color": "rgba(0,0,0,0.35)",
      "border-width": 1,

      width: "mapData(slog, 0, 10, 8, 20)",
      height: "mapData(slog, 0, 10, 8, 20)",
    },
  },
  {
    selector: "node.vd-labels",
    style: {
      label: "data(label)",
      "text-outline-width": 2,
      "text-outline-color": "rgba(248,245,239,0.96)",
      "z-index": 10,
    },
  },
  {
    selector: "node:hover, node:selected, node.vd-focus",
    style: {
      "border-width": 2,
      "z-index": 12,
    },
  },
  {
    selector: "edge",
    style: {
      width: "mapData(wlog, 0, 10, 0.30, 1.35)",
      "curve-style": "bezier",
      "line-color": "rgba(0,0,0,0.16)",
      "target-arrow-color": "rgba(0,0,0,0.16)",
      "target-arrow-shape": "triangle",
      "arrow-scale": 0.55,
      opacity: 0.55,
    },
  },
  {
    selector: 'edge[type="comention"]',
    style: {
      "target-arrow-shape": "none",
      "line-color": "rgba(0,0,0,0.12)",
      opacity: 0.42,
    },
  },
  {
    selector: "edge:hover",
    style: {
      width: 2.0,
      "line-color": "rgba(0,0,0,0.60)",
      "target-arrow-color": "rgba(0,0,0,0.60)",
      opacity: 0.95,
    },
  },
  { selector: ".vd-dim", style: { opacity: 0.10 } },
];

/* -----------------------------
   Fit helpers
----------------------------- */

function largestComponent() {
  if (!cy) return null;
  const comps = cy.elements().components();
  if (!comps || !comps.length) return null;

  let best = comps[0];
  let bestScore = -1;

  for (const c of comps) {
    const n = c.nodes().length;
    const e = c.edges().length;
    const score = n * 10 + e;
    if (score > bestScore) {
      bestScore = score;
      best = c;
    }
  }
  return best;
}

function fitLargestComponent(padding = 90) {
  if (!cy) return;
  const best = largestComponent();
  if (!best) {
    cy.fit(undefined, padding);
    LAST_FIT_SCOPE = "all";
    return;
  }
  cy.fit(best, padding);
  LAST_FIT_SCOPE = "largest";
}

function fitAll(padding = 55) {
  if (!cy) return;
  cy.fit(undefined, padding);
  LAST_FIT_SCOPE = "all";
}

/* -----------------------------
   Init / update
----------------------------- */

function initCytoscape(elements) {
  cy = cytoscape({
    container: UI.container,
    elements: [...elements.nodes, ...elements.edges],
    style: STYLE,

    wheelSensitivity: 0.18,
    pixelRatio: 1,
    boxSelectionEnabled: false,
    selectionType: "single",

    motionBlur: true,
    motionBlurOpacity: 0.15,
    textureOnViewport: true,
    hideEdgesOnViewport: false,
    hideLabelsOnViewport: true,
  });

  // background tap
  cy.on("tap", (evt) => {
    if (evt.target === cy) closeTooltip();
  });

  // tooltips on tap (node/edge)
  cy.on("tap", "node", (evt) => showNodeTooltip(evt.target));
  cy.on("tap", "edge", (evt) => showEdgeTooltip(evt.target));

  // labels via hover/selection
  cy.on("mouseover", "node", (evt) => showLabelForNode(evt.target));
  cy.on("mouseout", "node", (evt) => {
    if (FOCUS_NODE_ID) {
      enforceFocusLabelPolicy();
      return;
    }
    hideLabelForNode(evt.target);
  });

  cy.on("select", "node", (evt) => {
    showLabelForNode(evt.target);
    if (FOCUS_NODE_ID) enforceFocusLabelPolicy();
  });

  cy.on("unselect", "node", () => {
    if (FOCUS_NODE_ID) enforceFocusLabelPolicy();
  });

  setupResizeObserver();
}

function setupResizeObserver() {
  if (!UI.container) return;
  try {
    if (RESIZE_OBSERVER) RESIZE_OBSERVER.disconnect();

    RESIZE_OBSERVER = new ResizeObserver(
      debounce(() => {
        if (!cy) return;
        cy.resize();
      }, 140)
    );

    RESIZE_OBSERVER.observe(UI.container);
  } catch {
    // ignore
  }
}

function runLayout(mode, elements, onDone) {
  if (!cy) return;

  const layout = cy.layout(layoutFor(mode, elements.nodes.length, elements.edges.length));

  let finished = false;
  const finish = () => {
    if (finished) return;
    finished = true;
    onDone?.();
  };

  layout.on("layoutstop", finish);
  setTimeout(finish, normalizeType(mode) === "comention" ? 5200 : 4200);
  layout.run();
}

function updateGraph(elements, mode, onDone) {
  if (!cy) {
    initCytoscape(elements);
  } else {
    cy.stop();
    cy.batch(() => {
      cy.elements().remove();
      cy.add([...elements.nodes, ...elements.edges]);
    });
  }

  clearAllNodeLabels();
  cy.resize();

  runLayout(mode, elements, onDone);
}

/* -----------------------------
   Focus (ego)
----------------------------- */

function clearFocus() {
  if (!cy) return;
  FOCUS_NODE_ID = null;
  cy.elements().removeClass("vd-dim");
  cy.nodes().removeClass("vd-focus");
  clearAllNodeLabels();
  closeTooltip();
}

function buildEgoKeep(node, depth) {
  let keep = node.closedNeighborhood();
  if (depth >= 2) {
    const ring = keep.nodes();
    ring.forEach((nn) => {
      keep = keep.union(nn.closedNeighborhood());
    });
  }
  return keep;
}

function runLocalEgoLayout(mode, keepWithEdges) {
  if (!cy || !keepWithEdges) return;

  const sub = keepWithEdges.filter((el) => !el.hasClass("vd-dim"));
  const n = sub.nodes().length;
  if (n < 3) return;

  const layout = sub.layout(egoLayoutFor(mode, n));
  layout.run();
}

function applyFocus(nodeId, depth) {
  if (!cy) return;

  const n = cy.getElementById(nodeId);
  if (!n || n.empty()) return;

  closeTooltip();

  cy.elements().removeClass("vd-dim");
  cy.nodes().removeClass("vd-focus");
  clearAllNodeLabels();

  const keep = buildEgoKeep(n, depth);
  const keepWithEdges = keep.union(keep.connectedEdges());

  cy.elements().difference(keepWithEdges).addClass("vd-dim");

  n.addClass("vd-focus");
  n.select();

  enforceFocusLabelPolicy();

  const mode = UI.mode?.value || "correspondence";
  runLocalEgoLayout(mode, keepWithEdges);

  setTimeout(() => {
    if (!cy) return;
    cy.fit(keepWithEdges, 95);
  }, 0);

  LAST_FIT_SCOPE = "largest";
}

/* -----------------------------
   Tooltip
----------------------------- */

function disposeTooltip(el) {
  const t = bootstrap.Tooltip.getInstance(el);
  if (t) t.dispose();
}

function closeTooltip() {
  const old = document.getElementById("vd-tooltip-anchor");
  if (old) {
    disposeTooltip(old);
    old.remove();
  }
}

function attachTooltipAt(renderedPos, html) {
  closeTooltip();

  const a = document.createElement("span");
  a.id = "vd-tooltip-anchor";
  a.className = "vd-tooltip-anchor";
  a.style.left = `${renderedPos.x}px`;
  a.style.top = `${renderedPos.y}px`;

  a.setAttribute("data-bs-toggle", "tooltip");
  a.setAttribute("data-bs-html", "true");
  a.setAttribute("data-bs-placement", "top");
  a.setAttribute("title", html);

  UI.container.style.position = "relative";
  UI.container.appendChild(a);

  const tip = new bootstrap.Tooltip(a, { trigger: "manual", container: UI.container });
  tip.show();
}

function escapeHtml(str) {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

/**
 * NODE tooltip now includes evidence links
 * - For correspondence: evidence are the letters that support that node's connections.
 * - For comention: also works, but you mostly cared about correspondence.
 */
function showNodeTooltip(node) {
  const label = node.data("label");
  const id = node.data("id");

  const deg = node.degree();
  const indeg = typeof node.indegree === "function" ? node.indegree() : "—";
  const outdeg = typeof node.outdegree === "function" ? node.outdegree() : "—";

  const ev = node.data("evidence") || [];
  const evCount = node.data("evidenceCount") ?? (Array.isArray(ev) ? ev.length : 0);
  const evHtml = evidenceToLinks(ev, 40);

  const html = `
    <div><strong>${escapeHtml(label)}</strong></div>
    <div style="font-size:12px;opacity:.85">${escapeHtml(id)}</div>
    <div style="margin-top:6px;font-size:12px">
      Degree: <strong>${deg}</strong> · In: <strong>${indeg}</strong> · Out: <strong>${outdeg}</strong>
    </div>
    <div style="margin-top:8px;font-size:12px">
      Evidence: <strong>${evCount}</strong>
    </div>
    <div style="margin-top:6px;font-size:12px;line-height:1.4">
      ${evHtml}
    </div>
  `;
  attachTooltipAt(node.renderedPosition(), html);
}

/**
 * EDGE tooltip: evidence links (already aggregated/deduped)
 */
function showEdgeTooltip(edge) {
  const type = normalizeType(edge.data("type"));
  const w = edge.data("weight");
  const evidence = edge.data("evidence") || [];

  const s = cy.getElementById(edge.data("source"));
  const t = cy.getElementById(edge.data("target"));

  const sLabel = s?.data("label") || edge.data("source");
  const tLabel = t?.data("label") || edge.data("target");

  const title = type === "correspondence" ? `${sLabel} → ${tLabel}` : `${sLabel} — ${tLabel}`;
  const evHtml = evidenceToLinks(evidence, 40);

  const html = `
    <div><strong>${escapeHtml(title)}</strong></div>
    <div style="margin-top:6px;font-size:12px">
      Weight: <strong>${w}</strong> · Evidence: <strong>${safeArray(evidence).length}</strong>
    </div>
    <div style="margin-top:6px;font-size:12px;line-height:1.4">
      ${evHtml}
    </div>
  `;
  attachTooltipAt(edge.midpoint(), html);
}

/* -----------------------------
   Person select
----------------------------- */

function populatePersonSelect() {
  if (!UI.personSelect) return;

  const items = Array.from(NODES_BY_ID.values())
    .map((n) => ({ id: n.id, label: n.label }))
    .sort((a, b) => a.label.localeCompare(b.label, "pt-BR"));

  UI.personSelect.innerHTML =
    `<option value="">Select a person…</option>` +
    items.map((p) => `<option value="${escapeHtml(p.id)}">${escapeHtml(p.label)}</option>`).join("");
}

/* -----------------------------
   Refresh
----------------------------- */

function refresh() {
  const mode = UI.mode?.value || "correspondence";
  const minWeight = Math.max(1, parseInt(UI.minWeight?.value || "1", 10));
  setWeightBadges(minWeight);

  closeTooltip();
  setLoading(true);

  runWhenIdle(() => {
    const elements = buildElementsFast(mode, minWeight);

    if (!elements.edges.length) {
      setLoading(false);
      hideEmptyState();
      showEmptyState();
      if (cy) {
        cy.destroy();
        cy = null;
      }
      return;
    }

    hideEmptyState();

    requestAnimationFrame(() => {
      updateGraph(elements, mode, () => {
        if (!cy) {
          setLoading(false);
          return;
        }

        if (FOCUS_NODE_ID) {
          const depth = parseInt(UI.egoDepth?.value || "1", 10) || 1;
          applyFocus(FOCUS_NODE_ID, depth);
        } else {
          fitAll(55);
        }

        setLoading(false);
      });
    });
  }, 300);
}

/* -----------------------------
   Main
----------------------------- */

async function main() {
  if (!UI.container) throw new Error("Network container (#network) not found.");

  setWeightBadges(parseInt(UI.minWeight?.value || "1", 10));
  setLoading(true);

  const res = await fetch(DATA_PATH, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to load ${DATA_PATH} (HTTP ${res.status})`);
  NETWORK = await res.json();

  indexNetworkData();
  populatePersonSelect();

  UI.mode?.addEventListener("change", () => {
    clearFocus();
    LAST_ELEMENTS_KEY = "";
    refresh();
  });

  UI.minWeight?.addEventListener(
    "input",
    debounce(() => {
      clearFocus();
      LAST_ELEMENTS_KEY = "";
      refresh();
    }, 220)
  );

  UI.fitBtn?.addEventListener("click", () => {
    if (!cy) return;
    closeTooltip();
    cy.resize();

    if (FOCUS_NODE_ID) {
      const depth = parseInt(UI.egoDepth?.value || "1", 10) || 1;
      applyFocus(FOCUS_NODE_ID, depth);
      return;
    }

    // toggle
    if (LAST_FIT_SCOPE === "largest") fitAll(55);
    else fitLargestComponent(90);
  });

  if (UI.focusBtn && UI.resetBtn && UI.personSelect && UI.egoDepth) {
    UI.focusBtn.addEventListener("click", () => {
      if (!cy) return;
      const id = (UI.personSelect.value || "").trim();
      if (!id) return;

      FOCUS_NODE_ID = id;
      const depth = parseInt(UI.egoDepth.value, 10) || 1;
      applyFocus(FOCUS_NODE_ID, depth);
    });

    UI.egoDepth.addEventListener("change", () => {
      if (!cy || !FOCUS_NODE_ID) return;
      const depth = parseInt(UI.egoDepth.value, 10) || 1;
      applyFocus(FOCUS_NODE_ID, depth);
    });

    UI.resetBtn.addEventListener("click", () => {
      if (UI.personSelect) UI.personSelect.value = "";
      closeTooltip();
      clearFocus();

      if (cy) {
        cy.elements().removeClass("vd-dim");
        cy.resize();
        fitAll(55);
      }
    });
  }

  setLoading(false);
  refresh();
}

main().catch((err) => {
  console.error(err);
  setLoading(false);

  if (cy) {
    cy.destroy();
    cy = null;
  }

  if (UI.container) {
    UI.container.innerHTML = `<pre class="p-3 text-danger">${err.stack || err}</pre>`;
  }
});