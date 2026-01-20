#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple
import xml.etree.ElementTree as ET

PROJECT_BASE = "https://carlamenegat.github.io/VarelaDigital"
PROJECT_PERSON_BASE = f"{PROJECT_BASE}/person/"
PROJECT_ORG_BASE = f"{PROJECT_BASE}/org/"
PROJECT_EVENT_BASE = f"{PROJECT_BASE}/event/"

REPO_ROOT = Path("/Users/carlamenegat/Documents/GitHub/Untitled/VarelaDigital")

TEI_DOCS_DIR = REPO_ROOT / "data" / "documents_XML"
STANDOFF_DIR = REPO_ROOT / "data" / "standoff"
OUTPUT_DIR = REPO_ROOT / "data" / "metadata"
OUTPUT_CSV = OUTPUT_DIR / "metadata_all.csv"

STANDOFF_PERSONS = STANDOFF_DIR / "standoff-persons.xml"
STANDOFF_ORGS = STANDOFF_DIR / "standoff-orgs.xml"
STANDOFF_PLACES = STANDOFF_DIR / "standoff-places.xml"
STANDOFF_EVENTS = STANDOFF_DIR / "standoff-events.xml"

TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"


def strip_text(s: Optional[str]) -> str:
    return (s or "").strip()


def find_first(root: ET.Element, xpath: str) -> Optional[ET.Element]:
    return root.find(xpath, TEI_NS)


def find_all(root: ET.Element, xpath: str) -> List[ET.Element]:
    return root.findall(xpath, TEI_NS)


def normalize_ref(ref: str) -> str:
    ref = (ref or "").strip()
    return ref[1:] if ref.startswith("#") else ref


def safe_join(values: Iterable[str], sep: str = ";") -> str:
    cleaned = [v.strip() for v in values if v and v.strip()]
    return sep.join(cleaned)


def uniq_preserve(seq: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for x in seq:
        x = strip_text(x)
        if not x or x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


@dataclass
class EntityRecord:
    xml_id: str
    label: str
    uri: str
    aliases: List[str] = field(default_factory=list)
    lat: str = ""
    lon: str = ""


def _collect_texts(parent: ET.Element, xpath: str) -> List[str]:
    els = parent.findall(xpath, TEI_NS)
    vals: List[str] = []
    for el in els:
        txt = strip_text("".join(el.itertext()))
        if txt:
            vals.append(txt)
    return vals


def parse_standoff_persons(path: Path) -> Dict[str, EntityRecord]:
    idx: Dict[str, EntityRecord] = {}
    if not path.exists():
        return idx

    root = ET.parse(path).getroot()
    for p in root.findall(".//tei:person", TEI_NS):
        xml_id = p.get(XML_ID)
        if not xml_id:
            continue

        names = _collect_texts(p, "tei:persName")
        label = names[0] if names else xml_id
        aliases = uniq_preserve(names[1:])

        idno_wd = p.find("tei:idno[@type='wikidata']", TEI_NS)
        idno_viaf = p.find("tei:idno[@type='viaf']", TEI_NS)

        if idno_wd is not None and strip_text(idno_wd.text):
            uri = strip_text(idno_wd.text)
        elif idno_viaf is not None and strip_text(idno_viaf.text):
            uri = strip_text(idno_viaf.text)
        else:
            uri = f"{PROJECT_PERSON_BASE}{xml_id}"

        idx[xml_id] = EntityRecord(xml_id=xml_id, label=label, uri=uri, aliases=aliases)

    return idx


def parse_standoff_orgs(path: Path) -> Dict[str, EntityRecord]:
    idx: Dict[str, EntityRecord] = {}
    if not path.exists():
        return idx

    root = ET.parse(path).getroot()
    for o in root.findall(".//tei:org", TEI_NS):
        xml_id = o.get(XML_ID)
        if not xml_id:
            continue

        names = _collect_texts(o, "tei:orgName")
        label = names[0] if names else xml_id
        aliases = uniq_preserve(names[1:])

        idno_wd = o.find("tei:idno[@type='wikidata']", TEI_NS)
        idno_viaf = o.find("tei:idno[@type='viaf']", TEI_NS)

        if idno_wd is not None and strip_text(idno_wd.text):
            uri = strip_text(idno_wd.text)
        elif idno_viaf is not None and strip_text(idno_viaf.text):
            uri = strip_text(idno_viaf.text)
        else:
            uri = f"{PROJECT_ORG_BASE}{xml_id}"

        idx[xml_id] = EntityRecord(xml_id=xml_id, label=label, uri=uri, aliases=aliases)

    return idx


def parse_standoff_places(path: Path) -> Dict[str, EntityRecord]:
    idx: Dict[str, EntityRecord] = {}
    if not path.exists():
        return idx

    root = ET.parse(path).getroot()
    for pl in root.findall(".//tei:place", TEI_NS):
        xml_id = pl.get(XML_ID)
        if not xml_id:
            continue

        names = _collect_texts(pl, "tei:placeName")
        label = names[0] if names else xml_id
        aliases = uniq_preserve(names[1:])

        idno_geo = pl.find("tei:idno[@type='geonames']", TEI_NS)
        uri = strip_text(idno_geo.text) if idno_geo is not None else ""

        lat = ""
        lon = ""
        geo_el = pl.find(".//tei:geo", TEI_NS)
        if geo_el is not None and strip_text(geo_el.text):
            raw = strip_text(geo_el.text).replace(",", " ")
            parts = [p for p in raw.split() if p]
            if len(parts) >= 2:
                lat, lon = parts[0], parts[1]

        idx[xml_id] = EntityRecord(xml_id=xml_id, label=label, uri=uri, aliases=aliases, lat=lat, lon=lon)

    return idx


def parse_standoff_events(path: Path) -> Dict[str, EntityRecord]:
    idx: Dict[str, EntityRecord] = {}
    if not path.exists():
        return idx

    root = ET.parse(path).getroot()
    for ev in root.findall(".//tei:event", TEI_NS):
        xml_id = ev.get(XML_ID)
        if not xml_id:
            continue

        descs = _collect_texts(ev, "tei:desc")
        label = descs[0] if descs else xml_id
        aliases = uniq_preserve(descs[1:])

        uri = f"{PROJECT_EVENT_BASE}{xml_id}"
        idx[xml_id] = EntityRecord(xml_id=xml_id, label=label, uri=uri, aliases=aliases)

    return idx


def extract_cv_id(root: ET.Element, fallback_filename: str) -> str:
    div = find_first(root, ".//tei:text//tei:div")
    if div is not None:
        xml_id = div.get(XML_ID)
        if xml_id:
            return xml_id.strip()
    return Path(fallback_filename).stem


def extract_subject(root: ET.Element) -> str:
    t = find_first(root, ".//tei:teiHeader/tei:fileDesc/tei:titleStmt/tei:title")
    return strip_text(t.text if t is not None else "")


def extract_author_from_header(root: ET.Element) -> Tuple[str, str]:
    pn = find_first(root, ".//tei:teiHeader/tei:fileDesc/tei:titleStmt/tei:author//tei:persName[@ref]")
    if pn is not None:
        return strip_text("".join(pn.itertext())), normalize_ref(pn.get("ref", ""))

    on = find_first(root, ".//tei:teiHeader/tei:fileDesc/tei:titleStmt/tei:author//tei:orgName[@ref]")
    if on is not None:
        return strip_text("".join(on.itertext())), normalize_ref(on.get("ref", ""))

    author = find_first(root, ".//tei:teiHeader/tei:fileDesc/tei:titleStmt/tei:author")
    if author is not None:
        return strip_text("".join(author.itertext())), ""

    return "", ""


def extract_corresp_sent_received(root: ET.Element) -> Tuple[str, str, str, str, str]:
    sent_p = find_first(
        root,
        ".//tei:teiHeader/tei:profileDesc/tei:correspDesc/tei:correspAction[@type='sent']/tei:persName[@ref]",
    )
    recv_p = find_first(
        root,
        ".//tei:teiHeader/tei:profileDesc/tei:correspDesc/tei:correspAction[@type='received']/tei:persName[@ref]",
    )
    sent_date = find_first(
        root,
        ".//tei:teiHeader/tei:profileDesc/tei:correspDesc/tei:correspAction[@type='sent']/tei:date[@when]",
    )

    author_name = strip_text("".join(sent_p.itertext())) if sent_p is not None else ""
    author_ref = normalize_ref(sent_p.get("ref", "")) if sent_p is not None else ""

    recipient_name = strip_text("".join(recv_p.itertext())) if recv_p is not None else ""
    recipient_ref = normalize_ref(recv_p.get("ref", "")) if recv_p is not None else ""

    sent_when = strip_text(sent_date.get("when")) if sent_date is not None else ""
    return author_name, author_ref, recipient_name, recipient_ref, sent_when


def extract_main_date_norm(root: ET.Element) -> str:
    sent_date = find_first(
        root,
        ".//tei:teiHeader/tei:profileDesc/tei:correspDesc/tei:correspAction[@type='sent']/tei:date[@when]",
    )
    if sent_date is not None:
        return strip_text(sent_date.get("when"))

    dl_date = find_first(root, ".//tei:text//tei:dateline//tei:date[@when]")
    if dl_date is not None and strip_text(dl_date.get("when")):
        return strip_text(dl_date.get("when"))

    return ""


def extract_main_place_from_corresp(root: ET.Element) -> Tuple[str, str]:
    p = find_first(
        root,
        ".//tei:teiHeader/tei:profileDesc/tei:correspDesc/tei:correspAction[@type='sent']/tei:placeName[@ref]",
    )
    if p is not None:
        return strip_text("".join(p.itertext())), normalize_ref(p.get("ref", ""))

    dp = find_first(root, ".//tei:text//tei:dateline//tei:placeName[@ref]")
    if dp is not None:
        return strip_text("".join(dp.itertext())), normalize_ref(dp.get("ref", ""))

    return "", ""


def surface_text_prefer_reg(el: ET.Element) -> str:
    reg = el.find(".//tei:reg", TEI_NS)
    if reg is not None:
        t = strip_text("".join(reg.itertext()))
        if t:
            return t
    return strip_text("".join(el.itertext()))


def collect_mentions(
    root: ET.Element,
) -> Tuple[Dict[str, Set[str]], Dict[str, Set[str]], Dict[str, Set[str]], Dict[str, Set[str]]]:
    people: Dict[str, Set[str]] = {}
    orgs: Dict[str, Set[str]] = {}
    places: Dict[str, Set[str]] = {}
    events: Dict[str, Set[str]] = {}

    def add(dct: Dict[str, Set[str]], rid: str, surface: str):
        rid = (rid or "").strip()
        surface = strip_text(surface)
        if not rid or not surface:
            return
        dct.setdefault(rid, set()).add(surface)

    for pn in find_all(root, ".//tei:text//tei:persName[@ref]"):
        rid = normalize_ref(pn.get("ref", ""))
        add(people, rid, "".join(pn.itertext()))

    for on in find_all(root, ".//tei:text//tei:orgName[@ref]"):
        rid = normalize_ref(on.get("ref", ""))
        add(orgs, rid, "".join(on.itertext()))

    for pl in find_all(root, ".//tei:text//tei:placeName[@ref]"):
        rid = normalize_ref(pl.get("ref", ""))
        add(places, rid, surface_text_prefer_reg(pl))

    for ev in find_all(root, ".//tei:text//tei:eventName[@ref]"):
        rid = normalize_ref(ev.get("ref", ""))
        add(events, rid, "".join(ev.itertext()))

    for ev in find_all(root, ".//tei:text//tei:rs[@type='event'][@ref]"):
        rid = normalize_ref(ev.get("ref", ""))
        add(events, rid, "".join(ev.itertext()))

    for ev in find_all(root, ".//tei:text//tei:name[@type='event'][@ref]"):
        rid = normalize_ref(ev.get("ref", ""))
        add(events, rid, "".join(ev.itertext()))

    return people, orgs, places, events


def collect_all_when_dates(root: ET.Element) -> str:
    dates: Set[str] = set()
    for d in root.findall(".//tei:date[@when]", TEI_NS):
        when = strip_text(d.get("when"))
        if when:
            dates.add(when)
    return ";".join(sorted(dates))


def resolve_person(xml_id: str, persons_idx: Dict[str, EntityRecord]) -> EntityRecord:
    return persons_idx.get(
        xml_id,
        EntityRecord(xml_id=xml_id, label=xml_id, uri=f"{PROJECT_PERSON_BASE}{xml_id}", aliases=[]),
    )


def resolve_org(xml_id: str, orgs_idx: Dict[str, EntityRecord]) -> EntityRecord:
    return orgs_idx.get(
        xml_id,
        EntityRecord(xml_id=xml_id, label=xml_id, uri=f"{PROJECT_ORG_BASE}{xml_id}", aliases=[]),
    )


def resolve_place(xml_id: str, places_idx: Dict[str, EntityRecord]) -> EntityRecord:
    return places_idx.get(
        xml_id,
        EntityRecord(xml_id=xml_id, label=xml_id, uri="", aliases=[], lat="", lon=""),
    )


def resolve_event(xml_id: str, events_idx: Dict[str, EntityRecord]) -> EntityRecord:
    return events_idx.get(
        xml_id,
        EntityRecord(xml_id=xml_id, label=xml_id, uri=f"{PROJECT_EVENT_BASE}{xml_id}", aliases=[]),
    )


def iter_tei_files(folder: Path) -> List[Path]:
    if not folder.exists():
        return []
    return sorted([p for p in folder.rglob("*.xml") if p.is_file()])


def pack_entity_csv(label: str, uri: str, aliases: List[str]) -> str:
    aliases = [a for a in uniq_preserve(aliases) if a != label]
    if aliases:
        return f"{label}|{uri}|{'§'.join(aliases)}"
    return f"{label}|{uri}"


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

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

        c_author_name, c_author_ref, recipient_name, recipient_ref, _sent_when = extract_corresp_sent_received(root)
        if c_author_name or c_author_ref:
            author_name, author_ref = c_author_name, c_author_ref
        else:
            author_name, author_ref = extract_author_from_header(root)

        author_uri = ""
        if author_ref:
            if author_ref in persons_idx:
                author_uri = persons_idx[author_ref].uri
            elif author_ref in orgs_idx:
                author_uri = orgs_idx[author_ref].uri
            else:
                author_uri = f"{PROJECT_PERSON_BASE}{author_ref}"

        recipient_uri = ""
        if recipient_ref:
            if recipient_ref in persons_idx:
                recipient_uri = persons_idx[recipient_ref].uri
            elif recipient_ref in orgs_idx:
                recipient_uri = orgs_idx[recipient_ref].uri
            else:
                recipient_uri = f"{PROJECT_PERSON_BASE}{recipient_ref}"

        date_norm = extract_main_date_norm(root)

        place_label, place_ref = extract_main_place_from_corresp(root)
        place_uri = ""
        lat = ""
        lon = ""
        if place_ref:
            pl_rec = resolve_place(place_ref, places_idx)
            if not place_label:
                place_label = pl_rec.label
            place_uri = pl_rec.uri
            lat = pl_rec.lat
            lon = pl_rec.lon

        m_people, m_orgs, m_places, m_events = collect_mentions(root)

        mentioned_people: List[str] = []
        for pid in sorted(m_people.keys()):
            rec = resolve_person(pid, persons_idx)
            surfaces = sorted(m_people[pid])
            aliases = rec.aliases + surfaces
            mentioned_people.append(pack_entity_csv(rec.label, rec.uri, aliases))

        mentioned_orgs: List[str] = []
        for oid in sorted(m_orgs.keys()):
            rec = resolve_org(oid, orgs_idx)
            surfaces = sorted(m_orgs[oid])
            aliases = rec.aliases + surfaces
            mentioned_orgs.append(pack_entity_csv(rec.label, rec.uri, aliases))

        mentioned_places: List[str] = []
        for plid in sorted(m_places.keys()):
            rec = resolve_place(plid, places_idx)
            surfaces = sorted(m_places[plid])
            aliases = rec.aliases + surfaces
            mentioned_places.append(pack_entity_csv(rec.label, rec.uri, aliases))

        mentioned_events: List[str] = []
        for evid in sorted(m_events.keys()):
            rec = resolve_event(evid, events_idx)
            surfaces = sorted(m_events[evid])
            aliases = rec.aliases + surfaces
            mentioned_events.append(pack_entity_csv(rec.label, rec.uri, aliases))

        mentioned_dates = collect_all_when_dates(root)

        rows.append(
            {
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
            }
        )

    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    print(f"OK — wrote {len(rows)} rows to: {OUTPUT_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())