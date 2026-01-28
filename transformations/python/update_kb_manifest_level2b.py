#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Varela Digital — Level 2B manifest updater (ODI total style, but in a single TTL)

Edits kbvareladigital.ttl in-place:
- fills void:entities / void:triples from the current RDF graph
- generates full partitions from the frozen vocabulary snapshot
- generates void:subset blocks (letters/persons/orgs/places/events) with example resources
- does NOT create any extra TTL file

Inputs:
- assets/data/rdf/graph.ttl
- data_models/kbvareladigital/extracted/vocab/classes_used.txt
- data_models/kbvareladigital/extracted/vocab/properties_used.txt
- data_models/kbvareladigital/kbvareladigital.ttl  (edited in-place)

Assumptions:
- graph.ttl uses the same namespaces you validated against (incl. hrao:, san:, skos:, etc.)
"""

from __future__ import annotations

from pathlib import Path
import re
from collections import defaultdict
from typing import Dict, Iterable, List, Set, Tuple

from rdflib import Graph, URIRef, Namespace
from rdflib.namespace import RDF


# -----------------------------
# Paths
# -----------------------------

BASE_DIR = Path("/Users/carlamenegat/Documents/GitHub/Untitled/VarelaDigital")

GRAPH_TTL = BASE_DIR / "assets/data/rdf/graph.ttl"

FROZEN_DIR = BASE_DIR / "data_models/kbvareladigital/extracted/vocab"
FROZEN_CLASSES = FROZEN_DIR / "classes_used.txt"
FROZEN_PROPS = FROZEN_DIR / "properties_used.txt"

KB_TTL = BASE_DIR / "data_models/kbvareladigital/kbvareladigital.ttl"


# -----------------------------
# Constants / dataset URIs
# -----------------------------

DATASET_URI = URIRef("https://carlamenegat.github.io/VarelaDigital/dataset/kbvareladigital")

# Expected base spaces (used to build deterministic subsets)
BASE_URI = "https://carlamenegat.github.io/VarelaDigital/"
PERSON_BASE = BASE_URI + "person/"
ORG_BASE = BASE_URI + "org/"
PLACE_BASE = BASE_URI + "place/"
EVENT_BASE = BASE_URI + "event/"
LETTER_BASE = BASE_URI + "letter/"


# -----------------------------
# Helpers
# -----------------------------

def require_file(p: Path) -> None:
    if not p.exists():
        raise FileNotFoundError(f"Required file not found:\n  {p}")


def load_frozen_terms(path: Path) -> List[str]:
    """
    One CURIE per line (e.g., fabio:Letter, san:refersTo, hrao:servedUnder).
    Keeps order stable (sorted at the end).
    """
    terms: Set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        t = line.strip()
        if not t or t.startswith("#"):
            continue
        terms.add(t)
    return sorted(terms)


def build_ns_map(g: Graph) -> Dict[str, str]:
    return {p: str(ns) for p, ns in g.namespace_manager.namespaces()}


def curie_for_uri(uri: URIRef, ns_map: Dict[str, str]) -> str:
    """
    Convert URI -> CURIE based on graph namespace bindings.
    Uses longest matching namespace for stability.
    If no match, returns the full URI string.
    """
    u = str(uri)
    best_prefix = None
    best_ns = None

    for prefix, ns in ns_map.items():
        if not prefix or not ns:
            continue
        if u.startswith(ns):
            if best_ns is None or len(ns) > len(best_ns):
                best_prefix = prefix
                best_ns = ns

    if best_prefix and best_ns is not None:
        local = u[len(best_ns):]
        if local:
            return f"{best_prefix}:{local}"

    return u


def uri_for_curie(curie: str, ns_map: Dict[str, str]) -> URIRef | None:
    """
    Convert CURIE -> URIRef using ns_map (prefix -> namespace).
    Returns None if prefix not found or curie not well-formed.
    """
    curie = (curie or "").strip()
    if not curie or ":" not in curie:
        return None
    prefix, local = curie.split(":", 1)
    prefix = prefix.strip()
    local = local.strip()
    if not prefix or not local:
        return None
    if prefix not in ns_map:
        return None
    return URIRef(ns_map[prefix] + local)


def stable_sample(uris: Iterable[str], k: int = 5) -> List[str]:
    """
    Deterministic: sort and take first k.
    """
    return sorted(set(uris))[:k]


def find_subjects_of_type(g: Graph, class_uri: URIRef) -> Set[str]:
    out: Set[str] = set()
    for s in g.subjects(RDF.type, class_uri):
        if isinstance(s, URIRef):
            out.add(str(s))
    return out


def count_entities_by_class(g: Graph, class_uri: URIRef) -> int:
    return len(find_subjects_of_type(g, class_uri))


def count_triples_by_property(g: Graph, prop_uri: URIRef) -> int:
    c = 0
    for _s, _p, _o in g.triples((None, prop_uri, None)):
        c += 1
    return c


def guess_bucket(uri: str) -> str | None:
    if uri.startswith(LETTER_BASE):
        return "letters"
    if uri.startswith(PERSON_BASE):
        return "persons"
    if uri.startswith(ORG_BASE):
        return "orgs"
    if uri.startswith(PLACE_BASE):
        return "places"
    if uri.startswith(EVENT_BASE):
        return "events"
    return None


def build_subset_examples(g: Graph) -> Dict[str, List[str]]:
    """
    Build examples for each bucket by scanning subjects in graph.
    """
    buckets: Dict[str, Set[str]] = {k: set() for k in ("letters", "persons", "orgs", "places", "events")}

    for s in set(str(s) for s in g.subjects() if isinstance(s, URIRef)):
        b = guess_bucket(s)
        if b:
            buckets[b].add(s)

    return {k: stable_sample(v, k=5) for k, v in buckets.items()}


def ttl_list(uris: List[str], indent: int = 8) -> str:
    pad = " " * indent
    if not uris:
        return pad + "# (no examples found in graph)"
    lines = []
    for i, u in enumerate(uris):
        sep = " ," if i < len(uris) - 1 else " ."
        lines.append(f"{pad}<{u}>{sep}")
    return "\n".join(lines)


# -----------------------------
# TTL block generation
# -----------------------------

def generate_partitions_block(
    g: Graph,
    ns_map: Dict[str, str],
    frozen_classes: List[str],
    frozen_props: List[str],
) -> str:
    """
    Full partitions using frozen vocabulary lists, with actual counts from graph.
    """
    class_parts = []
    for c in frozen_classes:
        cu = uri_for_curie(c, ns_map)
        if cu is None:
            # keep it visible (but 0), avoids silent drop
            entities = 0
            class_parts.append(
                "        [\n"
                f"            void:class {c} ;\n"
                f"            void:entities \"{entities}\"^^xsd:integer\n"
                "        ]"
            )
            continue

        entities = count_entities_by_class(g, cu)
        class_parts.append(
            "        [\n"
            f"            void:class {c} ;\n"
            f"            void:entities \"{entities}\"^^xsd:integer\n"
            "        ]"
        )

    prop_parts = []
    for p in frozen_props:
        pu = uri_for_curie(p, ns_map)
        if pu is None:
            triples = 0
            prop_parts.append(
                "        [\n"
                f"            void:property {p} ;\n"
                f"            void:triples \"{triples}\"^^xsd:integer\n"
                "        ]"
            )
            continue

        triples = count_triples_by_property(g, pu)
        prop_parts.append(
            "        [\n"
            f"            void:property {p} ;\n"
            f"            void:triples \"{triples}\"^^xsd:integer\n"
            "        ]"
        )

    # Join partitions
    class_part_str = " ,\n".join(class_parts) + " ;"
    prop_part_str = " ,\n".join(prop_parts) + " ."

    return (
        "#################################################################\n"
        "# 6) Effective vocabulary (frozen snapshot) as VOID partitions\n"
        "#################################################################\n\n"
        "<https://carlamenegat.github.io/VarelaDigital/dataset/kbvareladigital>\n"
        "    void:uriSpace \"https://carlamenegat.github.io/VarelaDigital/\"^^xsd:string ;\n\n"
        "    void:classPartition\n"
        f"{class_part_str}\n\n"
        "    void:propertyPartition\n"
        f"{prop_part_str}\n"
    )


def generate_subsets_block(examples: Dict[str, List[str]]) -> str:
    """
    Adds void:subset blocks with deterministic example URIs.
    No new file: goes into the same kbvareladigital.ttl.
    """
    def subset_uri(name: str) -> str:
        return f"{BASE_URI}dataset/kbvareladigital/{name}"

    return (
        "\n#################################################################\n"
        "# 6a) Dataset subsets (letters/persons/orgs/places/events)\n"
        "#################################################################\n\n"
        "<https://carlamenegat.github.io/VarelaDigital/dataset/kbvareladigital>\n"
        "    void:subset\n"
        f"        <{subset_uri('letters')}> ,\n"
        f"        <{subset_uri('persons')}> ,\n"
        f"        <{subset_uri('orgs')}> ,\n"
        f"        <{subset_uri('places')}> ,\n"
        f"        <{subset_uri('events')}> .\n\n"
        f"<{subset_uri('letters')}>\n"
        "    a void:Dataset ;\n"
        "    dcterms:title \"Varela Digital — Letters subset\"@en ;\n"
        "    void:class fabio:Letter ;\n"
        "    void:exampleResource\n"
        f"{ttl_list(examples.get('letters', []))}\n\n"
        f"<{subset_uri('persons')}>\n"
        "    a void:Dataset ;\n"
        "    dcterms:title \"Varela Digital — Persons subset\"@en ;\n"
        "    void:class foaf:Person ;\n"
        "    void:exampleResource\n"
        f"{ttl_list(examples.get('persons', []))}\n\n"
        f"<{subset_uri('orgs')}>\n"
        "    a void:Dataset ;\n"
        "    dcterms:title \"Varela Digital — Organizations subset\"@en ;\n"
        "    void:class foaf:Organization ;\n"
        "    void:exampleResource\n"
        f"{ttl_list(examples.get('orgs', []))}\n\n"
        f"<{subset_uri('places')}>\n"
        "    a void:Dataset ;\n"
        "    dcterms:title \"Varela Digital — Places subset\"@en ;\n"
        "    void:class geo:SpatialThing ;\n"
        "    void:exampleResource\n"
        f"{ttl_list(examples.get('places', []))}\n\n"
        f"<{subset_uri('events')}>\n"
        "    a void:Dataset ;\n"
        "    dcterms:title \"Varela Digital — Events subset\"@en ;\n"
        "    void:class rico:Event ;\n"
        "    void:exampleResource\n"
        f"{ttl_list(examples.get('events', []))}\n"
    )


def replace_block_in_kb(kb_text: str, new_block: str) -> str:
    """
    Replace the existing block starting at:
      '# 6) Effective vocabulary (frozen snapshot) as VOID partitions'
    up to the next '#################################################################' that starts a new section,
    with `new_block`.

    This lets you keep everything else (your Level 1 + later examples).
    """
    start_pat = r"#################################################################\n# 6\) Effective vocabulary \(frozen snapshot\) as VOID partitions\n#################################################################\n"
    m = re.search(start_pat, kb_text)
    if not m:
        raise RuntimeError("Could not find the Level 2B marker block header (# 6) in kbvareladigital.ttl")

    start_idx = m.start()

    # Find the next section header AFTER the #6 block (we include subsets inside the replacement).
    next_header = re.search(r"\n#################################################################\n#\s*7\)", kb_text[m.end():])
    if not next_header:
        # fallback: replace until end
        end_idx = len(kb_text)
    else:
        end_idx = m.end() + next_header.start() + 1  # keep the "\n" before the header

    return kb_text[:start_idx] + new_block + "\n" + kb_text[end_idx:]


def main() -> None:
    require_file(GRAPH_TTL)
    require_file(FROZEN_CLASSES)
    require_file(FROZEN_PROPS)
    require_file(KB_TTL)

    g = Graph()
    g.parse(GRAPH_TTL, format="turtle")

    ns_map = build_ns_map(g)

    frozen_classes = load_frozen_terms(FROZEN_CLASSES)
    frozen_props = load_frozen_terms(FROZEN_PROPS)

    partitions = generate_partitions_block(g, ns_map, frozen_classes, frozen_props)
    subsets = generate_subsets_block(build_subset_examples(g))

    new_block = partitions + subsets

    kb_text = KB_TTL.read_text(encoding="utf-8")
    updated = replace_block_in_kb(kb_text, new_block)

    KB_TTL.write_text(updated, encoding="utf-8")

    print("✔ Updated kbvareladigital.ttl with Level 2B partitions + subsets:")
    print("  ", KB_TTL)
    print("✔ Counts were computed from:")
    print("  ", GRAPH_TTL)
    print("✔ Frozen vocab was read from:")
    print("  ", FROZEN_DIR)


if __name__ == "__main__":
    main()