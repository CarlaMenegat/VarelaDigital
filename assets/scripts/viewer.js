/* =========================================================
   Varela Digital – TEI Viewer
   ========================================================= */

console.log('viewer.js loaded');

/* Paths */
const BASE_XML_PATH = '../../data/documents_XML/';
const STANDOFF_BASE_PATH = '../../data/standoff/';

const STANDOFF_FILES = {
  person: STANDOFF_BASE_PATH + 'standoff-person.xml',
  places: STANDOFF_BASE_PATH + 'standoff-places.xml',
  orgs: STANDOFF_BASE_PATH + 'standoff-orgs.xml'
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
   Standoff loading
   ========================================================= */

async function loadStandoffFiles() {
  for (const path of Object.values(STANDOFF_FILES)) {
    const xml = await fetchXML(path);
    xml.querySelectorAll('[xml\\:id]').forEach(el => {
      STANDOFF_INDEX[el.getAttribute('xml:id')] = el;
    });
  }
}

/* =========================================================
   Viewer rendering
   ========================================================= */

function renderViewer(teiDoc, fileName) {
  renderLetterNavInfo(teiDoc);
  renderMetadataSidebar(teiDoc, fileName);
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
   Metadata sidebar
   ========================================================= */

function renderMetadataSidebar(teiDoc, fileName) {
  const c = document.getElementById('metadata-content');
  if (!c) return;

  const q = s => teiDoc.querySelector(s)?.textContent || '';
  const qa = (s, a) => teiDoc.querySelector(s)?.getAttribute(a) || '';

  c.innerHTML = `
    <div class="metadata-entry"><strong>Title:</strong> ${q('titleStmt > title')}</div>
    <div class="metadata-entry"><strong>From:</strong> ${q('correspAction[type="sent"] persName')}</div>
    <div class="metadata-entry"><strong>To:</strong> ${q('correspAction[type="received"] persName')}</div>
    <div class="metadata-entry"><strong>Place:</strong> ${q('correspAction[type="sent"] placeName')}</div>
    <div class="metadata-entry"><strong>Date:</strong> ${qa('correspAction[type="sent"] date','when')}</div>
    <div class="metadata-entry">
      <a href="${BASE_XML_PATH + fileName}" target="_blank">Download TEI XML</a>
    </div>
  `;
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