#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import csv
import re
from pathlib import Path
from datetime import date

from lxml import etree as ET
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, XSD, SKOS


# -----------------------------
# Paths
# -----------------------------

BASE_DIR = Path("/Users/carlamenegat/Documents/GitHub/Untitled/VarelaDigital")
DATA_DIR = BASE_DIR / "letters_data"

CSV_METADATA = DATA_DIR / "metadata/metadata_all.csv"

STANDOFF_DIR = DATA_DIR / "standoff"
STANDOFF_PERSONS = STANDOFF_DIR / "standoff_persons.xml"
STANDOFF_ORGS = STANDOFF_DIR / "standoff_orgs.xml"
STANDOFF_PLACES = STANDOFF_DIR / "standoff_places.xml"
STANDOFF_EVENTS = STANDOFF_DIR / "standoff_events.xml"
STANDOFF_RELATIONS = STANDOFF_DIR / "standoff_relations.xml"


OUT_DIR = BASE_DIR / "assets/data/rdf"
OUT_TTL = OUT_DIR / "graph.ttl"
OUT_JSONLD = OUT_DIR / "graph.jsonld"


def require_file(p: Path) -> None:
    if not p.exists():
        raise FileNotFoundError(f"Required file not found:\n  {p}")


def safe_parse(path: Path) -> ET._ElementTree:
    try:
        return ET.parse(str(path))
    except ET.XMLSyntaxError as e:
        raise RuntimeError(f"XML syntax error while parsing: {path}\n{e}") from e


# -----------------------------
# Namespaces
# -----------------------------

BASE_URI = "https://carlamenegat.github.io/VarelaDigital/"
PERSON_BASE = BASE_URI + "person/"
ORG_BASE = BASE_URI + "org/"
PLACE_BASE = BASE_URI + "place/"
EVENT_BASE = BASE_URI + "event/"
LETTER_BASE = BASE_URI + "letter/"

# Option B provenance
DATASET_URI = URIRef(BASE_URI + "dataset/kbvareladigital")
PROCESS_URI = URIRef(BASE_URI + "process/rdf-generation")
AGENT_URI = URIRef(BASE_URI + "agent/carla-menegat")

SOURCE_PERSONS_URI = URIRef(BASE_URI + "source/standoff_persons_xml")
SOURCE_ORGS_URI = URIRef(BASE_URI + "source/standoff_orgs_xml")
SOURCE_PLACES_URI = URIRef(BASE_URI + "source/standoff_places_xml")
SOURCE_EVENTS_URI = URIRef(BASE_URI + "source/standoff_events_xml")
SOURCE_RELATIONS_URI = URIRef(BASE_URI + "source/standoff_relations_xml")
SOURCE_METADATA_URI = URIRef(BASE_URI + "source/metadata_all_csv")

TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"

DCTERMS = Namespace("http://purl.org/dc/terms/")
FOAF = Namespace("http://xmlns.com/foaf/0.1/")
PRO = Namespace("http://purl.org/spar/pro/")

# IMPORTANT: use https consistently to avoid schema1:
SCHEMA = Namespace("https://schema.org/")

PROV = Namespace("http://www.w3.org/ns/prov#")
REL = Namespace("http://purl.org/vocab/relationship/")
RICO = Namespace("https://www.ica.org/standards/RiC/ontology#")
FABIO = Namespace("http://purl.org/spar/fabio/")
FRBR = Namespace("http://purl.org/vocab/frbr/core#")

# SAN
SAN = Namespace("http://dati.san.beniculturali.it/ode/?uri=http://dati.san.beniculturali.it/SAN/")

# HRAO predicates must be '#'
HRAO = Namespace(BASE_URI + "hrao#")

PREFIX_MAP = {
    "dcterms": str(DCTERMS),
    "foaf": str(FOAF),
    "pro": str(PRO),
    "schema": str(SCHEMA),
    "prov": str(PROV),
    "rel": str(REL),
    "rico": str(RICO),
    "fabio": str(FABIO),
    "frbr": str(FRBR),
    "san": str(SAN),
    "hrao": str(HRAO),
}


# -----------------------------
# URI builders
# -----------------------------

def person_uri(pid: str) -> URIRef:
    return URIRef(PERSON_BASE + pid)


def org_uri(oid: str) -> URIRef:
    return URIRef(ORG_BASE + oid)


def place_uri(pid: str) -> URIRef:
    return URIRef(PLACE_BASE + pid)


def event_uri(eid: str) -> URIRef:
    return URIRef(EVENT_BASE + eid)


def letter_uri(cv_id: str) -> URIRef:
    return URIRef(LETTER_BASE + cv_id)


# -----------------------------
# Normalization helpers
# -----------------------------

def normalize_schema_uri(u: str) -> str:
    # Kill schema1 by forcing a single canonical namespace
    return u.replace("http://schema.org/", "https://schema.org/")


def parse_curie(curie: str) -> URIRef | None:
    """
    Resolve CURIE like 'hrao:servedUnder'.
    Accepts full URIs as-is (and normalizes schema.org http->https).
    """
    curie = (curie or "").strip()
    if not curie:
        return None

    if curie.startswith(("http://", "https://")):
        curie = normalize_schema_uri(curie)
        return URIRef(curie)

    if ":" not in curie:
        return None

    prefix, local = curie.split(":", 1)
    prefix = prefix.strip()
    local = local.strip()

    if not prefix or not local:
        return None
    if prefix not in PREFIX_MAP:
        return None

    return URIRef(PREFIX_MAP[prefix] + local)


def split_semicolon(v: str | None) -> list[str]:
    v = (v or "").strip()
    if not v or v.lower() == "nan":
        return []
    return [x.strip() for x in v.split(";") if x.strip()]


def parse_mentions(field: str | None) -> list[str]:
    out: list[str] = []
    for entry in split_semicolon(field):
        parts = [p.strip() for p in entry.split("|")]
        if len(parts) >= 2 and parts[1].startswith(("http://", "https://")):
            out.append(parts[1].strip())
    return out


def add_date(graph: Graph, subj: URIRef, date_str: str | None) -> None:
    date_str = (date_str or "").strip()
    if not date_str:
        return

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_str):
        graph.add((subj, DCTERMS.date, Literal(date_str, datatype=XSD.date)))
    elif re.fullmatch(r"\d{4}-\d{2}", date_str):
        graph.add((subj, DCTERMS.date, Literal(date_str, datatype=XSD.gYearMonth)))
    elif re.fullmatch(r"\d{4}", date_str):
        graph.add((subj, DCTERMS.date, Literal(date_str, datatype=XSD.gYear)))
    else:
        graph.add((subj, DCTERMS.date, Literal(date_str)))


def resolve_entity_uri(
    entity_id: str,
    person_ids: set[str],
    org_ids: set[str],
    place_ids: set[str],
    event_ids: set[str],
) -> URIRef | None:
    entity_id = (entity_id or "").strip()
    if not entity_id:
        return None

    if re.fullmatch(r"CV-\d+[A-Za-z]?", entity_id):
        return letter_uri(entity_id)

    if entity_id in person_ids:
        return person_uri(entity_id)
    if entity_id in org_ids:
        return org_uri(entity_id)
    if entity_id in place_ids:
        return place_uri(entity_id)
    if entity_id in event_ids:
        return event_uri(entity_id)

    print(f"[WARN] Unknown entity id '{entity_id}' (not in persons/orgs/places/events). Ignoring.")
    return None


def canonicalize_uri_strict(raw: str, exactmatch_index: dict[str, URIRef]) -> URIRef | None:
    """
    Strict:
    - normalize schema.org http->https
    - if raw is in exactmatch_index -> internal URI
    - if raw already starts with BASE_URI -> keep
    - else -> ignore
    """
    raw = (raw or "").strip()
    if not raw:
        return None

    raw = normalize_schema_uri(raw)

    if raw in exactmatch_index:
        return exactmatch_index[raw]

    if raw.startswith(BASE_URI):
        return URIRef(raw)

    return None


# -----------------------------
# Loaders
# -----------------------------

def load_persons(graph: Graph) -> tuple[set[str], dict[str, URIRef]]:
    xml = safe_parse(STANDOFF_PERSONS)
    person_ids: set[str] = set()
    exact: dict[str, URIRef] = {}

    for p in xml.findall(".//tei:listPerson/tei:person", TEI_NS):
        pid = p.get(XML_ID)
        if not pid:
            continue

        person_ids.add(pid)
        u = person_uri(pid)

        graph.add((u, RDF.type, FOAF.Person))

        name_el = p.find("./tei:persName", TEI_NS)
        if name_el is not None and (name_el.text or "").strip():
            graph.add((u, RDFS.label, Literal(name_el.text.strip(), lang="pt")))

        for idno in p.findall("./tei:idno", TEI_NS):
            val = (idno.text or "").strip()
            if val.startswith(("http://", "https://")):
                val = normalize_schema_uri(val)
                graph.add((u, SKOS.exactMatch, URIRef(val)))
                exact[val] = u

    return person_ids, exact


def load_orgs(graph: Graph) -> tuple[set[str], dict[str, URIRef]]:
    xml = safe_parse(STANDOFF_ORGS)
    org_ids: set[str] = set()
    exact: dict[str, URIRef] = {}

    for o in xml.findall(".//tei:listOrg/tei:org", TEI_NS):
        oid = o.get(XML_ID)
        if not oid:
            continue

        org_ids.add(oid)
        u = org_uri(oid)

        graph.add((u, RDF.type, FOAF.Organization))

        name_el = o.find("./tei:orgName", TEI_NS)
        if name_el is not None and (name_el.text or "").strip():
            graph.add((u, RDFS.label, Literal(name_el.text.strip(), lang="pt")))

        for idno in o.findall("./tei:idno", TEI_NS):
            val = (idno.text or "").strip()
            if val.startswith(("http://", "https://")):
                val = normalize_schema_uri(val)
                graph.add((u, SKOS.exactMatch, URIRef(val)))
                exact[val] = u

    return org_ids, exact


def load_places(graph: Graph) -> tuple[set[str], dict[str, URIRef]]:
    xml = safe_parse(STANDOFF_PLACES)
    place_ids: set[str] = set()
    exact: dict[str, URIRef] = {}

    for pl in xml.findall(".//tei:listPlace/tei:place", TEI_NS):
        pid = pl.get(XML_ID)
        if not pid:
            continue

        place_ids.add(pid)
        u = place_uri(pid)

        # Minimal typing (change later if your model has a specific class)
        graph.add((u, RDF.type, RICO.Place))

        name_el = pl.find("./tei:placeName", TEI_NS)
        if name_el is not None and (name_el.text or "").strip():
            graph.add((u, RDFS.label, Literal(name_el.text.strip(), lang="pt")))

        for idno in pl.findall("./tei:idno", TEI_NS):
            val = (idno.text or "").strip()
            if val.startswith(("http://", "https://")):
                val = normalize_schema_uri(val)
                graph.add((u, SKOS.exactMatch, URIRef(val)))
                exact[val] = u

    return place_ids, exact


def load_events(graph: Graph) -> tuple[set[str], dict[str, URIRef]]:
    xml = safe_parse(STANDOFF_EVENTS)
    event_ids: set[str] = set()
    exact: dict[str, URIRef] = {}

    for ev in xml.findall(".//tei:listEvent/tei:event", TEI_NS):
        eid = ev.get(XML_ID)
        if not eid:
            continue

        event_ids.add(eid)
        u = event_uri(eid)

        graph.add((u, RDF.type, RICO.Event))

        label_el = ev.find("./tei:label", TEI_NS)
        if label_el is None:
            label_el = ev.find("./tei:head", TEI_NS)
        if label_el is not None and (label_el.text or "").strip():
            graph.add((u, RDFS.label, Literal(label_el.text.strip(), lang="pt")))

        for idno in ev.findall("./tei:idno", TEI_NS):
            val = (idno.text or "").strip()
            if val.startswith(("http://", "https://")):
                val = normalize_schema_uri(val)
                graph.add((u, SKOS.exactMatch, URIRef(val)))
                exact[val] = u

    return event_ids, exact


def load_relations(
    graph: Graph,
    person_ids: set[str],
    org_ids: set[str],
    place_ids: set[str],
    event_ids: set[str],
) -> None:
    xml = safe_parse(STANDOFF_RELATIONS)

    for r in xml.findall(".//tei:relation", TEI_NS):
        name = (r.get("name") or "").strip()
        if not name:
            continue

        pred = parse_curie(name)
        if pred is None:
            print(f"[WARN] Skipping relation with invalid/unknown predicate @name='{name}'")
            continue

        active = (r.get("active") or "").strip().lstrip("#")
        passive = (r.get("passive") or "").strip().lstrip("#")
        if not active or not passive:
            continue

        subj = resolve_entity_uri(active, person_ids, org_ids, place_ids, event_ids)
        obj = resolve_entity_uri(passive, person_ids, org_ids, place_ids, event_ids)
        if subj is None or obj is None:
            continue

        graph.add((subj, pred, obj))


def add_dataset_provenance(graph: Graph) -> None:
    graph.add((DATASET_URI, RDF.type, PROV.Entity))
    graph.add((DATASET_URI, RDF.type, SCHEMA.Dataset))
    graph.add((DATASET_URI, DCTERMS.title, Literal("Varela Digital — Knowledge Base (RDF dataset)", lang="en")))
    graph.add((DATASET_URI, DCTERMS.source, URIRef("https://github.com/CarlaMenegat/VarelaDigital")))

    graph.add((AGENT_URI, RDF.type, FOAF.Person))
    graph.add((AGENT_URI, FOAF.name, Literal("Carla Menegat")))

    for src in (
        SOURCE_PERSONS_URI,
        SOURCE_ORGS_URI,
        SOURCE_PLACES_URI,
        SOURCE_EVENTS_URI,
        SOURCE_RELATIONS_URI,
        SOURCE_METADATA_URI,
    ):
        graph.add((src, RDF.type, PROV.Entity))

    graph.add((PROCESS_URI, RDF.type, PROV.Activity))
    graph.add((PROCESS_URI, PROV.used, SOURCE_PERSONS_URI))
    graph.add((PROCESS_URI, PROV.used, SOURCE_ORGS_URI))
    graph.add((PROCESS_URI, PROV.used, SOURCE_PLACES_URI))
    graph.add((PROCESS_URI, PROV.used, SOURCE_EVENTS_URI))
    graph.add((PROCESS_URI, PROV.used, SOURCE_RELATIONS_URI))
    graph.add((PROCESS_URI, PROV.used, SOURCE_METADATA_URI))
    graph.add((PROCESS_URI, PROV.wasAssociatedWith, AGENT_URI))

    graph.add((DATASET_URI, PROV.wasGeneratedBy, PROCESS_URI))
    graph.add((DATASET_URI, DCTERMS.created, Literal(date.today().isoformat(), datatype=XSD.date)))


# -----------------------------
# Main
# -----------------------------

def build_graph() -> None:
    require_file(CSV_METADATA)
    require_file(STANDOFF_PERSONS)
    require_file(STANDOFF_ORGS)
    require_file(STANDOFF_PLACES)
    require_file(STANDOFF_EVENTS)
    require_file(STANDOFF_RELATIONS)

    g = Graph()

    # Bind prefixes (override to avoid schema1/ns1)
    g.bind("dcterms", DCTERMS, override=True)
    g.bind("foaf", FOAF, override=True)
    g.bind("pro", PRO, override=True)
    g.bind("schema", SCHEMA, override=True)
    g.bind("prov", PROV, override=True)
    g.bind("rel", REL, override=True)
    g.bind("rico", RICO, override=True)
    g.bind("skos", SKOS, override=True)
    g.bind("hrao", HRAO, override=True)
    g.bind("fabio", FABIO, override=True)
    g.bind("frbr", FRBR, override=True)
    g.bind("san", SAN, override=True)

    person_ids, person_exact = load_persons(g)
    org_ids, org_exact = load_orgs(g)
    place_ids, place_exact = load_places(g)
    event_ids, event_exact = load_events(g)

    exactmatch_index = {**person_exact, **org_exact, **place_exact, **event_exact}

    load_relations(g, person_ids, org_ids, place_ids, event_ids)

    with CSV_METADATA.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cv_id = (row.get("cv_id") or "").strip()
            if not cv_id:
                continue

            letter = letter_uri(cv_id)

            # Your model choice for letters
            g.add((letter, RDF.type, FABIO.Letter))
            g.add((letter, RDF.type, FRBR.Work))

            author_raw = (row.get("author_uri") or "").strip()
            if author_raw:
                a = canonicalize_uri_strict(author_raw, exactmatch_index)
                if a is not None:
                    g.add((letter, DCTERMS.creator, a))

            recipient_raw = (row.get("recipient_uri") or "").strip()
            if recipient_raw:
                rcp = canonicalize_uri_strict(recipient_raw, exactmatch_index)
                if rcp is not None:
                    g.add((letter, PRO.addressee, rcp))

            add_date(g, letter, row.get("date"))

            place_raw = (row.get("place_uri") or "").strip()
            if place_raw:
                pl = canonicalize_uri_strict(place_raw, exactmatch_index)
                if pl is not None:
                    g.add((letter, DCTERMS.spatial, pl))

            # Mentions -> SAN refersTo
            for field in ("mentioned_people", "mentioned_orgs", "mentioned_places", "mentioned_events"):
                for u in parse_mentions(row.get(field)):
                    m = canonicalize_uri_strict(u, exactmatch_index)
                    if m is not None:
                        g.add((letter, SAN.refersTo, m))

    add_dataset_provenance(g)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    g.serialize(str(OUT_TTL), format="turtle")
    g.serialize(str(OUT_JSONLD), format="json-ld", indent=2)

    print("✔ RDF generated:")
    print("  ", OUT_TTL)
    print("  ", OUT_JSONLD)


if __name__ == "__main__":
    build_graph()