#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Validate graph.ttl against frozen vocabulary lists.

Inputs:
- assets/data/rdf/graph.ttl
- data_models/kbvareladigital/extracted/vocab/classes_used.txt
- data_models/kbvareladigital/extracted/vocab/properties_used.txt

Output:
- prints a report to stdout
- writes JSON report to assets/data/rdf/validation_report.json
"""

from __future__ import annotations

from pathlib import Path
import json
from collections import defaultdict
from rdflib import Graph, URIRef
from rdflib.namespace import RDF


BASE_DIR = Path("/Users/carlamenegat/Documents/GitHub/Untitled/VarelaDigital")

GRAPH_TTL = BASE_DIR / "assets/data/rdf/graph.ttl"

FROZEN_DIR = BASE_DIR / "data_models/kbvareladigital/extracted/vocab"
FROZEN_CLASSES = FROZEN_DIR / "classes_used.txt"
FROZEN_PROPS = FROZEN_DIR / "properties_used.txt"

REPORT_JSON = BASE_DIR / "assets/data/rdf/validation_report.json"

# Canonical namespaces we want to normalize to stable CURIE prefixes
CANON_NS = {
    "geo": "http://www.w3.org/2003/01/geo/wgs84_pos#",
    # if you ever need more canonicalizations, add here
    # "schema": "https://schema.org/",
}


def require_file(p: Path) -> None:
    if not p.exists():
        raise FileNotFoundError(f"Required file not found:\n  {p}")


def load_frozen_terms(path: Path) -> set[str]:
    terms: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        t = line.strip()
        if not t or t.startswith("#"):
            continue
        terms.add(t)
    return terms


def normalize_term(t: str) -> str:
    return (t or "").strip()


def curie_for_uri(uri: URIRef, ns_map: dict[str, str]) -> str:
    """
    Convert a full URI to a CURIE.

    IMPORTANT:
    - We normalize certain namespaces to a *canonical prefix* regardless of what
      prefix name appears in the TTL (e.g., geo1 -> geo).
    - Otherwise, we use the longest matching namespace from graph bindings.
    """
    u = str(uri)

    # 1) Canonical namespace normalization (prefix-name independent)
    for canon_prefix, canon_ns in CANON_NS.items():
        if u.startswith(canon_ns):
            local = u[len(canon_ns):]
            if local:
                return f"{canon_prefix}:{local}"
            return u

    # 2) Otherwise: best (longest) match from bindings
    best_prefix: str | None = None
    best_ns: str | None = None

    for prefix, ns in ns_map.items():
        if not prefix or not ns:
            continue
        ns = str(ns)
        if u.startswith(ns):
            if best_ns is None or len(ns) > len(best_ns):
                best_prefix = prefix
                best_ns = ns

    if best_prefix and best_ns is not None:
        local = u[len(best_ns):]
        if local:
            return f"{best_prefix}:{local}"

    return u


def main() -> None:
    require_file(GRAPH_TTL)
    require_file(FROZEN_CLASSES)
    require_file(FROZEN_PROPS)

    frozen_classes = {normalize_term(x) for x in load_frozen_terms(FROZEN_CLASSES)}
    frozen_props = {normalize_term(x) for x in load_frozen_terms(FROZEN_PROPS)}

    g = Graph()
    g.parse(GRAPH_TTL, format="turtle")

    ns_map = {p: str(ns) for p, ns in g.namespace_manager.namespaces()}

    used_props: set[str] = set()
    used_classes: set[str] = set()

    pred_examples: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    class_examples: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    EXAMPLES_LIMIT = 3

    # Predicates
    for s, pred, o in g:
        if isinstance(pred, URIRef):
            p = normalize_term(curie_for_uri(pred, ns_map))
            used_props.add(p)
            if len(pred_examples[p]) < EXAMPLES_LIMIT:
                pred_examples[p].append((str(s), str(pred), str(o)))

    # Classes (objects of rdf:type)
    for s, _, obj in g.triples((None, RDF.type, None)):
        if isinstance(obj, URIRef):
            c = normalize_term(curie_for_uri(obj, ns_map))
            used_classes.add(c)
            if len(class_examples[c]) < EXAMPLES_LIMIT:
                class_examples[c].append((str(s), str(RDF.type), str(obj)))

    props_outside = sorted(used_props - frozen_props)
    classes_outside = sorted(used_classes - frozen_classes)

    props_missing = sorted(frozen_props - used_props)
    classes_missing = sorted(frozen_classes - used_classes)

    print("\n==============================")
    print("Varela Digital — RDF Validation")
    print("==============================\n")

    print(f"Graph: {GRAPH_TTL}")
    print(f"Frozen vocab dir: {FROZEN_DIR}\n")

    print(f"Used properties: {len(used_props)}")
    print(f"Used classes:     {len(used_classes)}\n")

    if props_outside:
        print("❌ Properties used OUTSIDE frozen vocabulary:")
        for t in props_outside:
            print("  -", t)
        print("\nExamples (first 3 triples per property):")
        for t in props_outside:
            for (s, p, o) in pred_examples.get(t, []):
                print("    ", s, p, o)
        print()
    else:
        print("✅ No properties outside frozen vocabulary.\n")

    if classes_outside:
        print("❌ Classes used OUTSIDE frozen vocabulary:")
        for t in classes_outside:
            print("  -", t)
        print("\nExamples (first 3 rdf:type triples per class):")
        for t in classes_outside:
            for (s, p, o) in class_examples.get(t, []):
                print("    ", s, p, o)
        print()
    else:
        print("✅ No classes outside frozen vocabulary.\n")

    print("ℹ️  Frozen properties NOT found in this graph (may be OK):", len(props_missing))
    print("ℹ️  Frozen classes NOT found in this graph (may be OK):", len(classes_missing))

    report = {
        "graph": str(GRAPH_TTL),
        "frozen_vocab_dir": str(FROZEN_DIR),
        "counts": {
            "used_properties": len(used_props),
            "used_classes": len(used_classes),
            "frozen_properties": len(frozen_props),
            "frozen_classes": len(frozen_classes),
        },
        "outside_frozen": {
            "properties": props_outside,
            "classes": classes_outside,
        },
        "missing_from_graph": {
            "properties": props_missing,
            "classes": classes_missing,
        },
        "examples": {
            "properties": {k: v for k, v in pred_examples.items() if k in props_outside},
            "classes": {k: v for k, v in class_examples.items() if k in classes_outside},
        },
        "namespace_bindings_in_graph": ns_map,
        "canonical_namespace_rules": CANON_NS,
    }

    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport saved: {REPORT_JSON}\n")


if __name__ == "__main__":
    main()