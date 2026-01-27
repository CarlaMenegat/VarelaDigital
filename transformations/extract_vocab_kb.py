#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Varela Digital — Extract effective vocabulary (classes/properties/prefixes)
from:
  - data/kbvareladigital/*.graphml
  - data/standoff/standoff_relations.xml

Outputs (under data/kbvareladigital/extracted/vocab/):
  - namespaces_used.txt
  - curies_used.txt
  - properties_used.txt
  - classes_used.txt
  - graphml_only_curies.txt
  - standoff_only_properties.txt

Heuristics:
  - Anything in standoff_relations @name is treated as a PROPERTY (CURIE).
  - From graphml, we collect all CURIE-like strings prefix:Local.
  - Class vs property from graphml is guessed:
      * Local starts with uppercase letter -> class
      * Local starts with lowercase letter -> property
    (you’ll review/freeze after generation)
"""

from __future__ import annotations

import re
from pathlib import Path
from lxml import etree as ET

# -----------------------------
# Paths
# -----------------------------
BASE_DIR = Path("/Users/carlamenegat/Documents/GitHub/Untitled/VarelaDigital")

GRAPHML_DIR = BASE_DIR / "data" / "kbvareladigital"
GRAPHML_FILES = sorted(GRAPHML_DIR.glob("*.graphml"))

STANDOFF_RELATIONS = BASE_DIR / "data/standoff/standoff_relations.xml"

OUT_DIR = BASE_DIR / "data/kbvareladigital/extracted/vocab"

# -----------------------------
# Regex: CURIE
# -----------------------------
CURIE_RE = re.compile(r"\b(?!https?:|urn:|mailto:|xml:|xmlns:|xs:)([a-zA-Z_][\w.-]*):([A-Za-z_][\w.-]*)\b")
IGNORE_PREFIX = {
    "http", "https", "urn", "mailto",
    "xml", "xmlns", "xs", "xsd", "xsi",
    "y",  # yWorks GraphML (técnico)
}

TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}


def ensure_dirs() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

print("GraphML files found:")
for fp in GRAPHML_FILES:
    print(" -", fp)
if not GRAPHML_FILES:
    raise SystemExit("No .graphml files found in data/kbvareladigital/")

def collect_curies_from_text(text: str) -> set[str]:
    curies = set()
    for m in CURIE_RE.finditer(text or ""):
        pfx = m.group(1)
        if pfx in IGNORE_PREFIX:
            continue
        curies.add(f"{pfx}:{m.group(2)}")
    return curies


def prefix_of(curie: str) -> str:
    return curie.split(":", 1)[0]


def local_of(curie: str) -> str:
    return curie.split(":", 1)[1]


def scan_graphml(files: list[Path]) -> set[str]:
    curies: set[str] = set()
    for fp in files:
        if not fp.exists():
            continue
        txt = fp.read_text(encoding="utf-8", errors="ignore")
        curies |= collect_curies_from_text(txt)
    return curies


def scan_standoff_relations(standoff_path: Path) -> set[str]:
    """
    Extract properties used as relation predicates (CURIE) from @name.
    """
    props: set[str] = set()
    if not standoff_path.exists():
        return props

    xml = ET.parse(str(standoff_path))
    for rel in xml.findall(".//tei:relation", TEI_NS):
        name = (rel.get("name") or "").strip()
        if not name:
            continue
        # accept CURIEs only (ignore full URIs here)
        if ":" in name and not name.startswith(("http://", "https://")):
            # validate pattern
            props |= collect_curies_from_text(name)
    return props


def guess_classes_and_properties_from_graphml(curies: set[str], standoff_props: set[str]) -> tuple[set[str], set[str]]:
    """
    Heuristic split. Anything in standoff_props is property.
    From remaining graphml curies:
      - Local starts uppercase -> class
      - else -> property
    """
    classes: set[str] = set()
    properties: set[str] = set()

    for c in curies:
        if c in standoff_props:
            properties.add(c)
            continue

        local = local_of(c)
        if local and local[0].isupper():
            classes.add(c)
        else:
            properties.add(c)

    return classes, properties


def write_sorted(path: Path, items: set[str]) -> None:
    path.write_text("\n".join(sorted(items)) + ("\n" if items else ""), encoding="utf-8")


def main() -> None:
    ensure_dirs()

    graphml_curies = scan_graphml(GRAPHML_FILES)
    standoff_props = scan_standoff_relations(STANDOFF_RELATIONS)

    # Split graphml into guessed classes/properties, but treat standoff as authoritative for properties
    classes_from_graphml, props_from_graphml = guess_classes_and_properties_from_graphml(graphml_curies, standoff_props)

    # Final sets
    all_properties = set(standoff_props) | set(props_from_graphml)
    all_classes = set(classes_from_graphml)

    all_curies = set(graphml_curies) | set(standoff_props)
    namespaces = {prefix_of(c) for c in all_curies}

    # Diffs help you review your model coverage
    graphml_only = graphml_curies - standoff_props
    standoff_only = standoff_props - graphml_curies

    # Write outputs
    write_sorted(OUT_DIR / "namespaces_used.txt", namespaces)
    write_sorted(OUT_DIR / "curies_used.txt", all_curies)
    write_sorted(OUT_DIR / "properties_used.txt", all_properties)
    write_sorted(OUT_DIR / "classes_used.txt", all_classes)
    write_sorted(OUT_DIR / "graphml_only_curies.txt", graphml_only)
    write_sorted(OUT_DIR / "standoff_only_properties.txt", standoff_only)

    print("✔ Vocabulary extracted to:", OUT_DIR)
    print("  - namespaces_used.txt")
    print("  - curies_used.txt")
    print("  - properties_used.txt")
    print("  - classes_used.txt")
    print("  - graphml_only_curies.txt (review: present in diagrams, not in standoff)")
    print("  - standoff_only_properties.txt (review: used in standoff, not in diagrams)")


if __name__ == "__main__":
    main()