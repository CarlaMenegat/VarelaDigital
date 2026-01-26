console.log("map.js loaded");

const INDEXES_URL = "../data/indexes/indexes.json";
const STANDOFF_PLACES_URL = "../data/standoff/standoff_places.xml";
const ALIGNMENTS_URL = "../data/indexes/alignments.json";

const mapModeSelect = document.getElementById("mapMode");
const yearFilter = document.getElementById("yearFilter");
const senderFilter = document.getElementById("senderFilter");
const recipientFilter = document.getElementById("recipientFilter");
const alignmentFilter = document.getElementById("alignmentFilter"); // NEW (HTML)
const mutualExchangeToggle = document.getElementById("mutualExchangeToggle");
const clearBtn = document.getElementById("clearFiltersBtn");

const docCountEl = document.getElementById("docCount");
const placeCountEl = document.getElementById("placeCount");
const missingGeoCountEl = document.getElementById("missingGeoCount");

const yearPlayProgressEl = document.getElementById("yearPlayProgress");
const yearPlayLabelEl = document.getElementById("yearPlayLabel");

/**
 * IMPORTANT:
 * Supports BOTH old and new IDs for threshold UI.
 */
const thresholdFilter =
  document.getElementById("minDocsThreshold") || document.getElementById("thresholdFilter");

const thresholdValueEl =
  document.getElementById("minDocsThresholdValue") || document.getElementById("thresholdValue");

const thresholdValueInlineEl =
  document.getElementById("thresholdValueInline") ||
  document.getElementById("minDocsThresholdValueInline");

const mentionedTypeFilter = document.getElementById("mentionedTypeFilter");

const playYearsBtn = document.getElementById("playYearsBtn");
const stopYearsBtn = document.getElementById("stopYearsBtn");

let DATA = [];
let FILTERED = [];
let PLACES_GEO = { labelIndex: new Map() };

let ALIGNMENTS = { byUri: {}, meta: {} }; // NEW

let MAP = null;
let LAYER = null;
let LEGEND = null;

let YEAR_TIMER = null;

let YEAR_OPTIONS = [];
let YEAR_INDEX = 0;
const YEAR_INTERVAL_MS = 1700; // adjust speed here

/* =========================================================
   Utils
   ========================================================= */

function normalizeText(s) {
  return (s || "").toString().trim().toLowerCase();
}

function uniqueSorted(arr) {
  return [...new Set(arr.filter(Boolean))].sort((a, b) =>
    a.localeCompare(b, undefined, { sensitivity: "base" })
  );
}

function getEntityLabel(entity) {
  if (!entity) return "";
  if (typeof entity === "object") return (entity.label || entity.uri || "").toString().trim();
  const s = entity.toString();
  if (s.includes("|")) return s.split("|")[0].trim();
  return s.trim();
}

function parseYearFromISO(dateStr) {
  const s = (dateStr || "").toString().trim();
  if (!s) return "";
  const m = s.match(/^(\d{4})/);
  return m ? m[1] : "";
}

function getDocYear(d) {
  const y = d?.year ? String(d.year) : parseYearFromISO(d?.date);
  return y && /^\d{4}$/.test(y) ? y : "";
}

/* =========================================================
   Author / Recipient helpers (label for UI, uri for match)
   ========================================================= */

function getAuthorValue(d) {
  const v =
    (typeof d?.author === "string" ? d.author : "") ||
    d?.author?.label ||
    d?.author_name ||
    d?.sender ||
    d?.sender_name ||
    d?.from ||
    d?.from_name ||
    d?.corresp?.sender ||
    "";
  return (v || "").toString().trim();
}

function getAuthorUri(d) {
  const v =
    (typeof d?.author === "object" ? d?.author?.uri : "") ||
    d?.author_uri ||
    d?.from_uri ||
    d?.sender_uri ||
    "";
  return (v || "").toString().trim();
}

function getRecipientValue(d) {
  const v =
    (typeof d?.recipient === "string" ? d.recipient : "") ||
    d?.recipient?.label ||
    d?.recipient_name ||
    d?.addressee?.label ||
    d?.addressee_name ||
    d?.to ||
    d?.to_name ||
    d?.corresp?.recipient ||
    "";
  return (v || "").toString().trim();
}

function getRecipientUri(d) {
  const v =
    (typeof d?.recipient === "object" ? d?.recipient?.uri : "") ||
    d?.recipient_uri ||
    d?.to_uri ||
    d?.addressee_uri ||
    "";
  return (v || "").toString().trim();
}

function matchesMutualPair(d, a, b) {
  const author = getAuthorValue(d);
  const rec = getRecipientValue(d);
  return (author === a && rec === b) || (author === b && rec === a);
}

/* =========================================================
   Map helpers
   ========================================================= */

function safeLatLng(lat, lon) {
  const la = Number(lat);
  const lo = Number(lon);
  if (!Number.isFinite(la) || !Number.isFinite(lo)) return null;
  if (Math.abs(la) > 90 || Math.abs(lo) > 180) return null;
  return [la, lo];
}

function getSendingLatLng(d) {
  const latRaw = d?.place?.lat ?? d?.lat;
  const lonRaw = d?.place?.long ?? d?.long;
  return safeLatLng(latRaw, lonRaw);
}

function getSendingLabel(d) {
  return d?.place?.label || d?.place_label || "Sending place";
}

function ensureOverlays() {
  const mapEl = document.getElementById("map");
  if (!mapEl) return;

  if (!mapEl.querySelector(".map-wash")) {
    const wash = document.createElement("div");
    wash.className = "map-wash";
    mapEl.appendChild(wash);
  }

  if (!mapEl.querySelector(".map-paper")) {
    const paper = document.createElement("div");
    paper.className = "map-paper";
    mapEl.appendChild(paper);
  }
}

/* =========================================================
   Init Leaflet
   ========================================================= */

function initMap() {
  MAP = L.map("map", { zoomControl: true });

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(MAP);

  LAYER = L.layerGroup().addTo(MAP);
  MAP.setView([-30.0, -53.0], 6);
  ensureOverlays();
}

/* =========================================================
   Loaders
   ========================================================= */

async function loadStandoffPlaces() {
  const res = await fetch(STANDOFF_PLACES_URL);
  if (!res.ok) throw new Error(`Failed to load ${STANDOFF_PLACES_URL}`);

  const xmlText = await res.text();
  const parser = new DOMParser();
  const xml = parser.parseFromString(xmlText, "application/xml");

  const placeEls = Array.from(xml.getElementsByTagNameNS("http://www.tei-c.org/ns/1.0", "place"));

  placeEls.forEach((pl) => {
    const geoEl = pl.getElementsByTagNameNS("http://www.tei-c.org/ns/1.0", "geo")[0];
    if (!geoEl) return;

    const geo = (geoEl.textContent || "").trim().replace(",", " ");
    const parts = geo.split(/\s+/).filter(Boolean);
    if (parts.length < 2) return;

    const ll = safeLatLng(parts[0], parts[1]);
    if (!ll) return;

    const placeNameEls = Array.from(
      pl.getElementsByTagNameNS("http://www.tei-c.org/ns/1.0", "placeName")
    );

    const labels = placeNameEls.map((n) => (n.textContent || "").trim()).filter(Boolean);
    if (labels.length === 0) return;

    const canonicalLabel = labels[0];

    labels.forEach((lab) => {
      const k = normalizeText(lab);
      if (!k) return;
      if (!PLACES_GEO.labelIndex.has(k)) {
        PLACES_GEO.labelIndex.set(k, { label: canonicalLabel, lat: ll[0], lon: ll[1] });
      }
    });
  });
}

async function loadAlignments() {
  const res = await fetch(ALIGNMENTS_URL);
  if (!res.ok) {
    console.warn("Could not load alignments:", ALIGNMENTS_URL);
    return;
  }
  const json = await res.json();
  if (json && typeof json === "object") {
    ALIGNMENTS = {
      byUri: json.byUri || {},
      meta: json.meta || {},
    };
  }
}

/* =========================================================
   UI helpers
   ========================================================= */

function getThresholdValue() {
  if (!thresholdFilter) return 1;
  const v = Number(thresholdFilter.value);
  return Number.isFinite(v) && v >= 1 ? Math.floor(v) : 1;
}

function syncThresholdUI() {
  const v = getThresholdValue();
  if (thresholdValueEl) thresholdValueEl.textContent = String(v);
  if (thresholdValueInlineEl) thresholdValueInlineEl.textContent = String(v);
}

function initTooltips() {
  const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
  tooltipTriggerList.forEach((el) => {
    new bootstrap.Tooltip(el);
  });
}

function getMentionedTypeValue() {
  if (!mentionedTypeFilter) return "all";
  return (mentionedTypeFilter.value || "all").toString().trim().toLowerCase();
}

function docMatchesMentionedType(d, t) {
  if (!t || t === "all") return true;
  if (t === "people") return Array.isArray(d.mentioned_people) && d.mentioned_people.length > 0;
  if (t === "orgs") return Array.isArray(d.mentioned_orgs) && d.mentioned_orgs.length > 0;
  if (t === "events") return Array.isArray(d.mentioned_events) && d.mentioned_events.length > 0;
  if (t === "places") return Array.isArray(d.mentioned_places) && d.mentioned_places.length > 0;
  return true;
}

/* =========================================================
   Alignment filter (sender OR recipient)
   alignments.json expected shape:
   {
     "byUri": {
       "https://.../person/antonio_abreu": {
         "timeline": [
           { "side":"farroupilha", "from":"1835-01-01", "to":"1845-12-31" },
           { "side":"imperio", "from":"1846-01-01", "to":"9999-12-31" }
         ]
       }
     }
   }
   ========================================================= */

function populateAlignmentFilter() {
  if (!alignmentFilter) return;

  // Keep existing placeholder if already in HTML
  const existing = new Set(Array.from(alignmentFilter.options).map((o) => o.value));

  const opts = [
    { value: "", label: "All alignments" },
    { value: "farroupilha", label: "Farroupilha (sender OR recipient)" },
    { value: "imperio", label: "Império (sender OR recipient)" },
    { value: "mixed", label: "Mixed / switched (sender OR recipient)" },
    { value: "unknown", label: "Unknown / not aligned" },
  ];

  opts.forEach((o) => {
    if (!existing.has(o.value)) alignmentFilter.add(new Option(o.label, o.value));
  });
}

function getTimelineForUri(uri) {
  const u = (uri || "").toString().trim();
  if (!u) return [];
  const rec = ALIGNMENTS.byUri?.[u];
  const tl = rec?.timeline;
  return Array.isArray(tl) ? tl : [];
}

function sideAtYear(timeline, year) {
  if (!year || !Array.isArray(timeline) || timeline.length === 0) return "";

  // compare ISO strings; use YYYY-01-01 probe
  const probe = `${year}-01-01`;

  for (const seg of timeline) {
    const side = (seg?.side || "").toString().trim().toLowerCase();
    const from = (seg?.from || "").toString().trim();
    const to = (seg?.to || "").toString().trim();
    if (!side || !from || !to) continue;
    if (from <= probe && probe <= to) return side; // inclusive
  }
  return "";
}

function docMatchesAlignment(d, selected) {
  const s = (selected || "").toString().trim().toLowerCase();
  if (!s) return true; // All

  const year = getDocYear(d);

  const aUri = getAuthorUri(d);
  const rUri = getRecipientUri(d);

  const aSide = sideAtYear(getTimelineForUri(aUri), year);
  const rSide = sideAtYear(getTimelineForUri(rUri), year);

  const hasA = !!aSide;
  const hasR = !!rSide;

  if (s === "unknown") return !hasA && !hasR;

  if (s === "mixed") {
    if (aSide === "mixed" || rSide === "mixed") return true;
    if (hasA && hasR && aSide !== rSide) return true; // one each side
    return false;
  }

  // "imperio" or "farroupilha": sender OR recipient
  return aSide === s || rSide === s;
}

/* =========================================================
   Filters population
   ========================================================= */

function populateFilters() {
  const years = DATA.map((d) => getDocYear(d)).filter(Boolean);
  uniqueSorted(years).forEach((y) => yearFilter?.add(new Option(y, y)));

  uniqueSorted(DATA.map((d) => getAuthorValue(d))).forEach((v) => {
    senderFilter?.add(new Option(v, v));
  });

  uniqueSorted(DATA.map((d) => getRecipientValue(d))).forEach((v) => {
    recipientFilter?.add(new Option(v, v));
  });
}

/* =========================================================
   Apply filters
   ========================================================= */

function applyFilters(resetView = false) {
  const mode = mapModeSelect ? mapModeSelect.value : "sending";
  const y = yearFilter ? yearFilter.value : "";
  const a = senderFilter ? senderFilter.value : "";
  const r = recipientFilter ? recipientFilter.value : "";
  const mutual = mutualExchangeToggle ? mutualExchangeToggle.checked : false;

  const mentionedType = getMentionedTypeValue();
  const selectedAlignment = alignmentFilter ? (alignmentFilter.value || "").toString().trim() : "";

  FILTERED = DATA.filter((d) => {
    if (mutual && a && r) {
      if (!matchesMutualPair(d, a, r)) return false;
    } else {
      if (a && getAuthorValue(d) !== a) return false;
      if (r && getRecipientValue(d) !== r) return false;
    }

    if (y) {
      const dy = getDocYear(d);
      if (dy !== y) return false;
    }

    if (!docMatchesMentionedType(d, mentionedType)) return false;

    if (selectedAlignment) {
      if (!docMatchesAlignment(d, selectedAlignment)) return false;
    }

    return true;
  });

  renderMap(mode, resetView);
}

/* =========================================================
   Map rendering
   ========================================================= */

function clearLayer() {
  if (LAYER) LAYER.clearLayers();
}

function buildPopupHTML(placeLabel, docs) {
  const total = docs.length;
  const maxList = 20;
  const slice = docs.slice(0, maxList);

  const listItems = slice
    .map((d) => {
      const id = d.cv_id || "—";
      const url = d.viewer_url || "";
      return url ? `<li><a href="${url}">${id}</a></li>` : `<li>${id}</li>`;
    })
    .join("");

  const more = total > maxList ? `<div class="vd-popup-meta">…and ${total - maxList} more</div>` : "";

  return `
    <div class="vd-popup">
      <h6>${placeLabel}</h6>
      <div class="vd-popup-meta">${total} document(s)</div>
      <ul>${listItems}</ul>
      ${more}
    </div>
  `;
}

function upsertLegend(mode, stats) {
  if (!MAP) return;

  const thresholdText = stats.threshold && stats.threshold > 1 ? ` · ≥ ${stats.threshold}` : "";

  const content = (() => {
    if (mode === "sending") {
      return `
        <div style="display:flex;align-items:center;gap:.5rem;">
          <span style="width:12px;height:12px;border-radius:50%;background:#4E7A5A;border:1px solid rgba(0,0,0,.35);display:inline-block;"></span>
          <span>Sending places</span>
        </div>
        <div style="margin-top:.35rem;opacity:.8;font-size:.9rem;">
          ${stats.plotted} plotted${thresholdText}
        </div>
      `;
    }
    if (mode === "mentioned") {
      return `
        <div style="display:flex;align-items:center;gap:.5rem;">
          <span style="width:12px;height:12px;border-radius:50%;background:#B56A5A;border:1px solid rgba(0,0,0,.35);display:inline-block;"></span>
          <span>Mentioned places</span>
        </div>
        <div style="margin-top:.35rem;opacity:.8;font-size:.9rem;">
          ${stats.plotted} plotted${thresholdText}
        </div>
      `;
    }
    return `
      <div style="display:flex;align-items:center;gap:.5rem;">
        <span style="width:12px;height:12px;border-radius:50%;background:#6B6B6B;border:1px solid rgba(0,0,0,.35);display:inline-block;"></span>
        <span>All places</span>
      </div>
      <div style="margin-top:.35rem;opacity:.8;font-size:.9rem;">
        ${stats.plotted} plotted${thresholdText}
      </div>
    `;
  })();

  if (!LEGEND) {
    LEGEND = L.control({ position: "bottomright" });
    LEGEND.onAdd = function () {
      const div = L.DomUtil.create("div", "vd-map-legend");
      div.style.background = "rgba(253,253,251,.92)";
      div.style.border = "1px solid rgba(0,0,0,.08)";
      div.style.borderRadius = "12px";
      div.style.padding = ".6rem .75rem";
      div.style.boxShadow = "0 10px 24px rgba(0,0,0,0.16)";
      div.style.fontSize = ".95rem";
      div.style.color = "#2f3b2c";
      div.innerHTML = content;
      return div;
    };
    LEGEND.addTo(MAP);
  } else {
    const el = document.querySelector(".vd-map-legend");
    if (el) el.innerHTML = content;
  }
}

function renderMap(mode, resetView) {
  clearLayer();

  let missingGeo = 0;
  const threshold = getThresholdValue();

  const bucketsSending = new Map();
  const bucketsMentioned = new Map();
  const bucketsAll = new Map();

  const addBucket = (buckets, label, lat, lon, doc) => {
    const key = `${lat},${lon}`;
    if (!buckets.has(key)) buckets.set(key, { label, lat, lon, docs: [] });
    buckets.get(key).docs.push(doc);
  };

  FILTERED.forEach((d) => {
    // Sending
    const llSend = getSendingLatLng(d);
    if (llSend) {
      if (mode === "sending") addBucket(bucketsSending, getSendingLabel(d), llSend[0], llSend[1], d);
      if (mode === "all") addBucket(bucketsAll, getSendingLabel(d), llSend[0], llSend[1], d);
    } else {
      if (d?.place?.label || d?.place_label) missingGeo++;
    }

    // Mentioned places
    const mentioned = Array.isArray(d.mentioned_places) ? d.mentioned_places : [];
    mentioned.forEach((ent) => {
      const lab = getEntityLabel(ent);
      const k = normalizeText(lab);
      if (!k) return;

      const geo = PLACES_GEO.labelIndex.get(k);
      if (!geo) {
        missingGeo++;
        return;
      }

      if (mode === "mentioned") addBucket(bucketsMentioned, geo.label, geo.lat, geo.lon, d);
      if (mode === "all") addBucket(bucketsAll, geo.label, geo.lat, geo.lon, d);
    });
  });

  // In "all", dedupe docs inside each bucket
  if (mode === "all") {
    bucketsAll.forEach((b) => {
      const seen = new Set();
      b.docs = b.docs.filter((doc) => {
        const id = doc?.cv_id || doc?.text_file || "";
        const key = id || JSON.stringify(doc);
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      });
    });
  }

  const bounds = [];
  let plotted = 0;

  const makeMarker = (b, fill, className) => {
    if (b.docs.length < threshold) return;

    const marker = L.circleMarker([b.lat, b.lon], {
      radius: Math.max(5, Math.min(18, 4 + Math.log2(b.docs.length + 1) * 3)),
      weight: 1,
      color: "rgba(32, 48, 35, 0.55)",
      fillColor: fill,
      fillOpacity: 0.68,
      className,
    });

    marker.bindPopup(buildPopupHTML(b.label, b.docs), { maxWidth: 340 });
    marker.addTo(LAYER);

    bounds.push([b.lat, b.lon]);
    plotted += 1;
  };

  const SENDING_FILL = "#4E7A5A";
  const MENTIONED_FILL = "#B56A5A";
  const ALL_FILL = "#6B6B6B";

  if (mode === "sending") {
    bucketsSending.forEach((b) => makeMarker(b, SENDING_FILL, "vd-marker vd-marker-sending"));
  } else if (mode === "mentioned") {
    bucketsMentioned.forEach((b) => makeMarker(b, MENTIONED_FILL, "vd-marker vd-marker-mentioned"));
  } else {
    bucketsAll.forEach((b) => makeMarker(b, ALL_FILL, "vd-marker vd-marker-all"));
  }

  if (docCountEl) docCountEl.textContent = String(FILTERED.length);
  if (placeCountEl) placeCountEl.textContent = String(plotted);
  if (missingGeoCountEl) missingGeoCountEl.textContent = String(missingGeo);

  upsertLegend(mode, { plotted, threshold });

  // Keep UI in sync
  syncThresholdUI();

  if (resetView && bounds.length > 0) {
    MAP.fitBounds(bounds, { padding: [30, 30] });
  }
}

/* =========================================================
   Clear filters
   ========================================================= */

function clearFilters() {
  if (mapModeSelect) mapModeSelect.value = "sending";
  if (yearFilter) yearFilter.value = "";
  if (senderFilter) senderFilter.value = "";
  if (recipientFilter) recipientFilter.value = "";
  if (alignmentFilter) alignmentFilter.value = "";
  if (mutualExchangeToggle) mutualExchangeToggle.checked = false;

  if (thresholdFilter) thresholdFilter.value = "1";
  if (mentionedTypeFilter) mentionedTypeFilter.value = "all";

  syncThresholdUI();
  stopYearAnimation();
  applyFilters(true);
}

/* =========================================================
   Year animation UI
   ========================================================= */

function setFiltersDisabled(isDisabled) {
  // basics
  if (mapModeSelect) mapModeSelect.disabled = isDisabled;
  if (yearFilter) yearFilter.disabled = isDisabled;
  if (senderFilter) senderFilter.disabled = isDisabled;
  if (recipientFilter) recipientFilter.disabled = isDisabled;
  if (alignmentFilter) alignmentFilter.disabled = isDisabled;
  if (mutualExchangeToggle) mutualExchangeToggle.disabled = isDisabled;

  // advanced
  if (thresholdFilter) thresholdFilter.disabled = isDisabled;
  if (mentionedTypeFilter) mentionedTypeFilter.disabled = isDisabled;

  // actions
  if (playYearsBtn) playYearsBtn.disabled = isDisabled;
  if (stopYearsBtn) stopYearsBtn.disabled = !isDisabled;
}

function updateYearPlayUI(currentYear, idx, total) {
  if (yearPlayLabelEl) yearPlayLabelEl.textContent = currentYear || "—";

  if (!yearPlayProgressEl) return;

  const pct = total > 1 ? Math.round((idx / (total - 1)) * 100) : 0;
  yearPlayProgressEl.style.width = `${pct}%`;
  yearPlayProgressEl.setAttribute("aria-valuenow", String(pct));
}

function resetYearPlayUI() {
  updateYearPlayUI("", 0, 0);
}

function stopYearAnimation() {
  if (YEAR_TIMER) {
    clearInterval(YEAR_TIMER);
    YEAR_TIMER = null;
  }
  setFiltersDisabled(false);

  const y = yearFilter ? yearFilter.value : "";
  if (YEAR_OPTIONS && YEAR_OPTIONS.length) {
    const idx = Math.max(0, YEAR_OPTIONS.indexOf(y));
    updateYearPlayUI(y, idx, YEAR_OPTIONS.length);
  } else {
    updateYearPlayUI(y, 0, 0);
  }
}

function startYearAnimation() {
  if (!yearFilter) return;

  stopYearAnimation(); // no duplicate timer

  YEAR_OPTIONS = Array.from(yearFilter.options)
    .map((o) => o.value)
    .filter((v) => v && /^\d{4}$/.test(v))
    .sort((a, b) => Number(a) - Number(b));

  if (YEAR_OPTIONS.length === 0) return;

  // start from currently selected year (if any), else first
  const current = yearFilter.value;
  YEAR_INDEX = YEAR_OPTIONS.indexOf(current);
  if (YEAR_INDEX < 0) YEAR_INDEX = 0;

  setFiltersDisabled(true);

  // apply first frame immediately
  yearFilter.value = YEAR_OPTIONS[YEAR_INDEX];
  resetYearPlayUI();
  applyFilters(false);
  updateYearPlayUI(YEAR_OPTIONS[YEAR_INDEX], YEAR_INDEX, YEAR_OPTIONS.length);

  YEAR_TIMER = setInterval(() => {
    // stop at end (no loop)
    if (YEAR_INDEX >= YEAR_OPTIONS.length - 1) {
      stopYearAnimation();
      return;
    }
    YEAR_INDEX += 1;
    yearFilter.value = YEAR_OPTIONS[YEAR_INDEX];
    applyFilters(false);
    updateYearPlayUI(YEAR_OPTIONS[YEAR_INDEX], YEAR_INDEX, YEAR_OPTIONS.length);
  }, YEAR_INTERVAL_MS);
}

/* =========================================================
   Boot
   ========================================================= */

async function boot() {
  initMap();

  try {
    await loadStandoffPlaces();
  } catch (e) {
    console.warn("Could not load standoff places geo:", e);
  }

  await loadAlignments();

  const res = await fetch(INDEXES_URL);
  if (!res.ok) throw new Error(`Failed to load ${INDEXES_URL}`);
  const json = await res.json();
  DATA = Array.isArray(json) ? json : [];

  populateFilters();
  populateAlignmentFilter();
  initTooltips();

  // Initialize threshold UI once
  syncThresholdUI();

  applyFilters(true);
  setTimeout(() => MAP && MAP.invalidateSize(), 50);

  [
    mapModeSelect,
    yearFilter,
    senderFilter,
    recipientFilter,
    alignmentFilter,
    mutualExchangeToggle,
    mentionedTypeFilter,
  ].forEach((el) => {
    if (!el) return;
    el.addEventListener("change", () => applyFilters(false));
  });

  // Threshold: smooth slider
  if (thresholdFilter) {
    thresholdFilter.addEventListener("input", () => {
      syncThresholdUI();
      applyFilters(false);
    });
    thresholdFilter.addEventListener("change", () => {
      syncThresholdUI();
      applyFilters(false);
    });
  }

  if (clearBtn) {
    clearBtn.addEventListener("click", (e) => {
      e.preventDefault();
      clearFilters();
    });
  }

  if (playYearsBtn) {
    playYearsBtn.addEventListener("click", (e) => {
      e.preventDefault();
      startYearAnimation();
    });
  }

  if (stopYearsBtn) {
    stopYearsBtn.addEventListener("click", (e) => {
      e.preventDefault();
      stopYearAnimation();
    });
  }

  // initial state
  if (stopYearsBtn) stopYearsBtn.disabled = true;
  resetYearPlayUI();
}

boot().catch((err) => {
  console.error(err);
  alert(err.message || String(err));
});