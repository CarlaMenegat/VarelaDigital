#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv
import os
import re
import unicodedata
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CSV_PATH = os.path.join(ROOT, "letters_data", "metadata", "metadata_all.csv")

# TEI letters with <sourceDesc> (for volume/pages/publisher)
DOCS_XML_DIR = os.path.join(ROOT, "letters_data", "documents_XML")

STANDOFF_DIR = os.path.join(ROOT, "letters_data", "standoff")
ST_PERSONS   = os.path.join(STANDOFF_DIR, "standoff_persons.xml")
ST_ORGS      = os.path.join(STANDOFF_DIR, "standoff_orgs.xml")
ST_PLACES    = os.path.join(STANDOFF_DIR, "standoff_places.xml")
ST_EVENTS    = os.path.join(STANDOFF_DIR, "standoff_events.xml")
ST_RELATIONS = os.path.join(STANDOFF_DIR, "standoff_relations.xml")

# ✅ corrected output path
OUT_TTL = os.path.join(ROOT, "data_models", "kbvd.ttl")

BASE = "https://carlamenegat.github.io/VarelaDigital/"
BASE_ITEM   = BASE + "item/"
BASE_PERSON = BASE + "person/"
BASE_ORG    = BASE + "org/"
BASE_PLACE  = BASE + "place/"
BASE_EVENT  = BASE + "event/"
BASE_ROLEINTIME = BASE + "roleintime/"
BASE_ROLE = "https://carlamenegat.github.io/VarelaDigital/ontology/role/"

VD_HOST = "carlamenegat.github.io"
GEONAMES_HOST = "www.geonames.org"

PREFIX_BLOCK = """@prefix vdi: <https://carlamenegat.github.io/VarelaDigital/> .
@prefix item: <https://carlamenegat.github.io/VarelaDigital/item/> .
@prefix person: <https://carlamenegat.github.io/VarelaDigital/person/> .
@prefix org: <https://carlamenegat.github.io/VarelaDigital/org/> .
@prefix place: <https://carlamenegat.github.io/VarelaDigital/place/> .
@prefix event: <https://carlamenegat.github.io/VarelaDigital/event/> .

@prefix vd: <https://carlamenegat.github.io/VarelaDigital/ontology/> .
@prefix vdrole: <https://carlamenegat.github.io/VarelaDigital/ontology/role/> .

@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

@prefix bibo: <http://purl.org/ontology/bibo/> .
@prefix dct: <http://purl.org/dc/terms/> .
@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix doco: <http://purl.org/spar/doco/> .
@prefix fabio: <http://purl.org/spar/fabio/> .
@prefix foaf: <http://xmlns.com/foaf/0.1/> .
@prefix frbr: <http://purl.org/vocab/frbr/core#> .
@prefix geo: <http://www.w3.org/2003/01/geo/wgs84_pos#> .
@prefix hico: <http://purl.org/emmedi/hico/> .
@prefix hrao: <https://carlamenegat.github.io/hrao/hrao#> .
@prefix pro: <http://purl.org/spar/pro/> .
@prefix prov: <http://www.w3.org/ns/prov#> .
@prefix rel: <http://purl.org/vocab/relationship/> .
@prefix rico: <https://www.ica.org/standards/RiC/ontology#> .
@prefix san: <http://dati.san.beniculturali.it/ode/?uri=http://dati.san.beniculturali.it/SAN/> .
@prefix schema: <https://schema.org/> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .

"""

P = {
    "title": "dcterms:title",
    "creator": "dcterms:creator",
    "recipient": "vd:recipient",
    "date": "dcterms:date",
    "spatial": "dcterms:spatial",
    "source": "dcterms:source",
    "isPartOf": "dct:isPartOf",
    "isVersionOf": "dcterms:isVersionOf",
    "description": "dcterms:description",
    "mentionsPerson": "vd:mentionsPerson",
    "mentionsOrg": "vd:mentionsOrg",
    "mentionsPlace": "vd:mentionsPlace",
    "mentionsEvent": "vd:mentionsEvent",
    "lat": "vd:lat",
    "long": "vd:long",
    "exactMatch": "skos:exactMatch",
    "altLabel": "skos:altLabel",
    "withRole": "pro:withRole",
    "isHeldBy": "pro:isHeldBy",
    "relatesTo": "pro:relatesTo",
    "isRelatedToRoleInTime": "pro:isRelatedToRoleInTime",
    "subOrgOf": "schema:subOrganizationOf",
    "startDate": "schema:startDate",
    "endDate": "schema:endDate",
    "realization": "frbr:realization",
    "embodiment": "frbr:embodiment",
    "exemplar": "frbr:exemplar",
    "publisher": "dct:publisher",
    "identifier": "dct:identifier",
    "rights": "dct:rights",
}

T = {
    "Person": "foaf:Person",
    "Org": "foaf:Organization",
    "Place": "geo:SpatialThing",
    "Event": "san:Event",
    "RoleInTime": "pro:RoleInTime",
    "Role": "pro:Role",
}

KB_COLLECTION = BASE + "collection/colecao_varela"
KB_EDITION    = BASE + "edition/varela_digital"


def ttl_escape(s: str) -> str:
    if s is None:
        return ""
    s = s.replace("\\", "\\\\").replace('"', '\\"')
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    return s


def normalize_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def is_http_uri(u: str) -> bool:
    if not u:
        return False
    try:
        p = urlparse(u.strip())
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        return False


def uri_or_none(u: str):
    u = (u or "").strip()
    return u if is_http_uri(u) else None


def host_of(u: str) -> str:
    try:
        return urlparse(u).netloc
    except Exception:
        return ""


def is_vd_uri(u: str) -> bool:
    return host_of(u) == VD_HOST and "/VarelaDigital/" in u


def classify_vd_uri(u: str) -> str:
    try:
        path = urlparse(u).path
        if "/VarelaDigital/person/" in path:
            return "person"
        if "/VarelaDigital/org/" in path:
            return "org"
        if "/VarelaDigital/place/" in path:
            return "place"
        if "/VarelaDigital/event/" in path:
            return "event"
        if "/VarelaDigital/item/" in path:
            return "item"
        if "/VarelaDigital/roleintime/" in path:
            return "roleintime"
        return "other"
    except Exception:
        return "other"


def slugify(label: str) -> str:
    label = normalize_ws(label)
    label = unicodedata.normalize("NFKD", label)
    label = "".join(ch for ch in label if not unicodedata.combining(ch))
    label = label.lower()
    label = re.sub(r"[^a-z0-9]+", "_", label)
    label = re.sub(r"_+", "_", label).strip("_")
    return label or "unnamed"


def safe_float_str(s: str):
    s = (s or "").strip()
    if not s:
        return None
    try:
        float(s)
        return s
    except ValueError:
        return None


def item_uri(cv_id: str) -> str:
    return BASE_ITEM + cv_id


def item_expression_uri(cv_id: str) -> str:
    return f"{BASE_ITEM}{cv_id}/expression"


def item_manifestation_uri(cv_id: str, kind: str) -> str:
    return f"{BASE_ITEM}{cv_id}/{kind}"


def item_exemplar_uri(cv_id: str) -> str:
    return f"{BASE_ITEM}{cv_id}/exemplar"

def textchunk_uri(cv_id: str, chunk_id: str = "whole") -> str:
    # One stable TextChunk per letter (minimum viable anchoring)
    return f"{BASE_ITEM}{cv_id}/chunk/{chunk_id}"

def interpretation_act_uri(cv_id: str) -> str:
    return f"{BASE_ITEM}{cv_id}/interpretationAct"

def entityref_uri(cv_id: str, kind: str, target_slug: str, n: int) -> str:
    # Stable per letter + kind + target + counter (avoids collisions)
    return f"{BASE_ITEM}{cv_id}/ref/{kind}/{target_slug}_{n}"


def person_uri(xmlid: str) -> str:
    return BASE_PERSON + xmlid


def org_uri(xmlid: str) -> str:
    return BASE_ORG + xmlid


def place_uri(xmlid: str) -> str:
    return BASE_PLACE + xmlid


def event_uri(xmlid: str) -> str:
    return BASE_EVENT + xmlid


def roleintime_uri(xmlid: str) -> str:
    return BASE_ROLEINTIME + xmlid


def role_uri_from_label(label: str) -> str:
    return BASE_ROLE + slugify(label)


def localname(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def get_xml_id(el):
    return (
        el.attrib.get("{http://www.w3.org/XML/1998/namespace}id")
        or el.attrib.get("xml:id")
        or el.attrib.get("id")
        or ""
    )


def children_texts(el, tagname: str):
    out = []
    for c in list(el):
        if localname(c.tag) == tagname:
            out.append(normalize_ws("".join(c.itertext())))
    return [x for x in out if x]


def child_text(el, tagname: str):
    for c in list(el):
        if localname(c.tag) == tagname:
            return normalize_ws("".join(c.itertext()))
    return ""


def write_prefixes(f):
    f.write(PREFIX_BLOCK)


def _obj_to_ttl(obj: str, is_uri: bool) -> str:
    if not is_uri:
        return f"\"{ttl_escape(obj)}\""
    if obj.startswith("http://") or obj.startswith("https://"):
        return f"<{obj}>"
    return obj


def emit_triples(f, subj: str, triples: list):
    if not triples:
        return
    f.write(f"<{subj}> ")
    for i, (pred, obj, is_uri) in enumerate(triples):
        sep = " ;\n    " if i > 0 else ""
        f.write(f"{sep}{pred} {_obj_to_ttl(obj, is_uri)}")
    f.write(" .\n\n")


def parse_compound_field(raw: str):
    out = []
    if not raw:
        return out
    parts = [p.strip() for p in raw.split(";") if p.strip()]
    for part in parts:
        segs = [s.strip() for s in part.split("|") if s.strip()]
        if not segs:
            continue
        label = normalize_ws(segs[0])
        uri = uri_or_none(segs[1]) if len(segs) >= 2 else None
        alt = None
        if "§" in label:
            main, a = label.split("§", 1)
            label = normalize_ws(main)
            alt = normalize_ws(a) if a.strip() else None
        out.append({"label": label, "uri": uri, "altLabel": alt})
    return out


def upsert(store: dict, uri: str, label: str = None, alt: str = None, exact: str = None):
    rec = store.setdefault(uri, {"label": uri, "altLabels": set(), "exactMatches": set()})
    if label and (rec["label"] == uri or not rec["label"]):
        rec["label"] = label
    if alt:
        rec["altLabels"].add(alt)
    if exact:
        rec["exactMatches"].add(exact)
    return rec


def normalize_relation_uri(u: str):
    u = uri_or_none(u)
    if not u:
        return None
    if u.startswith(BASE_PERSON + "CV-"):
        return u.replace(BASE_PERSON, BASE_ITEM)
    if u.startswith(BASE_ORG + "CV-"):
        return u.replace(BASE_ORG, BASE_ITEM)
    if u.startswith(BASE_PLACE + "CV-"):
        return u.replace(BASE_PLACE, BASE_ITEM)
    if u.startswith(BASE_EVENT + "CV-"):
        return u.replace(BASE_EVENT, BASE_ITEM)
    return u


def resolve_project_uri(label: str, uri: str, kind_hint: str, exact_to_project: dict):
    label = normalize_ws(label)
    uri = uri_or_none(uri)

    if uri and is_vd_uri(uri):
        return uri, classify_vd_uri(uri), None

    if uri and uri in exact_to_project:
        pu = exact_to_project[uri]
        return pu, classify_vd_uri(pu), uri

    if uri and host_of(uri) == GEONAMES_HOST:
        if uri in exact_to_project:
            pu = exact_to_project[uri]
            return pu, "place", uri
        pu = place_uri(slugify(label or uri))
        return pu, "place", uri

    if kind_hint == "org":
        pu = org_uri(slugify(label or uri or "unnamed"))
        return pu, "org", uri
    if kind_hint == "place":
        pu = place_uri(slugify(label or uri or "unnamed"))
        return pu, "place", uri
    if kind_hint == "event":
        pu = event_uri(slugify(label or uri or "unnamed"))
        return pu, "event", uri

    pu = person_uri(slugify(label or uri or "unnamed"))
    return pu, "person", uri


def ref_to_uri(ref: str, id_to_project: dict, exact_to_project: dict):
    ref = (ref or "").strip()
    if not ref:
        return None

    if ref.startswith("#"):
        key = ref[1:]
        if re.match(r"^CV-\d+$", key):
            return item_uri(key)
        if key in id_to_project:
            return id_to_project[key]
        return person_uri(key)

    if is_http_uri(ref):
        u = normalize_relation_uri(ref)
        if u in exact_to_project:
            return exact_to_project[u]
        return u

    return None


def find_letter_xml(cv_id: str) -> str | None:
    if not os.path.isdir(DOCS_XML_DIR):
        return None
    candidates = [
        os.path.join(DOCS_XML_DIR, f"{cv_id}.xml"),
        os.path.join(DOCS_XML_DIR, f"{cv_id.lower()}.xml"),
        os.path.join(DOCS_XML_DIR, f"{cv_id.upper()}.xml"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    for fn in os.listdir(DOCS_XML_DIR):
        if not fn.lower().endswith(".xml"):
            continue
        if fn.startswith(cv_id) or fn.lower().startswith(cv_id.lower()):
            p = os.path.join(DOCS_XML_DIR, fn)
            if os.path.isfile(p):
                return p
    return None


def extract_print_bibl_from_tei(xml_path: str) -> dict:
    out = {"volume": None, "page_from": None, "page_to": None, "publisher_label": None, "pubyear": None}
    try:
        root = ET.parse(xml_path).getroot()
    except Exception:
        return out

    imprint = None
    for el in root.iter():
        if localname(el.tag) == "imprint":
            imprint = el
            break
    if imprint is None:
        return out

    for c in list(imprint):
        tag = localname(c.tag)
        if tag == "publisher":
            val = normalize_ws("".join(c.itertext()))
            if val:
                out["publisher_label"] = val
        elif tag == "date":
            when = (c.attrib.get("when") or "").strip()
            if when and re.match(r"^\d{4}$", when):
                out["pubyear"] = when
            else:
                val = normalize_ws("".join(c.itertext()))
                if val and re.match(r"^\d{4}$", val):
                    out["pubyear"] = val
        elif tag == "biblScope":
            btype = (c.attrib.get("type") or "").strip().lower()
            unit  = (c.attrib.get("unit") or "").strip().lower()
            if btype == "volume":
                val = normalize_ws("".join(c.itertext()))
                if val:
                    out["volume"] = val
            if unit == "page":
                frm = (c.attrib.get("from") or "").strip()
                to  = (c.attrib.get("to") or "").strip()
                if frm:
                    out["page_from"] = frm
                if to:
                    out["page_to"] = to
    return out

def load_standoffs():
    persons, orgs, places, events = {}, {}, {}, {}
    exact_to_project = {}
    id_to_project = {}

    role_nodes = {}
    role_in_time = []
    person_roles_index = {}
    org_affiliations = []

    def register(kind: str, xmlid: str, label: str, alts: list, exacts: list):
        if kind == "person":
            pu = person_uri(xmlid)
            upsert(persons, pu, label=label)
        elif kind == "org":
            pu = org_uri(xmlid)
            upsert(orgs, pu, label=label)
        elif kind == "place":
            pu = place_uri(xmlid)
            upsert(places, pu, label=label)
        elif kind == "event":
            pu = event_uri(xmlid)
            upsert(events, pu, label=label)
        else:
            return None

        for a in alts:
            if a and a != label:
                if kind == "person":
                    upsert(persons, pu, alt=a)
                elif kind == "org":
                    upsert(orgs, pu, alt=a)
                elif kind == "place":
                    upsert(places, pu, alt=a)
                elif kind == "event":
                    upsert(events, pu, alt=a)

        for ex in exacts:
            ex = uri_or_none(ex)
            if ex:
                if kind == "person":
                    upsert(persons, pu, exact=ex)
                elif kind == "org":
                    upsert(orgs, pu, exact=ex)
                elif kind == "place":
                    upsert(places, pu, exact=ex)
                elif kind == "event":
                    upsert(events, pu, exact=ex)
                exact_to_project[ex] = pu

        id_to_project[xmlid] = pu
        return pu

    # ---- PERSONS + RoleInTime ----
    if os.path.exists(ST_PERSONS):
        root = ET.parse(ST_PERSONS).getroot()
        for el in root.iter():
            if localname(el.tag) != "person":
                continue
            pid = get_xml_id(el)
            if not pid:
                continue

            names = children_texts(el, "persName")
            label = names[0] if names else pid
            alts = names[1:]

            exacts = []
            for c in list(el):
                if localname(c.tag) == "idno":
                    t = (c.attrib.get("type") or "").strip().lower()
                    val = normalize_ws("".join(c.itertext()))
                    if val and t != "project":
                        exacts.append(val)

            p_uri = register("person", pid, label, alts, exacts) or person_uri(pid)

            for st in list(el):
                if localname(st.tag) != "state":
                    continue
                if (st.attrib.get("type") or "").strip() != "roleInTime":
                    continue

                st_id = get_xml_id(st)
                if not st_id:
                    continue

                rit_uri = roleintime_uri(st_id)
                role_label = child_text(st, "roleName") or st_id
                r_uri = role_uri_from_label(role_label)
                role_nodes[r_uri] = role_label

                triples = [
                    ("rdf:type", T["RoleInTime"], True),
                    (P["isHeldBy"], p_uri, True),
                    (P["withRole"], r_uri, True),
                ]

                for a in list(st):
                    if localname(a.tag) == "affiliation":
                        ref = (a.attrib.get("ref") or "").strip()
                        org_u = ref_to_uri(ref, id_to_project, exact_to_project)
                        if org_u:
                            triples.append((P["relatesTo"], org_u, True))
                            upsert(orgs, org_u)

                start = None
                end = None
                for d in list(st):
                    if localname(d.tag) != "date":
                        continue
                    dtype = (d.attrib.get("type") or "").strip().lower()
                    when = (d.attrib.get("when") or "").strip()
                    frm = (d.attrib.get("from") or "").strip()
                    to = (d.attrib.get("to") or "").strip()

                    if dtype == "begin" and when:
                        start = when
                    elif dtype == "end" and when:
                        end = when
                    elif frm or to:
                        if frm:
                            start = frm
                        if to:
                            end = to
                    elif when:
                        start = start or when

                if start:
                    triples.append((P["startDate"], start, False))
                if end:
                    triples.append((P["endDate"], end, False))

                note = child_text(st, "note")
                if note:
                    triples.append((P["description"], note, False))

                role_in_time.append((rit_uri, triples))
                person_roles_index.setdefault(p_uri, set()).add(rit_uri)

        # ---- ORGS ----
    if os.path.exists(ST_ORGS):
        root = ET.parse(ST_ORGS).getroot()
        for el in root.iter():
            if localname(el.tag) != "org":
                continue
            oid = get_xml_id(el)
            if not oid:
                continue

            names = children_texts(el, "orgName")
            label = names[0] if names else oid
            alts = names[1:]

            exacts = []
            for c in list(el):
                if localname(c.tag) == "idno":
                    t = (c.attrib.get("type") or "").strip().lower()
                    val = normalize_ws("".join(c.itertext()))
                    if val and t != "project":
                        exacts.append(val)

            o_uri = register("org", oid, label, alts, exacts) or org_uri(oid)

            for c in list(el):
                if localname(c.tag) == "affiliation":
                    ref = (c.attrib.get("ref") or "").strip()
                    parent = ref_to_uri(ref, id_to_project, exact_to_project)
                    if parent:
                        org_affiliations.append((o_uri, parent))
                        upsert(orgs, parent)

    # ---- PLACES ----
    if os.path.exists(ST_PLACES):
        root = ET.parse(ST_PLACES).getroot()
        for el in root.iter():
            if localname(el.tag) != "place":
                continue
            xid = get_xml_id(el)
            if not xid:
                continue

            names = children_texts(el, "placeName")
            label = names[0] if names else xid
            alts = names[1:]

            exacts = []
            for c in list(el):
                if localname(c.tag) == "idno":
                    t = (c.attrib.get("type") or "").strip().lower()
                    val = normalize_ws("".join(c.itertext()))
                    if val and t != "project":
                        exacts.append(val)

            register("place", xid, label, alts, exacts)

    # ---- EVENTS ----
    if os.path.exists(ST_EVENTS):
        root = ET.parse(ST_EVENTS).getroot()
        for el in root.iter():
            if localname(el.tag) != "eventName":
                continue
            xid = get_xml_id(el)
            if not xid:
                continue

            label = child_text(el, "desc") or child_text(el, "label") or xid

            exacts = []
            for c in list(el):
                if localname(c.tag) == "idno":
                    t = (c.attrib.get("type") or "").strip().lower()
                    val = normalize_ws("".join(c.itertext()))
                    if val and t != "project":
                        exacts.append(val)

            register("event", xid, label, [], exacts)

    return (
        persons,
        orgs,
        places,
        events,
        exact_to_project,
        id_to_project,
        role_nodes,
        role_in_time,
        person_roles_index,
        org_affiliations,
    )


def build_relations(id_to_project: dict, exact_to_project: dict):
    triples = []
    if not os.path.exists(ST_RELATIONS):
        return triples

    root = ET.parse(ST_RELATIONS).getroot()
    for el in root.iter():
        if localname(el.tag) != "relation":
            continue

        name = (el.attrib.get("name") or "").strip()
        active = (el.attrib.get("active") or "").strip()
        passive = (el.attrib.get("passive") or "").strip()
        mutual = (el.attrib.get("mutual") or "").strip().lower() == "true"

        if not name or not active or not passive:
            continue

        a_uri = ref_to_uri(active, id_to_project, exact_to_project)
        p_uri = ref_to_uri(passive, id_to_project, exact_to_project)
        if not a_uri or not p_uri:
            continue

        triples.append((a_uri, name, p_uri))
        if mutual:
            triples.append((p_uri, name, a_uri))

    return triples

def main():
    (
        persons,
        orgs,
        places,
        events,
        exact_to_project,
        id_to_project,
        role_nodes,
        role_in_time,
        person_roles_index,
        org_affiliations,
    ) = load_standoffs()

    discovered_persons = {}
    discovered_orgs = {}
    discovered_places = {}
    discovered_events = {}

    works_triples = []
    expr_triples_list = []
    mani_triples_list = []
    exemplar_triples_list = []
    textchunk_triples_list = []
    entityref_triples_list = []
    hico_triples_list = []

    with open(CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cv_id = normalize_ws(row.get("cv_id"))
            if not cv_id:
                continue

            work_uri = item_uri(cv_id)
            expr_uri = item_expression_uri(cv_id)
            chunk_uri = textchunk_uri(cv_id, "whole")
            chunk_triples = [
                ("rdf:type", "doco:TextChunk", True),
                ("rdfs:label", f"Text chunk (whole letter) — {cv_id}", False),
            ]
            textchunk_triples_list.append((chunk_uri, chunk_triples))

            man_uri  = item_manifestation_uri(cv_id, "manuscript")
            prt_uri  = item_manifestation_uri(cv_id, "print1978")
            dig_uri  = item_manifestation_uri(cv_id, "digital")
            ex_uri   = item_exemplar_uri(cv_id)
            act_uri = interpretation_act_uri(cv_id)
            hico_triples_list.append((act_uri, [
                ("rdf:type", "hico:InterpretationAct", True),
                ("rdfs:label", f"Interpretation act — {cv_id}", False),
            ]))

            # pull volume/pages/publisher from TEI (documents_XML)
            tei_path = find_letter_xml(cv_id)
            bibl = extract_print_bibl_from_tei(tei_path) if tei_path else {}
            vol = (bibl.get("volume") or "").strip() or None
            pg_from = (bibl.get("page_from") or "").strip() or None
            pg_to = (bibl.get("page_to") or "").strip() or None
            pub_label = (bibl.get("publisher_label") or "").strip() or None
            pubyear = (bibl.get("pubyear") or "").strip() or None

            # publisher node as foaf:Agent (org)
            pub_agent_uri = None
            if pub_label:
                pub_agent_uri = org_uri(slugify(pub_label))
                upsert(discovered_orgs, pub_agent_uri, label=pub_label)

            # ---- Work (Letter) ----
            w_triples = [
                ("rdf:type", "fabio:Letter", True),
                ("rdf:type", "frbr:Work", True),
                (P["isPartOf"], KB_EDITION, True),
                (P["isPartOf"], KB_COLLECTION, True),   # aligns with CollectionModel
                (P["realization"], expr_uri, True),
            ]

            title = normalize_ws(row.get("subject"))
            if title:
                w_triples.append((P["title"], title, False))

            date = normalize_ws(row.get("date"))
            if date:
                w_triples.append((P["date"], date, False))

            lat = safe_float_str(row.get("lat"))
            lon = safe_float_str(row.get("long"))
            if lat:
                w_triples.append((P["lat"], lat, False))
            if lon:
                w_triples.append((P["long"], lon, False))

            text_file = normalize_ws(row.get("text_file"))
            if text_file:
                w_triples.append((P["source"], text_file, False))

            # creator
            a_name = normalize_ws(row.get("author_name"))
            a_uri  = uri_or_none(row.get("author_uri"))
            if a_name or a_uri:
                a_proj, a_kind, a_exact = resolve_project_uri(a_name or a_uri, a_uri, "person", exact_to_project)
                w_triples.append((P["creator"], a_proj, True))
                if a_kind == "org":
                    upsert(discovered_orgs, a_proj, label=(a_name or None), exact=a_exact)
                else:
                    upsert(discovered_persons, a_proj, label=(a_name or None), exact=a_exact)

            # recipient
            r_name = normalize_ws(row.get("recipient_name"))
            r_uri  = uri_or_none(row.get("recipient_uri"))
            if r_name or r_uri:
                r_proj, r_kind, r_exact = resolve_project_uri(r_name or r_uri, r_uri, "person", exact_to_project)
                w_triples.append((P["recipient"], r_proj, True))
                if r_kind == "org":
                    upsert(discovered_orgs, r_proj, label=(r_name or None), exact=r_exact)
                else:
                    upsert(discovered_persons, r_proj, label=(r_name or None), exact=r_exact)

            # place of writing
            pl_label = normalize_ws(row.get("place_label"))
            pl_uri = uri_or_none(row.get("place_uri"))
            if pl_label or pl_uri:
                pl_proj, _, pl_exact = resolve_project_uri(pl_label or pl_uri, pl_uri, "place", exact_to_project)
                w_triples.append((P["spatial"], pl_proj, True))
                upsert(discovered_places, pl_proj, label=(pl_label or None), exact=pl_exact)

            # ---- Mentions as SAN EntityReference (instead of vd:mentions*) ----
            ref_counter = 0

            def add_entity_reference(kind: str, label: str, uri: str, kind_hint: str):
                nonlocal ref_counter
                ref_counter += 1

                proj, resolved_kind, ex = resolve_project_uri(label or uri, uri, kind_hint, exact_to_project)

                # Ensure target entity exists in stores (as before)
                if resolved_kind == "org":
                    upsert(discovered_orgs, proj, label=(label or None), alt=None, exact=ex)
                elif resolved_kind == "place":
                    upsert(discovered_places, proj, label=(label or None), alt=None, exact=ex)
                elif resolved_kind == "event":
                    upsert(discovered_events, proj, label=(label or None), alt=None, exact=ex)
                else:
                    upsert(discovered_persons, proj, label=(label or None), alt=None, exact=ex)

                target_slug = slugify(label or proj)
                er_uri = entityref_uri(cv_id, kind, target_slug, ref_counter)

                er_triples = [
                    ("rdf:type", "san:EntityReference", True),
                    ("san:refersTo", proj, True),
                ]
                if label:
                    er_triples.append(("rdfs:label", label, False))

                entityref_triples_list.append((er_uri, er_triples))

                # Link the TextChunk to the EntityReference (as in your LetterModel)
                chunk_link_triples.append(("san:refersTo", er_uri, True))


            # We collect chunk links here and then append them to the chunk node already created
            chunk_link_triples = []

            for mp in parse_compound_field(row.get("mentioned_people") or ""):
                add_entity_reference("person", mp["label"], mp["uri"], "person")

            for pl in parse_compound_field(row.get("mentioned_places") or ""):
                add_entity_reference("place", pl["label"], pl["uri"], "place")

            for og in parse_compound_field(row.get("mentioned_orgs") or ""):
                add_entity_reference("org", og["label"], og["uri"], "org")

            for ev in parse_compound_field(row.get("mentioned_events") or ""):
                add_entity_reference("event", ev["label"], ev["uri"], "event")

            # Append the san:refersTo links to the existing chunk triples (same subject URI)
            if chunk_link_triples:
                textchunk_triples_list[-1] = (chunk_uri, chunk_triples + chunk_link_triples)

            works_triples.append((work_uri, w_triples))

            # ---- Expression ----
            e_triples = [
                ("rdf:type", "fabio:Expression", True),
                ("rdf:type", "frbr:Expression", True),
                (P["embodiment"], man_uri, True),
                (P["embodiment"], prt_uri, True),
                (P["embodiment"], dig_uri, True),
            ]
            
            e_triples.append(("doco:contains", chunk_uri, True))

            # ✅ Expression -> pro:isRelatedToRoleInTime (aligns with your LetterModel)
            involved = set()
            for pred, obj, is_uri in w_triples:
                if is_uri and pred in (P["creator"], P["recipient"], P["mentionsPerson"]):
                    involved.add(obj)
            for p_u in sorted(involved):
                for rit in sorted(person_roles_index.get(p_u, set())):
                    e_triples.append((P["isRelatedToRoleInTime"], rit, True))

            expr_triples_list.append((expr_uri, e_triples))

            # ---- Manifestations ----
            mani_triples_list.append((man_uri, [
                ("rdf:type", "fabio:AnalogManifestation", True),
                ("rdf:type", "frbr:Manifestation", True),
            ]))

            prt_mani = [
                ("rdf:type", "fabio:AnalogManifestation", True),
                ("rdf:type", "frbr:Manifestation", True),
                (P["exemplar"], ex_uri, True),
            ]
            if pub_agent_uri:
                prt_mani.append((P["publisher"], pub_agent_uri, True))
            if pubyear:
                prt_mani.append((P["date"], pubyear, False))
            mani_triples_list.append((prt_uri, prt_mani))

            dig_mani = [
                ("rdf:type", "fabio:DigitalManifestation", True),
                ("rdf:type", "frbr:Manifestation", True),
                (P["rights"], f"{BASE}rights/digital", True),     
                ("prov:wasGeneratedBy", act_uri, True),           
            ]
            if text_file:
                dig_mani.append((P["source"], text_file, False))
            mani_triples_list.append((dig_uri, dig_mani))

            # ---- Exemplar (frbr:Item) ----
            ex_triples = [
                ("rdf:type", "frbr:Item", True),
                (P["identifier"], cv_id, False),
                ("frbr:exemplarOf", prt_uri, True),
            ]
            if vol:
                ex_triples.append(("bibo:volume", vol, False))
            if pg_from:
                ex_triples.append(("bibo:pageStart", pg_from, False))
            if pg_to:
                ex_triples.append(("bibo:pageEnd", pg_to, False))
            exemplar_triples_list.append((ex_uri, ex_triples))

    # merge discovered entities into main stores
    for u, rec in discovered_persons.items():
        upsert(persons, u, label=rec["label"])
        for a in rec["altLabels"]:
            upsert(persons, u, alt=a)
        for ex in rec["exactMatches"]:
            upsert(persons, u, exact=ex)

    for u, rec in discovered_orgs.items():
        upsert(orgs, u, label=rec["label"])
        for a in rec["altLabels"]:
            upsert(orgs, u, alt=a)
        for ex in rec["exactMatches"]:
            upsert(orgs, u, exact=ex)

    for u, rec in discovered_places.items():
        upsert(places, u, label=rec["label"])
        for a in rec["altLabels"]:
            upsert(places, u, alt=a)
        for ex in rec["exactMatches"]:
            upsert(places, u, exact=ex)

    for u, rec in discovered_events.items():
        upsert(events, u, label=rec["label"])
        for ex in rec["exactMatches"]:
            upsert(events, u, exact=ex)

    rel_triples = build_relations(id_to_project, exact_to_project)

    os.makedirs(os.path.dirname(OUT_TTL), exist_ok=True)
    with open(OUT_TTL, "w", encoding="utf-8") as out:
        write_prefixes(out)

        emit_triples(out, KB_COLLECTION, [
            ("rdf:type", "fabio:WorkCollection", True),
            ("rdfs:label", "Coleção Varela", False),
        ])

        emit_triples(out, KB_EDITION, [
            ("rdf:type", "fabio:DigitalEdition", True),
            ("rdfs:label", "Varela Digital — Edição digital da Coleção Varela", False),
            (P["isVersionOf"], KB_COLLECTION, True),
        ])
        
        for subj, triples in sorted(hico_triples_list, key=lambda x: x[0]):
            emit_triples(out, subj, triples)

        for subj, triples in sorted(works_triples, key=lambda x: x[0]):
            emit_triples(out, subj, triples)

        # Text chunks
        for subj, triples in sorted(textchunk_triples_list, key=lambda x: x[0]):
            emit_triples(out, subj, triples)

        # Entity references
        for subj, triples in sorted(entityref_triples_list, key=lambda x: x[0]):
            emit_triples(out, subj, triples)
        
        for subj, triples in sorted(expr_triples_list, key=lambda x: x[0]):
            emit_triples(out, subj, triples)

        for subj, triples in sorted(mani_triples_list, key=lambda x: x[0]):
            emit_triples(out, subj, triples)

        for subj, triples in sorted(exemplar_triples_list, key=lambda x: x[0]):
            emit_triples(out, subj, triples)

        # places
        for uri in sorted(places.keys()):
            rec = places[uri]
            triples = [("rdf:type", T["Place"], True)]
            if rec.get("label"):
                triples.append(("rdfs:label", rec["label"], False))
            for alt in sorted(rec.get("altLabels", [])):
                triples.append((P["altLabel"], alt, False))
            for ex in sorted(rec.get("exactMatches", [])):
                triples.append((P["exactMatch"], ex, True))
            emit_triples(out, uri, triples)

        # events
        for uri in sorted(events.keys()):
            rec = events[uri]
            triples = [("rdf:type", T["Event"], True)]
            if rec.get("label"):
                triples.append(("rdfs:label", rec["label"], False))
            for ex in sorted(rec.get("exactMatches", [])):
                triples.append((P["exactMatch"], ex, True))
            emit_triples(out, uri, triples)

        # persons (NO LONGER emitting pro:isRelatedToRoleInTime here; it is on Expression now)
        for uri in sorted(persons.keys()):
            rec = persons[uri]
            triples = [("rdf:type", T["Person"], True)]
            if rec.get("label"):
                triples.append(("rdfs:label", rec["label"], False))
            for alt in sorted(rec.get("altLabels", [])):
                triples.append((P["altLabel"], alt, False))
            for ex in sorted(rec.get("exactMatches", [])):
                triples.append((P["exactMatch"], ex, True))
            emit_triples(out, uri, triples)

        # orgs
        for uri in sorted(orgs.keys()):
            rec = orgs[uri]
            triples = [("rdf:type", T["Org"], True)]
            if rec.get("label"):
                triples.append(("rdfs:label", rec["label"], False))
            for alt in sorted(rec.get("altLabels", [])):
                triples.append((P["altLabel"], alt, False))
            for ex in sorted(rec.get("exactMatches", [])):
                triples.append((P["exactMatch"], ex, True))
            emit_triples(out, uri, triples)

        # org hierarchy
        for child, parent in org_affiliations:
            emit_triples(out, child, [(P["subOrgOf"], parent, True)])

        # relations from standoff_relations.xml
        for s, p, o in rel_triples:
            emit_triples(out, s, [(p, o, True)])

        # roles
        for ruri in sorted(role_nodes.keys()):
            emit_triples(out, ruri, [
                ("rdf:type", T["Role"], True),
                ("rdfs:label", role_nodes[ruri], False),
            ])

        # role in time
        for rit_uri, triples in role_in_time:
            emit_triples(out, rit_uri, triples)

    print(f"OK: generated {OUT_TTL}")


if __name__ == "__main__":
    main()