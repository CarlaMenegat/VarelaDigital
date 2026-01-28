#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple

from rdflib import Graph, URIRef, Literal
from rdflib.namespace import RDF, OWL, RDFS, XSD


# -----------------------------
# Paths
# -----------------------------

BASE_DIR = Path("/Users/carlamenegat/Documents/GitHub/Untitled/VarelaDigital")

GRAPH_TTL = BASE_DIR / "assets/data/rdf/graph.ttl"

FROZEN_DIR = BASE_DIR / "data_models/ontology/extracted/vocab"
FROZEN_CLASSES = FROZEN_DIR / "classes_used.txt"
FROZEN_PROPS = FROZEN_DIR / "properties_used.txt"

OUT_TTL = BASE_DIR / "data_models/ontology/ttl/ontology.ttl"


# -----------------------------
# Ontology URI
# -----------------------------

ONTOLOGY_URI = URIRef("https://carlamenegat.github.io/VarelaDigital/ontology/ontology")


# -----------------------------
# Helpers
# -----------------------------

def require_file(p: Path) -> None:
    if not p.exists():
        raise FileNotFoundError(f"Required file not found:\n  {p}")


def load_terms(path: Path) -> List[str]:
    """
    One CURIE per line (e.g., fabio:Letter, san:refersTo, hrao:servedUnder).
    Ignores blanks and #-comments in the vocab files.
    Returns a stable sorted list.
    """
    terms: Set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        t = line.strip()
        if not t or t.startswith("#"):
            continue
        terms.add(t)
    return sorted(terms)


def build_ns_map(g: Graph) -> Dict[str, str]:
    """
    prefix -> namespace URI string
    """
    return {p: str(ns) for p, ns in g.namespace_manager.namespaces()}


def parse_curie(curie: str) -> Tuple[str, str]:
    curie = (curie or "").strip()
    if ":" not in curie:
        raise ValueError(f"Not a CURIE: {curie}")
    prefix, local = curie.split(":", 1)
    prefix = prefix.strip()
    local = local.strip()
    if not prefix or not local:
        raise ValueError(f"Malformed CURIE: {curie}")
    return prefix, local


def uri_for_curie(curie: str, ns_map: Dict[str, str]) -> URIRef:
    prefix, local = parse_curie(curie)
    if prefix not in ns_map:
        raise KeyError(prefix)
    return URIRef(ns_map[prefix] + local)


def used_prefixes(terms: Iterable[str]) -> Set[str]:
    out: Set[str] = set()
    for t in terms:
        if ":" in t:
            p, _ = t.split(":", 1)
            out.add(p.strip())
    return out


def infer_property_kind(g: Graph, prop_uri: URIRef) -> str:
    """
    Returns "object" or "datatype" based on observed objects in graph:
      - if any object is a Literal => datatype
      - else if any object is a URIRef/BNode => object
    If property never occurs in graph => default "object".
    If mixed => choose "object" (safer for LOD linking) but you can adjust.
    """
    saw_literal = False
    saw_resource = False

    for _s, _p, o in g.triples((None, prop_uri, None)):
        if isinstance(o, Literal):
            saw_literal = True
        else:
            saw_resource = True

        if saw_literal and saw_resource:
            # mixed usage
            return "object"

    if saw_literal and not saw_resource:
        return "datatype"
    if saw_resource and not saw_literal:
        return "object"

    # not found
    return "object"


def format_prefixes(prefix_map: Dict[str, str], prefixes_in_use: Set[str]) -> str:
    """
    Output prefix lines in a stable, readable order:
    owl, rdf, rdfs, xsd first; then others alphabetically.
    """
    mandatory = {
        "owl": str(OWL),
        "rdf": str(RDF),
        "rdfs": str(RDFS),
        "xsd": str(XSD),
    }

    lines: List[str] = []
    for p in ("owl", "rdf", "rdfs", "xsd"):
        lines.append(f"@prefix {p}: <{mandatory[p]}> .")

    # include only prefixes actually needed by the terms (plus the mandatory ones)
    others = sorted(p for p in prefixes_in_use if p not in mandatory)
    for p in others:
        ns = prefix_map.get(p)
        if ns:
            lines.append(f"@prefix {p}: <{ns}> .")

    return "\n".join(lines)


def write_ontology_ttl(
    out_path: Path,
    prefix_map: Dict[str, str],
    classes: List[str],
    props: List[str],
    prop_kinds: Dict[str, str],
) -> None:
    prefixes_in_use = used_prefixes(classes) | used_prefixes(props)

    prefix_block = format_prefixes(prefix_map, prefixes_in_use)

    # Ontology header
    ttl_parts: List[str] = []
    ttl_parts.append(prefix_block)
    ttl_parts.append("")
    ttl_parts.append(f"<{ONTOLOGY_URI}> a owl:Ontology ;")
    ttl_parts.append('    rdfs:label "Varela Digital Vocabulary Declaration"@en .')
    ttl_parts.append("")

    # Class declarations
    for c in classes:
        ttl_parts.append(f"{c} a owl:Class .")
    ttl_parts.append("")

    # Property declarations
    for p in props:
        kind = prop_kinds.get(p, "object")
        if kind == "datatype":
            ttl_parts.append(f"{p} a owl:DatatypeProperty .")
        else:
            ttl_parts.append(f"{p} a owl:ObjectProperty .")

    ttl = "\n".join(ttl_parts).strip() + "\n"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(ttl, encoding="utf-8")


# -----------------------------
# Main
# -----------------------------

def main() -> None:
    require_file(GRAPH_TTL)
    require_file(FROZEN_CLASSES)
    require_file(FROZEN_PROPS)

    g = Graph()
    g.parse(GRAPH_TTL, format="turtle")

    ns_map = build_ns_map(g)

    classes = load_terms(FROZEN_CLASSES)
    props = load_terms(FROZEN_PROPS)

    # Validate prefixes exist (fail fast, no silent bad URIs)
    needed_prefixes = used_prefixes(classes) | used_prefixes(props)
    missing = sorted(p for p in needed_prefixes if p not in ns_map)
    if missing:
        raise RuntimeError(
            "Missing prefix bindings in graph.ttl for:\n  "
            + ", ".join(missing)
            + "\nBind them in graph.ttl or add them to the script's namespace map."
        )

    # Infer property kinds from graph
    prop_kinds: Dict[str, str] = {}
    for p in props:
        pu = uri_for_curie(p, ns_map)
        prop_kinds[p] = infer_property_kind(g, pu)

    write_ontology_ttl(
        out_path=OUT_TTL,
        prefix_map=ns_map,
        classes=classes,
        props=props,
        prop_kinds=prop_kinds,
    )

    print("✔ Generated TBox ontology:")
    print("  ", OUT_TTL)
    print("✔ From frozen vocab:")
    print("  ", FROZEN_DIR)
    print("✔ Property typing inferred from:")
    print("  ", GRAPH_TTL)


if __name__ == "__main__":
    main()