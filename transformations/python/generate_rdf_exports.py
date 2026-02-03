#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

from lxml import etree
from rdflib import Graph, Namespace, URIRef, Literal
from rdflib.namespace import RDF, RDFS, DCTERMS, XSD, FOAF


TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}

# ---- Paths ----
# script location: transformations/python/generate_rdf_exports.py
# repo root:       (python -> transformations -> repo) = parents[2]
REPO_ROOT = Path(__file__).resolve().parents[2]

TEI_DIR = REPO_ROOT / "letters_data" / "documents_XML"
CSV_PATH = REPO_ROOT / "letters_data" / "metadata" / "metadata_all.csv"

OUT_JSON_DIR = REPO_ROOT / "assets" / "data" / "rdf" / "json"
OUT_TTL_DIR = REPO_ROOT / "assets" / "data" / "rdf" / "ttl"

OUT_JSON_DIR.mkdir(parents=True, exist_ok=True)
OUT_TTL_DIR.mkdir(parents=True, exist_ok=True)

# ---- Project base URIs ----
BASE_WEB = "https://carlamenegat.github.io/VarelaDigital/"
VD = Namespace(BASE_WEB)
HRAO = Namespace(BASE_WEB + "hrao#")  # se você usa hrao como base no site


def norm(s: Optional[str]) -> str:
    return (s or "").strip()


def add_date_literal(g: Graph, subj: URIRef, prop: URIRef, date_str: str) -> None:
    """
    Add a date literal using the most appropriate XSD datatype:
      - YYYY       -> xsd:gYear
      - YYYY-MM    -> xsd:gYearMonth
      - YYYY-MM-DD -> xsd:date
    Any other form (including unknowns like 1842-01-??) is stored as plain literal.
    """
    s = norm(date_str)
    if not s:
        return

    if re.fullmatch(r"\d{4}", s):
        g.add((subj, prop, Literal(s, datatype=XSD.gYear)))
        return

    if re.fullmatch(r"\d{4}-\d{2}", s):
        g.add((subj, prop, Literal(s, datatype=XSD.gYearMonth)))
        return

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        g.add((subj, prop, Literal(s, datatype=XSD.date)))
        return

    # Fallback for partial/unknown or free text
    g.add((subj, prop, Literal(s)))


def load_metadata_csv(path: Path) -> Dict[str, Dict[str, Any]]:
    idx: Dict[str, Dict[str, Any]] = {}
    if not path.exists():
        return idx

    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cv_id = norm(
                row.get("cv_id")
                or row.get("id")
                or row.get("file")
                or row.get("text_file")
            )
            if not cv_id:
                continue

            # normaliza: CV-10 / CV-10.xml
            cv_id = cv_id.replace(".xml", "").strip()

            if not cv_id.upper().startswith("CV-"):
                # se por acaso vier só número
                if cv_id.isdigit():
                    cv_id = f"CV-{int(cv_id)}"

            cv_id = cv_id.replace("cv-", "CV-")
            idx[cv_id] = row

    return idx


def tei_extract_doc_type(tei_path: Path, stem: str) -> str:
    """
    Extrai o @type do <div type="..."> no body.
    Você comentou: <div type="letter" xml:id="CV-1">
    """
    try:
        xml = etree.parse(str(tei_path))
    except Exception:
        return ""

    # 1) tenta casar pelo xml:id
    xp1 = f'//tei:text//tei:body//tei:div[@xml:id="{stem}"]/@type'
    res = xml.xpath(xp1, namespaces=TEI_NS)
    if res:
        return norm(res[0])

    # 2) tenta uppercase
    xp2 = f'//tei:text//tei:body//tei:div[@xml:id="{stem.upper()}"]/@type'
    res = xml.xpath(xp2, namespaces=TEI_NS)
    if res:
        return norm(res[0])

    # 3) fallback: primeiro div com @type
    xp3 = '//tei:text//tei:body//tei:div[@type][1]/@type'
    res = xml.xpath(xp3, namespaces=TEI_NS)
    if res:
        return norm(res[0])

    return ""


def tei_extract_title_date_place(tei_path: Path) -> Tuple[str, str, str]:
    """
    Fallback leve (se faltar algo no CSV). Tenta pegar title/date/place do TEI header.
    Se não achar, retorna strings vazias.
    """
    try:
        xml = etree.parse(str(tei_path))
    except Exception:
        return ("", "", "")

    # title
    title = norm(
        xml.xpath(
            "string(//tei:teiHeader//tei:titleStmt//tei:title[1])",
            namespaces=TEI_NS,
        )
    )

    # date (tenta profileDesc/correspDesc e depois creation)
    date = norm(
        xml.xpath(
            "string(//tei:teiHeader//tei:profileDesc//tei:correspDesc//tei:date[1]/@when)",
            namespaces=TEI_NS,
        )
    )
    if not date:
        date = norm(
            xml.xpath(
                "string(//tei:teiHeader//tei:profileDesc//tei:creation//tei:date[1]/@when)",
                namespaces=TEI_NS,
            )
        )

    # place
    place = norm(
        xml.xpath(
            "string(//tei:teiHeader//tei:profileDesc//tei:correspDesc//tei:placeName[1])",
            namespaces=TEI_NS,
        )
    )

    return (title, date, place)


def build_graph(stem: str, tei_path: Path, meta: Dict[str, Any]) -> Graph:
    g = Graph()

    # Namespaces
    g.bind("vd", VD)
    g.bind("dcterms", DCTERMS)
    g.bind("foaf", FOAF)
    g.bind("rdfs", RDFS)
    g.bind("hrao", HRAO)

    doc_uri = URIRef(BASE_WEB + "doc/" + stem)  # sua escolha de endpoint
    xml_uri = URIRef(BASE_WEB + "letters_data/documents_XML/" + stem + ".xml")
    html_uri = URIRef(BASE_WEB + "assets/html/documents_html/" + stem + ".html")

    g.add((doc_uri, RDF.type, DCTERMS.BibliographicResource))
    g.add((doc_uri, DCTERMS.identifier, Literal(stem)))

    # título
    title = norm(meta.get("subject") or meta.get("title"))
    if not title:
        fallback_title, _, _ = tei_extract_title_date_place(tei_path)
        title = fallback_title
    if title:
        g.add((doc_uri, DCTERMS.title, Literal(title, lang="pt-BR")))

    # data (ISO / parcial / livre)
    date = norm(meta.get("date") or meta.get("when"))
    if not date:
        _, fallback_date, _ = tei_extract_title_date_place(tei_path)
        date = fallback_date
    add_date_literal(g, doc_uri, DCTERMS.date, date)

    # place
    place_label = norm(meta.get("place_label") or meta.get("place"))
    place_uri = norm(meta.get("place_uri"))
    if not place_label and not place_uri:
        _, _, fallback_place = tei_extract_title_date_place(tei_path)
        place_label = fallback_place

    if place_uri:
        place_node = URIRef(place_uri)
        g.add((doc_uri, DCTERMS.spatial, place_node))
        if place_label:
            g.add((place_node, RDFS.label, Literal(place_label, lang="pt-BR")))
    elif place_label:
        g.add((doc_uri, DCTERMS.spatial, Literal(place_label, lang="pt-BR")))

    # author
    author_name = norm(meta.get("author_name") or meta.get("from"))
    author_uri = norm(meta.get("author_uri"))
    if author_uri:
        a = URIRef(author_uri)
        g.add((doc_uri, DCTERMS.creator, a))
        if author_name:
            g.add((a, FOAF.name, Literal(author_name)))
    elif author_name:
        g.add((doc_uri, DCTERMS.creator, Literal(author_name)))

    # recipient
    recipient_name = norm(meta.get("recipient_name") or meta.get("to"))
    recipient_uri = norm(meta.get("recipient_uri"))
    if recipient_uri:
        r = URIRef(recipient_uri)
        g.add((doc_uri, DCTERMS.relation, r))  # genérico
        g.add((doc_uri, HRAO.addressedTo, r))  # propriedade do teu projeto (opcional)
        if recipient_name:
            g.add((r, FOAF.name, Literal(recipient_name)))
    elif recipient_name:
        g.add((doc_uri, HRAO.addressedTo, Literal(recipient_name)))

    # type (do TEI: <div type="letter"...>)
    dtype = tei_extract_doc_type(tei_path, stem)
    if dtype:
        g.add((doc_uri, DCTERMS.type, Literal(dtype)))

    # links de download / representação
    g.add((doc_uri, DCTERMS.hasFormat, xml_uri))
    g.add((doc_uri, DCTERMS.hasFormat, html_uri))
    g.add((xml_uri, RDF.type, DCTERMS.FileFormat))
    g.add((html_uri, RDF.type, DCTERMS.FileFormat))

    return g


def main() -> None:
    meta_idx = load_metadata_csv(CSV_PATH)

    tei_files = sorted(TEI_DIR.glob("CV-*.xml"))
    if not tei_files:
        raise SystemExit(f"Nenhum XML encontrado em {TEI_DIR}")

    for tei_path in tei_files:
        stem = tei_path.stem  # CV-10
        meta = meta_idx.get(stem, {})
        g = build_graph(stem, tei_path, meta)

        # TTL
        ttl_path = OUT_TTL_DIR / f"{stem}.ttl"
        g.serialize(destination=str(ttl_path), format="turtle")

        # JSON-LD
        json_path = OUT_JSON_DIR / f"{stem}.json"
        g.serialize(destination=str(json_path), format="json-ld", indent=2)

    print(
        f"OK: gerados {len(tei_files)} TTL em {OUT_TTL_DIR} e JSON-LD em {OUT_JSON_DIR}"
    )


if __name__ == "__main__":
    main()