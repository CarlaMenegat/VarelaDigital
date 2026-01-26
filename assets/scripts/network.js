/* =========================================================
   Varela Digital — Social Network (Cytoscape)
   Source: data/network/network_people.json
   ========================================================= */

const DATA_PATH = "../../data/network/network_people.json";
const VIEWER_PATTERN = "viewer.html?file={cv}.xml";

let NETWORK = null;
let cy = null;

// focus state
let FOCUS_NODE_ID = null;

// Track what "fit" is showing (largest vs all)
let LAST_FIT_SCOPE = "largest"; // "largest" | "all"

// keep one observer (desktop layout changes / sidebar scrollbars, etc.)
let RESIZE_OBSERVER = null;

function debounce(fn, wait = 160) {
  let t = null;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), wait);
  };
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
   Build elements
----------------------------- */

function buildElements(mode, minWeight) {
  const used = new Set();
  const wanted = normalizeType(mode);

  const edgesRaw = (NETWORK.edges || []).map((e) => ({
    ...e,
    type: normalizeType(e.type),
    weight: typeof e.weight === "number" ? e.weight : parseInt(e.weight || "1", 10) || 1,
  }));

  const edges = edgesRaw
    .filter((e) => e.type === wanted)
    .filter((e) => (e.weight || 0) >= minWeight)
    .map((e) => {
      used.add(e.source);
      used.add(e.target);
      return {
        data: {
          id: e.id || `${e.source}__${e.target}__${e.type}`,
          type: e.type,
          source: e.source,
          target: e.target,
          weight: e.weight || 1,
          directed: !!e.directed,
          evidence: Array.isArray(e.evidence) ? e.evidence : [],
        },
      };
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
   Layout tuning
   - The biggest practical gain for “amontoado” is:
     1) nodeRepulsion + nodeOverlap
     2) nodeDimensionsIncludeLabels (layout considers labels)
     3) spacingFactor for extra separation
----------------------------- */

function layoutFor(mode, nodeCount, edgeCount) {
  const isCo = normalizeType(mode) === "comention";
  const dense = nodeCount > 220 || edgeCount > 800;
  const veryDense = nodeCount > 380 || edgeCount > 1600;

  // Stronger repulsion + overlap padding
  const baseRepulsion = isCo ? 65000 : 28000;
  const repulsion = veryDense ? baseRepulsion * 1.3 : dense ? baseRepulsion * 1.15 : baseRepulsion;

  const baseEdge = isCo ? 260 : 200;
  const edgeLen = veryDense ? baseEdge * 1.08 : baseEdge;

  const iter = veryDense ? 750 : dense ? 1000 : 1200;

  return {
    name: "cose",
    animate: false,
    randomize: true,

    // Key “de-amontoar” knobs:
    nodeRepulsion: repulsion,
    nodeOverlap: 18, // padding between nodes (helps a lot)
    idealEdgeLength: edgeLen,
    edgeElasticity: isCo ? 0.18 : 0.16,
    gravity: isCo ? 0.03 : 0.04,
    componentSpacing: isCo ? 360 : 190,
    spacingFactor: isCo ? 1.35 : 1.2,

    // Make layout account for label size (important when many names)
    nodeDimensionsIncludeLabels: true,

    numIter: iter,

    // Cooling (keeps it from “collapsing” too early)
    initialTemp: 2000,
    coolingFactor: 0.99,
    minTemp: 1.0,
  };
}

/* -----------------------------
   Cytoscape style
   FIX: remove maroon edges; use neutral grays
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

  // Base edges: neutral gray (no brown)
  {
    selector: "edge",
    style: {
      width: "mapData(weight, 1, 20, 1, 6)",
      "curve-style": "bezier",

      "line-color": "rgba(0,0,0,0.24)",
      "target-arrow-color": "rgba(0,0,0,0.24)",

      // directed only shows arrow if we keep triangle; we will remove for co-mentions below
      "target-arrow-shape": "triangle",
      "arrow-scale": 0.8,

      opacity: 0.85,
    },
  },

  // Co-mentions: still gray, no arrow, slightly lighter
  {
    selector: 'edge[type="comention"]',
    style: {
      "target-arrow-shape": "none",
      "line-color": "rgba(0,0,0,0.20)",
      opacity: 0.78,
    },
  },

  // Hover: darker gray for feedback
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
   Smart fit: largest component vs all
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
    pixelRatio: 1, // stable rendering on retina; bump to 2 if you prefer crisp lines
    boxSelectionEnabled: false,
    selectionType: "single",
  });

  cy.on("tap", (evt) => {
    if (evt.target === cy) closeTooltip();
  });
  cy.on("tap", "node", (evt) => showNodeTooltip(evt.target));
  cy.on("tap", "edge", (evt) => showEdgeTooltip(evt.target));

  // Keep Cytoscape synced with container size (critical on desktop app layouts)
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

        // don’t explode user’s current zoom/pan if they are exploring:
        // only “re-fit” when we’re not focused and we previously fit largest.
        if (!FOCUS_NODE_ID && LAST_FIT_SCOPE === "largest") {
          fitLargestComponent(90);
        }
      }, 120)
    );

    RESIZE_OBSERVER.observe(UI.container);
  } catch (e) {
    // ResizeObserver not supported — ignore
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

  // Safety fallback (dense layouts can stall on some machines)
  setTimeout(finish, normalizeType(mode) === "comention" ? 7000 : 5000);

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

  cy.resize();
  runLayout(mode, elements, onDone);
}

/* -----------------------------
   Node sizing
----------------------------- */

function updateNodeSizesByDegree() {
  if (!cy) return;
  const degs = cy.nodes().map((n) => n.degree());
  const maxDeg = Math.max(1, ...degs);

  cy.nodes().forEach((n) => {
    const d = n.degree();
    // 9..24 (slightly larger = readable without insane zoom)
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
   Person SELECT population
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
   Refresh
----------------------------- */

function refresh() {
  const mode = UI.mode?.value || "correspondence";
  const minWeight = Math.max(1, parseInt(UI.minWeight?.value || "1", 10));
  setWeightBadges(minWeight);

  closeTooltip();
  setLoading(true);

  requestAnimationFrame(() => {
    const elements = buildElements(mode, minWeight);

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

    updateGraph(elements, mode, () => {
      if (!cy) {
        setLoading(false);
        return;
      }

      updateNodeSizesByDegree();

      // Re-apply focus if any
      if (FOCUS_NODE_ID) {
        const depth = parseInt(UI.egoDepth?.value || "1", 10) || 1;
        applyFocus(FOCUS_NODE_ID, depth);
      } else {
        // Default: show the largest component (readable),
        // not “everything” (which makes it microscopic).
        fitLargestComponent(90);
      }

      setLoading(false);
    });
  });
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

  populatePersonSelect();

  UI.mode?.addEventListener("change", () => {
    clearFocus();
    refresh();
  });

  UI.minWeight?.addEventListener(
    "input",
    debounce(() => {
      clearFocus();
      refresh();
    }, 190)
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