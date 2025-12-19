/* =========================================================
   Varela Digital – TEI Viewer
   ========================================================= */

console.log('viewer.js loaded');

/* Paths relative to assets/html/viewer.html */
const BASE_XML_PATH = '../../data/documents_XML/';
const STANDOFF_BASE_PATH = '../../data/standoff/';

const STANDOFF_FILES = {
  persons: STANDOFF_BASE_PATH + 'standoff-persons.xml',
  places: STANDOFF_BASE_PATH + 'standoff-places.xml',
  orgs: STANDOFF_BASE_PATH + 'standoff-orgs.xml'
};

let VIEW_MODE = 'reading';
let STANDOFF_INDEX = {};

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
    const teiDoc = await fetchXML(BASE_XML_PATH + fileParam);
    window.CURRENT_TEI_DOC = teiDoc;

    await loadStandoffFiles();

    renderViewer(teiDoc, fileParam);
    setupViewTabs();
    setupAnnotationBehaviour();

  } catch (err) {
    console.error(err);
  }
});

/* =========================================================
   Load standoff files
   ========================================================= */

async function loadStandoffFiles() {
  for (const path of Object.values(STANDOFF_FILES)) {
    const xml = await fetchXML(path);
    indexStandoff(xml);
  }
}

function indexStandoff(xml) {
  xml.querySelectorAll('[xml\\:id]').forEach(el => {
    const id = el.getAttribute('xml:id');
    STANDOFF_INDEX[id] = el;
  });
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

      renderText(window.CURRENT_TEI_DOC);
    });
  });
}

/* =========================================================
   Annotation behaviour (standoff integration)
   ========================================================= */

function setupAnnotationBehaviour() {
  const box = document.getElementById('annotations-box');
  const content = document.getElementById('annotations-content');
  const closeBtn = document.getElementById('close-annotations');

  if (!box || !content) return;

  box.classList.add('d-none');

  document.addEventListener('click', e => {
    const span = e.target.closest('.annotated');
    if (!span) return;

    const ref = span.dataset.ref;
    if (!ref) return;

    const id = ref.replace('#', '');
    const entry = STANDOFF_INDEX[id];

    document.body.classList.add('annotations-open');
    box.classList.remove('d-none');

    if (!entry) {
      content.innerHTML = `
        <p class="text-muted small">
          No annotation available for this entity.
        </p>`;
      return;
    }

    const label =
      entry.querySelector('persName, placeName, orgName')?.textContent || id;
    const note =
      entry.querySelector('note')?.textContent || '';

    content.innerHTML = `
      <h6>${label}</h6>
      <p class="small">${note}</p>
    `;
  });

  closeBtn.addEventListener('click', () => {
    box.classList.add('d-none');
    document.body.classList.remove('annotations-open');
    content.innerHTML = '';
  });
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

  const tag = node.tagName.toLowerCase();
  let el;

  switch (tag) {

    case 'p':
      el = document.createElement('p');
      break;

    case 'head':
      el = document.createElement('h3');
      break;

    case 'opener':
    case 'closer':
    case 'postscript':
    case 'note':
      el = document.createElement('div');
      break;

    case 'choice':
      if (VIEW_MODE === 'reading') {
        const expan = node.querySelector('expan');
        return expan
          ? renderNode(expan)
          : document.createDocumentFragment();
      }
      el = document.createElement('span');
      break;

    case 'pb':
      el = document.createElement('span');
      el.className = 'page-break';
      el.textContent =
        VIEW_MODE === 'reading'
          ? `[${node.getAttribute('n')}]`
          : `[pb ${node.getAttribute('n')}]`;
      break;

    case 'seg':
      if (node.getAttribute('type') === 'folio') {
        if (VIEW_MODE === 'reading') {
          return document.createDocumentFragment();
        }
        el = document.createElement('span');
        el.className = 'page-break';
        el.textContent = node.textContent;
        break;
      }
      el = document.createElement('span');
      break;

    case 'persname':
    case 'placename':
    case 'orgname':
    case 'date':
      el = document.createElement('span');
      el.className = 'annotated';
      el.dataset.type = tag.replace('name', '');
      if (node.getAttribute('ref')) {
        el.dataset.ref = node.getAttribute('ref');
      }
      break;

    default:
      el = document.createElement('span');
  }

  node.childNodes.forEach(child => {
    el.appendChild(renderNode(child));
  });

  return el;
}