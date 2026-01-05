"""
Varela Digital — TEI + Standoff -> RDF (v0.2+)

Adds (requested):
1) Read standoff persons/orgs/events/places to build an entity index,
   applying the rule "places = GeoNames URI as primary" when available.
2) Generate a metadata CSV automatically from TEI files, including:
   - duplicates (e.g., CV-16) via <listRelation>/<relation name="dcterms:isVersionOf">
   - non-letter document types (e.g., CV-179) via <div @type>

RDF v0.2 principle:
- TEI + standoff XML remain authoritative.
- RDF is a controlled projection.
- Relations can be:
  (a) explicit in standoff_relations.xml
  (b) inferred from TEI <correspDesc>
  (c) derived from role/affiliation in standoff persons/orgs (hook included)

USAGE (RDF):
  python tei_to_rdf_v02_plus.py rdf \
    --tei CV-10.xml --doc-id CV-10 --out CV-10.ttl \
    --standoff-relations standoff_relations.xml \
    --standoff-persons standoff_persons.xml \
    --standoff-orgs standoff_orgs.xml \
    --standoff-places standoff_places.xml \
    --standoff-events standoff_events.xml \
    --base "https://carlamenegat.github.io/VarelaDigital/resource/" \
    --hrao "https://carlamenegat.github.io/VarelaDigital/hrao#"

USAGE (CSV):
  python tei_to_rdf_v02_plus.py csv \
    --tei-dir ../../data/documents_XML \
    --out-csv ../../data/metadata_letters_auto.csv \
    --standoff-places ../../data/standoff/standoff_places.xml \
    --base "https://carlamenegat.github.io/VarelaDigital/resource/"
"""

from __future__ import annotations

import argparse
import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Iterable, Tuple, List

from lxml import etree
from rdflib import Graph, Namespace, URIRef, Literal
from rdflib.namespace import RDF, RDFS, XSD, DCTERMS


# -------------------------
# Namespaces (default)
# -------------------------

FABIO = Namespace("http://purl.org/spar/fabio/")
FOAF = Namespace("http://xmlns.com/foaf/0.1/")
PRO = Namespace("http://purl.org/spar/pro/")
FRBR = Namespace("http://purl.org/vocab/frbr/core#")
DOCO = Namespace("http://purl.org/spar/doco/")
C4O = Namespace("http://purl.org/spar/c4o/")
SAN = Namespace("http://www.ontologydesignpatterns.org/cp/owl/semanticannotation.owl#")
PROV = Namespace("http://www.w3.org/ns/prov#")
REL = Namespace("http://purl.org/vocab/relationship/")
GEO = Namespace("http://www.w3.org/2003/01/geo/wgs84_pos#")
TIME = Namespace("http://www.w3.org/2006/time#")
HICO = Namespace("http://purl.org/emmedi/hico/")

TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}
XML_NS = "http://www.w3.org/XML/1998/namespace"


# -------------------------
# Bundles / Index
# -------------------------

@dataclass
class NSBundle:
    base: Namespace
    hrao: Namespace

    @property
    def prefix_map(self) -> Dict[str, Namespace]:
        # Extend when you introduce new prefixes in standoff_relations
        return {
            "base": self.base,
            "fabio": FABIO,
            "foaf": FOAF,
            "pro": PRO,
            "frbr": FRBR,
            "doco": DOCO,
            "c4o": C4O,
            "san": SAN,
            "prov": PROV,
            "rel": REL,
            "geo": GEO,
            "time": TIME,
            "hico": HICO,
            "hrao": self.hrao,
            "dcterms": DCTERMS,
            "rdfs": RDFS,
            "xsd": XSD,
        }


@dataclass
class EntityIndex:
    """
    Maps TEI/standoff xml:ids to their primary URIs.
    Key rule requested:
      - places: if <idno type="geonames"> exists, use it as PRIMARY URI
      - persons/orgs/events: default to project-minted base URI (unless you later
        decide to make external IDs primary; currently you said external IDs are alignments)
    """
    persons: Dict[str, URIRef]
    orgs: Dict[str, URIRef]
    events: Dict[str, URIRef]
    places: Dict[str, URIRef]

    def uri_for_id(self, xml_id: str, nsb: NSBundle) -> URIRef:
        if xml_id in self.places:
            return self.places[xml_id]
        if xml_id in self.persons:
            return self.persons[xml_id]
        if xml_id in self.orgs:
            return self.orgs[xml_id]
        if xml_id in self.events:
            return self.events[xml_id]
        # fallback: mint in project namespace
        return nsb.base[xml_id]


# -------------------------
# XML helpers
# -------------------------

def parse_xml_root(path: Path) -> etree._Element:
    return etree.parse(str(path)).getroot()


def get_xml_id(el: etree._Element) -> Optional[str]:
    return el.get(f"{{{XML_NS}}}id")


def text_or_none(el: Optional[etree._Element]) -> Optional[str]:
    if el is None:
        return None
    t = " ".join(el.itertext()).strip()
    return t or None


# -------------------------
# Entity standoff parsing
# -------------------------

def build_entity_index(
    nsb: NSBundle,
    standoff_persons: Optional[Path] = None,
    standoff_orgs: Optional[Path] = None,
    standoff_places: Optional[Path] = None,
    standoff_events: Optional[Path] = None,
) -> EntityIndex:
    persons: Dict[str, URIRef] = {}
    orgs: Dict[str, URIRef] = {}
    places: Dict[str, URIRef] = {}
    events: Dict[str, URIRef] = {}

    def ingest_people(path: Path) -> None:
        root = parse_xml_root(path)
        for p in root.xpath(".//tei:person", namespaces=TEI_NS):
            pid = get_xml_id(p)
            if not pid:
                continue
            persons[pid] = nsb.base[pid]

    def ingest_orgs(path: Path) -> None:
        root = parse_xml_root(path)
        for o in root.xpath(".//tei:org", namespaces=TEI_NS):
            oid = get_xml_id(o)
            if not oid:
                continue
            orgs[oid] = nsb.base[oid]

    def ingest_places(path: Path) -> None:
        root = parse_xml_root(path)
        for pl in root.xpath(".//tei:place", namespaces=TEI_NS):
            plid = get_xml_id(pl)
            if not plid:
                continue

            # Rule: GeoNames as primary, if present
            geon = pl.xpath("./tei:idno[@type='geonames'][1]", namespaces=TEI_NS)
            if geon:
                uri_txt = text_or_none(geon[0])
                if uri_txt:
                    places[plid] = URIRef(uri_txt)
                    continue

            # fallback: project-minted
            places[plid] = nsb.base[plid]

    def ingest_events(path: Path) -> None:
        root = parse_xml_root(path)
        for ev in root.xpath(".//tei:event", namespaces=TEI_NS):
            evid = get_xml_id(ev)
            if not evid:
                continue
            events[evid] = nsb.base[evid]

    if standoff_persons and standoff_persons.exists():
        ingest_people(standoff_persons)
    if standoff_orgs and standoff_orgs.exists():
        ingest_orgs(standoff_orgs)
    if standoff_places and standoff_places.exists():
        ingest_places(standoff_places)
    if standoff_events and standoff_events.exists():
        ingest_events(standoff_events)

    return EntityIndex(persons=persons, orgs=orgs, events=events, places=places)


# -------------------------
# URI helpers (now index-aware)
# -------------------------

def uri_from_ref(ref: str, nsb: NSBundle, idx: Optional[EntityIndex] = None) -> URIRef:
    """
    Converts TEI-style '#id' or 'id' to a URIRef.
    If an EntityIndex is provided, it is used FIRST (especially for places→GeoNames).
    """
    rid = ref.lstrip("#").strip()
    if not rid:
        return nsb.base["UNRESOLVED"]
    if idx is not None:
        return idx.uri_for_id(rid, nsb)
    return nsb.base[rid]


def uri_from_qname(qname: str, nsb: NSBundle) -> URIRef:
    """Converts 'prefix:local' into a full URIRef using known namespaces."""
    if ":" not in qname:
        return nsb.base[qname]
    prefix, local = qname.split(":", 1)
    ns = nsb.prefix_map.get(prefix)
    if ns is None:
        raise ValueError(f"Unknown prefix in relation name: {qname}")
    return ns[local]


def mint_statement_uri(s: URIRef, p: URIRef, o: URIRef, source: URIRef, method: str, nsb: NSBundle) -> URIRef:
    key = "|".join([str(s), str(p), str(o), str(source), method]).encode("utf-8")
    h = hashlib.sha256(key).hexdigest()[:16]
    return nsb.base[f"assertion/{h}"]


# -------------------------
# RDF assertion + provenance
# -------------------------

def add_triple_with_provenance(
    g: Graph,
    s: URIRef,
    p: URIRef,
    o: URIRef,
    *,
    source: URIRef,
    method: str,
    certainty: str = "high",
    interpretation_type: Optional[str] = None,
    nsb: NSBundle,
) -> None:
    """
    Adds:
      s p o .
    And reifies with rdf:Statement + basic PROV/HiCO hooks.
    """
    g.add((s, p, o))

    stmt = mint_statement_uri(s, p, o, source, method, nsb)
    g.add((stmt, RDF.type, RDF.Statement))
    g.add((stmt, RDF.subject, s))
    g.add((stmt, RDF.predicate, p))
    g.add((stmt, RDF.object, o))

    g.add((stmt, PROV.wasDerivedFrom, source))
    g.add((stmt, HICO.hasCertainty, Literal(certainty)))

    # store method tag as literal (simple + robust)
    g.add((stmt, DCTERMS.description, Literal(f"Method: {method}")))

    if interpretation_type:
        g.add((stmt, HICO.hasInterpretationType, Literal(interpretation_type)))


# -------------------------
# Relation extraction (standoff_relations.xml)
# -------------------------

def iter_standoff_relations(standoff_relations: Path) -> Iterable[etree._Element]:
    root = parse_xml_root(standoff_relations)
    # Typical TEI standoff: <standOff><listRelation>...<relation .../></listRelation></standOff>
    rels = root.xpath(".//tei:relation", namespaces=TEI_NS)
    for r in rels:
        yield r


def map_explicit_relations(
    g: Graph,
    standoff_relations: Path,
    *,
    doc_uri: URIRef,
    nsb: NSBundle,
    idx: Optional[EntityIndex] = None,
) -> None:
    """
    Maps <relation name="prefix:prop" active="#a" passive="#b"/> to RDF.
    """
    for rel in iter_standoff_relations(standoff_relations):
        name = rel.get("name")
        active = rel.get("active")
        passive = rel.get("passive")
        mutual = rel.get("mutual")

        if not name or not active or not passive:
            continue

        p = uri_from_qname(name, nsb)
        s = uri_from_ref(active, nsb, idx)
        o = uri_from_ref(passive, nsb, idx)

        # asserted relation
        add_triple_with_provenance(
            g, s, p, o,
            source=doc_uri,
            method="standoff_relations:explicit",
            certainty="high",
            interpretation_type="relation_assertion",
            nsb=nsb
        )

        # if mutual="true", also add inverse
        if mutual and mutual.strip().lower() == "true":
            add_triple_with_provenance(
                g, o, p, s,
                source=doc_uri,
                method="standoff_relations:explicit_mutual",
                certainty="high",
                interpretation_type="relation_assertion",
                nsb=nsb
            )


# -------------------------
# TEI parsing for correspondence metadata (correspDesc)
# -------------------------

def extract_corresp_agents(root: etree._Element) -> Tuple[List[str], List[str]]:
    """
    Returns (senders, addressees) as list of @ref values (e.g., '#domingos_jose_almeida').
    """
    senders = []
    addressees = []

    # correspDesc is in teiHeader/profileDesc
    # example:
    # <correspDesc>
    #   <correspAction type="sent"><persName ref="#x"/></correspAction>
    #   <correspAction type="received"><persName ref="#y"/></correspAction>
    # </correspDesc>
    for act in root.xpath(".//tei:correspDesc//tei:correspAction", namespaces=TEI_NS):
        act_type = (act.get("type") or "").strip().lower()

        # prefer persName/orgName refs
        refs = act.xpath(".//tei:persName/@ref | .//tei:orgName/@ref", namespaces=TEI_NS)
        refs = [r for r in refs if r]

        if act_type == "sent":
            senders.extend(refs)
        elif act_type == "received":
            addressees.extend(refs)

    return (senders, addressees)


def map_document_based_relations(
    g: Graph,
    tei_root: etree._Element,
    *,
    doc_uri: URIRef,
    nsb: NSBundle,
    idx: Optional[EntityIndex] = None,
) -> None:
    """
    Derives sender/addressee relations from TEI <correspDesc>.
    Minimal, evidence-based.
    """
    senders, addressees = extract_corresp_agents(tei_root)
    if not senders and not addressees:
        return

    # Document node as fabio:Letter or fabio:Work (simplified)
    g.add((doc_uri, RDF.type, FABIO.Letter))

    # Use PROV/FOAF-ish communication predicates:
    # - prov:wasAttributedTo for sender (agent → doc)
    # - dcterms:relation or FOAF-based links are options
    # Here we keep it simple and explicit:
    for sref in senders:
        s_uri = uri_from_ref(sref, nsb, idx)
        add_triple_with_provenance(
            g, doc_uri, PROV.wasAttributedTo, s_uri,
            source=doc_uri,
            method="tei_correspDesc:sender",
            certainty="high",
            interpretation_type="document_structure",
            nsb=nsb
        )

    for aref in addressees:
        a_uri = uri_from_ref(aref, nsb, idx)
        add_triple_with_provenance(
            g, doc_uri, DCTERMS.relation, a_uri,
            source=doc_uri,
            method="tei_correspDesc:addressee",
            certainty="high",
            interpretation_type="document_structure",
            nsb=nsb
        )


# -------------------------
# MAIN RDF builder
# -------------------------

def build_graph(
    tei_path: Path,
    doc_id: str,
    *,
    nsb: NSBundle,
    standoff_relations: Optional[Path] = None,
    idx: Optional[EntityIndex] = None,
) -> Graph:
    g = Graph()

    # Bind prefixes
    for pfx, ns in nsb.prefix_map.items():
        g.bind(pfx, ns)

    tei_root = parse_xml_root(tei_path)

    doc_uri = nsb.base[doc_id]
    g.add((doc_uri, RDF.type, FABIO.Letter))
    g.add((doc_uri, RDFS.label, Literal(doc_id)))

    # TEI-based relations (sender/addressee)
    map_document_based_relations(g, tei_root, doc_uri=doc_uri, nsb=nsb, idx=idx)

    # Explicit standoff relations
    if standoff_relations and standoff_relations.exists():
        map_explicit_relations(g, standoff_relations, doc_uri=doc_uri, nsb=nsb, idx=idx)

    # Hook: role-derived relations could be added later using idx + standoff persons/orgs
    # (You already described this as a source of structural relations in 4.4.6.)
    return g


# -------------------------
# CSV metadata generator
# -------------------------

def first_div_type(root: etree._Element) -> Optional[str]:
    div = root.xpath(".//tei:text//tei:div[1]", namespaces=TEI_NS)
    if not div:
        return None
    return div[0].get("type")


def extract_title(root: etree._Element) -> Optional[str]:
    t = root.xpath(".//tei:teiHeader//tei:fileDesc//tei:titleStmt//tei:title[1]", namespaces=TEI_NS)
    return text_or_none(t[0]) if t else None


def extract_creation_date_when(root: etree._Element) -> Optional[str]:
    # <creation><date when="1835-01-01">...</date>
    d = root.xpath(".//tei:teiHeader//tei:profileDesc//tei:creation//tei:date[1]", namespaces=TEI_NS)
    if not d:
        return None
    when = d[0].get("when")
    return when or text_or_none(d[0])


def extract_creation_place_ref(root: etree._Element) -> Optional[str]:
    pl = root.xpath(".//tei:teiHeader//tei:profileDesc//tei:creation//tei:placeName[1]", namespaces=TEI_NS)
    if not pl:
        return None
    return pl[0].get("ref") or text_or_none(pl[0])


def extract_extent_pages(root: etree._Element) -> Optional[str]:
    m = root.xpath(".//tei:teiHeader//tei:fileDesc//tei:extent//tei:measure[1]", namespaces=TEI_NS)
    return text_or_none(m[0]) if m else None


def extract_duplicate_of(root: etree._Element) -> Optional[str]:
    """
    Detect duplicates like CV-16 via:
      <listRelation>
        <relation name="dcterms:isVersionOf" active="#CV-16" passive="#CV-12"/>
      </listRelation>
    Returns passive id (without '#') if found.
    """
    rel = root.xpath(".//tei:listRelation//tei:relation[contains(@name,'isVersionOf')][1]", namespaces=TEI_NS)
    if not rel:
        return None
    passive = rel[0].get("passive")
    if not passive:
        return None
    return passive.lstrip("#").strip() or None


def extract_sender_addressee_ids(root: etree._Element) -> Tuple[str, str]:
    senders, addressees = extract_corresp_agents(root)
    s = ";".join([x.lstrip("#") for x in senders]) if senders else ""
    a = ";".join([x.lstrip("#") for x in addressees]) if addressees else ""
    return s, a


def generate_metadata_csv(
    tei_dir: Path,
    out_csv: Path,
    *,
    nsb: NSBundle,
    idx: Optional[EntityIndex] = None,
) -> None:
    tei_files = sorted([p for p in tei_dir.glob("*.xml") if p.is_file()])
    if not tei_files:
        raise FileNotFoundError(f"No TEI XML files found in: {tei_dir}")

    fieldnames = [
        "cv_id",
        "project_uri",
        "doc_type",
        "is_letter",
        "title",
        "date_when",
        "place_ref",
        "place_uri_primary",
        "sender_ids",
        "addressee_ids",
        "extent",
        "duplicate_of",
        "source_file",
    ]

    with out_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()

        for tei_path in tei_files:
            root = parse_xml_root(tei_path)

            # prefer TEI xml:id in <div type="..."> if present; fallback to filename stem
            div = root.xpath(".//tei:text//tei:div[1]", namespaces=TEI_NS)
            cv_id = None
            if div:
                cv_id = get_xml_id(div[0])
            if not cv_id:
                cv_id = tei_path.stem  # e.g., CV-179

            doc_type = first_div_type(root) or ""
            is_letter = "true" if doc_type == "letter" else "false"

            title = extract_title(root) or ""
            date_when = extract_creation_date_when(root) or ""
            place_ref = extract_creation_place_ref(root) or ""

            place_uri_primary = ""
            if place_ref:
                pu = uri_from_ref(place_ref, nsb, idx)
                place_uri_primary = str(pu)

            sender_ids, addressee_ids = extract_sender_addressee_ids(root)
            extent = extract_extent_pages(root) or ""
            duplicate_of = extract_duplicate_of(root) or ""

            w.writerow({
                "cv_id": cv_id,
                "project_uri": str(nsb.base[cv_id]),
                "doc_type": doc_type,
                "is_letter": is_letter,
                "title": title,
                "date_when": date_when,
                "place_ref": place_ref,
                "place_uri_primary": place_uri_primary,
                "sender_ids": sender_ids,
                "addressee_ids": addressee_ids,
                "extent": extent,
                "duplicate_of": duplicate_of,
                "source_file": tei_path.name,
            })


# -------------------------
# CLI
# -------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Varela Digital — TEI/standoff -> RDF (v0.2+) and CSV metadata generator")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # RDF subcommand
    p_rdf = sub.add_parser("rdf", help="Generate RDF (TTL) from one TEI document + standoff relations")
    p_rdf.add_argument("--tei", required=True, type=Path, help="Path to TEI XML (single document)")
    p_rdf.add_argument("--doc-id", required=True, help="Document id used for the doc URI (e.g., CV-10)")
    p_rdf.add_argument("--out", required=True, type=Path, help="Output .ttl path")
    p_rdf.add_argument("--standoff-relations", type=Path, help="standoff_relations.xml")
    p_rdf.add_argument("--standoff-persons", type=Path, help="standoff_persons.xml (optional, for indexing URIs)")
    p_rdf.add_argument("--standoff-orgs", type=Path, help="standoff_orgs.xml (optional, for indexing URIs)")
    p_rdf.add_argument("--standoff-places", type=Path, help="standoff_places.xml (optional, for GeoNames primary URIs)")
    p_rdf.add_argument("--standoff-events", type=Path, help="standoff_events.xml (optional, for indexing URIs)")
    p_rdf.add_argument("--base", required=True, help="Base namespace for project resources")
    p_rdf.add_argument("--hrao", required=True, help="HRAO namespace")

    # CSV subcommand
    p_csv = sub.add_parser("csv", help="Generate metadata CSV from a directory of TEI documents")
    p_csv.add_argument("--tei-dir", required=True, type=Path, help="Directory containing TEI XML files")
    p_csv.add_argument("--out-csv", required=True, type=Path, help="Output CSV path")
    p_csv.add_argument("--standoff-places", type=Path, help="standoff_places.xml (optional, for GeoNames primary URIs)")
    p_csv.add_argument("--base", required=True, help="Base namespace for project resources")

    args = parser.parse_args()

    if args.cmd == "rdf":
        nsb = NSBundle(base=Namespace(args.base), hrao=Namespace(args.hrao))
        idx = build_entity_index(
            nsb,
            standoff_persons=args.standoff_persons,
            standoff_orgs=args.standoff_orgs,
            standoff_places=args.standoff_places,
            standoff_events=args.standoff_events,
        )
        g = build_graph(
            args.tei,
            args.doc_id,
            nsb=nsb,
            standoff_relations=args.standoff_relations,
            idx=idx
        )
        args.out.parent.mkdir(parents=True, exist_ok=True)
        g.serialize(destination=str(args.out), format="turtle")
        print(f"[✔] RDF written to: {args.out}")

    elif args.cmd == "csv":
        nsb = NSBundle(base=Namespace(args.base), hrao=Namespace(args.base + "hrao#"))  # not used in CSV
        idx = build_entity_index(nsb, standoff_places=args.standoff_places) if args.standoff_places else None
        args.out_csv.parent.mkdir(parents=True, exist_ok=True)
        generate_metadata_csv(args.tei_dir, args.out_csv, nsb=nsb, idx=idx)
        print(f"[✔] CSV written to: {args.out_csv}")


if __name__ == "__main__":
    main()