#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Varela Digital — TEI metadata extractor
---------------------------------------
Generates a CSV with core header metadata + entity mentions (persons/orgs/places/events) from TEI P5 files.

Output columns:
cv_id,subject,author_name,author_uri,recipient_name,recipient_uri,date,place_label,place_uri,lat,long,
mentioned_people,mentioned_orgs,mentioned_places,mentioned_events,mentioned_dates,text_file

Rules / assumptions:
- TEI namespace: http://www.tei-c.org/ns/1.0
- People/org URIs:
  * Prefer idno[@type='wikidata' or 'viaf'] in the corresponding standoff entry.
  * If the entity standoff entry has <idno type="project"/> (placeholder) OR has no wikidata/viaf,
    build a project URI:
        https://carlamenegat.github.io/VarelaDigital/person/{xml:id}
        https://carlamenegat.github.io/VarelaDigital/org/{xml:id}
- Places: prefer GeoNames from standoff places (<idno type="geonames">...).
- Main date logic:
  * If there is a correspDesc sent date, use ONLY that (no fallback).
  * Otherwise (non-letter / no sent), fallback to first dateline date in the text.
- Mentioned dates:
  * Collect all //date[@when] (header + text), deduplicate, sorted, joined by ';'
- Non-letter docs can have missing sent/received; keep blank if absent.
- Version/copy docs (dcterms:isVersionOf) are allowed; just extract what exists.

Paths (edit if needed):
- TEI documents folder (XML):   .../data/documents_XML
- Standoff files:              .../data/standoff/standoff-persons.xml
                               .../data/standoff/standoff-orgs.xml
                               .../data/standoff/standoff-places.xml
                               .../data/standoff/standoff-events.xml
- Output CSV folder:           .../data/metadata

Usage:
    python scripts/extract_metadata_csv.py

You can also override base paths by editing the constants below.
"""

from __future__ import annotations

import csv
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple
import xml.etree.ElementTree as ET


# =========================
# CONFIG — EDIT IF NEEDED
# =========================

PROJECT_BASE = "https://carlamenegat.github.io/VarelaDigital"
PROJECT_PERSON_BASE = f"{PROJECT_BASE}/person/"
PROJECT_ORG_BASE = f"{PROJECT_BASE}/org/"

# Your local GitHub Desktop repo root (adjust if you renamed/relocated)
REPO_ROOT = Path("/Users/carlamenegat/Documents/GitHub/Untitled/VarelaDigital")

TEI_DOCS_DIR = REPO_ROOT / "data" / "documents_XML"
STANDOFF_DIR = REPO_ROOT / "data" / "standoff"
OUTPUT_DIR = REPO_ROOT / "data" / "metadata"
OUTPUT_CSV = OUTPUT_DIR / "metadata_all.csv"

STANDOFF_PERSONS = STANDOFF_DIR / "standoff-persons.xml"
STANDOFF_ORGS = STANDOFF_DIR / "standoff-orgs.xml"
STANDOFF_PLACES = STANDOFF_DIR / "standoff-places.xml"
STANDOFF_EVENTS = STANDOFF_DIR / "standoff-events.xml"


TEI_NS = {
    "tei": "http://www.tei-c.org/ns/1.0",
    "xml": "http://www.w3.org/XML/1998/namespace",
}


# =========================
# UTILITIES
# =========================

def strip_text(s: Optional[str]) -> str:
    return (s or "").strip()


def find_first(root: ET.Element, xpath: str) -> Optional[ET.Element]:
    return root.find(xpath, TEI_NS)


def find_all(root: ET.Element, xpath: str) -> List[ET.Element]:
    return root.findall(xpath, TEI_NS)


def local_name(tag: str) -> str:
    """Return local name of tag: '{ns}tag' -> 'tag'."""
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def normalize_ref(ref: str) -> str:
    """Normalize a TEI @ref value to an xml:id-like token (no '#')."""
    ref = (ref or "").strip()
    if ref.startswith("#"):
        return ref[1:]
    return ref


def safe_join(values: Iterable[str], sep: str = ";") -> str:
    cleaned = [v.strip() for v in values if v and v.strip()]
    return sep.join(cleaned)


# =========================
# STANDOFF INDEXES
# =========================

@dataclass
class EntityRecord:
    xml_id: str
    label: str
    uri: str
    lat: str = ""
    lon: str = ""


def parse_standoff_persons(path: Path) -> Dict[str, EntityRecord]:
    """
    Index people by @xml:id -> EntityRecord(label, uri).
    URI preference: wikidata > viaf > project URI.
    If <idno type="project"/> exists, still build project URI (explicit placeholder).
    """
    idx: Dict[str, EntityRecord] = {}
    if not path.exists():
        return idx

    root = ET.parse(path).getroot()

    for p in root.findall(".//tei:person", TEI_NS):
        xml_id = p.get("{http://www.w3.org/XML/1998/namespace}id")
        if not xml_id:
            continue

        # label: first persName (any)
        pers_name = p.find("tei:persName", TEI_NS)
        label = strip_text(pers_name.text if pers_name is not None else xml_id)

        # detect idnos
        idno_wd = p.find("tei:idno[@type='wikidata']", TEI_NS)
        idno_viaf = p.find("tei:idno[@type='viaf']", TEI_NS)
        idno_project = p.find("tei:idno[@type='project']", TEI_NS)

        if idno_wd is not None and strip_text(idno_wd.text):
            uri = strip_text(idno_wd.text)
        elif idno_viaf is not None and strip_text(idno_viaf.text):
            uri = strip_text(idno_viaf.text)
        else:
            # If project placeholder exists or no external IDs at all:
            uri = f"{PROJECT_PERSON_BASE}{xml_id}"

        idx[xml_id] = EntityRecord(xml_id=xml_id, label=label, uri=uri)

    return idx


def parse_standoff_orgs(path: Path) -> Dict[str, EntityRecord]:
    """
    Index orgs by @xml:id -> EntityRecord(label, uri).
    URI preference: wikidata > viaf > project URI.
    """
    idx: Dict[str, EntityRecord] = {}
    if not path.exists():
        return idx

    root = ET.parse(path).getroot()

    for o in root.findall(".//tei:org", TEI_NS):
        xml_id = o.get("{http://www.w3.org/XML/1998/namespace}id")
        if not xml_id:
            continue

        org_name = o.find("tei:orgName", TEI_NS)
        label = strip_text(org_name.text if org_name is not None else xml_id)

        idno_wd = o.find("tei:idno[@type='wikidata']", TEI_NS)
        idno_viaf = o.find("tei:idno[@type='viaf']", TEI_NS)
        idno_project = o.find("tei:idno[@type='project']", TEI_NS)

        if idno_wd is not None and strip_text(idno_wd.text):
            uri = strip_text(idno_wd.text)
        elif idno_viaf is not None and strip_text(idno_viaf.text):
            uri = strip_text(idno_viaf.text)
        else:
            uri = f"{PROJECT_ORG_BASE}{xml_id}"

        idx[xml_id] = EntityRecord(xml_id=xml_id, label=label, uri=uri)

    return idx


def parse_standoff_places(path: Path) -> Dict[str, EntityRecord]:
    """
    Index places by @xml:id -> EntityRecord(label, geonames uri, lat, lon).
    Place label: first placeName.
    geonames: <idno type="geonames">...</idno>
    geo: <geo>lat lon</geo> or "lat,lon" (we attempt both).
    """
    idx: Dict[str, EntityRecord] = {}
    if not path.exists():
        return idx

    root = ET.parse(path).getroot()

    for pl in root.findall(".//tei:place", TEI_NS):
        xml_id = pl.get("{http://www.w3.org/XML/1998/namespace}id")
        if not xml_id:
            continue

        place_name = pl.find("tei:placeName", TEI_NS)
        label = strip_text(place_name.text if place_name is not None else xml_id)

        idno_geo = pl.find("tei:idno[@type='geonames']", TEI_NS)
        uri = strip_text(idno_geo.text) if idno_geo is not None else ""

        lat = ""
        lon = ""
        geo_el = pl.find("tei:geo", TEI_NS)
        if geo_el is not None and strip_text(geo_el.text):
            raw = strip_text(geo_el.text).replace(",", " ")
            parts = [p for p in raw.split() if p]
            if len(parts) >= 2:
                lat, lon = parts[0], parts[1]

        idx[xml_id] = EntityRecord(xml_id=xml_id, label=label, uri=uri, lat=lat, lon=lon)

    return idx


def parse_standoff_events(path: Path) -> Dict[str, EntityRecord]:
    """
    Index events by @xml:id -> EntityRecord(label, uri).
    Events usually won't have external URIs; we use project URI as default.
    Label: <desc> if present.
    """
    idx: Dict[str, EntityRecord] = {}
    if not path.exists():
        return idx

    root = ET.parse(path).getroot()

    for ev in root.findall(".//tei:event", TEI_NS):
        xml_id = ev.get("{http://www.w3.org/XML/1998/namespace}id")
        if not xml_id:
            continue

        desc = ev.find("tei:desc", TEI_NS)
        label = strip_text(desc.text if desc is not None else xml_id)

        # If you later add idno for events, you can extend this.
        uri = f"{PROJECT_BASE}/event/{xml_id}"

        idx[xml_id] = EntityRecord(xml_id=xml_id, label=label, uri=uri)

    return idx


# =========================
# EXTRACTION FROM DOCS
# =========================

XML_ID = "{http://www.w3.org/XML/1998/namespace}id"

def extract_cv_id(root: ET.Element, fallback_filename: str) -> str:
    """
    Prefer:
    - //text//div[@xml:id][1]/@xml:id
    Else:
    - Use filename stem
    """
    div = find_first(root, ".//tei:text//tei:div")
    if div is not None:
        xml_id = div.get(XML_ID)
        if xml_id:
            return xml_id.strip()
    return Path(fallback_filename).stem


def extract_subject(root: ET.Element) -> str:
    """
    Use titleStmt/title text as 'subject' (your requested field).
    """
    t = find_first(root, ".//tei:teiHeader/tei:fileDesc/tei:titleStmt/tei:title")
    return strip_text(t.text if t is not None else "")


def extract_author_from_header(root: ET.Element) -> Tuple[str, str]:
    """
    author_name, author_uri (person or org).
    Tries:
    1) titleStmt/author//persName[@ref]
    2) titleStmt/author//orgName[@ref]
    3) titleStmt/author text
    """
    # 1) persName with ref
    pn = find_first(root, ".//tei:teiHeader/tei:fileDesc/tei:titleStmt/tei:author//tei:persName[@ref]")
    if pn is not None:
        name = strip_text("".join(pn.itertext()))
        return name, normalize_ref(pn.get("ref", ""))

    # 2) orgName with ref
    on = find_first(root, ".//tei:teiHeader/tei:fileDesc/tei:titleStmt/tei:author//tei:orgName[@ref]")
    if on is not None:
        name = strip_text("".join(on.itertext()))
        return name, normalize_ref(on.get("ref", ""))

    # 3) plain author text
    author = find_first(root, ".//tei:teiHeader/tei:fileDesc/tei:titleStmt/tei:author")
    if author is not None:
        name = strip_text("".join(author.itertext()))
        return name, ""

    return "", ""


def extract_corresp_sent_received(root: ET.Element) -> Tuple[str, str, str, str, str]:
    """
    Returns:
    author_name (from sent), author_ref (xmlid), recipient_name, recipient_ref, sent_date_when
    Only from correspDesc.
    """
    sent_p = find_first(root, ".//tei:teiHeader/tei:profileDesc/tei:correspDesc/tei:correspAction[@type='sent']/tei:persName[@ref]")
    recv_p = find_first(root, ".//tei:teiHeader/tei:profileDesc/tei:correspDesc/tei:correspAction[@type='received']/tei:persName[@ref]")
    sent_date = find_first(root, ".//tei:teiHeader/tei:profileDesc/tei:correspDesc/tei:correspAction[@type='sent']/tei:date[@when]")

    author_name = strip_text("".join(sent_p.itertext())) if sent_p is not None else ""
    author_ref = normalize_ref(sent_p.get("ref", "")) if sent_p is not None else ""

    recipient_name = strip_text("".join(recv_p.itertext())) if recv_p is not None else ""
    recipient_ref = normalize_ref(recv_p.get("ref", "")) if recv_p is not None else ""

    sent_when = strip_text(sent_date.get("when")) if sent_date is not None else ""

    return author_name, author_ref, recipient_name, recipient_ref, sent_when


def extract_main_date_norm(root: ET.Element) -> str:
    """
    Main date logic:
    - If the document has a correspDesc with a sent date, use ONLY that (no fallback).
    - Otherwise (non-letter / no sent), fallback to the first dateline date in the text.
    """
    sent_date = find_first(
        root,
        ".//tei:teiHeader/tei:profileDesc/tei:correspDesc/tei:correspAction[@type='sent']/tei:date[@when]"
    )
    if sent_date is not None:
        return strip_text(sent_date.get("when"))

    dl_date = find_first(root, ".//tei:text//tei:dateline//tei:date[@when]")
    if dl_date is not None and strip_text(dl_date.get("when")):
        return strip_text(dl_date.get("when"))

    return ""


def extract_main_place_from_corresp(root: ET.Element) -> Tuple[str, str, str, str]:
    """
    place_label, place_ref, lat, lon

    Primary rule: if there is correspAction[@type='sent']/placeName[@ref], use that.
    Otherwise: try first dateline placeName in the text.
    """
    p = find_first(root, ".//tei:teiHeader/tei:profileDesc/tei:correspDesc/tei:correspAction[@type='sent']/tei:placeName[@ref]")
    if p is not None:
        label = strip_text("".join(p.itertext()))
        return label, normalize_ref(p.get("ref", "")), "", ""

    # fallback
    dp = find_first(root, ".//tei:text//tei:dateline//tei:placeName[@ref]")
    if dp is not None:
        label = strip_text("".join(dp.itertext()))
        return label, normalize_ref(dp.get("ref", "")), "", ""

    return "", "", "", ""


def collect_mentions(root: ET.Element) -> Tuple[Set[str], Set[str], Set[str], Set[str]]:
    """
    Collect xml:id refs mentioned in the text body:
    - persons: //text//persName[@ref]
    - orgs:    //text//orgName[@ref]
    - places:  //text//placeName[@ref]
    - events:  //text//rs[@type='event'][@ref] or //text//name[@type='event'][@ref] (best-effort)
      (If you use <eventName>, add it too.)
    """
    persons: Set[str] = set()
    orgs: Set[str] = set()
    places: Set[str] = set()
    events: Set[str] = set()

    for pn in find_all(root, ".//tei:text//tei:persName[@ref]"):
        rid = normalize_ref(pn.get("ref", ""))
        if rid:
            persons.add(rid)

    for on in find_all(root, ".//tei:text//tei:orgName[@ref]"):
        rid = normalize_ref(on.get("ref", ""))
        if rid:
            orgs.add(rid)

    for pl in find_all(root, ".//tei:text//tei:placeName[@ref]"):
        rid = normalize_ref(pl.get("ref", ""))
        if rid:
            places.add(rid)

    # best-effort events (adapt if you have a consistent element for events)
    for ev in find_all(root, ".//tei:text//tei:eventName[@ref]"):
        rid = normalize_ref(ev.get("ref", ""))
        if rid:
            events.add(rid)

    for ev in find_all(root, ".//tei:text//tei:rs[@type='event'][@ref]"):
        rid = normalize_ref(ev.get("ref", ""))
        if rid:
            events.add(rid)

    for ev in find_all(root, ".//tei:text//tei:name[@type='event'][@ref]"):
        rid = normalize_ref(ev.get("ref", ""))
        if rid:
            events.add(rid)

    return persons, orgs, places, events


def collect_all_when_dates(root: ET.Element) -> str:
    """
    Collect every //date[@when] across header + text and return as
    'YYYY-MM-DD;YYYY-MM-DD;...'
    """
    dates: Set[str] = set()
    for d in root.findall(".//tei:date[@when]", TEI_NS):
        when = strip_text(d.get("when"))
        if when:
            dates.add(when)
    return ";".join(sorted(dates))


# =========================
# RESOLUTION OF URIs/LABELS
# =========================

def resolve_person(xml_id: str, persons_idx: Dict[str, EntityRecord]) -> Tuple[str, str]:
    rec = persons_idx.get(xml_id)
    if rec:
        return rec.label, rec.uri
    # fallback: assume project URI
    return xml_id, f"{PROJECT_PERSON_BASE}{xml_id}"


def resolve_org(xml_id: str, orgs_idx: Dict[str, EntityRecord]) -> Tuple[str, str]:
    rec = orgs_idx.get(xml_id)
    if rec:
        return rec.label, rec.uri
    return xml_id, f"{PROJECT_ORG_BASE}{xml_id}"


def resolve_place(xml_id: str, places_idx: Dict[str, EntityRecord]) -> Tuple[str, str, str, str]:
    rec = places_idx.get(xml_id)
    if rec:
        return rec.label, rec.uri, rec.lat, rec.lon
    return xml_id, "", "", ""


def resolve_event(xml_id: str, events_idx: Dict[str, EntityRecord]) -> Tuple[str, str]:
    rec = events_idx.get(xml_id)
    if rec:
        return rec.label, rec.uri
    return xml_id, f"{PROJECT_BASE}/event/{xml_id}"


# =========================
# MAIN
# =========================

def iter_tei_files(folder: Path) -> List[Path]:
    if not folder.exists():
        return []
    return sorted([p for p in folder.rglob("*.xml") if p.is_file()])


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load standoff indexes
    persons_idx = parse_standoff_persons(STANDOFF_PERSONS)
    orgs_idx = parse_standoff_orgs(STANDOFF_ORGS)
    places_idx = parse_standoff_places(STANDOFF_PLACES)
    events_idx = parse_standoff_events(STANDOFF_EVENTS)

    tei_files = iter_tei_files(TEI_DOCS_DIR)
    if not tei_files:
        print(f"No TEI XML files found in: {TEI_DOCS_DIR}", file=sys.stderr)
        return 1

    fieldnames = [
        "cv_id",
        "subject",
        "author_name",
        "author_uri",
        "recipient_name",
        "recipient_uri",
        "date",
        "place_label",
        "place_uri",
        "lat",
        "long",
        "mentioned_people",
        "mentioned_orgs",
        "mentioned_places",
        "mentioned_events",
        "mentioned_dates",
        "text_file",
    ]

    rows: List[Dict[str, str]] = []

    for path in tei_files:
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as e:
            print(f"XML parse error in {path}: {e}", file=sys.stderr)
            continue

        cv_id = extract_cv_id(root, path.name)
        subject = extract_subject(root)

        # Prefer correspDesc author/recipient if present; else fallback to titleStmt author
        c_author_name, c_author_ref, recipient_name, recipient_ref, _sent_when = extract_corresp_sent_received(root)

        if c_author_name or c_author_ref:
            author_name = c_author_name
            author_ref = c_author_ref
        else:
            a_name, a_ref = extract_author_from_header(root)
            author_name, author_ref = a_name, a_ref

        # Resolve author uri (person or org) if we have a ref.
        author_uri = ""
        if author_ref:
            if author_ref in persons_idx:
                _, author_uri = resolve_person(author_ref, persons_idx)
            elif author_ref in orgs_idx:
                _, author_uri = resolve_org(author_ref, orgs_idx)
            else:
                # assume person as default
                author_uri = f"{PROJECT_PERSON_BASE}{author_ref}"

        recipient_uri = ""
        if recipient_ref:
            if recipient_ref in persons_idx:
                _, recipient_uri = resolve_person(recipient_ref, persons_idx)
            elif recipient_ref in orgs_idx:
                _, recipient_uri = resolve_org(recipient_ref, orgs_idx)
            else:
                recipient_uri = f"{PROJECT_PERSON_BASE}{recipient_ref}"

        date_norm = extract_main_date_norm(root)

        place_label, place_ref, _lat, _lon = extract_main_place_from_corresp(root)
        place_uri = ""
        lat = ""
        lon = ""
        if place_ref:
            pl_label2, place_uri, lat, lon = resolve_place(place_ref, places_idx)
            if not place_label:
                place_label = pl_label2

        # Mentions from text
        m_people, m_orgs, m_places, m_events = collect_mentions(root)

        # Expand mentions into "Label|URI" pairs (semicolon separated)
        mentioned_people = []
        for pid in sorted(m_people):
            label, uri = resolve_person(pid, persons_idx)
            mentioned_people.append(f"{label}|{uri}")

        mentioned_orgs = []
        for oid in sorted(m_orgs):
            label, uri = resolve_org(oid, orgs_idx)
            mentioned_orgs.append(f"{label}|{uri}")

        mentioned_places = []
        for plid in sorted(m_places):
            label, uri, plat, plon = resolve_place(plid, places_idx)
            # keep it compact; coordinates are already in main columns for main place
            mentioned_places.append(f"{label}|{uri}")

        mentioned_events = []
        for evid in sorted(m_events):
            label, uri = resolve_event(evid, events_idx)
            mentioned_events.append(f"{label}|{uri}")

        mentioned_dates = collect_all_when_dates(root)

        rows.append({
            "cv_id": cv_id,
            "subject": subject,
            "author_name": author_name,
            "author_uri": author_uri,
            "recipient_name": recipient_name,
            "recipient_uri": recipient_uri,
            "date": date_norm,
            "place_label": place_label,
            "place_uri": place_uri,
            "lat": lat,
            "long": lon,
            "mentioned_people": safe_join(mentioned_people, ";"),
            "mentioned_orgs": safe_join(mentioned_orgs, ";"),
            "mentioned_places": safe_join(mentioned_places, ";"),
            "mentioned_events": safe_join(mentioned_events, ";"),
            "mentioned_dates": mentioned_dates,
            "text_file": str(path),
        })

    # Write CSV
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    print(f"OK — wrote {len(rows)} rows to: {OUTPUT_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())