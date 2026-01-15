/* =========================================================
   Varela Digital – TEI Viewer
   ========================================================= */

console.log('viewer.js loaded');

/* Paths */
const BASE_XML_PATH = '../../data/documents_XML/';
const STANDOFF_BASE_PATH = '../../data/standoff/';

const STANDOFF_FILES = {
  persons: STANDOFF_BASE_PATH + 'standoff_persons.xml',
  places: STANDOFF_BASE_PATH + 'standoff_places.xml',
  orgs: STANDOFF_BASE_PATH + 'standoff_orgs.xml'
};

let VIEW_MODE = 'reading';
let STANDOFF_INDEX = {};
let CURRENT_TEI_DOC = null;

/* =========================================================
   Utilities
   ========================================================= */

function getQueryParam(name) {
  return new URLSearchParams(window.location.search).get(name);
}

async function fetchXML(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`Failed to load ${path}`);
  const txt = await res.text();
  return new DOMParser().parseFromString(txt, 'application/xml');
}

/* =========================================================
   Initialization
   ========================================================= */

document.addEventListener('DOMContentLoaded', async () => {
  const fileParam = getQueryParam('file');
  if (!fileParam) return;

  try {
    CURRENT_TEI_DOC = await fetchXML(BASE_XML_PATH + fileParam);
    await loadStandoffFiles();

    renderViewer(CURRENT_TEI_DOC, fileParam);
    setupViewTabs();
    setupAnnotationBehaviour();

  } catch (err) {
    console.error(err);
  }
});

/* =========================================================
   Standoff loading (FIXED)
   ========================================================= */

async function loadStandoffFiles() {
  for (const path of Object.values(STANDOFF_FILES)) {
    const xml = await fetchXML(path);

    xml.querySelectorAll('person[xml\\:id], place[xml\\:id], org[xml\\:id]')
      .forEach(el => {
        const id = el.getAttribute('xml:id');
        STANDOFF_INDEX[id] = el;
      });
  }

  console.log('STANDOFF INDEX LOADED:', Object.keys(STANDOFF_INDEX));
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
   Letter navigation
   ========================================================= */

function renderLetterNavInfo(teiDoc) {
  const box = document.getElementById('letter-info');
  if (!box) return;

  const title = teiDoc.querySelector('titleStmt > title')?.textContent || '';
  const date = teiDoc
    .querySelector('correspAction[type="sent"] date')
    ?.getAttribute('when') || '';

  box.innerHTML = `
    <div class="letter-title">${title}</div>
    <div class="letter-date">${date}</div>
  `;
}

/* =========================================================
   Metadata panel (NEW layout)
   ========================================================= */

const BASE_RDF_PATH = '../../data/rdf/';
const BASE_RDF_JSON_PATH = BASE_RDF_PATH + 'json/'; // e.g., CV-300.json
const BASE_RDF_TTL_PATH  = BASE_RDF_PATH + 'ttl/';  // e.g., CV-300.ttl

function renderMetadataPanel(teiDoc, fileName) {
  const panel = document.getElementById('metadataPanel');
  if (!panel) return;

  // Targets (new HTML ids)
  const mdTitle = document.getElementById('mdTitle');
  const mdFrom  = document.getElementById('mdFrom');
  const mdTo    = document.getElementById('mdTo');
  const mdPlace = document.getElementById('mdPlace');
  const mdDate  = document.getElementById('mdDate');
  const mdType  = document.getElementById('mdType');

  const dlXml    = document.getElementById('dlXml');
  const dlJsonld = document.getElementById('dlJsonld');
  const dlTtl    = document.getElementById('dlTtl');

  const safeSet = (el, val) => {
    if (!el) return;
    const v = (val || '').trim();
    el.textContent = v ? v : '—';
  };


  // Title
  const title = teiDoc.querySelector('teiHeader titleStmt > title')?.textContent || '';

  // From/To can be persName OR orgName (first one inside correspAction)
  const firstParty = (actionType) => {
    const action = teiDoc.querySelector(`teiHeader correspDesc correspAction[type="${actionType}"]`);
    if (!action) return '';
    const node = action.querySelector('persName, orgName');
    return node ? node.textContent : '';
  };

  // Place and date (sent) if present
  const sentAction = teiDoc.querySelector(`teiHeader correspDesc correspAction[type="sent"]`);
  const place = sentAction?.querySelector('placeName')?.textContent || '';
  const dateWhen = sentAction?.querySelector('date')?.getAttribute('when') || '';

  // Document type = @type of first div in body
  const docType = teiDoc.querySelector('text > body > div')?.getAttribute('type') || '';

  safeSet(mdTitle, title);
  safeSet(mdFrom, firstParty('sent'));
  safeSet(mdTo, firstParty('received'));
  safeSet(mdPlace, place);
  safeSet(mdDate, dateWhen);
  safeSet(mdType, docType);

  const stem = (fileName || '').replace(/\.xml$/i, '');
  const xmlHref  = BASE_XML_PATH + fileName;
  const jsonHref = BASE_RDF_JSON_PATH + stem + '.json'; 
  const ttlHref  = BASE_RDF_TTL_PATH  + stem + '.ttl';

  setDownloadLink(dlXml, xmlHref, `Download TEI XML`);
  setDownloadLink(dlJsonld, jsonHref, `Download JSON-LD`);
  setDownloadLink(dlTtl, ttlHref, `Download TTL`);
}

function setDownloadLink(aEl, href, label) {
  if (!aEl) return;
  aEl.href = href;
  aEl.setAttribute('download', '');
  aEl.textContent = label;
}

async function checkFileExists(url) {
  try {
    const res = await fetch(url, { method: 'HEAD' });
    return res.ok;
  } catch {
    return false;
  }
}

function toggleLink(aEl, enabled) {
  if (!aEl) return;
  aEl.classList.toggle('disabled', !enabled);
  aEl.setAttribute('aria-disabled', enabled ? 'false' : 'true');
  aEl.tabIndex = enabled ? 0 : -1;
}

/* =========================================================
   Text rendering
   ========================================================= */

function renderText(teiDoc) {
  const layer = document.querySelector(
    `.transcription-layer[data-view="${VIEW_MODE}"]`
  );
  if (!layer) return;

  layer.innerHTML = '';
  const div = teiDoc.querySelector('text > body > div');
  if (div) layer.appendChild(renderNode(div));
}

/* =========================================================
   View tabs
   ========================================================= */

function setupViewTabs() {
  document.querySelectorAll('.tab-button').forEach(btn => {
    btn.addEventListener('click', () => {
      if (btn.disabled) return;

      VIEW_MODE = btn.dataset.view;

      document.querySelectorAll('.tab-button')
        .forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      document.querySelectorAll('.transcription-layer')
        .forEach(l => l.classList.toggle(
          'd-none',
          l.dataset.view !== VIEW_MODE
        ));

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

  if (!box || !content) return;

  box.classList.add('d-none');

  document.addEventListener('click', e => {
    const span = e.target.closest('.annotated');
    if (!span || !span.dataset.ref) return;

    const id = span.dataset.ref.replace('#', '');
    const entry = STANDOFF_INDEX[id];

    document.body.classList.add('annotations-open');
    box.classList.remove('d-none');

    content.innerHTML = renderStandoffEntry(entry);
  });

  closeBtn.addEventListener('click', () => {
    box.classList.add('d-none');
    document.body.classList.remove('annotations-open');
    content.innerHTML = '';
  });
}

/* =========================================================
   Standoff renderer
   ========================================================= */

function renderStandoffEntry(entry) {
  if (!entry) {
    return `<p class="text-muted small">No annotation available.</p>`;
  }

  const tag = entry.tagName.toLowerCase();
  const getText = sel =>
    entry.querySelector(sel)?.textContent.trim() || '';

  const idnos = Array.from(entry.querySelectorAll('idno'))
    .filter(id => id.getAttribute('type') !== 'project')
    .map(id => `
      <div class="annotation-idno small">
        <strong>${id.getAttribute('type')}:</strong>
        <a href="${id.textContent}" target="_blank">${id.textContent}</a>
      </div>
    `)
    .join('');

  let html = '';

  if (tag === 'person') {
    const name = getText('persName');
    const birth = entry.querySelector('birth')?.getAttribute('when');
    const death = entry.querySelector('death')?.getAttribute('when');
    const note = getText('note');

    html += `<h6>${name}</h6>`;
    if (birth || death) {
      html += `<div class="small text-muted mb-1">
        ${birth || '?'} – ${death || '?'}
      </div>`;
    }
    html += idnos;
    if (note) html += `<p class="small">${note}</p>`;
  }

  else if (tag === 'place') {
    const name =
      getText('placeName[type="historical"]') || getText('placeName');
    const note = getText('note');

    html += `<h6>${name}</h6>`;
    html += idnos;
    if (note) html += `<p class="small">${note}</p>`;
  }

  else if (tag === 'org') {
    const name = getText('orgName');
    const note = getText('note');

    html += `<h6>${name}</h6>`;
    html += idnos;
    if (note) html += `<p class="small">${note}</p>`;
  }

  return html;
}

/* =========================================================
   TEI → HTML rendering
   ========================================================= */

function renderNode(node) {
  if (node.nodeType === Node.TEXT_NODE) {
    return document.createTextNode(node.textContent);
  }

  if (node.nodeType !== Node.ELEMENT_NODE) {
    return document.createDocumentFragment();
  }

  let el;

  switch (node.tagName) {

    case 'p':
      el = document.createElement('p'); break;

    case 'head':
      el = document.createElement('h3'); break;

    case 'choice':
      if (VIEW_MODE === 'reading') {
        const expan = node.querySelector('expan');
        return expan ? renderNode(expan) : document.createDocumentFragment();
      }
      el = document.createElement('span'); break;

    case 'pb':
      el = document.createElement('span');
      el.className = 'page-break';
      el.textContent =
        VIEW_MODE === 'reading'
          ? `[${node.getAttribute('n')}]`
          : `[pb ${node.getAttribute('n')}]`;
      break;

    case 'seg':
      if (node.getAttribute('type') === 'folio' && VIEW_MODE === 'reading') {
        return document.createDocumentFragment();
      }
      el = document.createElement('span');
      el.className = 'page-break';
      break;

    case 'persName':
    case 'placeName':
    case 'orgName':
    case 'date':
      el = document.createElement('span');
      el.className = 'annotated';
      if (node.getAttribute('ref')) {
        el.dataset.ref = node.getAttribute('ref');
      }
      break;

    case 'opener':
    case 'closer':
    case 'postscript':
    case 'note':
      el = document.createElement('div'); break;

    default:
      el = document.createElement('span');
  }

  node.childNodes.forEach(ch => el.appendChild(renderNode(ch)));
  return el;
}