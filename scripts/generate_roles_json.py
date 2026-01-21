#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
import xml.etree.ElementTree as ET

REPO_ROOT = Path("/Users/carlamenegat/Documents/GitHub/Untitled/VarelaDigital")

STANDOFF_PERSONS = REPO_ROOT / "data" / "standoff" / "standoff_persons.xml"
OUT_JSON = REPO_ROOT / "data" / "indexes" / "roles.json"

PROJECT_BASE = "https://carlamenegat.github.io/VarelaDigital"
PROJECT_PERSON_BASE = f"{PROJECT_BASE}/person/"

TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"


def strip_text(s: Optional[str]) -> str:
    return (s or "").strip()


@dataclass
class RoleInTime:
    roleName: str
    affiliationRef: str
    begin: str
    end: str


def first_text(el: Optional[ET.Element]) -> str:
    if el is None:
        return ""
    return strip_text("".join(el.itertext()))


def get_person_uri(person_el: ET.Element, xml_id: str) -> str:
    idno_wd = person_el.find("tei:idno[@type='wikidata']", TEI_NS)
    if idno_wd is not None and strip_text(idno_wd.text):
        return strip_text(idno_wd.text)

    idno_viaf = person_el.find("tei:idno[@type='viaf']", TEI_NS)
    if idno_viaf is not None and strip_text(idno_viaf.text):
        return strip_text(idno_viaf.text)

    return f"{PROJECT_PERSON_BASE}{xml_id}"


def parse_roles(person_el: ET.Element) -> List[RoleInTime]:
    roles: List[RoleInTime] = []

    for st in person_el.findall("tei:state[@type='roleInTime']", TEI_NS):
        role_name = first_text(st.find("tei:roleName", TEI_NS))
        if not role_name:
            continue

        aff = st.find("tei:affiliation", TEI_NS)
        affiliation_ref = ""
        if aff is not None:
            affiliation_ref = strip_text(aff.get("ref") or "")
            if affiliation_ref.startswith("#"):
                affiliation_ref = affiliation_ref[1:]

        begin = ""
        end = ""
        for d in st.findall("tei:date", TEI_NS):
            t = strip_text(d.get("type") or "").lower()
            when = strip_text(d.get("when") or "")
            if t == "begin" and when:
                begin = when
            elif t == "end" and when:
                end = when

        roles.append(
            RoleInTime(
                roleName=role_name,
                affiliationRef=affiliation_ref,
                begin=begin,
                end=end,
            )
        )

    return roles


def main() -> int:
    if not STANDOFF_PERSONS.exists():
        raise SystemExit(f"Missing file: {STANDOFF_PERSONS}")

    root = ET.parse(STANDOFF_PERSONS).getroot()

    by_id: Dict[str, dict] = {}
    by_uri: Dict[str, str] = {}
    all_role_names = set()

    for p in root.findall(".//tei:person", TEI_NS):
        xml_id = strip_text(p.get(XML_ID) or "")
        if not xml_id:
            continue

        names = [first_text(n) for n in p.findall("tei:persName", TEI_NS)]
        names = [n for n in names if n]
        label = names[0] if names else xml_id

        uri = get_person_uri(p, xml_id)

        roles = parse_roles(p)
        if not roles:
            continue

        roles_payload = []
        for r in roles:
            all_role_names.add(r.roleName)
            roles_payload.append(
                {
                    "roleName": r.roleName,
                    "affiliationRef": r.affiliationRef,
                    "begin": r.begin,
                    "end": r.end,
                }
            )

        by_id[xml_id] = {
            "label": label,
            "uri": uri,
            "roles": roles_payload,
        }

        if uri:
            by_uri[uri] = xml_id
        by_uri[f"{PROJECT_PERSON_BASE}{xml_id}"] = xml_id

    out = {
        "byId": by_id,
        "byUri": by_uri,
        "allRoleNames": sorted(all_role_names, key=lambda s: s.casefold()),
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"OK — wrote {len(by_id)} people with roles -> {OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())