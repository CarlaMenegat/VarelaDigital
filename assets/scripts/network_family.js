/* =========================================================
   Varela Digital — Family Network (Cytoscape)
   Source: ../../data/network/network_family.json

   Types in JSON:
   - hrao:compadreOf  (undirected)
   - rel:*            (directed/undirected depending on edge.directed)
   ========================================================= */

const DATA_PATH = "../data/network/network_family.json";

let NETWORK = null;
let cy = null;

// focus state
let FOCUS_NODE_ID = null;

// fit toggle
let LAST_FIT_SCOPE = "largest"; // "largest" | "all"

// resize observer
let RESIZE_OBSERVER = null;

function debounce(fn, wait = 160) {
  let t = null;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), wait);
  };
}

const UI = {
  // Mode selector for family network
  mode: document.getElementById("familyMode"), // all | family | compadre

  fitBtn: document.getElementById("fitNetworkBtn"),
  container: document.getElementById("network"),

  personSelect: document.getElementById("personSelect"),
  egoDepth: document.getElementById("egoDepth"),
  focusBtn: document.getElementById("focusBtn"),
  resetBtn: document.getElementById("resetBtn"),
};

function normalizeType(t) {
  return String(t || "").trim().toLowerCase();
}

function isCompadreType(t) {
  // exact in your JSON: "hrao:compadreOf"
  return normalizeType(t) === "hrao:compadreof";
}

function isFamilyType(t) {
  // your JSON shows: rel:parentOf, etc. → any "rel:*" counts as family
  // If later you also include rico:hasFamilyAssociationWith, it will also match here.
  const s = normalizeType(t);
  return s.startsWith("rel:") || s === "rico:hasfamilyassociationwith";
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
        <div class="vd-network-empty-title">No relationships match the current filter.</div>
        <div class="vd-network-empty-text">Try “All”, or clear focus.</div>
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
   Build elements (single load)
----------------------------- */

function buildElements() {
  const edges = (NETWORK.edges || []).map((e) => ({
    data: {
      id: e.id || `${e.source}__${e.target}__${e.type || "rel"}`,
      source: e.source,
      target: e.target,
      type: e.type || "",
      directed: !!e.directed,
      evidence: Array.isArray(e.evidence) ? e.evidence : [],
      weight: typeof e.weight === "number" ? e.weight : parseInt(e.weight || "1", 10) || 1,
    },
  }));

  const used = new Set();
  edges.forEach((ed) => {
    used.add(ed.data.source);
    used.add(ed.data.target);
  });

  const nodes = (NETWORK.nodes || [])
    .filter((n) => used.has(n.id))
    .map((n) => ({
      data: {
        id: n.id,
        label: nodeLabel(n),
      },
    }));

  return { nodes, edges };
}

/* -----------------------------
   Layout: fast + stable
   - If fcose is available, use it; else fallback to cose
----------------------------- */

function layoutOptions(nodeCount, edgeCount) {
  // "fcose" exists if you included the extension before this script
  const hasFcose = !!(cytoscape && cytoscape.extensions && cytoscape.extensions("layout", "fcose"));
  const name = hasFcose ? "fcose" : "cose";

  if (name === "fcose") {
    return {
      name: "fcose",
      animate: false,
      randomize: true,
      quality: "default",
      nodeRepulsion: nodeCount > 250 ? 12000 : 9000,
      idealEdgeLength: 160,
      gravity: 0.25,
      numIter: nodeCount > 250 || edgeCount > 500 ? 550 : 400,
    };
  }

  return {
    name: "cose",
    animate: false,
    randomize: true,
    nodeRepulsion: nodeCount > 250 ? 16000 : 12000,
    idealEdgeLength: 140,
    gravity: 0.08,
    numIter: nodeCount > 250 || edgeCount > 500 ? 750 : 550,
  };
}

/* -----------------------------
   Cytoscape style
   - edges NOT brown
   - family edges: neutral grey/greenish
   - compadre edges: dashed + lighter
   - arrows only when edge.directed == true
----------------------------- */

const STYLE = [
  {
    selector: "node",
    style: {
      label: "",
      "font-size": 10,
      "text-wrap": "wrap",
      "text-max-width": 180,

      "background-color": "#2f3b2c", // map green
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

  // Base edge: no arrow by default
  {
    selector: "edge",
    style: {
      width: "mapData(weight, 1, 20, 1.25, 5)",
      "curve-style": "bezier",
      "line-color": "rgba(47, 59, 44, 0.35)",
      "target-arrow-shape": "none",
      "arrow-scale": 0.75,
    },
  },

  // Directed edges (from JSON: directed true) → show arrow
  {
    selector: "edge[directed = 1]",
    style: {
      "target-arrow-shape": "triangle",
      "target-arrow-color": "rgba(47, 59, 44, 0.35)",
    },
  },

  // Compadre: lighter + dashed + no arrow
  {
    selector: 'edge[type = "hrao:compadreOf"]',
    style: {
      "line-color": "rgba(47, 47, 47, 0.28)",
      "line-style": "dashed",
      "target-arrow-shape": "none",
    },
  },

  // Family (rel:*): keep solid, slightly stronger
  {
    selector: 'edge[type ^= "rel:"]',
    style: {
      "line-color": "rgba(47, 59, 44, 0.42)",
      "line-style": "solid",
    },
  },

  { selector: ".vd-dim", style: { opacity: 0.10 } },
  { selector: ".vd-hide", style: { display: "none" } },
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

function fitAll(padding = 60) {
  if (!cy) return;
  cy.fit(undefined, padding);
  LAST_FIT_SCOPE = "all";
}

/* -----------------------------
   ResizeObserver
----------------------------- */

function setupResizeObserver() {
  if (!UI.container) return;

  try {
    if (RESIZE_OBSERVER) RESIZE_OBSERVER.disconnect();

    RESIZE_OBSERVER = new ResizeObserver(
      debounce(() => {
        if (!cy) return;
        cy.resize();

        // Don’t nuke user exploration
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
  const html = `
    <div><strong>${escapeHtml(label)}</strong></div>
    <div style="font-size:12px;opacity:.85">${escapeHtml(id)}</div>
  `;
  attachTooltipAt(node.renderedPosition(), html);
}

function showEdgeTooltip(edge) {
  const type = String(edge.data("type") || "");
  const directed = !!edge.data("directed");

  const s = cy.getElementById(edge.data("source"));
  const t = cy.getElementById(edge.data("target"));
  const sLabel = s?.data("label") || edge.data("source");
  const tLabel = t?.data("label") || edge.data("target");

  const arrow = directed ? " → " : " — ";
  const html = `
    <div><strong>${escapeHtml(sLabel)}${arrow}${escapeHtml(tLabel)}</strong></div>
    <div style="margin-top:6px;font-size:12px;opacity:.85">
      Type: <strong>${escapeHtml(type || "relation")}</strong>
    </div>
  `;
  attachTooltipAt(edge.midpoint(), html);
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
   Person select
----------------------------- */

function populatePersonSelect() {
  if (!UI.personSelect) return;

  const items = (NETWORK.nodes || [])
    .map((n) => ({ id: n.id, label: nodeLabel(n) }))
    .sort((a, b) => a.label.localeCompare(b.label, "pt-BR"));

  UI.personSelect.innerHTML =
    `<option value="">Select a person…</option>` +
    items.map((p) => `<option value="${escapeHtml(p.id)}">${escapeHtml(p.label)}</option>`).join("");
}

/* -----------------------------
   Filtering WITHOUT relayout (fast)
----------------------------- */

function applyTypeFilter(modeValue) {
  if (!cy) return;

  const mode = normalizeType(modeValue || "all");

  cy.startBatch();

  cy.edges().forEach((e) => {
    const t = e.data("type") || "";

    const show =
      mode === "all" ||
      (mode === "family" && isFamilyType(t)) ||
      (mode === "compadre" && isCompadreType(t));

    e.toggleClass("vd-hide", !show);
  });

  // hide isolated nodes (based on visible edges)
  cy.nodes().forEach((n) => {
    const visibleEdges = n.connectedEdges().filter((e) => !e.hasClass("vd-hide"));
    n.toggleClass("vd-hide", visibleEdges.length === 0);
  });

  cy.endBatch();

  // Keep focus if active, else fit
  if (FOCUS_NODE_ID) {
    const depth = parseInt(UI.egoDepth?.value || "1", 10) || 1;
    applyFocus(FOCUS_NODE_ID, depth);
  } else {
    fitLargestComponent(90);
  }

  const anyVisibleEdge = cy.edges().filter((e) => !e.hasClass("vd-hide")).length > 0;
  if (!anyVisibleEdge) showEmptyState();
  else hideEmptyState();
}

/* -----------------------------
   Init
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
  });

  cy.on("tap", (evt) => {
    if (evt.target === cy) closeTooltip();
  });
  cy.on("tap", "node", (evt) => showNodeTooltip(evt.target));
  cy.on("tap", "edge", (evt) => showEdgeTooltip(evt.target));

  setupResizeObserver();
}

/* -----------------------------
   Main
----------------------------- */

async function main() {
  if (!UI.container) throw new Error("Network container (#network) not found.");

  setLoading(true);

  const res = await fetch(DATA_PATH, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to load ${DATA_PATH} (HTTP ${res.status})`);
  NETWORK = await res.json();

  populatePersonSelect();

  const elements = buildElements();
  if (!elements.edges.length) {
    setLoading(false);
    showEmptyState();
    return;
  }

  initCytoscape(elements);

  // Run layout ONCE
  const layout = cy.layout(layoutOptions(elements.nodes.length, elements.edges.length));
  layout.run();

  // Fit after layout
  setTimeout(() => {
    if (!cy) return;
    fitLargestComponent(90);
    setLoading(false);
  }, 0);

  // Mode filter (fast, no relayout)
  UI.mode?.addEventListener("change", () => {
    clearFocus();
    applyTypeFilter(UI.mode.value);
  });

  // Fit toggles largest <-> all
  UI.fitBtn?.addEventListener("click", () => {
    if (!cy) return;
    closeTooltip();
    cy.resize();

    if (FOCUS_NODE_ID) {
      const depth = parseInt(UI.egoDepth?.value || "1", 10) || 1;
      applyFocus(FOCUS_NODE_ID, depth);
      return;
    }

    if (LAST_FIT_SCOPE === "largest") fitAll(60);
    else fitLargestComponent(90);
  });

  // Focus controls
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

  // initial filter
  applyTypeFilter(UI.mode?.value || "all");
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