/* =========================================================
   Varela Digital — Indexes browser
   File: /assets/scripts/indexes.js
   ========================================================= */

const PAGE_SIZE = 20;

let data = [];
let filtered = [];
let currentPage = 1;

const resultsDiv = document.getElementById("results");
const countInfo = document.getElementById("countInfo");

const searchInput = document.getElementById("searchInput");
const authorFilter = document.getElementById("authorFilter");
const recipientFilter = document.getElementById("recipientFilter");
const yearFilter = document.getElementById("yearFilter");
const placeFilter = document.getElementById("placeFilter");

const mentionedPeopleFilter = document.getElementById("mentionedPeopleFilter");
const mentionedPlacesFilter = document.getElementById("mentionedPlacesFilter");
const mentionedOrgsFilter = document.getElementById("mentionedOrgsFilter");
const mentionedEventsFilter = document.getElementById("mentionedEventsFilter");

const mutualExchangeToggle = document.getElementById("mutualExchangeToggle");

const prevBtn = document.getElementById("prevBtn");
const nextBtn = document.getElementById("nextBtn");

// Optional UI
const pageLinks = document.getElementById("pageLinks");
const clearBtn = document.getElementById("clearFiltersBtn");

function hasPageLinks() {
  return !!pageLinks;
}

function scrollToTopSmooth() {
  window.scrollTo({ top: 0, behavior: "smooth" });
}

/* -------------------------
   Load data
------------------------- */

fetch("../data/indexes/indexes.json")
  .then((res) => {
    if (!res.ok) throw new Error("Failed to load indexes.json");
    return res.json();
  })
  .then((json) => {
    data = Array.isArray(json) ? json : [];
    populateFilters();
    applyFilters(true);
  })
  .catch((err) => {
    resultsDiv.innerHTML = `<div class="alert alert-danger">${err.message}</div>`;
  });

/* -------------------------
   Helpers
------------------------- */

function normalizeText(s) {
  return (s || "").toString().toLowerCase();
}

function uniqueSorted(arr) {
  return [...new Set(arr.filter(Boolean))].sort((a, b) => a.localeCompare(b));
}

/**
 * Entities in JSON are expected as:
 *   { label: "...", uri: "..." }
 * But we keep backward compatibility with plain strings.
 * For filtering we prefer a stable key (URI if present, else label).
 */
function entityKey(e) {
  if (!e) return "";
  if (typeof e === "string") return e.trim();
  return (e.uri || e.label || "").trim();
}

function entityLabel(e) {
  if (!e) return "";
  if (typeof e === "string") return e.trim();
  return (e.label || e.uri || "").trim();
}

function listEntityKeys(list) {
  if (!Array.isArray(list)) return [];
  return list.map(entityKey).filter(Boolean);
}

function listEntityLabels(list) {
  if (!Array.isArray(list)) return [];
  return list.map(entityLabel).filter(Boolean);
}

function matchesQuery(d, q) {
  if (!q) return true;

  const hay = [
    d.cv_id,
    d.subject,
    d.author?.label,
    d.recipient?.label,
    d.place?.label,

    ...listEntityLabels(d.mentioned_people),
    ...listEntityLabels(d.mentioned_places),
    ...listEntityLabels(d.mentioned_orgs),
    ...listEntityLabels(d.mentioned_events),

    ...(Array.isArray(d.mentioned_dates) ? d.mentioned_dates : []),
  ].join(" ");

  return normalizeText(hay).includes(q);
}

function matchesMutualPair(d, a, b) {
  const author = d.author?.label || "";
  const rec = d.recipient?.label || "";
  return (author === a && rec === b) || (author === b && rec === a);
}

/* -------------------------
   Populate filters
------------------------- */

function populateFilters() {
  // Basic (label-only) filters
  uniqueSorted(data.map((d) => d.author?.label)).forEach((v) =>
    authorFilter.add(new Option(v, v))
  );

  uniqueSorted(data.map((d) => d.recipient?.label)).forEach((v) =>
    recipientFilter.add(new Option(v, v))
  );

  uniqueSorted(data.map((d) => d.place?.label)).forEach((v) =>
    placeFilter.add(new Option(v, v))
  );

  uniqueSorted(data.map((d) => (d.year ? String(d.year) : null))).forEach((v) =>
    yearFilter.add(new Option(v, v))
  );

  /**
   * Mentioned filters:
   * - show ALL labels (aliases) that occur for the same key
   * - store stable value (URI if present else label)
   *
   * This fixes: “Chico Pedro appears, but Moringue doesn’t”
   * when both share the same URI.
   */
  const peopleMap = new Map(); // key -> Set(labels)
  const placesMap = new Map();
  const orgsMap = new Map();
  const eventsMap = new Map();

  function addToMap(map, key, label) {
    if (!key || !label) return;
    if (!map.has(key)) map.set(key, new Set());
    map.get(key).add(label);
  }

  data.forEach((d) => {
    (d.mentioned_people || []).forEach((e) => addToMap(peopleMap, entityKey(e), entityLabel(e)));
    (d.mentioned_places || []).forEach((e) => addToMap(placesMap, entityKey(e), entityLabel(e)));
    (d.mentioned_orgs || []).forEach((e) => addToMap(orgsMap, entityKey(e), entityLabel(e)));
    (d.mentioned_events || []).forEach((e) => addToMap(eventsMap, entityKey(e), entityLabel(e)));
  });

  function populateMentionSelect(selectEl, map) {
    if (!selectEl) return;

    // Build flat list: [{key, label}, ...] (one per alias)
    const pairs = [];
    for (const [key, labelSet] of map.entries()) {
      for (const label of labelSet.values()) {
        pairs.push({ key, label });
      }
    }

    // Sort by visible label
    pairs.sort((a, b) => a.label.localeCompare(b.label));

    // Add options (same value may appear multiple times; that's OK)
    pairs.forEach(({ key, label }) => {
      selectEl.add(new Option(label, key));
    });
  }

  populateMentionSelect(mentionedPeopleFilter, peopleMap);
  populateMentionSelect(mentionedPlacesFilter, placesMap);
  populateMentionSelect(mentionedOrgsFilter, orgsMap);
  populateMentionSelect(mentionedEventsFilter, eventsMap);
}

/* -------------------------
   Filtering + rendering
------------------------- */

function applyFilters(resetPage = false) {
  if (resetPage) currentPage = 1;

  const q = normalizeText(searchInput.value);

  const a = authorFilter.value;
  const r = recipientFilter.value;
  const y = yearFilter.value;
  const p = placeFilter.value;

  const mpKey = mentionedPeopleFilter.value;
  const mplKey = mentionedPlacesFilter.value;
  const moKey = mentionedOrgsFilter ? mentionedOrgsFilter.value : "";
  const meKey = mentionedEventsFilter ? mentionedEventsFilter.value : "";

  const mutual = mutualExchangeToggle.checked;

  filtered = data.filter((d) => {
    // Mutual exchange logic (only meaningful if BOTH sender and recipient chosen)
    if (mutual && a && r) {
      if (!matchesMutualPair(d, a, r)) return false;
    } else {
      if (a && d.author?.label !== a) return false;
      if (r && d.recipient?.label !== r) return false;
    }

    if (y && String(d.year) !== y) return false;
    if (p && d.place?.label !== p) return false;

    if (mpKey && !listEntityKeys(d.mentioned_people).includes(mpKey)) return false;
    if (mplKey && !listEntityKeys(d.mentioned_places).includes(mplKey)) return false;
    if (moKey && !listEntityKeys(d.mentioned_orgs).includes(moKey)) return false;
    if (meKey && !listEntityKeys(d.mentioned_events).includes(meKey)) return false;

    if (!matchesQuery(d, q)) return false;

    return true;
  });

  renderPage();
}

function renderPage() {
  resultsDiv.innerHTML = "";

  const total = filtered.length;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  if (currentPage > totalPages) currentPage = totalPages;
  if (currentPage < 1) currentPage = 1;

  const startIdx = (currentPage - 1) * PAGE_SIZE;
  const endIdx = Math.min(startIdx + PAGE_SIZE, total);
  const pageItems = filtered.slice(startIdx, endIdx);

  if (pageItems.length === 0 && total > 0) {
    currentPage = 1;
    return renderPage();
  }

  pageItems.forEach((d) => {
    const div = document.createElement("div");
    div.className = "index-item";

    const place = d.place?.label ? d.place.label : "—";
    const date = d.date || "—";
    const author = d.author?.label || "—";
    const rec = d.recipient?.label || "—";

    div.innerHTML = `
      <div>
        <strong>${d.cv_id}</strong> — ${author} → ${rec}<br/>
        <span class="index-meta">${place}, ${date}</span><br/>
        <a href="${d.viewer_url}">Open in Viewer</a>
      </div>
    `;

    resultsDiv.appendChild(div);
  });

  if (total === 0) {
    countInfo.textContent = "No results";
  } else {
    const safeStart = Math.min(startIdx + 1, total);
    const safeEnd = Math.min(endIdx, total);
    countInfo.textContent = `Showing ${safeStart}–${safeEnd} of ${total} (page ${currentPage}/${totalPages})`;
  }

  prevBtn.disabled = currentPage <= 1;
  nextBtn.disabled = currentPage >= totalPages;

  if (hasPageLinks()) renderPageLinks(totalPages);
}

/* -------------------------
   Numeric pagination links
------------------------- */

function renderPageLinks(totalPages) {
  pageLinks.innerHTML = "";
  if (totalPages <= 1) return;

  const makeBtn = (label, page, { active = false } = {}) => {
    const a = document.createElement("a");
    a.href = "#";
    a.className = "page-link-btn" + (active ? " is-active" : "");
    a.textContent = label;

    a.addEventListener("click", (e) => {
      e.preventDefault();
      currentPage = page;
      renderPage();
      scrollToTopSmooth();
    });

    return a;
  };

  const makeEllipsis = () => {
    const span = document.createElement("span");
    span.className = "page-ellipsis";
    span.textContent = "…";
    return span;
  };

  const windowSize = 2; // current-2 .. current+2
  const start = Math.max(1, currentPage - windowSize);
  const end = Math.min(totalPages, currentPage + windowSize);

  pageLinks.appendChild(makeBtn("First", 1));

  if (start > 2) pageLinks.appendChild(makeEllipsis());

  for (let p = start; p <= end; p++) {
    pageLinks.appendChild(makeBtn(String(p), p, { active: p === currentPage }));
  }

  if (end < totalPages - 1) pageLinks.appendChild(makeEllipsis());

  pageLinks.appendChild(makeBtn("Last", totalPages));

  const next5 = Math.min(totalPages, currentPage + 5);
  if (next5 !== currentPage) pageLinks.appendChild(makeBtn("Next 5", next5));
}

/* -------------------------
   Clear filters
------------------------- */

function clearFilters() {
  if (searchInput) searchInput.value = "";

  [
    authorFilter,
    recipientFilter,
    yearFilter,
    placeFilter,
    mentionedPeopleFilter,
    mentionedPlacesFilter,
    mentionedOrgsFilter,
    mentionedEventsFilter,
  ].forEach((sel) => {
    if (sel) sel.value = "";
  });

  if (mutualExchangeToggle) mutualExchangeToggle.checked = false;

  applyFilters(true);
  scrollToTopSmooth();
}

if (clearBtn) {
  clearBtn.addEventListener("click", (e) => {
    e.preventDefault();
    clearFilters();
  });
}

/* -------------------------
   Events
------------------------- */

if (searchInput) searchInput.addEventListener("input", () => applyFilters(true));

[
  authorFilter,
  recipientFilter,
  yearFilter,
  placeFilter,
  mentionedPeopleFilter,
  mentionedPlacesFilter,
  mentionedOrgsFilter,
  mentionedEventsFilter,
  mutualExchangeToggle,
].forEach((el) => {
  if (!el) return;
  el.addEventListener("change", () => applyFilters(true));
});

prevBtn.addEventListener("click", () => {
  if (currentPage > 1) {
    currentPage--;
    renderPage();
    scrollToTopSmooth();
  }
});

nextBtn.addEventListener("click", () => {
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  if (currentPage < totalPages) {
    currentPage++;
    renderPage();
    scrollToTopSmooth();
  }
});