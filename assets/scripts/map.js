console.log("map.js loaded");

const INDEXES_URL = "../../data/indexes/indexes.json";
const STANDOFF_PLACES_URL = "../../data/standoff/standoff_places.xml";

const mapModeSelect = document.getElementById("mapMode");
const yearFilter = document.getElementById("yearFilter");
const senderFilter = document.getElementById("senderFilter");
const recipientFilter = document.getElementById("recipientFilter");
const mutualExchangeToggle = document.getElementById("mutualExchangeToggle");
const clearBtn = document.getElementById("clearFiltersBtn");

const docCountEl = document.getElementById("docCount");
const placeCountEl = document.getElementById("placeCount");
const missingGeoCountEl = document.getElementById("missingGeoCount");

let DATA = [];
let FILTERED = [];
let PLACES_GEO = { labelIndex: new Map() };

let MAP = null;
let LAYER_SENDING = null;
let LAYER_MENTIONED = null;
let LEGEND = null;

const COLORS = {
  sending: { fill: "#4E7A5A", stroke: "#2F5D3A" },
  mentioned: { fill: "#B56A5A", stroke: "#7A3E34" },
};

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

function matchesMutualPair(d, a, b) {
  const author = d.author?.label || d.author_name || "";
  const rec = d.recipient?.label || d.recipient_name || "";
  return (author === a && rec === b) || (author === b && rec === a);
}

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
    wash.style.position = "absolute";
    wash.style.inset = "0";
    wash.style.pointerEvents = "none";
    wash.style.zIndex = "200";
    mapEl.appendChild(wash);
  }

  if (!mapEl.querySelector(".map-paper")) {
    const paper = document.createElement("div");
    paper.className = "map-paper";
    paper.style.position = "absolute";
    paper.style.inset = "0";
    paper.style.pointerEvents = "none";
    paper.style.zIndex = "201";
    mapEl.appendChild(paper);
  }
}

function initMap() {
  MAP = L.map("map", { zoomControl: true });

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(MAP);

  MAP.createPane("sendingPane");
  MAP.getPane("sendingPane").style.zIndex = 410;

  MAP.createPane("mentionedPane");
  MAP.getPane("mentionedPane").style.zIndex = 420;

  LAYER_SENDING = L.layerGroup([], { pane: "sendingPane" }).addTo(MAP);
  LAYER_MENTIONED = L.layerGroup([], { pane: "mentionedPane" }).addTo(MAP);

  MAP.setView([-30.0, -53.0], 6);

  ensureOverlays();
}

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

function populateFilters() {
  const years = DATA.map((d) => (d.year ? String(d.year) : parseYearFromISO(d.date)));
  uniqueSorted(years).forEach((y) => yearFilter.add(new Option(y, y)));

  uniqueSorted(DATA.map((d) => d.author?.label || d.author_name)).forEach((v) => {
    senderFilter.add(new Option(v, v));
  });

  uniqueSorted(DATA.map((d) => d.recipient?.label || d.recipient_name)).forEach((v) => {
    recipientFilter.add(new Option(v, v));
  });
}

function applyFilters(resetView = false) {
  const mode = mapModeSelect ? mapModeSelect.value : "sending";
  const y = yearFilter ? yearFilter.value : "";
  const a = senderFilter ? senderFilter.value : "";
  const r = recipientFilter ? recipientFilter.value : "";
  const mutual = mutualExchangeToggle ? mutualExchangeToggle.checked : false;

  FILTERED = DATA.filter((d) => {
    if (mutual && a && r) {
      if (!matchesMutualPair(d, a, r)) return false;
    } else {
      if (a && (d.author?.label || d.author_name) !== a) return false;
      if (r && (d.recipient?.label || d.recipient_name) !== r) return false;
    }

    if (y) {
      const dy = d.year ? String(d.year) : parseYearFromISO(d.date);
      if (dy !== y) return false;
    }

    return true;
  });

  renderMap(mode, resetView);
}

function clearLayers() {
  if (LAYER_SENDING) LAYER_SENDING.clearLayers();
  if (LAYER_MENTIONED) LAYER_MENTIONED.clearLayers();
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

  const row = (label, c) => `
    <div style="display:flex;align-items:center;gap:.5rem;">
      <span style="width:12px;height:12px;border-radius:50%;background:${c.fill};border:1px solid ${c.stroke};display:inline-block;"></span>
      <span>${label}</span>
    </div>
  `;

  const content = (() => {
    if (mode === "sending") {
      return `
        ${row("Sending places", COLORS.sending)}
        <div style="margin-top:.35rem;opacity:.8;font-size:.9rem;">
          ${stats.sendingPlaces} plotted
        </div>
      `;
    }
    if (mode === "mentioned") {
      return `
        ${row("Mentioned places", COLORS.mentioned)}
        <div style="margin-top:.35rem;opacity:.8;font-size:.9rem;">
          ${stats.mentionedPlaces} plotted
        </div>
      `;
    }
    return `
      <div style="display:flex;flex-direction:column;gap:.35rem;">
        ${row("Sending", COLORS.sending)}
        ${row("Mentioned", COLORS.mentioned)}
      </div>
      <div style="margin-top:.35rem;opacity:.8;font-size:.9rem;">
        ${stats.sendingPlaces} sending · ${stats.mentionedPlaces} mentioned
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

function offsetLatLng(lat, lon, dx, dy) {
  if (!MAP) return [lat, lon];
  const p = MAP.latLngToLayerPoint([lat, lon]);
  const p2 = L.point(p.x + dx, p.y + dy);
  const ll2 = MAP.layerPointToLatLng(p2);
  return [ll2.lat, ll2.lng];
}

function renderMap(mode, resetView) {
  clearLayers();

  let missingGeo = 0;

  const bucketsSending = new Map();
  const bucketsMentioned = new Map();

  const addBucket = (buckets, label, lat, lon, doc) => {
    const key = `${lat},${lon}`;
    if (!buckets.has(key)) buckets.set(key, { label, lat, lon, docs: [] });
    buckets.get(key).docs.push(doc);
  };

  FILTERED.forEach((d) => {
    if (mode === "sending" || mode === "both") {
      const ll = getSendingLatLng(d);
      if (ll) addBucket(bucketsSending, getSendingLabel(d), ll[0], ll[1], d);
      else if (d?.place?.label || d?.place_label) missingGeo++;
    }

    if (mode === "mentioned" || mode === "both") {
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
        addBucket(bucketsMentioned, geo.label, geo.lat, geo.lon, d);
      });
    }
  });

  const markersBounds = [];
  const seenBoth = new Set(bucketsSending.keys());
  for (const k of bucketsMentioned.keys()) if (seenBoth.has(k)) seenBoth.add(k);

  const makeMarker = (layer, b, color, lat, lon) => {
    const marker = L.circleMarker([lat, lon], {
      pane: layer.options?.pane,
      radius: Math.max(5, Math.min(18, 4 + Math.log2(b.docs.length + 1) * 3)),
      weight: 1,
      color: color.stroke,
      fillColor: color.fill,
      fillOpacity: 0.65,
    });
    marker.bindPopup(buildPopupHTML(b.label, b.docs), { maxWidth: 340 });
    marker.addTo(layer);
    markersBounds.push([lat, lon]);
  };

  if (mode === "sending") {
    bucketsSending.forEach((b) => makeMarker(LAYER_SENDING, b, COLORS.sending, b.lat, b.lon));
  } else if (mode === "mentioned") {
    bucketsMentioned.forEach((b) => makeMarker(LAYER_MENTIONED, b, COLORS.mentioned, b.lat, b.lon));
  } else {
    bucketsSending.forEach((b, key) => {
      const overlaps = bucketsMentioned.has(key);
      const lat = b.lat;
      const lon = b.lon;
      makeMarker(LAYER_SENDING, b, COLORS.sending, lat, lon);
      if (overlaps) {
        const [mlat, mlon] = offsetLatLng(lat, lon, 7, -7);
        const mb = bucketsMentioned.get(key);
        makeMarker(LAYER_MENTIONED, mb, COLORS.mentioned, mlat, mlon);
      }
    });

    bucketsMentioned.forEach((b, key) => {
      if (bucketsSending.has(key)) return;
      makeMarker(LAYER_MENTIONED, b, COLORS.mentioned, b.lat, b.lon);
    });
  }

  const plottedPlaces =
    mode === "sending"
      ? bucketsSending.size
      : mode === "mentioned"
      ? bucketsMentioned.size
      : new Set([...bucketsSending.keys(), ...bucketsMentioned.keys()]).size;

  if (docCountEl) docCountEl.textContent = String(FILTERED.length);
  if (placeCountEl) placeCountEl.textContent = String(plottedPlaces);
  if (missingGeoCountEl) missingGeoCountEl.textContent = String(missingGeo);

  upsertLegend(mode, {
    sendingPlaces: bucketsSending.size,
    mentionedPlaces: bucketsMentioned.size,
  });

  if (resetView && markersBounds.length > 0) {
    MAP.fitBounds(markersBounds, { padding: [30, 30] });
  }
}

function clearFilters() {
  if (mapModeSelect) mapModeSelect.value = "sending";
  if (yearFilter) yearFilter.value = "";
  if (senderFilter) senderFilter.value = "";
  if (recipientFilter) recipientFilter.value = "";
  if (mutualExchangeToggle) mutualExchangeToggle.checked = false;
  applyFilters(true);
}

async function boot() {
  initMap();

  try {
    await loadStandoffPlaces();
  } catch (e) {
    console.warn("Could not load standoff places geo:", e);
  }

  const res = await fetch(INDEXES_URL);
  if (!res.ok) throw new Error(`Failed to load ${INDEXES_URL}`);
  const json = await res.json();
  DATA = Array.isArray(json) ? json : [];

  populateFilters();
  applyFilters(true);

  [mapModeSelect, yearFilter, senderFilter, recipientFilter, mutualExchangeToggle].forEach((el) => {
    if (!el) return;
    el.addEventListener("change", () => applyFilters(false));
  });

  if (MAP) MAP.on("zoomend", () => applyFilters(false));

  if (clearBtn) {
    clearBtn.addEventListener("click", (e) => {
      e.preventDefault();
      clearFilters();
    });
  }
}

boot().catch((err) => {
  console.error(err);
  alert(err.message || String(err));
});