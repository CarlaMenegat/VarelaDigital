/* =========================================================
   Varela Digital – TEI Viewer (viewer.js)
   - TEI namespaces handled via XPath
   - Standoff loaded once + indexed by xml:id
   - Click on entities opens annotations panel
   ========================================================= */

console.log('viewer.js loaded');

/* =========================================================
   Constants / Paths
   ========================================================= */

const TEI_NS = 'http://www.tei-c.org/ns/1.0';
const XML_NS = 'http://www.w3.org/XML/1998/namespace';

const BASE_XML_PATH = '../../data/documents_XML/';
const STANDOFF_BASE_PATH = '../../data/standoff/';

const STANDOFF_FILES = {
  persons: STANDOFF_BASE_PATH + 'standoff_persons.xml',
  places:  STANDOFF_BASE_PATH + 'standoff_places.xml',
  orgs:    STANDOFF_BASE_PATH + 'standoff_orgs.xml',
  events:  STANDOFF_BASE_PATH + 'standoff_events.xml'
};

// RDF download locations (relative to /assets/html/pages/)
const BASE_RDF_PATH      = '../../data/rdf/';
const BASE_RDF_JSON_PATH = BASE_RDF_PATH + 'json/'; // CV-300.json
const BASE_RDF_TTL_PATH  = BASE_RDF_PATH + 'ttl/';  // CV-300.ttl

let VIEW_MODE = 'reading';
let CURRENT_TEI_DOC = null;

// One index for all standoff entities: key = xml:id, value = Element
let STANDOFF_INDEX = Object.create(null);

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
  const doc = new DOMParser().parseFromString(txt, 'application/xml');

  // Basic XML parse error check
  const parseError = doc.querySelector('parsererror');
  if (parseError) {
    console.error(parseError.textContent);
    throw new Error(`XML parse error in ${path}`);
  }
  return doc;
}

/** Namespace resolver for XPath */
function nsResolver(prefix) {
  if (prefix === 'tei') return TEI_NS;
  if (prefix === 'xml') return XML_NS;
  return null;
}

/** XPath string helper */
function xStr(docOrNode, xpath) {
  return docOrNode.evaluate(
    xpath,
    docOrNode,
    nsResolver,
    XPathResult.STRING_TYPE,
    null
  ).stringValue.trim();
}

/** XPath node helper */
function xNode(docOrNode, xpath) {
  return docOrNode.evaluate(
    xpath,
    docOrNode,
    nsResolver,
    XPathResult.FIRST_ORDERED_NODE_TYPE,
    null
  ).singleNodeValue;
}

/** XPath nodes helper */
function xNodes(docOrNode, xpath) {
  const out = [];
  const it = docOrNode.evaluate(
    xpath,
    docOrNode,
    nsResolver,
    XPathResult.ORDERED_NODE_ITERATOR_TYPE,
    null
  );
  let n = it.iterateNext();
  while (n) {
    out.push(n);
    n = it.iterateNext();
  }
  return out;
}

function getXmlId(el) {
  return el?.getAttributeNS(XML_NS, 'id') || '';
}

function textOf(node) {
  return (node?.textContent || '').trim();
}

/* =========================================================
   Project URI builder (fallback when only <idno type="project"/>)
   ========================================================= */

function buildProjectURI(localId, kind) {
  if (!localId) return '';
  if (kind === 'org')   return `https://carlamenegat.github.io/VarelaDigital/org/${localId}`;
  if (kind === 'place') return `https://carlamenegat.github.io/VarelaDigital/place/${localId}`;
  if (kind === 'event') return `https://carlamenegat.github.io/VarelaDigital/event/${localId}`;
  return `https://carlamenegat.github.io/VarelaDigital/person/${localId}`;
}

/* =========================================================
   Initialization
   ========================================================= */

document.addEventListener('DOMContentLoaded', async () => {
  const fileParam = getQueryParam('file');
  if (!fileParam) {
    console.warn('No ?file= provided.');
    return;
  }

  try {
    // 1) Load TEI document
    CURRENT_TEI_DOC = await fetchXML(BASE_XML_PATH + fileParam);

    // 2) Load standoff once
    await loadStandoffFiles();

    // 3) Render viewer
    renderViewer(CURRENT_TEI_DOC, fileParam);

    // 4) Bind UI interactions
    setupViewTabs();
    setupAnnotationBehaviour();

  } catch (err) {
    console.error(err);
  }
});

/* =========================================================
   Standoff loading + indexing
   ========================================================= */

async function loadStandoffFiles() {
  STANDOFF_INDEX = Object.create(null);

  const files = Object.values(STANDOFF_FILES);
  const docs = await Promise.all(files.map(p => fetchXML(p)));

  // Index persons, places, orgs, events by xml:id
  for (const doc of docs) {
    // We index any TEI element that has xml:id in standoff
    // but restrict to the expected container elements:
    const entries = xNodes(doc, '//*[@xml:id]');
    for (const el of entries) {
      const id = getXmlId(el);
      if (id) STANDOFF_INDEX[id] = el;
    }
  }

  console.log('Standoff loaded. Entries indexed:', Object.keys(STANDOFF_INDEX).length);
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
   Letter navigation info (title/date display in the top bar)
   ========================================================= */

function renderLetterNavInfo(teiDoc) {
  const box = document.getElementById('letter-info');
  if (!box) return;

  const title = xStr(teiDoc, 'string(//tei:teiHeader//tei:titleStmt/tei:title[1])');

  // sent date if present
  const when = xStr(teiDoc, 'string((//tei:teiHeader//tei:correspDesc//tei:correspAction[@type="sent"]/tei:date[1]/@when))');

  box.innerHTML = `
    <div class="letter-title">${title || ''}</div>
    <div class="letter-date">${when || ''}</div>
  `;
}

/* =========================================================
   Metadata panel (new layout)
   ========================================================= */

function renderMetadataPanel(teiDoc, fileName) {
  const panel = document.getElementById('metadataPanel');
  if (!panel) return;

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
  const title = xStr(teiDoc, 'string(//tei:teiHeader//tei:titleStmt/tei:title[1])');

  // From/To: first persName OR orgName inside correspAction
  const from = xStr(
    teiDoc,
    'string((//tei:teiHeader//tei:correspDesc//tei:correspAction[@type="sent"]/*[self::tei:persName or self::tei:orgName])[1])'
  );

  const to = xStr(
    teiDoc,
    'string((//tei:teiHeader//tei:correspDesc//tei:correspAction[@type="received"]/*[self::tei:persName or self::tei:orgName])[1])'
  );

  // Place + date from sent
  const place = xStr(teiDoc, 'string((//tei:teiHeader//tei:correspDesc//tei:correspAction[@type="sent"]/tei:placeName)[1])');
  const dateWhen = xStr(teiDoc, 'string((//tei:teiHeader//tei:correspDesc//tei:correspAction[@type="sent"]/tei:date[1]/@when))');

  // Document type = @type of the first div in body
  const docType = xStr(teiDoc, 'string((//tei:text//tei:body/tei:div[1]/@type))');

  safeSet(mdTitle, title);
  safeSet(mdFrom, from);
  safeSet(mdTo, to);
  safeSet(mdPlace, place);
  safeSet(mdDate, dateWhen);
  safeSet(mdType, docType);

  // Downloads
  const stem = (fileName || '').replace(/\.xml$/i, '');
  const xmlHref  = BASE_XML_PATH + fileName;
  const jsonHref = BASE_RDF_JSON_PATH + stem + '.json'; // user prefers .json
  const ttlHref  = BASE_RDF_TTL_PATH  + stem + '.ttl';

  setDownloadLink(dlXml, xmlHref, `Download TEI XML`);
  setDownloadLink(dlJsonld, jsonHref, `Download JSON`);
  setDownloadLink(dlTtl, ttlHref, `Download TTL`);
}

function setDownloadLink(aEl, href, label) {
  if (!aEl) return;
  aEl.href = href;
  aEl.setAttribute('download', '');
  aEl.textContent = label;
}

/* =========================================================
   Text rendering
   ========================================================= */

function renderText(teiDoc) {
  const layer = document.querySelector(`.transcription-layer[data-view="${VIEW_MODE}"]`);
  if (!layer) return;

  layer.innerHTML = '';

  // First div in body
  const div = xNode(teiDoc, '//tei:text/tei:body/tei:div[1]');
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

      document.querySelectorAll('.tab-button').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      document.querySelectorAll('.transcription-layer').forEach(l => {
        l.classList.toggle('d-none', l.dataset.view !== VIEW_MODE);
      });

      renderText(CURRENT_TEI_DOC);
    });
  });
}

/* =========================================================
   Annotation behaviour
   - Hidden by default (annotations-box has d-none)
   - Clicking .annotated opens panel and renders standoff entry
   ========================================================= */

function setupAnnotationBehaviour() {
  const box = document.getElementById('annotations-box');
  const content = document.getElementById('annotations-content');
  const closeBtn = document.getElementById('close-annotations');

  if (!box || !content || !closeBtn) return;

  // Start hidden
  box.classList.add('d-none');

  document.addEventListener('click', (e) => {
    const span = e.target.closest('.annotated');
    if (!span) return;

    // Entities with @ref
    if (span.dataset.ref) {
      const id = span.dataset.ref.replace('#', '');
      const entry = STANDOFF_INDEX[id];

      document.body.classList.add('annotations-open');
      box.classList.remove('d-none');

      content.innerHTML = renderStandoffEntryCard(entry);
      return;
    }

    // Dates with @when (even if no ref)
    if (span.dataset.when) {
      document.body.classList.add('annotations-open');
      box.classList.remove('d-none');

      content.innerHTML = `
        <div class="annotation-card">
          <h6 class="annotation-title">Date</h6>
          <div class="small text-muted mb-2">${span.dataset.when}</div>
          <p class="small mb-0">${span.textContent.trim()}</p>
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
   Standoff entry renderer (card)
   - Shows: label + variants + idnos (incl. project fallback) + note
   ========================================================= */

function renderStandoffEntryCard(entry) {
  if (!entry) {
    return `<p class="text-muted small">No annotation available.</p>`;
  }

  const tag = (entry.localName || entry.tagName || '').toLowerCase(); // person/place/org/event
  const localId = getXmlId(entry);

  const qAllLocal = (localName) => Array.from(entry.getElementsByTagNameNS(TEI_NS, localName));

  const getFirst = (localName) => {
    const nodes = qAllLocal(localName);
    return nodes.length ? textOf(nodes[0]) : '';
  };

  const renderVariants = (kind) => {
    let names = [];
    if (kind === 'person') names = qAllLocal('persName').map(textOf).filter(Boolean);
    if (kind === 'place')  names = qAllLocal('placeName').map(textOf).filter(Boolean);
    if (kind === 'org')    names = qAllLocal('orgName').map(textOf).filter(Boolean);
    if (names.length <= 1) return '';
    return `
      <div class="small text-muted mb-2">
        <strong>Variants:</strong> ${names.join(' · ')}
      </div>
    `;
  };

  const renderIdnos = (kind) => {
    const idnoNodes = qAllLocal('idno');
    const idnos = idnoNodes.map(n => ({
      type: (n.getAttribute('type') || '').trim(),
      value: textOf(n)
    }));

    const hasProjectPlaceholder = idnos.some(x => x.type === 'project'); // empty or not
    const real = idnos.filter(x => x.type && x.type !== 'project' && x.value);

    const parts = [];

    // External ids
    for (const x of real) {
      parts.push(`
        <div class="annotation-idno small">
          <strong>${x.type}:</strong>
          <a href="${x.value}" target="_blank" rel="noopener">${x.value}</a>
        </div>
      `);
    }

    // Place: geonames placeholder common in your pattern
    const geon = idnos.find(x => x.type === 'geonames');
    if (geon && !geon.value) {
      parts.push(`
        <div class="annotation-idno small">
          <strong>geonames:</strong> <span class="text-muted">not set</span>
        </div>
      `);
    }

    // Project fallback URI
    if (hasProjectPlaceholder || real.length === 0) {
      const proj = buildProjectURI(localId, kind);
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
  };

  // Title/note/extra
  let kind = tag;
  let title = '';
  let note = getFirst('note');
  let extra = '';

  if (tag === 'person') {
    title = getFirst('persName');
    const birth = qAllLocal('birth')[0]?.getAttribute('when') || '';
    const death = qAllLocal('death')[0]?.getAttribute('when') || '';
    if (birth || death) extra = `<div class="small text-muted mb-1">${birth || '?'} – ${death || '?'}</div>`;
  }

  if (tag === 'place') {
    const placeNames = qAllLocal('placeName');
    const historical = placeNames.find(n => (n.getAttribute('type') || '').toLowerCase() === 'historical');
    title = textOf(historical) || textOf(placeNames[0]) || '';
  }

  if (tag === 'org') {
    title = getFirst('orgName');
  }

  if (tag === 'event') {
    title = getFirst('desc') || (localId ? `Event ${localId}` : 'Event');
    const when = qAllLocal('date')[0]?.getAttribute('when') || '';
    if (when) extra = `<div class="small text-muted mb-1">${when}</div>`;
  }

  const variants = renderVariants(kind);
  const idnos = renderIdnos(kind);

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
   - Uses node.localName to ignore namespaces
   - Adds .annotated spans for persName/placeName/orgName/date
   - For dates: adds data-when
   ========================================================= */

function renderNode(node) {
  // Text node
  if (node.nodeType === Node.TEXT_NODE) {
    return document.createTextNode(node.textContent);
  }

  // Non-element
  if (node.nodeType !== Node.ELEMENT_NODE) {
    return document.createDocumentFragment();
  }

  const name = (node.localName || node.tagName || '').toLowerCase();
  let el;

  switch (name) {
    case 'div':
      el = document.createElement('div');
      break;

    case 'p':
      el = document.createElement('p');
      break;

    case 'head':
      el = document.createElement('h3');
      break;

    case 'lb':
      return document.createElement('br');

    case 'choice': {
      // In reading view, prefer expan; otherwise show full content
      if (VIEW_MODE === 'reading') {
        const expan = Array.from(node.childNodes).find(
          n => n.nodeType === Node.ELEMENT_NODE && (n.localName || '').toLowerCase() === 'expan'
        );
        return expan ? renderNode(expan) : document.createDocumentFragment();
      }
      el = document.createElement('span');
      break;
    }

    case 'abbr':
    case 'expan':
    case 'hi':
    case 'seg':
    case 'signed':
    case 'salute':
    case 'dateline':
    case 'opener':
    case 'closer':
    case 'postscript':
    case 'note':
    case 'address':
      el = document.createElement('span');
      // Some blocks are better as divs visually; keep span for minimal interference.
      // If you prefer: opener/closer/postscript/note could be 'div' instead.
      if (['opener', 'closer', 'postscript', 'note', 'address', 'dateline'].includes(name)) {
        el = document.createElement('div');
      }
      break;

    case 'pb': {
      el = document.createElement('span');
      el.className = 'page-break';
      const n = node.getAttribute('n') || '';
      el.textContent = VIEW_MODE === 'reading' ? `[${n}]` : `[pb ${n}]`;
      return el;
    }

    // Annotated entities
    case 'persname':
    case 'placename':
    case 'orgname':
    case 'date': {
      el = document.createElement('span');
      el.className = 'annotated';

      const ref = node.getAttribute('ref');
      if (ref) el.dataset.ref = ref;

      if (name === 'date') {
        const when = node.getAttribute('when');
        if (when) el.dataset.when = when;
      }
      break;
    }

    default:
      el = document.createElement('span');
  }

  // Copy some lightweight rendering hints if you ever need later
  // (we are not doing anything fancy with @rend right now)
  // const rend = node.getAttribute('rend'); if (rend) el.dataset.rend = rend;

  // Render children
  node.childNodes.forEach(ch => el.appendChild(renderNode(ch)));
  return el;
}