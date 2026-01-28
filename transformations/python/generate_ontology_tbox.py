#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from rdflib import Graph, URIRef, Literal
from rdflib.namespace import RDF, RDFS, OWL, XSD


# ============================================================
# Paths (project-specific)
# ============================================================

BASE_DIR = Path("/Users/carlamenegat/Documents/GitHub/Untitled/VarelaDigital")

GRAPH_TTL = BASE_DIR / "assets/data/rdf/graph.ttl"

FROZEN_DIR = BASE_DIR / "data_models/ontology/extracted/vocab"
FROZEN_CLASSES = FROZEN_DIR / "classes_used.txt"
FROZEN_PROPS = FROZEN_DIR / "properties_used.txt"

OUT_TTL = BASE_DIR / "data_models/ontology/ttl/ontology.ttl"

# HRAO declaration (imported as an ontology dependency)
HRAO_LOCAL_TTL = BASE_DIR / "assets/hrao/hrao_declaration.ttl"
HRAO_PUBLIC_IRI = "https://carlamenegat.github.io/VarelaDigital/assets/hrao/hrao_declaration.ttl"

# Ontology IRI (public URL of the TTL file you publish)
ONTOLOGY_IRI = "https://carlamenegat.github.io/VarelaDigital/data_models/ontology/ttl/ontology.ttl"


# ============================================================
# Policy knobs (important)
# ============================================================

# These must be DatatypeProperties even if not observed in graph.ttl
FORCED_DATATYPE_PROPERTIES: Set[str] = {
    "bibo:pageStart",
    "bibo:pageEnd",
    "bibo:volume",
}

# Avoid domain/range inference for these prefixes (too generic / too risky)
NO_DOMAIN_RANGE_PREFIXES: Set[str] = {
    "prov",
}


# ============================================================
# Small utilities
# ============================================================

def require_file(p: Path) -> None:
    if not p.exists():
        raise FileNotFoundError(f"Required file not found:\n  {p}")


def load_terms(path: Path) -> List[str]:
    """
    One CURIE per line (e.g., fabio:Letter, san:refersTo, hrao:servedUnder).
    """
    out: Set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        t = line.strip()
        if not t or t.startswith("#"):
            continue
        out.add(t)
    return sorted(out)


def local_name_from_iri(iri: str) -> str:
    if "#" in iri:
        return iri.rsplit("#", 1)[1]
    return iri.rstrip("/").rsplit("/", 1)[-1]


def pretty_label_from_local(local: str) -> str:
    # snake_case -> words
    if "_" in local:
        return local.replace("_", " ").strip()
    # camelCase -> camel Case
    out: List[str] = []
    prev_lower = False
    for ch in local:
        if prev_lower and ch.isupper():
            out.append(" ")
        out.append(ch)
        prev_lower = ch.islower()
    return "".join(out).strip()


def uri_for_curie(curie: str, ns_map: Dict[str, str]) -> Optional[URIRef]:
    curie = (curie or "").strip()
    if ":" not in curie:
        return None
    prefix, local = curie.split(":", 1)
    prefix, local = prefix.strip(), local.strip()
    if not prefix or not local:
        return None
    ns = ns_map.get(prefix)
    if not ns:
        return None
    return URIRef(ns + local)


def ensure_prefix(ns_map: Dict[str, str], prefix: str, ns: str) -> None:
    if prefix not in ns_map:
        ns_map[prefix] = ns


def build_ns_map_from_graph(g: Graph) -> Dict[str, str]:
    return {p: str(ns) for p, ns in g.namespace_manager.namespaces()}


def merge_fallback_prefixes(ns_map: Dict[str, str]) -> Dict[str, str]:
    """
    Resilient even if graph.ttl is missing some prefix bindings.
    Also fixes geo: to the WGS84 namespace (needed for geo:SpatialThing).
    """
    # Core
    ensure_prefix(ns_map, "owl", str(OWL))
    ensure_prefix(ns_map, "rdf", str(RDF))
    ensure_prefix(ns_map, "rdfs", str(RDFS))
    ensure_prefix(ns_map, "xsd", str(XSD))

    # Project
    ensure_prefix(ns_map, "hrao", "https://carlamenegat.github.io/VarelaDigital/hrao#")

    # External vocabs
    ensure_prefix(ns_map, "bibo", "http://purl.org/ontology/bibo/")
    ensure_prefix(ns_map, "dcterms", "http://purl.org/dc/terms/")
    ensure_prefix(ns_map, "doco", "http://purl.org/spar/doco/")
    ensure_prefix(ns_map, "fabio", "http://purl.org/spar/fabio/")
    ensure_prefix(ns_map, "foaf", "http://xmlns.com/foaf/0.1/")
    ensure_prefix(ns_map, "frbr", "http://purl.org/vocab/frbr/core#")
    ensure_prefix(ns_map, "hico", "http://purl.org/emmedi/hico/")
    ensure_prefix(ns_map, "pro", "http://purl.org/spar/pro/")
    ensure_prefix(ns_map, "prov", "http://www.w3.org/ns/prov#")
    ensure_prefix(ns_map, "rel", "http://purl.org/vocab/relationship/")
    ensure_prefix(ns_map, "rico", "https://www.ica.org/standards/RiC/ontology#")
    ensure_prefix(ns_map, "schema", "https://schema.org/")
    ensure_prefix(ns_map, "time", "http://www.w3.org/2006/time#")
    ensure_prefix(ns_map, "skos", "http://www.w3.org/2004/02/skos/core#")
    ensure_prefix(ns_map, "san", "http://dati.san.beniculturali.it/ode/?uri=http://dati.san.beniculturali.it/SAN/")

    # IMPORTANT: geo: must be WGS84 if you use geo:SpatialThing
    ns_map["geo"] = "http://www.w3.org/2003/01/geo/wgs84_pos#"

    return ns_map


def is_infra_term(curie: str) -> bool:
    """
    Terms that should not be declared in ontology.ttl.
    """
    bad = {
        "rdf:type",
        "rdfs:label",
        "rdfs:comment",
        "rdfs:subClassOf",
        "owl:imports",
        "owl:Ontology",
        "owl:Class",
        "owl:ObjectProperty",
        "owl:DatatypeProperty",
        "owl:AnnotationProperty",
    }
    return curie in bad


def split_prefix(curie: str) -> str:
    return curie.split(":", 1)[0] if ":" in curie else ""


def property_observation(g: Graph, p: URIRef) -> Tuple[bool, bool]:
    """
    Returns (seen_uri_or_bnode, seen_literal)
    """
    seen_uri = False
    seen_lit = False
    for _s, _p, o in g.triples((None, p, None)):
        if isinstance(o, Literal):
            seen_lit = True
        else:
            seen_uri = True
        if seen_uri and seen_lit:
            break
    return seen_uri, seen_lit


def guess_domain_range(g: Graph, p: URIRef) -> Tuple[Optional[URIRef], Optional[URIRef]]:
    """
    Conservative domain/range inference:
    - domain: if all observed subjects share exactly one rdf:type -> use it
    - range: if all observed URIRef objects share exactly one rdf:type -> use it
    Otherwise: None
    """
    subj_types: Set[URIRef] = set()
    obj_types: Set[URIRef] = set()

    for s, _p, o in g.triples((None, p, None)):
        if isinstance(s, URIRef):
            for t in g.objects(s, RDF.type):
                if isinstance(t, URIRef):
                    subj_types.add(t)

        if isinstance(o, URIRef):
            for t in g.objects(o, RDF.type):
                if isinstance(t, URIRef):
                    obj_types.add(t)

        if len(subj_types) > 1 and len(obj_types) > 1:
            break

    domain = next(iter(subj_types)) if len(subj_types) == 1 else None
    range_ = next(iter(obj_types)) if len(obj_types) == 1 else None
    return domain, range_


def ttl_term(iri: URIRef, ns_map: Dict[str, str]) -> str:
    """
    Prefer CURIE if possible; else <IRI>.
    """
    u = str(iri)
    best_prefix: Optional[str] = None
    best_ns: Optional[str] = None
    for prefix, ns in ns_map.items():
        if prefix and ns and u.startswith(ns):
            if best_ns is None or len(ns) > len(best_ns):
                best_prefix = prefix
                best_ns = ns
    if best_prefix and best_ns is not None:
        local = u[len(best_ns):]
        if local:
            return f"{best_prefix}:{local}"
    return f"<{u}>"


# ============================================================
# Turtle building
# ============================================================

def prefixes_block(ns_map: Dict[str, str]) -> str:
    order = [
        "owl", "rdf", "rdfs", "xsd",
        "bibo", "dcterms", "doco", "fabio", "foaf", "frbr", "geo",
        "hico", "hrao", "pro", "prov", "rel", "rico", "san", "schema",
        "skos", "time",
    ]
    lines: List[str] = []
    for p in order:
        ns = ns_map.get(p)
        if ns:
            lines.append(f"@prefix {p}: <{ns}> .")
    return "\n".join(lines) + "\n\n"


def ontology_header() -> str:
    return (
        f"<{ONTOLOGY_IRI}> a owl:Ontology ;\n"
        f"    rdfs:label \"Varela Digital Vocabulary Declaration\"@en ;\n"
        f"    rdfs:comment \"TBox declaration of classes and properties used in the Varela Digital knowledge base.\"@en ;\n"
        f"    owl:imports <{HRAO_PUBLIC_IRI}> .\n\n"
    )


def declare_class(curie: str, iri: URIRef) -> str:
    local = local_name_from_iri(str(iri))
    label = pretty_label_from_local(local)
    return (
        f"{curie} a owl:Class ;\n"
        f"    rdfs:label \"{label}\"@en ;\n"
        f"    rdfs:comment \"Class used in the Varela Digital knowledge base.\"@en .\n\n"
    )


def declare_property(
    curie: str,
    iri: URIRef,
    kind: URIRef,
    ns_map: Dict[str, str],
    domain: Optional[URIRef],
    range_: Optional[URIRef],
) -> str:
    local = local_name_from_iri(str(iri))
    label = pretty_label_from_local(local)

    comment = (
        "Project-defined relation used in the Varela Digital knowledge base."
        if curie.startswith("hrao:")
        else "Property used in the Varela Digital knowledge base."
    )

    lines: List[str] = [
        f"{curie} a {ttl_term(kind, ns_map)} ;",
        f"    rdfs:label \"{label}\"@en ;",
        f"    rdfs:comment \"{comment}\"@en ;",
    ]

    if domain is not None:
        lines.append(f"    rdfs:domain {ttl_term(domain, ns_map)} ;")
    if range_ is not None:
        lines.append(f"    rdfs:range {ttl_term(range_, ns_map)} ;")

    # last ; -> .
    if lines[-1].endswith(" ;"):
        lines[-1] = lines[-1][:-2] + " ."
    else:
        lines[-1] = lines[-1].rstrip(";") + " ."

    return "\n".join(lines) + "\n\n"


# ============================================================
# Main
# ============================================================

def main() -> None:
    require_file(GRAPH_TTL)
    require_file(FROZEN_CLASSES)
    require_file(FROZEN_PROPS)

    # HRAO import is optional at runtime: if missing locally, we still generate the TBox.
    # The public IRI stays in owl:imports anyway.
    if not HRAO_LOCAL_TTL.exists():
        print(f"[WARN] HRAO local TTL not found (continuing):\n  {HRAO_LOCAL_TTL}")

    g = Graph()
    g.parse(GRAPH_TTL, format="turtle")

    ns_map = merge_fallback_prefixes(build_ns_map_from_graph(g))

    classes = [c for c in load_terms(FROZEN_CLASSES) if not is_infra_term(c)]
    props = [p for p in load_terms(FROZEN_PROPS) if not is_infra_term(p)]

    # Validate CURIEs resolvable
    unresolved_classes = [c for c in classes if uri_for_curie(c, ns_map) is None]
    unresolved_props = [p for p in props if uri_for_curie(p, ns_map) is None]
    if unresolved_classes or unresolved_props:
        msg: List[str] = []
        if unresolved_classes:
            msg.append("Unresolved class CURIEs (missing prefix bindings):")
            msg.extend([f"  - {x}" for x in unresolved_classes])
        if unresolved_props:
            msg.append("Unresolved property CURIEs (missing prefix bindings):")
            msg.extend([f"  - {x}" for x in unresolved_props])
        raise RuntimeError("\n".join(msg))

    out: List[str] = []
    out.append(prefixes_block(ns_map))
    out.append(ontology_header())

    # Classes
    for c in classes:
        iri = uri_for_curie(c, ns_map)
        assert iri is not None
        out.append(declare_class(c, iri))

    # Properties
    for p in props:
        iri = uri_for_curie(p, ns_map)
        assert iri is not None

        # A) Forced datatype beats everything
        if p in FORCED_DATATYPE_PROPERTIES:
            out.append(declare_property(p, iri, OWL.DatatypeProperty, ns_map, None, None))
            continue

        seen_uri, seen_lit = property_observation(g, iri)

        # B) If observed only literals -> DatatypeProperty
        if seen_lit and not seen_uri:
            out.append(declare_property(p, iri, OWL.DatatypeProperty, ns_map, None, None))
            continue

        # C) Otherwise -> ObjectProperty
        kind = OWL.ObjectProperty

        # Domain/range inference: conservative + opt-out by prefix
        prefix = split_prefix(p)
        if prefix in NO_DOMAIN_RANGE_PREFIXES:
            domain = None
            range_ = None
        else:
            # If not observed at all, don't guess domain/range
            if not seen_uri and not seen_lit:
                domain = None
                range_ = None
            else:
                domain, range_ = guess_domain_range(g, iri)

        out.append(declare_property(p, iri, kind, ns_map, domain, range_))

    OUT_TTL.parent.mkdir(parents=True, exist_ok=True)
    OUT_TTL.write_text("".join(out).strip() + "\n", encoding="utf-8")

    print("✔ Generated ontology.ttl (TBox):")
    print("  ", OUT_TTL)
    print("✔ Ontology IRI:")
    print("  ", ONTOLOGY_IRI)
    print("✔ Classes from:")
    print("  ", FROZEN_CLASSES)
    print("✔ Properties from:")
    print("  ", FROZEN_PROPS)
    print("✔ Evidence graph:")
    print("  ", GRAPH_TTL)


if __name__ == "__main__":
    main()