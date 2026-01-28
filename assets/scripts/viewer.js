/* ===== Paths ===== */
const HOST = (window.location.hostname || '').toLowerCase();
const BASE = HOST.endsWith('github.io') ? '/VarelaDigital/' : '/';

const BASE_XML_PATH = BASE + 'letters_data/documents_XML/';

const DOCUMENTS_HTML_PATH_PRIMARY = BASE + 'assets/html/documents_html/';
const DOCUMENTS_HTML_PATH_FALLBACK = BASE + 'assets/html/documents_html/';

const STANDOFF_BASE_PATH = BASE + 'letters_data/standoff/';

const BASE_RDF_PATH = BASE + 'assets/data/rdf/';
const BASE_RDF_JSON_PATH = BASE_RDF_PATH + 'json/';
const BASE_RDF_TTL_PATH = BASE_RDF_PATH + 'ttl/';

const INDEXES_BASE_PATH = BASE + 'assets/data/indexes/';
const DEFAULT_ORDER = 'collection';

const TRANSLATIONS_BASE_PATH = BASE + 'assets/data/translations/';

const STANDOFF_FILES = {
  persons: STANDOFF_BASE_PATH + 'standoff_persons.xml',
  places: STANDOFF_BASE_PATH + 'standoff_places.xml',
  orgs: STANDOFF_BASE_PATH + 'standoff_orgs.xml',
  events: STANDOFF_BASE_PATH + 'standoff_events.xml'
};

/* ===== Namespaces ===== */
const TEI_NS = 'http://www.tei-c.org/ns/1.0';
const XML_NS = 'http://www.w3.org/XML/1998/namespace';
const NS = { tei: TEI_NS, xml: XML_NS };

/* ===== State ===== */
let VIEW_MODE = 'reading';
let CURRENT_FILE = '';
let CURRENT_STEM = '';
let CURRENT_HTML_PATH = '';
let METADATA_INDEX = null;

const STANDOFF_INDEX = Object.create(null);

/* ===== Env ===== */
function isLocalhost() {
  const h = (window.location.hostname || '').toLowerCase();
  return h === 'localhost' || h === '127.0.0.1';
}
function isGitHubPages() {
  const h = (window.location.hostname || '').toLowerCase();
  return h.endsWith('github.io');
}
function allowTranslationApiFallback() {
  return isLocalhost();
}

/* ===== Utilities ===== */
function getQueryParam(name) {
  return new URLSearchParams(window.location.search).get(name);
}
function stemFromFile(fileName) {
  return String(fileName || '').replace(/\.xml$/i, '').replace(/\.html$/i, '');
}
function escapeHTML(s) {
  return String(s || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
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
  if (kind === 'org') return `https://carlamenegat.github.io/VarelaDigital/org/${localId}`;
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
async function fetchText(path) {
  const res = await fetch(path, { cache: 'no-cache' });
  if (!res.ok) throw new Error(`Failed to load ${path} (${res.status})`);
  return await res.text();
}
async function fetchXML(path) {
  const txt = await fetchText(path);
  const doc = new DOMParser().parseFromString(txt, 'application/xml');
  if (doc.getElementsByTagName('parsererror').length) {
    throw new Error(`XML parse error in ${path}`);
  }
  return doc;
}
async function fetchJSON(path) {
  const res = await fetch(path, { cache: 'no-store' });
  if (!res.ok) throw new Error(`Failed to load ${path} (${res.status})`);
  return await res.json();
}
function buildViewerURL(file) {
  const url = new URL(window.location.href);
  url.searchParams.set('file', file);
  return url.toString();
}
function getDocFileFromDOMOrURL() {
  const qp = getQueryParam('file');
  if (qp) return qp.trim();

  const bodyFile = (document.body?.dataset?.file || '').trim();
  if (bodyFile) return bodyFile;

  return '';
}

/* ===== Boot ===== */
document.addEventListener('DOMContentLoaded', async () => {
  const fileParam = getDocFileFromDOMOrURL();
  if (!fileParam) return;

  CURRENT_FILE = fileParam;
  CURRENT_STEM = stemFromFile(fileParam);

  try {
    await loadDocumentHTML(CURRENT_STEM);
    await loadStandoffFiles();

    setupViewTabs();
    setupAnnotationBehaviour();
    disableNonImplementedUI();

    await setupDocNavigator(`${CURRENT_STEM}.xml`);
    await renderMetadataPanel(CURRENT_STEM, `${CURRENT_STEM}.xml`);

    if ((VIEW_MODE || '').toLowerCase() === 'translation') {
      await renderTranslation(`${CURRENT_STEM}.xml`);
    }
  } catch (e) {
    console.error(e);
  }
});

/* ===== Document HTML ===== */
async function loadDocumentHTML(stem) {
  const readingLayer = document.querySelector(`.transcription-layer[data-view="reading"]`);
  if (!readingLayer) return;

  const candidates = [
    `${DOCUMENTS_HTML_PATH_PRIMARY}${stem}.html`,
    `${DOCUMENTS_HTML_PATH_FALLBACK}${stem}.html`
  ];

  let htmlText = '';
  let usedPath = '';

  for (const p of candidates) {
    try {
      htmlText = await fetchText(p);
      usedPath = p;
      break;
    } catch (_) {}
  }

  if (!htmlText) {
    readingLayer.innerHTML = `<p class="text-muted small mb-0">HTML not found for <code>${escapeHTML(stem)}</code>.</p>`;
    return;
  }

  CURRENT_HTML_PATH = usedPath;

  const doc = new DOMParser().parseFromString(htmlText, 'text/html');

  const srcLetterInfo = doc.getElementById('letter-info');
  const dstLetterInfo = document.getElementById('letter-info');
  if (dstLetterInfo && srcLetterInfo) {
    dstLetterInfo.innerHTML = srcLetterInfo.innerHTML;
  }

  const srcBody = doc.querySelector('.tei-body');
  if (srcBody) {
    readingLayer.innerHTML = srcBody.innerHTML;
  } else {
    const fallback = doc.querySelector('.transcription-box') || doc.body;
    readingLayer.innerHTML = fallback ? fallback.innerHTML : htmlText;
  }
}

/* ===== Navigator ===== */
async function getOrderListFromURLorManifest() {
  const params = new URLSearchParams(window.location.search);

  const listParam = params.get('list');
  if (listParam) {
    return listParam
      .split(',')
      .map(s => decodeURIComponent(s.trim()))
      .filter(Boolean);
  }

  const order = (params.get('order') || DEFAULT_ORDER).trim();
  const manifestPath = INDEXES_BASE_PATH + order + '.json';

  try {
    const res = await fetch(manifestPath, { cache: 'no-cache' });
    if (!res.ok) throw new Error(`manifest ${manifestPath} ${res.status}`);

    const data = await res.json();
    if (!Array.isArray(data)) return [];

    return data.map(item => {
      if (typeof item === 'string') return item.trim();
      if (item && typeof item === 'object') {
        if (typeof item.file === 'string') return item.file.trim();
        if (typeof item.xml === 'string') return item.xml.trim();
        if (typeof item.path === 'string') return item.path.trim();
      }
      return '';
    }).filter(Boolean);
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

  const prev = num > 1 ? `CV-${num - 1}.xml` : null;
  const next = `CV-${num + 1}.xml`;

  if (suf) {
    return { prev: `CV-${num}.xml`, next: `CV-${num}.xml` };
  }

  return { prev, next };
}

function setNavTarget(el, targetFileXml, disabled) {
  if (!el) return;

  const tag = (el.tagName || '').toUpperCase();
  const isLink = tag === 'A';
  const isButton = tag === 'BUTTON';

  if (disabled || !targetFileXml) {
    el.classList.add('disabled');
    el.setAttribute('aria-disabled', 'true');
    if (isLink) el.removeAttribute('href');
    if (isButton) el.disabled = true;
    el.onclick = null;
    return;
  }

  el.classList.remove('disabled');
  el.removeAttribute('aria-disabled');
  if (isButton) el.disabled = false;

  const href = buildViewerURL(targetFileXml);

  if (isLink) {
    el.href = href;
    return;
  }

  el.onclick = (ev) => {
    ev.preventDefault();
    window.location.href = href;
  };
}

async function setupDocNavigator(currentFileXml) {
  const prevEl = document.querySelector(
    '#prev-letter, #btnPrev, #prevBtn, a[data-nav="prev"], button[data-nav="prev"]'
  );
  const nextEl = document.querySelector(
    '#next-letter, #btnNext, #nextBtn, a[data-nav="next"], button[data-nav="next"]'
  );

  if (!prevEl && !nextEl) return;

  const list = await getOrderListFromURLorManifest();

  if (list.length) {
    const i = list.indexOf(currentFileXml);
    const prev = i > 0 ? list[i - 1] : null;
    const next = i >= 0 && i < list.length - 1 ? list[i + 1] : null;

    setNavTarget(prevEl, prev, !prev);
    setNavTarget(nextEl, next, !next);
    return;
  }

  const g = guessPrevNextByCVNumber(currentFileXml);
  setNavTarget(prevEl, g.prev, !g.prev);
  setNavTarget(nextEl, g.next, !g.next);
}

/* ===== UI ===== */
function disableNonImplementedUI() {
  document.querySelectorAll('.tab-button').forEach(btn => {
    const v = (btn.dataset.view || '').toLowerCase();
    if (v === 'encoded' || v === 'diplomatic') btn.remove();
  });

  const readingBtn = document.querySelector('.tab-button[data-view="reading"]');
  if (readingBtn) {
    readingBtn.disabled = false;
    if (!document.querySelector('.tab-button.active')) {
      readingBtn.classList.add('active');
    }
  }

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

/* ===== Standoff ===== */
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
        kind === 'places' ? xAll(doc, `//tei:place`) :
        kind === 'orgs' ? xAll(doc, `//tei:org`) :
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

/* ===== Tabs ===== */
function setupViewTabs() {
  document.querySelectorAll('.tab-button').forEach(btn => {
    btn.addEventListener('click', async () => {
      if (btn.disabled) return;

      const next = (btn.dataset.view || '').toLowerCase();
      if (!next) return;

      VIEW_MODE = next;

      document.querySelectorAll('.tab-button').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      document.querySelectorAll('.transcription-layer').forEach(l => {
        const v = (l.dataset.view || '').toLowerCase();
        l.classList.toggle('d-none', v !== VIEW_MODE);
      });

      if (VIEW_MODE === 'translation') {
        await renderTranslation(`${CURRENT_STEM}.xml`);
      }
    });
  });
}

/* ===== Annotations ===== */
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
          <div class="small text-muted mb-2">${escapeHTML(when)}</div>
          <p class="small mb-0">${escapeHTML(pretty || when)}</p>
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

/* ===== Standoff card ===== */
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
        <strong>${escapeHTML(x.type)}:</strong>
        <a href="${escapeHTML(x.value)}" target="_blank" rel="noopener">${escapeHTML(x.value)}</a>
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
          <a href="${escapeHTML(proj)}" target="_blank" rel="noopener">${escapeHTML(proj)}</a>
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
      <strong>Variants:</strong> ${escapeHTML(names.join(' · '))}
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
      extra = `<div class="small text-muted mb-1">${escapeHTML(birth || '')}${(birth && death) ? ' – ' : ''}${escapeHTML(death || '')}</div>`;
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
    if (when) extra = `<div class="small text-muted mb-1">${escapeHTML(formatPtBRDate(when) || when)}</div>`;
  }

  const variants = renderVariants(entry, kind);
  const idnos = renderIdnos(entry, kind);

  return `
    <div class="annotation-card">
      <h6 class="annotation-title">${escapeHTML(title || localId || '—')}</h6>
      ${extra}
      ${variants}
      ${idnos ? `<div class="mb-2">${idnos}</div>` : ''}
      ${note ? `<p class="small mb-0">${escapeHTML(note)}</p>` : ''}
    </div>
  `;
}

/* ===== Metadata ===== */
async function loadMetadataIndex() {
  if (METADATA_INDEX) return METADATA_INDEX;

  try {
    const data = await fetchJSON(INDEXES_BASE_PATH + 'metadata.json');

    if (Array.isArray(data)) {
      const idx = Object.create(null);
      for (const row of data) {
        const key = (row?.cv_id || row?.id || row?.file || '').trim();
        if (!key) continue;
        idx[key] = row;
      }
      METADATA_INDEX = idx;
      return METADATA_INDEX;
    }

    if (data && typeof data === 'object') {
      METADATA_INDEX = data;
      return METADATA_INDEX;
    }

    METADATA_INDEX = null;
    return null;
  } catch (e) {
    METADATA_INDEX = null;
    console.warn('Could not load metadata index:', e);
    return null;
  }
}

function setDownloadLink(aEl, href, label) {
  if (!aEl) return;
  aEl.href = href;
  aEl.setAttribute('download', '');
  aEl.textContent = label;
}

async function renderMetadataPanel(stem, fileNameXml) {
  const mdTitle = document.getElementById('mdTitle');
  const mdFrom = document.getElementById('mdFrom');
  const mdTo = document.getElementById('mdTo');
  const mdPlace = document.getElementById('mdPlace');
  const mdDate = document.getElementById('mdDate');
  const mdType = document.getElementById('mdType');

  const dlXml = document.getElementById('dlXml');
  const dlJsonld = document.getElementById('dlJsonld');
  const dlTtl = document.getElementById('dlTtl');

  const safeSet = (el, val) => {
    if (!el) return;
    const v = (val == null) ? '' : String(val).trim();
    el.textContent = v ? v : '—';
  };

  const idx = await loadMetadataIndex();

  let meta = null;
  if (idx) {
    meta =
      idx[stem] ||
      idx[`${stem}.xml`] ||
      idx[`${stem}.html`] ||
      idx[stem.replace(/^CV-/, 'cv-')] ||
      null;

    if (!meta) {
      const k = Object.keys(idx).find(key => stemFromFile(key) === stem);
      if (k) meta = idx[k];
    }
  }

  if (meta) {
    safeSet(mdTitle, meta.subject || meta.title || '');
    safeSet(mdFrom, meta.author_name || meta.from || '');
    safeSet(mdTo, meta.recipient_name || meta.to || '');
    safeSet(mdPlace, meta.place_label || meta.place || '');
    safeSet(mdDate, meta.date || meta.when || '');
    safeSet(mdType, meta.type || meta.doc_type || '');
  } else {
    const letterInfo = document.getElementById('letter-info');
    const t = letterInfo?.querySelector('.letter-title')?.textContent || '';
    const d = letterInfo?.querySelector('.letter-date')?.textContent || '';
    safeSet(mdTitle, t);
    safeSet(mdDate, d);
    safeSet(mdFrom, '');
    safeSet(mdTo, '');
    safeSet(mdPlace, '');
    safeSet(mdType, '');
  }

  const xmlFile = fileNameXml && fileNameXml.endsWith('.xml') ? fileNameXml : `${stem}.xml`;
  setDownloadLink(dlXml, BASE_XML_PATH + xmlFile, 'Download TEI XML');
  setDownloadLink(dlJsonld, BASE_RDF_JSON_PATH + stem + '.json', 'Download JSON-LD');
  setDownloadLink(dlTtl, BASE_RDF_TTL_PATH + stem + '.ttl', 'Download TTL');
}

/* ===== Translation ===== */
function translationJSONToHTML(data) {
  const disclaimer = escapeHTML(data?.disclaimer || '');
  const translation = escapeHTML(data?.translation || '');

  const paras = translation
    .split(/\n{2,}/g)
    .map(p => p.trim())
    .filter(Boolean)
    .map(p => `<p>${p.replace(/\n/g, '<br/>')}</p>`)
    .join('');

  return `
    <div class="translation-disclaimer-box" role="note" aria-label="AI-assisted translation notice">
      <div class="translation-disclaimer-title">AI-assisted translation</div>
      <div class="translation-disclaimer-text" style="white-space: pre-wrap;">${disclaimer}</div>
    </div>
    <div class="translation-body">
      ${paras || '<p class="text-muted small">Empty translation.</p>'}
    </div>
  `;
}
function translationUnavailableHTML(cachePath) {
  const prodNote = isGitHubPages()
    ? `<p class="text-muted small mb-0">This site is served via GitHub Pages, so translations must be pre-generated and committed as static JSON files.</p>`
    : '';

  return `
    <p class="text-muted small mb-2">Translation not available for this document yet.</p>
    <p class="text-muted small mb-2">Expected cache: <code>${escapeHTML(cachePath)}</code></p>
    ${prodNote}
  `;
}
async function renderTranslation(fileParamXmlOrHtml) {
  const layer = document.querySelector(`.transcription-layer[data-view="translation"]`);
  if (!layer) return;

  layer.innerHTML = `<p class="text-muted small mb-0">Loading translation…</p>`;

  const stem = stemFromFile(fileParamXmlOrHtml);
  const target = DEFAULT_TARGET_LANG;
  const cachePath = `${TRANSLATIONS_BASE_PATH}${target}/${stem}.json`;

  try {
    const data = await fetchJSON(cachePath);
    layer.innerHTML = translationJSONToHTML(data);
    return;
  } catch (_) {}

  if (!allowTranslationApiFallback()) {
    layer.innerHTML = translationUnavailableHTML(cachePath);
    return;
  }

  try {
    const res = await fetch(TRANSLATION_API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file: `${stem}.xml`, target: target, force: false })
    });

    if (!res.ok) {
      let detail = `API ${res.status}`;
      try {
        const err = await res.json();
        if (err?.detail) detail = String(err.detail);
      } catch (_) {}
      throw new Error(detail);
    }

    const data = await res.json();
    layer.innerHTML = translationJSONToHTML(data);
  } catch (e2) {
    const msg = escapeHTML(e2?.message || String(e2));
    layer.innerHTML = `
      ${translationUnavailableHTML(cachePath)}
      <p class="text-muted small mt-2 mb-0">Dev API error: <code>${msg}</code></p>
    `;
  }
}