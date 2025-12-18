const annotationFiles = {
  events: 'data/standoff/standoff_events.xml',
  organziations: 'data/standoff/standoff_org.xml',
  persons: 'data/standoff/standoff_person.xml',
  places: 'annotations/annotations_org.xml',
  date: 'data/standoff/standoff_places.xml',
  relations: 'data/standoff/standoff_relations.xml'
};

const basePath = 'data/documents_XML/';
const annotationData = {};
const TEI_NS = 'http://www.tei-c.org/ns/1.0';

async function loadXML(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`Failed to fetch ${path}`);
  const text = await response.text();
  return new DOMParser().parseFromString(text, 'application/xml');
}

async function preloadAnnotationData() {
  await Promise.all(
    Object.entries(annotationFiles).map(async ([type, path]) => {
      try {
        annotationData[type] = await loadXML(path);
      } catch {
        console.warn(`Annotation file not loaded: ${path}`);
      }
    })
  );
}

function extractDescriptionFromRef(type, ref) {
  const id = ref.replace(/^#/, '');
  const doc = annotationData[type];
  if (!doc) return ref;

  if (type === 'person') {
    for (let p of doc.getElementsByTagNameNS(TEI_NS, 'person')) {
      if (p.getAttributeNS('http://www.w3.org/XML/1998/namespace', 'id') === id) {
        const name = p.querySelector('persName')?.textContent || '';
        const note = p.querySelector('note')?.textContent || '';
        return note ? `${name}<br>${note}` : name;
      }
    }
  }

  if (type === 'place') {
    for (let pl of doc.getElementsByTagNameNS(TEI_NS, 'place')) {
      if (pl.getAttributeNS('http://www.w3.org/XML/1998/namespace', 'id') === id) {
        const name = pl.querySelector('placeName')?.textContent || '';
        const note = pl.querySelector('note')?.textContent || '';
        return note ? `${name}<br>${note}` : name;
      }
    }
  }

  if (type === 'org') {
    for (let o of doc.getElementsByTagNameNS(TEI_NS, 'org')) {
      if (o.getAttributeNS('http://www.w3.org/XML/1998/namespace', 'id') === id) {
        const name = o.querySelector('orgName')?.textContent || '';
        const note = o.querySelector('note')?.textContent || '';
        return note ? `${name}<br>${note}` : name;
      }
    }
  }

  return ref;
}

function renderTEIText(node) {
  let html = '';

  node.childNodes.forEach(child => {
    if (child.nodeType === 1) {
      const tag = child.tagName.split(':').pop();
      const ref = child.getAttribute('ref');
      const content = renderTEIText(child);

      const classMap = {
        persName: 'person',
        placeName: 'place',
        orgName: 'org',
        date: 'date'
      };

      if (ref && classMap[tag]) {
        const desc = extractDescriptionFromRef(classMap[tag], ref);
        html += `<span class="annotated" data-type="${classMap[tag]}" data-desc="${desc.replace(/"/g, '&quot;')}">${content}</span>`;
        return;
      }

      if (tag === 'p') {
        html += `<p>${content}</p>`;
        return;
      }

      if (tag === 'lb') {
        html += '<br/>';
        return;
      }

      if (tag === 'choice') {
        const expan = child.querySelector('expan');
        html += expan ? renderTEIText(expan) : content;
        return;
      }

      html += content;
    } else if (child.nodeType === 3) {
      html += child.textContent;
    }
  });

  return html;
}

function applyAnnotationClicks(container) {
  container.querySelectorAll('.annotated').forEach(el => {
    el.addEventListener('click', () => {
      const desc = el.dataset.desc;
      const type = el.dataset.type;
      document.getElementById('annotations-content').innerHTML =
        `<div class="annotation-box"><strong>${type.toUpperCase()}</strong><br>${desc}</div>`;
      document.getElementById('annotations-box').classList.remove('d-none');
    });
  });
}

function updateTextForSurface(surfaceId, fileName) {
  const teiDoc = annotationData._teiDoc;
  const container = document.getElementById('transcription-content');

  const divs = teiDoc.getElementsByTagNameNS(TEI_NS, 'div');
  const target = Array.from(divs).find(
    d => d.getAttribute('corresp') === `#${surfaceId}`
  );

  if (target) {
    container.innerHTML = renderTEIText(target);
  } else {
    const letterDiv = Array.from(divs).find(
      d => d.getAttribute('type') === 'letter'
    );
    container.innerHTML = renderTEIText(letterDiv);
  }

  applyAnnotationClicks(container);
}

async function renderViewer(fileName) {
  const teiDoc = await loadXML(basePath + fileName);
  annotationData._teiDoc = teiDoc;
  window.currentLetterFileName = fileName;

  const selector = document.getElementById('surface-selector');
  selector.innerHTML = '';

  const divs = teiDoc.getElementsByTagNameNS(TEI_NS, 'div');
  const surfaces = Array.from(divs)
    .map(d => d.getAttribute('corresp'))
    .filter(v => v && v.startsWith('#surface-'))
    .map(v => v.slice(1));

  if (surfaces.length === 0) {
    selector.style.display = 'none';
    updateTextForSurface(null, fileName);
  } else {
    selector.style.display = 'inline-block';
    surfaces.forEach(s => {
      const opt = document.createElement('option');
      opt.value = s;
      opt.textContent = s.replace('surface-', 'Page ');
      selector.appendChild(opt);
    });
    selector.value = surfaces[0];
    updateTextForSurface(surfaces[0], fileName);
  }

  fillMetadataPanel(fileName);
}

function fillMetadataPanel(fileName) {
  const container = document.getElementById('metadata-content');
  container.innerHTML = '';

  loadXML(basePath + fileName).then(teiDoc => {
    const header = teiDoc.getElementsByTagNameNS(TEI_NS, 'teiHeader')[0];
    const title = header.querySelector('titleStmt > title')?.textContent || '';

    let sender = '';
    let receiver = '';
    let place = '';
    let date = '';

    const actions = header.getElementsByTagNameNS(TEI_NS, 'correspAction');
    for (let a of actions) {
      if (a.getAttribute('type') === 'sent') {
        sender = a.querySelector('persName')?.textContent || '';
        place = a.querySelector('placeName')?.textContent || '';
        date = a.querySelector('date')?.getAttribute('when') || '';
      }
      if (a.getAttribute('type') === 'received') {
        receiver = a.querySelector('persName')?.textContent || '';
      }
    }

    const publisher = header.querySelector('publicationStmt > publisher')?.textContent || '';
    const edition = header.querySelector('editionStmt > edition')?.textContent || '';

    container.innerHTML = `
      <div class="metadata-entry"><strong>Title:</strong><br>${title}</div>
      <div class="metadata-entry"><strong>Sender:</strong><br>${sender}</div>
      <div class="metadata-entry"><strong>Receiver:</strong><br>${receiver}</div>
      <div class="metadata-entry"><strong>Sent from:</strong><br>${place}</div>
      <div class="metadata-entry"><strong>Date:</strong><br>${date}</div>
      <div class="metadata-entry"><strong>Source:</strong><br>${publisher}</div>
      <div class="metadata-entry"><strong>Digital edition:</strong><br>${edition}</div>
      <div class="metadata-entry"><strong>RDF:</strong><br><em>Linked data export (planned)</em></div>
      <div class="metadata-entry">
        <strong>Download XML:</strong><br>
        <a href="${basePath + fileName}" download>Original TEI</a>
      </div>
    `;
  });
}

let letters = [];
let letterIndex = 0;

function setupLetterNavigation() {
  const params = new URLSearchParams(window.location.search);
  const fileParam = params.get('file');

  fetch('letters_order.json')
    .then(r => r.json())
    .then(data => {
      letters = data;
      let index = 0;
      if (fileParam) {
        const found = letters.findIndex(l => l.file === fileParam);
        if (found !== -1) index = found;
      }
      updateLetterView(index);
    });

  document.getElementById('prev-letter').onclick = () => {
    if (letterIndex > 0) updateLetterView(letterIndex - 1);
  };
  document.getElementById('next-letter').onclick = () => {
    if (letterIndex < letters.length - 1) updateLetterView(letterIndex + 1);
  };
}

function updateLetterView(index) {
  letterIndex = index;
  const letter = letters[index];
  renderViewer(letter.file);
  document.getElementById('letter-date').textContent =
    `${letter.place}, ${letter.date}`;
}

document.addEventListener('DOMContentLoaded', () => {
  preloadAnnotationData().then(setupLetterNavigation);

  document.getElementById('surface-selector')?.addEventListener('change', e => {
    updateTextForSurface(e.target.value, window.currentLetterFileName);
  });

  document.getElementById('close-annotations')?.addEventListener('click', () => {
    document.getElementById('annotations-box').classList.add('d-none');
  });
});