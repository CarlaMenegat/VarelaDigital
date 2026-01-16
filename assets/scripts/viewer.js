/* =========================================================
   Varela Digital – TEI Viewer (robust TEI namespace version)
   ========================================================= */

console.log('viewer.js loaded');

/* =========================
   Paths
========================= */
const BASE_XML_PATH = '../../data/documents_XML/';
const STANDOFF_BASE_PATH = '../../data/standoff/';
const BASE_RDF_PATH = '../../data/rdf/';
const BASE_RDF_JSON_PATH = BASE_RDF_PATH + 'json/';
const BASE_RDF_TTL_PATH  = BASE_RDF_PATH + 'ttl/';
const INDEXES_BASE_PATH = '../../data/indexes/';
const DEFAULT_ORDER = 'collection';

const STANDOFF_FILES = {
  persons: STANDOFF_BASE_PATH + 'standoff_persons.xml',
  places:  STANDOFF_BASE_PATH + 'standoff_places.xml',
  orgs:    STANDOFF_BASE_PATH + 'standoff_orgs.xml',
  events:  STANDOFF_BASE_PATH + 'standoff_events.xml'
};

/* =========================
   Namespaces
========================= */
const TEI_NS = 'http://www.tei-c.org/ns/1.0';
const XML_NS = 'http://www.w3.org/XML/1998/namespace';

const NS = { tei: TEI_NS, xml: XML_NS };

/* =========================
   State
========================= */
let VIEW_MODE = 'reading';
let CURRENT_TEI_DOC = null;
let BODY_DIV = null;

const STANDOFF_INDEX = Object.create(null);

let SURFACES = [];
let CURRENT_SURFACE = '';

/* =========================================================
   Utilities
========================================================= */

function getQueryParam(name) {
  return new URLSearchParams(window.location.search).get(name);
}

async function fetchXML(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`Failed to load ${path} (${res.status})`);
  const txt = await res.text();
  const doc = new DOMParser().parseFromString(txt, 'application/xml');
  if (doc.getElementsByTagName('parsererror').length) {
    throw new Error(`XML parse error in ${path}`);
  }
  return doc;
}

function nsResolver(prefix) {
  return NS[prefix] || null;
}

function xFirst(docOrNode, xpath) {
  const r = (docOrNode.ownerDocument || docOrNode).evaluate(
    xpath,
    docOrNode,
    nsResolver,
    XPathResult.FIRST_ORDERED_NODE_TYPE,
    null
  );
  return r.singleNodeValue || null;
}

function xAll(docOrNode, xpath) {
  const out = [];
  const it = (docOrNode.ownerDocument || docOrNode).evaluate(
    xpath,
    docOrNode,
    nsResolver,
    XPathResult.ORDERED_NODE_ITERATOR_TYPE,
    null
  );
  let n = it.iterateNext();
  while (n) { out.push(n); n = it.iterateNext(); }
  return out;
}

function xText(docOrNode, xpath) {
  const r = (docOrNode.ownerDocument || docOrNode).evaluate(
    xpath,
    docOrNode,
    nsResolver,
    XPathResult.STRING_TYPE,
    null
  );
  return (r.stringValue || '').trim();
}

function attr(node, name, ns = null) {
  if (!node) return '';
  if (ns) return (node.getAttributeNS(ns, name) || '').trim();
  return (node.getAttribute(name) || '').trim();
}

function textOf(node) {
  return (node?.textContent || '').trim();
}

function normUnknown(v) {
  const s = (v || '').trim();
  if (!s || s.toLowerCase() === 'unknown') return '';
  return s;
}

function buildProjectURI(localId, kind) {
  if (!localId) return '';
  if (kind === 'org')   return `https://carlamenegat.github.io/VarelaDigital/org/${localId}`;
  if (kind === 'place') return `https://carlamenegat.github.io/VarelaDigital/place/${localId}`;
  if (kind === 'event') return `https://carlamenegat.github.io/VarelaDigital/event/${localId}`;
  return `https://carlamenegat.github.io/VarelaDigital/person/${localId}`;
}

function formatPtBRDate(iso) {
  const s = (iso || '').trim();
  if (!s) return '';
  const m = s.match(/^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$/);
  if (!m) return '';
  const months = ['janeiro','fevereiro','março','abril','maio','junho','julho','agosto','setembro','outubro','novembro','dezembro'];
  if (m[3]) return `${parseInt(m[3], 10)} ${months[parseInt(m[2], 10) - 1]} ${m[1]}`;
  if (m[2]) return `${months[parseInt(m[2], 10) - 1]} ${m[1]}`;
  return m[1];
}

/* =========================================================
   Init
========================================================= */

document.addEventListener('DOMContentLoaded', async () => {
  const fileParam = getQueryParam('file');
  if (!fileParam) return;

  try {
    CURRENT_TEI_DOC = await fetchXML(BASE_XML_PATH + fileParam);
    await loadStandoffFiles();
    readSurfaces(CURRENT_TEI_DOC);

    renderViewer(CURRENT_TEI_DOC, fileParam);

    setupViewTabs();
    setupAnnotationBehaviour();

    disableNonImplementedUI();

    await setupDocNavigator(fileParam);
  } catch (e) {
    console.error(e);
  }
});

function buildViewerURL(file) {
  const url = new URL(window.location.href);
  url.searchParams.set('file', file);
  return url.toString();
}

function setNavTarget(el, targetFile, disabled) {
  if (!el) return;

  const tag = (el.tagName || '').toUpperCase();
  const isLink = tag === 'A';
  const isButton = tag === 'BUTTON';

  if (disabled || !targetFile) {
    el.classList.add('disabled');
    el.setAttribute('aria-disabled', 'true');

    if (isLink) el.removeAttribute('href');
    if (isButton) el.disabled = true;

    // also remove click handler if any
    el.onclick = null;
    return;
  }

  el.classList.remove('disabled');
  el.removeAttribute('aria-disabled');
  if (isButton) el.disabled = false;

  const href = buildViewerURL(targetFile);

  if (isLink) {
    el.href = href;
    return;
  }

  el.onclick = (ev) => {
    ev.preventDefault();
    window.location.href = href;
  };
}

async function getOrderListFromURLorManifest() {
  const params = new URLSearchParams(window.location.search);

  // 1) explicit list in URL: ?list=CV-1.xml,CV-2.xml...
  const listParam = params.get('list');
  if (listParam) {
    return listParam
      .split(',')
      .map(s => decodeURIComponent(s.trim()))
      .filter(Boolean);
  }

  // 2) manifest: ../../data/indexes/<order>.json
  const order = (params.get('order') || DEFAULT_ORDER).trim();
  const manifestPath = INDEXES_BASE_PATH + order + '.json';

  try {
    const res = await fetch(manifestPath, { cache: 'no-cache' });
    if (!res.ok) throw new Error(`manifest ${manifestPath} ${res.status}`);

    const data = await res.json();
    if (!Array.isArray(data)) return [];

    // Accept BOTH:
    // - ["CV-1.xml", "CV-2.xml", ...]
    // - [{id:"CV-1", file:"CV-1.xml"}, ...]
    const list = data.map(item => {
      if (typeof item === 'string') return item.trim();
      if (item && typeof item === 'object') {
        if (typeof item.file === 'string') return item.file.trim();
        if (typeof item.xml === 'string') return item.xml.trim(); // optional future key
        if (typeof item.path === 'string') return item.path.trim(); // optional future key
      }
      return '';
    }).filter(Boolean);

    return list;
  } catch (e) {
    console.warn('Could not load manifest:', manifestPath, e);
  }

  return [];
}

function guessPrevNextByCVNumber(fileParam) {
  const m = String(fileParam).match(/^CV-(\d+)([a-z])?\.xml$/i);
  if (!m) return { prev: null, next: null };

  const num = parseInt(m[1], 10);
  const suf = (m[2] || '').toLowerCase();

  // Basic fallback (ignores suffix ordering):
  const prev = num > 1 ? `CV-${num - 1}.xml` : null;
  const next = `CV-${num + 1}.xml`;

  // If current has suffix, fallback to base file
  if (suf) {
    return { prev: `CV-${num}.xml`, next: `CV-${num}.xml` };
  }

  return { prev, next };
}

async function setupDocNavigator(currentFile) {
  // match YOUR HTML ids (prev-letter / next-letter) plus older variants
  const prevEl = document.querySelector(
    '#prev-letter, #btnPrev, #prevBtn, a[data-nav="prev"], button[data-nav="prev"]'
  );
  const nextEl = document.querySelector(
    '#next-letter, #btnNext, #nextBtn, a[data-nav="next"], button[data-nav="next"]'
  );

  if (!prevEl && !nextEl) return;

  const list = await getOrderListFromURLorManifest();

  if (list.length) {
    const i = list.indexOf(currentFile);
    const prev = i > 0 ? list[i - 1] : null;
    const next = i >= 0 && i < list.length - 1 ? list[i + 1] : null;

    setNavTarget(prevEl, prev, !prev);
    setNavTarget(nextEl, next, !next);
    return;
  }

  // fallback if no manifest/list
  const g = guessPrevNextByCVNumber(currentFile);
  setNavTarget(prevEl, g.prev, !g.prev);
  setNavTarget(nextEl, g.next, !g.next);
}

/* =========================================================
   UI flags (remove non-implemented controls)
========================================================= */

function disableNonImplementedUI() {
  // Remove Encoded/Diplomatic buttons if they still exist in DOM
  document.querySelectorAll('.tab-button').forEach(btn => {
    const v = (btn.dataset.view || '').toLowerCase();
    if (v === 'encoded' || v === 'diplomatic') btn.remove();
  });

  // Ensure Reading is active
  const readingBtn = document.querySelector('.tab-button[data-view="reading"]');
  if (readingBtn) {
    readingBtn.disabled = false;
    readingBtn.classList.add('active');
  }

  // Hide surface selector block if it exists
  const sel = document.getElementById('surface-selector');
  if (sel) {
    const wrapper =
      sel.closest('.surface-selector-wrapper') ||
      sel.closest('.surface-selector') ||
      sel.parentElement;
    if (wrapper) wrapper.style.display = 'none';
    else sel.style.display = 'none';
  }
}

/* =========================================================
   Standoff loading
========================================================= */

async function loadStandoffFiles() {
  if (STANDOFF_INDEX.__loaded) return;

  const entries = [];

  for (const [kind, path] of Object.entries(STANDOFF_FILES)) {
    try {
      const doc = await fetchXML(path);

      const nodes = xAll(
        doc,
        `//tei:${kind === 'persons' ? 'person' : kind === 'places' ? 'place' : kind === 'orgs' ? 'org' : 'event'}`
      );

      const fallback =
        kind === 'persons' ? xAll(doc, `//tei:person`) :
        kind === 'places'  ? xAll(doc, `//tei:place`)  :
        kind === 'orgs'    ? xAll(doc, `//tei:org`)    :
        xAll(doc, `//tei:event`);

      (nodes.length ? nodes : fallback).forEach(n => entries.push({ kind, node: n }));
    } catch (e) {
      console.warn(`Could not load standoff: ${kind}`, e);
    }
  }

  for (const { node } of entries) {
    const id = attr(node, 'id', XML_NS);
    if (!id) continue;
    STANDOFF_INDEX[id] = node;
  }

  STANDOFF_INDEX.__loaded = true;
}

/* =========================================================
   Viewer rendering
========================================================= */

function renderViewer(teiDoc, fileName) {
  renderLetterNavInfo(teiDoc);
  renderMetadataPanel(teiDoc, fileName);
  renderText(teiDoc);
}

/* =========================================================
   Letter header info (title/date)
========================================================= */

function renderLetterNavInfo(teiDoc) {
  const box = document.getElementById('letter-info');
  if (!box) return;

  const title = xText(teiDoc, '//tei:teiHeader//tei:titleStmt/tei:title[1]');
  const date = xText(teiDoc, 'string((//tei:teiHeader//tei:correspDesc//tei:correspAction[@type="sent"][1]/tei:date[1]/@when))');

  box.innerHTML = `
    <div class="letter-title">${title || ''}</div>
    <div class="letter-date">${date || ''}</div>
  `;
}

/* =========================================================
   Metadata panel
========================================================= */

function renderMetadataPanel(teiDoc, fileName) {
  const mdTitle = document.getElementById('mdTitle');
  const mdFrom  = document.getElementById('mdFrom');
  const mdTo    = document.getElementById('mdTo');
  const mdPlace = document.getElementById('mdPlace');
  const mdDate  = document.getElementById('mdDate');
  const mdType  = document.getElementById('mdType');

  const dlXml    = document.getElementById('dlXml');
  const dlJsonld = document.getElementById('dlJsonld');
  const dlTtl    = document.getElementById('dlTtl');

  const safeSet = (el, val) => { if (el) el.textContent = (val && val.trim()) ? val.trim() : '—'; };

  const title = xText(teiDoc, '//tei:teiHeader//tei:titleStmt/tei:title[1]');

  const from = xText(teiDoc, 'string((//tei:teiHeader//tei:correspDesc//tei:correspAction[@type="sent"][1]/*[self::tei:persName or self::tei:orgName][1]))');
  const to   = xText(teiDoc, 'string((//tei:teiHeader//tei:correspDesc//tei:correspAction[@type="received"][1]/*[self::tei:persName or self::tei:orgName][1]))');

  const place = xText(teiDoc, 'string((//tei:teiHeader//tei:correspDesc//tei:correspAction[@type="sent"][1]/tei:placeName[1]))');
  const date  = xText(teiDoc, 'string((//tei:teiHeader//tei:correspDesc//tei:correspAction[@type="sent"][1]/tei:date[1]/@when))');

  const docType = xText(teiDoc, 'string((//tei:text//tei:body//tei:div[1]/@type))');

  safeSet(mdTitle, title);
  safeSet(mdFrom, from);
  safeSet(mdTo, to);
  safeSet(mdPlace, place);
  safeSet(mdDate, date);
  safeSet(mdType, docType);

  const stem = (fileName || '').replace(/\.xml$/i, '');
  setDownloadLink(dlXml, BASE_XML_PATH + fileName, 'Download TEI XML');
  setDownloadLink(dlJsonld, BASE_RDF_JSON_PATH + stem + '.json', 'Download JSON-LD');
  setDownloadLink(dlTtl, BASE_RDF_TTL_PATH + stem + '.ttl', 'Download TTL');
}

function setDownloadLink(aEl, href, label) {
  if (!aEl) return;
  aEl.href = href;
  aEl.setAttribute('download', '');
  aEl.textContent = label;
}

/* =========================================================
   Surfaces (kept, but disabled in UI / not used)
========================================================= */

function readSurfaces(teiDoc) {
  const surfaces = xAll(teiDoc, '//tei:facsimile/tei:surface');
  SURFACES = surfaces.map(s => ({ n: attr(s, 'n') })).filter(s => s.n);
  CURRENT_SURFACE = SURFACES[0]?.n || '';
}

/* =========================================================
   Text rendering
========================================================= */

function renderText(teiDoc) {
  const layer = document.querySelector(`.transcription-layer[data-view="${VIEW_MODE}"]`);
  if (!layer) return;

  layer.innerHTML = '';
  const div = xFirst(teiDoc, '//tei:text/tei:body/tei:div[1]');
  if (!div) return;

  layer.appendChild(renderNode(div));
}

/* =========================================================
   View tabs
========================================================= */

function setupViewTabs() {
  document.querySelectorAll('.tab-button').forEach(btn => {
    btn.addEventListener('click', () => {
      if (btn.disabled) return;

      VIEW_MODE = btn.dataset.view;

      document.querySelectorAll('.tab-button').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      document.querySelectorAll('.transcription-layer').forEach(l =>
        l.classList.toggle('d-none', l.dataset.view !== VIEW_MODE)
      );

      renderText(CURRENT_TEI_DOC);
    });
  });
}

/* =========================================================
   Annotation behaviour
========================================================= */

function setupAnnotationBehaviour() {
  const box = document.getElementById('annotations-box');
  const content = document.getElementById('annotations-content');
  const closeBtn = document.getElementById('close-annotations');

  if (!box || !content || !closeBtn) return;

  box.classList.add('d-none');

  document.addEventListener('click', (e) => {
    const span = e.target.closest('.annotated');
    if (!span) return;

    if (span.dataset.ref) {
      const id = span.dataset.ref.replace('#', '');
      const entry = STANDOFF_INDEX[id];

      document.body.classList.add('annotations-open');
      box.classList.remove('d-none');
      content.innerHTML = renderStandoffEntryCard(entry);
      return;
    }

    if (span.dataset.when) {
      const when = (span.dataset.when || '').trim();
      const pretty = formatPtBRDate(when);

      document.body.classList.add('annotations-open');
      box.classList.remove('d-none');
      content.innerHTML = `
        <div class="annotation-card">
          <h6 class="annotation-title">Date</h6>
          <div class="small text-muted mb-2">${when}</div>
          <p class="small mb-0">${pretty || when}</p>
        </div>
      `;
      return;
    }
  });

  closeBtn.addEventListener('click', () => {
    box.classList.add('d-none');
    document.body.classList.remove('annotations-open');
    content.innerHTML = '';
  });
}

/* =========================================================
   Standoff card renderer
========================================================= */

function getLocalId(entry) {
  return attr(entry, 'id', XML_NS);
}

function qAllLocal(entry, localName) {
  return Array.from(entry.getElementsByTagNameNS(TEI_NS, localName));
}

function getDirectChildNotes(entry) {
  const out = [];
  for (const ch of Array.from(entry.childNodes || [])) {
    if (ch.nodeType === Node.ELEMENT_NODE && ch.namespaceURI === TEI_NS && ch.localName === 'note') {
      out.push(ch);
    }
  }
  return out;
}

function renderIdnos(entry, kind) {
  const idnos = qAllLocal(entry, 'idno').map(n => ({
    type: (n.getAttribute('type') || '').trim(),
    value: textOf(n)
  }));

  const hasProjectPlaceholder = idnos.some(x => x.type === 'project');
  const filtered = idnos.filter(x => x.type && x.type !== 'project' && x.value);

  const parts = [];

  for (const x of filtered) {
    parts.push(`
      <div class="annotation-idno small">
        <strong>${x.type}:</strong>
        <a href="${x.value}" target="_blank" rel="noopener">${x.value}</a>
      </div>
    `);
  }

  const geon = idnos.find(x => x.type === 'geonames');
  if (geon && !geon.value) {
    parts.push(`
      <div class="annotation-idno small">
        <strong>geonames:</strong> <span class="text-muted">not set</span>
      </div>
    `);
  }

  if (hasProjectPlaceholder || filtered.length === 0) {
    const id = getLocalId(entry);
    const proj = buildProjectURI(id, kind);
    if (proj) {
      parts.push(`
        <div class="annotation-idno small">
          <strong>project:</strong>
          <a href="${proj}" target="_blank" rel="noopener">${proj}</a>
        </div>
      `);
    }
  }

  return parts.join('');
}

function renderVariants(entry, kind) {
  const map = { person: 'persName', place: 'placeName', org: 'orgName' };
  const ln = map[kind];
  if (!ln) return '';

  const names = qAllLocal(entry, ln).map(textOf).filter(Boolean);
  if (names.length <= 1) return '';

  return `
    <div class="small text-muted mb-2">
      <strong>Variants:</strong> ${names.join(' · ')}
    </div>
  `;
}

function renderStandoffEntryCard(entry) {
  if (!entry) return `<p class="text-muted small">No annotation available.</p>`;

  const tag = (entry.localName || '').toLowerCase();
  const localId = getLocalId(entry);

  const getFirst = (localName) => {
    const nodes = qAllLocal(entry, localName);
    return nodes.length ? textOf(nodes[0]) : '';
  };

  const kind = tag;
  let title = '';
  let extra = '';

  const directNotes = getDirectChildNotes(entry);
  const note = directNotes.length ? textOf(directNotes[directNotes.length - 1]) : '';

  if (tag === 'person') {
    title = getFirst('persName');

    const birthRaw = qAllLocal(entry, 'birth')[0]?.getAttribute('when') || '';
    const deathRaw = qAllLocal(entry, 'death')[0]?.getAttribute('when') || '';
    const birth = normUnknown(birthRaw);
    const death = normUnknown(deathRaw);

    if (birth || death) {
      extra = `<div class="small text-muted mb-1">${birth || ''}${(birth && death) ? ' – ' : ''}${death || ''}</div>`;
    }
  }

  if (tag === 'place') {
    const placeNames = qAllLocal(entry, 'placeName');
    const historical = placeNames.find(n => (n.getAttribute('type') || '').toLowerCase() === 'historical');
    title = textOf(historical) || textOf(placeNames[0]) || '';
  }

  if (tag === 'org') {
    title = getFirst('orgName');
  }

  if (tag === 'event') {
    title = getFirst('desc') || `Event ${localId}`;
    const when = qAllLocal(entry, 'date')[0]?.getAttribute('when') || '';
    if (when) extra = `<div class="small text-muted mb-1">${formatPtBRDate(when) || when}</div>`;
  }

  const variants = renderVariants(entry, kind);
  const idnos = renderIdnos(entry, kind);

  return `
    <div class="annotation-card">
      <h6 class="annotation-title">${title || localId || '—'}</h6>
      ${extra}
      ${variants}
      ${idnos ? `<div class="mb-2">${idnos}</div>` : ''}
      ${note ? `<p class="small mb-0">${note}</p>` : ''}
    </div>
  `;
}

/* =========================================================
   TEI → HTML rendering
========================================================= */

function renderNode(node) {
  if (!node) return document.createDocumentFragment();

  if (node.nodeType === Node.TEXT_NODE) {
    return document.createTextNode(node.textContent);
  }

  if (node.nodeType !== Node.ELEMENT_NODE) {
    return document.createDocumentFragment();
  }

  const ln = node.localName;
  let el;

  switch (ln) {
    case 'div': el = document.createElement('div'); break;
    case 'p': el = document.createElement('p'); break;
    case 'head': el = document.createElement('h3'); break;

    case 'choice':
      if (VIEW_MODE === 'reading') {
        const expan = xFirst(node, './tei:expan');
        return expan ? renderNode(expan) : document.createDocumentFragment();
      }
      el = document.createElement('span');
      break;

    case 'pb': {
      const n = attr(node, 'n');
      el = document.createElement('span');
      el.className = 'page-break';
      el.id = n ? `pb-${n}` : '';
      el.textContent = VIEW_MODE === 'reading'
        ? (n ? `[${n}]` : '[pb]')
        : (n ? `[pb ${n}]` : '[pb]');
      break;
    }

    case 'seg': {
      const type = attr(node, 'type');
      if (type === 'folio' && VIEW_MODE === 'reading') {
        return document.createDocumentFragment();
      }
      el = document.createElement('span');
      el.className = 'page-break';
      break;
    }

    case 'persName':
    case 'placeName':
    case 'orgName': {
      el = document.createElement('span');
      el.className = 'annotated';
      const r = attr(node, 'ref');
      if (r) el.dataset.ref = r;
      break;
    }

    case 'date': {
      el = document.createElement('span');
      el.className = 'annotated';
      const r = attr(node, 'ref');
      const when = attr(node, 'when');
      if (r) el.dataset.ref = r;
      if (when) el.dataset.when = when;
      break;
    }

    case 'opener':
    case 'closer':
    case 'postscript':
    case 'note':
    case 'dateline':
    case 'salute':
    case 'signed':
    case 'addressee':
      el = document.createElement('div');
      break;

    case 'g':
      el = document.createElement('span');
      break;

    default:
      el = document.createElement('span');
  }

  for (const ch of Array.from(node.childNodes)) {
    el.appendChild(renderNode(ch));
  }

  return el;
}