/* =========================================================
   Varela Digital — Organizations hierarchy (D3, TREE ONLY)
   File: assets/scripts/network_orgs.js

   Expects:
     - Container: #orgsTree

   Optional UI (if present):
     - #orgTypeFilter     (select: "all" or org @type)
     - #orgSearch         (input)
     - #expandAllBtn      (button)
     - #collapseAllBtn    (button)
     - #fitNetworkBtn     (button)
     - #resetBtn          (button)

   Data (TREE):
     - assets/data/network/network_orgs_tree.json
       { id, label, type?, children:[...] }
       OR { roots:[...] }
   ========================================================= */

const DATA_PATH = "../data/network/network_orgs_tree.json";

let RAW = null;       // loaded JSON
let ROOT_OBJ = null;  // normalized root {id,label,children:[]}

let svg = null;
let g = null;
let zoom = null;

let CURRENT_TYPE = "all";
let CURRENT_QUERY = "";

// Persist collapse state across rebuilds (key: nodeId)
const COLLAPSED = new Set();

const UI = {
  host: document.getElementById("orgsTree"),

  typeFilter: document.getElementById("orgTypeFilter"),
  search: document.getElementById("orgSearch"),

  expandAllBtn: document.getElementById("expandAllBtn"),
  collapseAllBtn: document.getElementById("collapseAllBtn"),

  fitBtn: document.getElementById("fitNetworkBtn"),
  resetBtn: document.getElementById("resetBtn"),
};

function debounce(fn, wait = 180) {
  let t = null;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), wait);
  };
}

function escapeHtml(str) {
  return String(str ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderFatal(msg) {
  if (!UI.host) return;
  UI.host.innerHTML = `<pre class="p-3 text-danger">${escapeHtml(msg)}</pre>`;
}

/* =========================================================
   D3 guard
========================================================= */

function ensureD3() {
  if (typeof window.d3 === "undefined") {
    throw new Error(
      "D3 not found. Add this to your HTML BEFORE network_orgs.js:\n" +
        '<script src="https://unpkg.com/d3@7/dist/d3.min.js"></script>'
    );
  }
  return window.d3;
}

/* =========================================================
   Normalize tree root
========================================================= */

function isTree(obj) {
  if (!obj || typeof obj !== "object" || Array.isArray(obj)) return false;
  if (Array.isArray(obj.children)) return true;
  if (Array.isArray(obj.roots)) return true;
  return false;
}

function toRootTree(data) {
  if (!isTree(data)) {
    return { id: "vd_orgs_root", label: "Organizations", type: "root", children: [] };
  }

  if (Array.isArray(data.roots)) {
    return { id: "vd_orgs_root", label: "Organizations", type: "root", children: data.roots };
  }

  if (data.id && Array.isArray(data.children)) return data;

  return { id: "vd_orgs_root", label: "Organizations", type: "root", children: [] };
}

/* =========================================================
   Filtering
========================================================= */

function nodeMatchesType(n) {
  if (CURRENT_TYPE === "all") return true;
  return String(n.type || "").toLowerCase() === String(CURRENT_TYPE).toLowerCase();
}

function nodeMatchesQuery(n) {
  const q = CURRENT_QUERY.trim().toLowerCase();
  if (!q) return true;
  const hay = `${n.label || ""} ${n.id || ""}`.toLowerCase();
  return hay.includes(q);
}

// keep node if matches OR descendant matches
function filterTree(node) {
  if (!node) return null;

  const kids = (node.children || []).map(filterTree).filter(Boolean);

  const selfOk =
    node.id === "vd_orgs_root" ? true : nodeMatchesType(node) && nodeMatchesQuery(node);

  if (selfOk || kids.length) return { ...node, children: kids };
  return null;
}

/* =========================================================
   Collapse state
========================================================= */

function collapseByDefault(d3root) {
  // collapse from depth >= 2 (keeps top levels visible)
  d3root.each((d) => {
    if (d.depth >= 2) {
      const id = d.data?.id;
      if (id) COLLAPSED.add(id);
    }
  });
}

function applyCollapseState(d3root) {
  d3root.each((d) => {
    if (d.depth === 0) return;
    const id = d.data?.id;
    if (!id) return;

    if (COLLAPSED.has(id) && d.children) {
      d._children = d.children;
      d.children = null;
    } else if (!COLLAPSED.has(id) && d._children) {
      d.children = d._children;
      d._children = null;
    }
  });
}

/* =========================================================
   SVG setup + layout + fit
========================================================= */

function setupSvg(d3) {
  UI.host.innerHTML = "";

  const { width, height } = UI.host.getBoundingClientRect();

  svg = d3
    .select(UI.host)
    .append("svg")
    .attr("width", width)
    .attr("height", height)
    .attr("role", "img")
    .attr("aria-label", "Organizations hierarchy");

  g = svg.append("g").attr("class", "vd-orgs-g");

  zoom = d3
    .zoom()
    .scaleExtent([0.2, 3])
    .on("zoom", (event) => g.attr("transform", event.transform));

  svg.call(zoom);
  svg.on("dblclick.zoom", null);
}

function computeLayout(d3, d3root) {
  // left-to-right tree
  const tree = d3.tree().nodeSize([22, 210]);
  tree(d3root);
  return d3root;
}

function fitToContent(d3, padding = 24) {
  if (!svg || !g) return;

  const bounds = g.node().getBBox();
  const host = UI.host.getBoundingClientRect();
  if (!bounds.width || !bounds.height) return;

  const fullW = host.width;
  const fullH = host.height;

  const scaleX = (fullW - padding * 2) / bounds.width;
  const scaleY = (fullH - padding * 2) / bounds.height;
  const scale = Math.min(2.5, Math.max(0.2, Math.min(scaleX, scaleY)));

  const tx = (fullW - bounds.width * scale) / 2 - bounds.x * scale;
  const ty = (fullH - bounds.height * scale) / 2 - bounds.y * scale;

  svg
    .transition()
    .duration(250)
    .call(zoom.transform, d3.zoomIdentity.translate(tx, ty).scale(scale));
}

/* =========================================================
   Render
========================================================= */

function drawTree(rootObj) {
  const d3 = ensureD3();
  setupSvg(d3);

  const pruned = filterTree(rootObj) || {
    id: "vd_orgs_root",
    label: "Organizations",
    type: "root",
    children: [],
  };

  const d3root = d3.hierarchy(pruned);

  // if no saved state yet, apply default collapsing
  if (COLLAPSED.size === 0) collapseByDefault(d3root);

  applyCollapseState(d3root);
  computeLayout(d3, d3root);

  const link = d3
    .linkHorizontal()
    .x((d) => d.y)
    .y((d) => d.x);

  // Links
  g.append("g")
    .attr("class", "vd-org-links")
    .selectAll("path")
    .data(d3root.links())
    .join("path")
    .attr("class", "vd-org-link")
    .attr("d", (d) => link(d));

  // Nodes
  const nodes = g
    .append("g")
    .attr("class", "vd-org-nodes")
    .selectAll("g")
    .data(d3root.descendants())
    .join("g")
    .attr("class", (d) => (d.depth === 0 ? "vd-org-node vd-org-root" : "vd-org-node"))
    .attr("transform", (d) => `translate(${d.y},${d.x})`);

  nodes
    .append("circle")
    .attr("r", (d) => (d.depth === 0 ? 6 : 5))
    .attr("class", (d) => (d._children ? "vd-org-dot vd-org-collapsed" : "vd-org-dot"))
    .style("cursor", (d) => (d.depth === 0 ? "default" : "pointer"))
    .on("click", (event, d) => {
      if (d.depth === 0) return;

      const id = d.data?.id;
      if (!id) return;

      if (COLLAPSED.has(id)) COLLAPSED.delete(id);
      else COLLAPSED.add(id);

      rebuild();
    });

  nodes
    .append("text")
    .attr("dy", "0.32em")
    .attr("x", 10)
    .attr("text-anchor", "start")
    .text((d) => d.data.label || d.data.id);

  nodes
    .append("title")
    .text((d) => {
      const id = d.data.id || "";
      const type = d.data.type ? `\nType: ${d.data.type}` : "";
      return `${d.data.label || id}\n${id}${type}`;
    });

  fitToContent(d3);
}

/* =========================================================
   UI helpers
========================================================= */

function populateTypeFilter(rootObj) {
  if (!UI.typeFilter) return;

  const types = new Set();
  const walk = (n) => {
    if (!n) return;
    if (n.type && n.id !== "vd_orgs_root") types.add(String(n.type));
    (n.children || []).forEach(walk);
  };
  walk(rootObj);

  const sorted = Array.from(types).sort((a, b) => a.localeCompare(b, "pt-BR"));
  const prev = UI.typeFilter.value || "all";

  UI.typeFilter.innerHTML =
    `<option value="all">All types</option>` +
    sorted.map((t) => `<option value="${escapeHtml(t)}">${escapeHtml(t)}</option>`).join("");

  UI.typeFilter.value = sorted.includes(prev) ? prev : "all";
}

function setupResizeObserver() {
  if (!UI.host || typeof ResizeObserver === "undefined") return;

  const d3 = ensureD3();
  const ro = new ResizeObserver(
    debounce(() => {
      if (!svg) return;
      const { width, height } = UI.host.getBoundingClientRect();
      svg.attr("width", width).attr("height", height);
      fitToContent(d3);
    }, 140)
  );

  ro.observe(UI.host);
}

function rebuild() {
  if (!ROOT_OBJ) return;
  drawTree(ROOT_OBJ);
}

/* =========================================================
   Main
========================================================= */

async function main() {
  if (!UI.host) throw new Error("Missing container #orgsTree");
  ensureD3();

  const res = await fetch(DATA_PATH, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to load ${DATA_PATH} (HTTP ${res.status})`);

  RAW = await res.json();
  ROOT_OBJ = toRootTree(RAW);

  populateTypeFilter(ROOT_OBJ);

  rebuild();
  setupResizeObserver();

  UI.typeFilter?.addEventListener("change", () => {
    CURRENT_TYPE = UI.typeFilter.value || "all";
    rebuild();
  });

  UI.search?.addEventListener(
    "input",
    debounce(() => {
      CURRENT_QUERY = UI.search.value || "";
      rebuild();
    }, 220)
  );

  UI.expandAllBtn?.addEventListener("click", () => {
    COLLAPSED.clear();
    rebuild();
  });

  UI.collapseAllBtn?.addEventListener("click", () => {
    // collapse everything except root
    const d3 = ensureD3();
    const pruned = filterTree(ROOT_OBJ) || ROOT_OBJ;
    const tmp = d3.hierarchy(pruned);

    COLLAPSED.clear();
    tmp.each((d) => {
      if (d.depth >= 1) {
        const id = d.data?.id;
        if (id) COLLAPSED.add(id);
      }
    });

    rebuild();
  });

  UI.fitBtn?.addEventListener("click", () => {
    const d3 = ensureD3();
    fitToContent(d3);
  });

  UI.resetBtn?.addEventListener("click", () => {
    CURRENT_TYPE = "all";
    CURRENT_QUERY = "";
    COLLAPSED.clear();

    if (UI.typeFilter) UI.typeFilter.value = "all";
    if (UI.search) UI.search.value = "";

    rebuild();
  });
}

main().catch((err) => {
  console.error(err);
  renderFatal(err?.message ? err.message : String(err));
});