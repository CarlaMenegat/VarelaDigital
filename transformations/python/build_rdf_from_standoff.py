#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Varela Digital — Standoff + CSV -> RDF -> JSON-LD

Inputs (fixed paths):
- data/metadata/metadata_all.csv
- data/standoff/standoff_persons.xml
- data/standoff/standoff_orgs.xml
- data/standoff/standoff_relations.xml

Outputs:
- data/rdf/graph.ttl
- data/rdf/graph.jsonld
"""

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

CSV_METADATA = BASE_DIR / "data/metadata/metadata_all.csv"
STANDOFF_PERSONS = BASE_DIR / "data/standoff/standoff_persons.xml"
STANDOFF_ORGS = BASE_DIR / "data/standoff/standoff_orgs.xml"
STANDOFF_RELATIONS = BASE_DIR / "data/standoff/standoff_relations.xml"

OUT_DIR = BASE_DIR / "data/rdf"
OUT_TTL = OUT_DIR / "graph.ttl"
OUT_JSONLD = OUT_DIR / "graph.jsonld"


# -----------------------------
# Namespaces
# -----------------------------

BASE_URI = "https://carlamenegat.github.io/VarelaDigital/"
PERSON_BASE = BASE_URI + "person/"
ORG_BASE = BASE_URI + "org/"
LETTER_BASE = BASE_URI + "letter/"

# lightweight provenance resources (Option B)
DATASET_URI = URIRef(BASE_URI + "dataset/kbvareladigital")
PROCESS_URI = URIRef(BASE_URI + "process/rdf-generation")
AGENT_URI = URIRef(BASE_URI + "agent/carla-menegat")

SOURCE_PERSONS_URI = URIRef(BASE_URI + "source/standoff_persons_xml")
SOURCE_ORGS_URI = URIRef(BASE_URI + "source/standoff_orgs_xml")
SOURCE_RELATIONS_URI = URIRef(BASE_URI + "source/standoff_relations_xml")
SOURCE_METADATA_URI = URIRef(BASE_URI + "source/metadata_all_csv")

TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"

DCTERMS = Namespace("http://purl.org/dc/terms/")
FOAF = Namespace("http://xmlns.com/foaf/0.1/")
PRO = Namespace("http://purl.org/spar/pro/")
SCHEMA = Namespace("http://schema.org/")
PROV = Namespace("http://www.w3.org/ns/prov#")
REL = Namespace("http://purl.org/vocab/relationship/")
RICO = Namespace("https://www.ica.org/standards/RiC/ontology#")

# IMPORTANT: for RDF predicates, HRAO must be the namespace ending with '#'
HRAO = Namespace(BASE_URI + "hrao#")

PREFIX_MAP = {
    "dcterms": str(DCTERMS),
    "foaf": str(FOAF),
    "pro": str(PRO),
    "schema": str(SCHEMA),
    "prov": str(PROV),
    "rel": str(REL),
    "rico": str(RICO),
    "hrao": str(HRAO),
}


# -----------------------------
# Helpers
# -----------------------------

def person_uri(pid: str) -> URIRef:
    return URIRef(PERSON_BASE + pid)


def org_uri(oid: str) -> URIRef:
    return URIRef(ORG_BASE + oid)


def letter_uri(cv_id: str) -> URIRef:
    return URIRef(LETTER_BASE + cv_id)


def parse_curie(curie: str) -> URIRef:
    """
    Resolve a CURIE like 'hrao:servedUnder' using PREFIX_MAP.
    Accepts full URIs as-is.
    """
    if curie.startswith(("http://", "https://")):
        return URIRef(curie)
    prefix, local = curie.split(":", 1)
    if prefix not in PREFIX_MAP:
        raise KeyError(f"Unknown prefix '{prefix}' in predicate '{curie}'")
    return URIRef(PREFIX_MAP[prefix] + local)


def split_semicolon(v: str | None) -> list[str]:
    v = (v or "").strip()
    if not v or v.lower() == "nan":
        return []
    return [x.strip() for x in v.split(";") if x.strip()]


def parse_mentions(field: str | None) -> list[str]:
    """
    CSV format assumed: label|URI ; label|URI ; ...
    Returns only the URI part.
    """
    out: list[str] = []
    for entry in split_semicolon(field):
        parts = [p.strip() for p in entry.split("|")]
        if len(parts) >= 2 and parts[1].startswith(("http://", "https://")):
            out.append(parts[1])
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


def resolve_entity_uri(entity_id: str, person_ids: set[str], org_ids: set[str]) -> URIRef:
    """
    entity_id is expected to be an xml:id (from standoff), without '#'.
    """
    if entity_id in person_ids:
        return person_uri(entity_id)
    if entity_id in org_ids:
        return org_uri(entity_id)
    return URIRef(BASE_URI + entity_id)


def canonicalize_uri(raw: str, sameas_index: dict[str, URIRef]) -> URIRef:
    """
    If raw is an external URI present in standoff as skos:exactMatch,
    replace it with the internal project URI. Otherwise keep raw.
    """
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("canonicalize_uri called with empty string")
    if raw in sameas_index:
        return sameas_index[raw]
    return URIRef(raw)


# -----------------------------
# Loaders
# -----------------------------

def load_persons(graph: Graph) -> tuple[set[str], dict[str, URIRef]]:
    xml = ET.parse(str(STANDOFF_PERSONS))
    person_ids: set[str] = set()
    sameas_index: dict[str, URIRef] = {}

    for p in xml.findall(".//tei:listPerson/tei:person", TEI_NS):
        pid = p.get(XML_ID)
        if not pid:
            continue

        person_ids.add(pid)
        u = person_uri(pid)

        graph.add((u, RDF.type, FOAF.Person))

        # First persName as label (keeps current behavior)
        name_el = p.find("./tei:persName", TEI_NS)
        if name_el is not None and (name_el.text or "").strip():
            graph.add((u, RDFS.label, Literal(name_el.text.strip(), lang="pt")))

        # Reconciliation links (project URI is subject; external URIs are exactMatch)
        for idno in p.findall("./tei:idno", TEI_NS):
            val = (idno.text or "").strip()
            if val.startswith(("http://", "https://")):
                graph.add((u, SKOS.exactMatch, URIRef(val)))
                sameas_index[val] = u

    return person_ids, sameas_index


def load_orgs(graph: Graph) -> tuple[set[str], dict[str, URIRef]]:
    xml = ET.parse(str(STANDOFF_ORGS))
    org_ids: set[str] = set()
    sameas_index: dict[str, URIRef] = {}

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
                graph.add((u, SKOS.exactMatch, URIRef(val)))
                sameas_index[val] = u

    return org_ids, sameas_index


def load_relations(graph: Graph, person_ids: set[str], org_ids: set[str]) -> None:
    xml = ET.parse(str(STANDOFF_RELATIONS))

    for r in xml.findall(".//tei:relation", TEI_NS):
        name = (r.get("name") or "").strip()
        if not name:
            continue

        pred = parse_curie(name)

        active = (r.get("active") or "").strip().lstrip("#")
        passive = (r.get("passive") or "").strip().lstrip("#")
        if not active or not passive:
            continue

        subj = resolve_entity_uri(active, person_ids, org_ids)
        obj = resolve_entity_uri(passive, person_ids, org_ids)

        graph.add((subj, pred, obj))


def add_dataset_provenance(graph: Graph) -> None:
    """
    Option B provenance: dataset/process/source-level provenance, not per statement.
    """
    # Dataset node
    graph.add((DATASET_URI, RDF.type, PROV.Entity))
    graph.add((DATASET_URI, RDF.type, SCHEMA.Dataset))
    graph.add((DATASET_URI, DCTERMS.title, Literal("Varela Digital — Knowledge Base (RDF dataset)", lang="en")))
    graph.add((DATASET_URI, DCTERMS.source, URIRef("https://github.com/CarlaMenegat/VarelaDigital")))

    # Agent
    graph.add((AGENT_URI, RDF.type, FOAF.Person))
    graph.add((AGENT_URI, FOAF.name, Literal("Carla Menegat")))

    # Sources
    for src in (SOURCE_PERSONS_URI, SOURCE_ORGS_URI, SOURCE_RELATIONS_URI, SOURCE_METADATA_URI):
        graph.add((src, RDF.type, PROV.Entity))

    # Process
    graph.add((PROCESS_URI, RDF.type, PROV.Activity))
    graph.add((PROCESS_URI, PROV.used, SOURCE_PERSONS_URI))
    graph.add((PROCESS_URI, PROV.used, SOURCE_ORGS_URI))
    graph.add((PROCESS_URI, PROV.used, SOURCE_RELATIONS_URI))
    graph.add((PROCESS_URI, PROV.used, SOURCE_METADATA_URI))
    graph.add((PROCESS_URI, PROV.wasAssociatedWith, AGENT_URI))

    # Link dataset to process
    graph.add((DATASET_URI, PROV.wasGeneratedBy, PROCESS_URI))
    graph.add((DATASET_URI, DCTERMS.created, Literal(date.today().isoformat(), datatype=XSD.date)))


# -----------------------------
# Main
# -----------------------------

def build_graph() -> None:
    g = Graph()

    # Bind prefixes to avoid ns1/ns2 surprises
    g.bind("dcterms", DCTERMS)
    g.bind("foaf", FOAF)
    g.bind("pro", PRO)
    g.bind("schema", SCHEMA)
    g.bind("prov", PROV)
    g.bind("rel", REL)
    g.bind("rico", RICO)
    g.bind("skos", SKOS)
    g.bind("hrao", HRAO)

    person_ids, person_sameas = load_persons(g)
    org_ids, org_sameas = load_orgs(g)
    sameas_index = {**person_sameas, **org_sameas}

    load_relations(g, person_ids, org_ids)

    with CSV_METADATA.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cv_id = (row.get("cv_id") or "").strip()
            if not cv_id:
                continue

            letter = letter_uri(cv_id)
            g.add((letter, RDF.type, SCHEMA.CreativeWork))

            author_raw = (row.get("author_uri") or "").strip()
            if author_raw:
                g.add((letter, DCTERMS.creator, canonicalize_uri(author_raw, sameas_index)))

            recipient_raw = (row.get("recipient_uri") or "").strip()
            if recipient_raw:
                g.add((letter, PRO.addressee, canonicalize_uri(recipient_raw, sameas_index)))

            add_date(g, letter, row.get("date"))

            place_uri = (row.get("place_uri") or "").strip()
            if place_uri:
                g.add((letter, DCTERMS.spatial, URIRef(place_uri)))

            # Canonicalize mentions when possible
            for u in parse_mentions(row.get("mentioned_people")):
                g.add((letter, SCHEMA.mentions, canonicalize_uri(u, sameas_index)))

            for u in parse_mentions(row.get("mentioned_orgs")):
                g.add((letter, SCHEMA.mentions, canonicalize_uri(u, sameas_index)))

            for u in parse_mentions(row.get("mentioned_places")):
                g.add((letter, SCHEMA.mentions, canonicalize_uri(u, sameas_index)))

            for u in parse_mentions(row.get("mentioned_events")):
                g.add((letter, SCHEMA.mentions, canonicalize_uri(u, sameas_index)))

    # Add dataset-level provenance (Option B)
    add_dataset_provenance(g)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    g.serialize(str(OUT_TTL), format="turtle")
    g.serialize(str(OUT_JSONLD), format="json-ld", indent=2)

    print("✔ RDF generated:")
    print("  ", OUT_TTL)
    print("  ", OUT_JSONLD)


if __name__ == "__main__":
    build_graph()