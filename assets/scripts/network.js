/* =========================================================
   Varela Digital — Social Network (Cytoscape) 
   ========================================================= */

const DATA_PATH = "../data/network/network_people.json";
const VIEWER_PATTERN = "viewer.html?file={cv}.xml";

let NETWORK = null;
let cy = null;

// focus state
let FOCUS_NODE_ID = null;

// Track what "fit" is showing (largest vs all)
let LAST_FIT_SCOPE = "largest"; // "largest" | "all"

// keep one observer (desktop layout changes / sidebar scrollbars, etc.)
let RESIZE_OBSERVER = null;

// --- NEW: caches to avoid rebuilding arrays repeatedly
let EDGES_BY_MODE = { correspondence: [], comention: [] };
let NODES_BY_ID = new Map(); // id -> {id,label}
let LAST_ELEMENTS_KEY = ""; // mode|minWeight (avoid redundant rebuild)
let LAST_ELEMENTS = null; // last built {nodes,edges}
let LAST_MIN_WEIGHT = 1;
let LAST_MODE = "correspondence";

function debounce(fn, wait = 160) {
  let t = null;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), wait);
  };
}

// Prefer idle time for heavy work; fallback to setTimeout
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

/* -----------------------------
   Overlay + empty state (CSS classes)
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
   Pre-index data for speed (NEW)
----------------------------- */

function indexNetworkData() {
  // nodes map
  NODES_BY_ID = new Map();
  (NETWORK.nodes || []).forEach((n) => {
    NODES_BY_ID.set(n.id, { id: n.id, label: nodeLabel(n) });
  });

  // edges by mode, normalized + weight as int
  EDGES_BY_MODE = { correspondence: [], comention: [] };
  (NETWORK.edges || []).forEach((e) => {
    const type = normalizeType(e.type);
    if (type !== "correspondence" && type !== "comention") return;

    const weight =
      typeof e.weight === "number" ? e.weight : parseInt(e.weight || "1", 10) || 1;

    EDGES_BY_MODE[type].push({
      id: e.id || `${e.source}__${e.target}__${type}`,
      type,
      source: e.source,
      target: e.target,
      weight,
      directed: !!e.directed,
      evidence: Array.isArray(e.evidence) ? e.evidence : [],
    });
  });

  // Optional: sort edges descending by weight so filtering can early-exit later
  // (kept simple; not strictly required)
  EDGES_BY_MODE.correspondence.sort((a, b) => b.weight - a.weight);
  EDGES_BY_MODE.comention.sort((a, b) => b.weight - a.weight);
}

/* -----------------------------
   Build elements (FAST + cached)
----------------------------- */

function buildElementsFast(mode, minWeight) {
  const wanted = normalizeType(mode);
  const key = `${wanted}|${minWeight}`;

  // If only minWeight changed upward/downward a bit, we still rebuild,
  // but we avoid doing it twice in the same tick.
  if (key === LAST_ELEMENTS_KEY && LAST_ELEMENTS) return LAST_ELEMENTS;

  const used = new Set();
  const edgesSrc = EDGES_BY_MODE[wanted] || [];

  // Because edges are sorted desc by weight:
  // - if minWeight is high, we can skip a lot once weight drops below it.
  const edges = [];
  for (const e of edgesSrc) {
    if (e.weight < minWeight) break;
    used.add(e.source);
    used.add(e.target);
    edges.push({
      data: {
        id: e.id,
        type: e.type,
        source: e.source,
        target: e.target,
        weight: e.weight,
        directed: e.directed,
        evidence: e.evidence,
      },
    });
  }

  const nodes = [];
  for (const id of used) {
    const n = NODES_BY_ID.get(id);
    nodes.push({
      data: {
        id,
        label: n?.label || humanizeId(id),
      },
    });
  }

  const out = { nodes, edges };
  LAST_ELEMENTS_KEY = key;
  LAST_ELEMENTS = out;
  LAST_MODE = wanted;
  LAST_MIN_WEIGHT = minWeight;
  return out;
}

/* -----------------------------
   Layout tuning
   NOTE: COSE is expensive; keep iterations controlled.
----------------------------- */

function layoutFor(mode, nodeCount, edgeCount) {
  const isCo = normalizeType(mode) === "comention";
  const dense = nodeCount > 220 || edgeCount > 800;
  const veryDense = nodeCount > 380 || edgeCount > 1600;

  // Keep repulsion strong but avoid huge iterations that lock the UI
  const baseRepulsion = isCo ? 62000 : 26000;
  const repulsion = veryDense ? baseRepulsion * 1.25 : dense ? baseRepulsion * 1.1 : baseRepulsion;

  const baseEdge = isCo ? 250 : 190;
  const edgeLen = veryDense ? baseEdge * 1.06 : baseEdge;

  // PERF: reduce numIter for big graphs (huge win)
  const iter = veryDense ? 420 : dense ? 520 : 650;

  return {
    name: "cose",
    animate: false,
    randomize: true,

    nodeRepulsion: repulsion,
    nodeOverlap: 16,
    idealEdgeLength: edgeLen,
    edgeElasticity: isCo ? 0.18 : 0.16,
    gravity: isCo ? 0.03 : 0.04,
    componentSpacing: isCo ? 340 : 180,
    spacingFactor: isCo ? 1.25 : 1.12,

    nodeDimensionsIncludeLabels: false, // PERF: label-aware layout is expensive
    numIter: iter,

    initialTemp: 1800,
    coolingFactor: 0.985,
    minTemp: 1.0,
  };
}

/* -----------------------------
   Cytoscape style
----------------------------- */

const STYLE = [
  {
    selector: "node",
    style: {
      label: "",
      "font-size": 10,
      "text-wrap": "wrap",
      "text-max-width": 180,

      "background-color": "#4e7a5a",
      "border-color": "rgba(0,0,0,0.35)",
      "border-width": 1,

      width: 10,
      height: 10,
    },
  },
  {
    selector: "node:hover, node:selected, node.vd-focus",
    style: {
      label: "data(label)",
      "text-outline-width": 2,
      "text-outline-color": "rgba(248,245,239,0.96)",
      "z-index": 10,
      "border-width": 2,
    },
  },
  {
    selector: "edge",
    style: {
      width: "mapData(weight, 1, 20, 1, 6)",
      "curve-style": "bezier",
      "line-color": "rgba(0,0,0,0.24)",
      "target-arrow-color": "rgba(0,0,0,0.24)",
      "target-arrow-shape": "triangle",
      "arrow-scale": 0.8,
      opacity: 0.85,
    },
  },
  {
    selector: 'edge[type="comention"]',
    style: {
      "target-arrow-shape": "none",
      "line-color": "rgba(0,0,0,0.20)",
      opacity: 0.78,
    },
  },
  {
    selector: "edge:hover",
    style: {
      "line-color": "rgba(0,0,0,0.55)",
      "target-arrow-color": "rgba(0,0,0,0.55)",
      opacity: 1,
    },
  },
  { selector: ".vd-dim", style: { opacity: 0.10 } },
];

/* -----------------------------
   Smart fit
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

function fitAll(padding = 60) {
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

    // PERF knobs
    motionBlur: true,
    motionBlurOpacity: 0.15,
    textureOnViewport: true,
    hideEdgesOnViewport: false,
    hideLabelsOnViewport: true,
  });

  cy.on("tap", (evt) => {
    if (evt.target === cy) closeTooltip();
  });
  cy.on("tap", "node", (evt) => showNodeTooltip(evt.target));
  cy.on("tap", "edge", (evt) => showEdgeTooltip(evt.target));

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

        // avoid re-fit during exploration
        if (!FOCUS_NODE_ID && LAST_FIT_SCOPE === "largest") {
          fitLargestComponent(90);
        }
      }, 140)
    );

    RESIZE_OBSERVER.observe(UI.container);
  } catch (e) {
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

  // shorter fallback: we reduced iter, so this is safe
  setTimeout(finish, normalizeType(mode) === "comention" ? 4500 : 3500);

  layout.run();
}

function updateGraph(elements, mode, onDone) {
  if (!cy) {
    initCytoscape(elements);
  } else {
    // PERF: batch remove/add is fine; keep it minimal
    cy.stop();
    cy.batch(() => {
      cy.elements().remove();
      cy.add([...elements.nodes, ...elements.edges]);
    });
  }

  cy.resize();
  runLayout(mode, elements, onDone);
}

/* -----------------------------
   Node sizing (PERF: only after layout, and skip if huge)
----------------------------- */

function updateNodeSizesByDegree() {
  if (!cy) return;

  const nCount = cy.nodes().length;
  // PERF: for very large graphs, skip dynamic sizing (big win)
  if (nCount > 900) return;

  const degs = cy.nodes().map((n) => n.degree());
  const maxDeg = Math.max(1, ...degs);

  cy.nodes().forEach((n) => {
    const d = n.degree();
    const size = Math.max(9, Math.min(24, 9 + Math.round((15 * d) / maxDeg)));
    n.style("width", size);
    n.style("height", size);
  });
}

/* -----------------------------
   Focus (ego)
----------------------------- */

function clearFocus() {
  if (!cy) return;
  FOCUS_NODE_ID = null;
  cy.elements().removeClass("vd-dim");
  cy.nodes().removeClass("vd-focus");
}

function applyFocus(nodeId, depth) {
  if (!cy) return;

  const n = cy.getElementById(nodeId);
  if (!n || n.empty()) return;

  closeTooltip();

  cy.elements().removeClass("vd-dim");
  cy.nodes().removeClass("vd-focus");

  let keep = n.closedNeighborhood();

  if (depth >= 2) {
    const ring = keep.nodes();
    ring.forEach((nn) => {
      keep = keep.union(nn.closedNeighborhood());
    });
  }

  const keepWithEdges = keep.union(keep.connectedEdges());

  cy.elements().difference(keepWithEdges).addClass("vd-dim");
  n.addClass("vd-focus");
  n.select();

  cy.fit(keepWithEdges, 90);
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

function showNodeTooltip(node) {
  const label = node.data("label");
  const id = node.data("id");

  const deg = node.degree();
  const indeg = typeof node.indegree === "function" ? node.indegree() : "—";
  const outdeg = typeof node.outdegree === "function" ? node.outdegree() : "—";

  const html = `
    <div><strong>${escapeHtml(label)}</strong></div>
    <div style="font-size:12px;opacity:.85">${escapeHtml(id)}</div>
    <div style="margin-top:6px;font-size:12px">
      Degree: <strong>${deg}</strong> · In: <strong>${indeg}</strong> · Out: <strong>${outdeg}</strong>
    </div>
  `;
  attachTooltipAt(node.renderedPosition(), html);
}

function showEdgeTooltip(edge) {
  const type = normalizeType(edge.data("type"));
  const w = edge.data("weight");
  const evidence = edge.data("evidence") || [];

  const s = cy.getElementById(edge.data("source"));
  const t = cy.getElementById(edge.data("target"));

  const sLabel = s?.data("label") || edge.data("source");
  const tLabel = t?.data("label") || edge.data("target");

  const title = type === "correspondence" ? `${sLabel} → ${tLabel}` : `${sLabel} — ${tLabel}`;

  const evLinks = evidence
    .slice(0, 30)
    .map((cv) => `<a href="${viewerUrl(cv)}" target="_blank" rel="noopener">${cv}</a>`)
    .join(" ");

  const html = `
    <div><strong>${escapeHtml(title)}</strong></div>
    <div style="margin-top:6px;font-size:12px">
      Weight: <strong>${w}</strong> · Evidence: <strong>${evidence.length}</strong>
    </div>
    <div style="margin-top:6px;font-size:12px;line-height:1.4">
      ${evLinks || "<span style='opacity:.8'>No evidence</span>"}
    </div>
  `;
  attachTooltipAt(edge.midpoint(), html);
}

/* -----------------------------
   Person SELECT population (PERF: build once)
----------------------------- */

function populatePersonSelect() {
  if (!UI.personSelect) return;

  // Use NODES_BY_ID (already built)
  const items = Array.from(NODES_BY_ID.values())
    .map((n) => ({ id: n.id, label: n.label }))
    .sort((a, b) => a.label.localeCompare(b.label, "pt-BR"));

  UI.personSelect.innerHTML =
    `<option value="">Select a person…</option>` +
    items.map((p) => `<option value="${escapeHtml(p.id)}">${escapeHtml(p.label)}</option>`).join("");
}

/* -----------------------------
   Refresh (NEW: idle scheduling + smaller work per tick)
----------------------------- */

function refresh() {
  const mode = UI.mode?.value || "correspondence";
  const minWeight = Math.max(1, parseInt(UI.minWeight?.value || "1", 10));
  setWeightBadges(minWeight);

  closeTooltip();
  setLoading(true);

  // don’t block UI; schedule heavy work when idle
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

    // Keep DOM responsive before layout
    requestAnimationFrame(() => {
      updateGraph(elements, mode, () => {
        if (!cy) {
          setLoading(false);
          return;
        }

        updateNodeSizesByDegree();

        if (FOCUS_NODE_ID) {
          const depth = parseInt(UI.egoDepth?.value || "1", 10) || 1;
          applyFocus(FOCUS_NODE_ID, depth);
        } else {
          fitLargestComponent(90);
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

  // NEW: index once
  indexNetworkData();

  populatePersonSelect();

  UI.mode?.addEventListener("change", () => {
    clearFocus();
    // reset cache key (mode changed)
    LAST_ELEMENTS_KEY = "";
    refresh();
  });

  // PERF: "input" still OK, but we debounce heavier and keep work idle
  UI.minWeight?.addEventListener(
    "input",
    debounce(() => {
      clearFocus();
      // minWeight changed -> new key
      refresh();
    }, 220)
  );

  // Fit button toggles largest <-> all
  UI.fitBtn?.addEventListener("click", () => {
    if (!cy) return;
    closeTooltip();
    cy.resize();

    if (FOCUS_NODE_ID) {
      const depth = parseInt(UI.egoDepth?.value || "1", 10) || 1;
      applyFocus(FOCUS_NODE_ID, depth);
      return;
    }

    if (LAST_FIT_SCOPE === "largest") {
      fitAll(60);
    } else {
      fitLargestComponent(90);
    }
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
        fitLargestComponent(90);
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