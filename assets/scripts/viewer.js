/* =========================================================
   Varela Digital – TEI Viewer
   ========================================================= */

/* Paths are relative to assets/html/viewer.html */
const BASE_XML_PATH = '../../data/documents_XML/';
const STANDOFF_BASE_PATH = '../../data/standoff/';

const STANDOFF_FILES = {
  persons: STANDOFF_BASE_PATH + 'standoff-persons.xml',
  places: STANDOFF_BASE_PATH + 'standoff-places.xml',
  events: STANDOFF_BASE_PATH + 'standoff-events.xml',
  orgs: STANDOFF_BASE_PATH + 'standoff-orgs.xml',
  relations: STANDOFF_BASE_PATH + 'standoff-relations.xml'
};

/* =========================================================
   Utilities
   ========================================================= */

function getQueryParam(name) {
  const params = new URLSearchParams(window.location.search);
  return params.get(name);
}

async function fetchXML(path) {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`Failed to load XML: ${path}`);
  }
  const text = await response.text();
  return new DOMParser().parseFromString(text, 'application/xml');
}

/* =========================================================
   Initialization
   ========================================================= */

document.addEventListener('DOMContentLoaded', async () => {
  const fileParam = getQueryParam('file');

  if (!fileParam) {
    console.warn('No file parameter provided (?file=CV-XXX.xml)');
    return;
  }

  try {
    const teiDoc = await fetchXML(BASE_XML_PATH + fileParam);
    renderViewer(teiDoc, fileParam);
  } catch (err) {
    console.error(err);
  }
});

/* =========================================================
   Main rendering
   ========================================================= */

function renderViewer(teiDoc, fileName) {
  renderMetadataSidebar(teiDoc, fileName);
  renderText(teiDoc);
}

/* =========================================================
   Metadata sidebar (from teiHeader only)
   ========================================================= */

function renderMetadataSidebar(teiDoc, fileName) {
  const sidebar = document.getElementById('metadata-sidebar');
  const content = sidebar.querySelector('.sidebar-content');

  content.innerHTML = '';

  const title =
    teiDoc.querySelector('titleStmt > title')?.textContent || '';
  const sender =
    teiDoc.querySelector('correspAction[type="sent"] persName')?.textContent ||
    '';
  const receiver =
    teiDoc.querySelector(
      'correspAction[type="received"] persName'
    )?.textContent || '';
  const place =
    teiDoc.querySelector(
      'correspAction[type="sent"] placeName'
    )?.textContent || '';
  const date =
    teiDoc
      .querySelector('correspAction[type="sent"] date')
      ?.getAttribute('when') || '';
  const publisher =
    teiDoc.querySelector('publicationStmt > publisher')?.textContent ||
    '';
  const edition =
    teiDoc.querySelector('editionStmt > edition')?.textContent || '';

  content.innerHTML = `
    <div class="metadata-entry"><strong>Title:</strong> ${title}</div>
    <div class="metadata-entry"><strong>From:</strong> ${sender}</div>
    <div class="metadata-entry"><strong>To:</strong> ${receiver}</div>
    <div class="metadata-entry"><strong>Place:</strong> ${place}</div>
    <div class="metadata-entry"><strong>Date:</strong> ${date}</div>
    <div class="metadata-entry"><strong>Source:</strong> ${publisher}</div>
    <div class="metadata-entry"><strong>Digital edition:</strong> ${edition}</div>
    <div class="metadata-entry">
      <a href="${BASE_XML_PATH + fileName}" target="_blank">
        Download TEI XML
      </a>
    </div>
    <div class="metadata-entry">
      <em>RDF version (coming soon)</em>
    </div>
  `;

  sidebar.classList.add('open');
}

/* =========================================================
   Text rendering
   ========================================================= */

function renderText(teiDoc) {
  const container = document.getElementById('transcription-content');
  container.innerHTML = '';

  const textDiv = teiDoc.querySelector('text > body > div');

  if (!textDiv) {
    console.warn('No text division found');
    return;
  }

  /* Fallback: no surface-based rendering yet */
  container.appendChild(renderNode(textDiv));
}

/* =========================================================
   Recursive TEI → HTML rendering
   ========================================================= */

function renderNode(node) {
  if (node.nodeType === Node.TEXT_NODE) {
    return document.createTextNode(node.textContent);
  }

  if (node.nodeType !== Node.ELEMENT_NODE) {
    return document.createTextNode('');
  }

  let el;

  switch (node.tagName) {
    case 'p':
      el = document.createElement('p');
      break;
    case 'head':
      el = document.createElement('h3');
      break;
    case 'pb':
      el = document.createElement('span');
      el.className = 'page-break';
      el.textContent = `[${node.getAttribute('n')}]`;
      break;
    case 'persName':
    case 'placeName':
    case 'orgName':
    case 'date':
      el = document.createElement('span');
      el.className = 'annotated';
      break;
    case 'list':
      el = document.createElement(
        node.getAttribute('type') === 'ordered' ? 'ol' : 'ul'
      );
      break;
    case 'item':
      el = document.createElement('li');
      break;
    case 'opener':
    case 'closer':
    case 'postscript':
    case 'note':
      el = document.createElement('div');
      break;
    default:
      el = document.createElement('span');
  }

  for (const child of node.childNodes) {
    el.appendChild(renderNode(child));
  }

  return el;
}