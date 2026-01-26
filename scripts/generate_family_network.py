#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path


# Relations to include (family + spiritual kinship)
INCLUDE = {
    "rel:parentOf",
    "rel:childOf",
    "rel:siblingOf",
    "rel:spouseOf",
    "rel:hasUncle",
    "rico:hasFamilyAssociationWith",
    "hrao:compadreOf",
}

# Relations we treat as undirected (no arrows)
UNDIRECTED = {
    "rel:siblingOf",
    "rel:spouseOf",
    "rico:hasFamilyAssociationWith",
    "hrao:compadreOf",
}

# Optional: treat hasUncle as undirected too (often semantically symmetric in graphs)
# If you prefer an arrow (uncle -> nephew/niece), remove it from here.
UNDIRECTED.add("rel:hasUncle")


def local_name(tag: str) -> str:
    """Extract localname from '{ns}tag' or 'tag'."""
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def normalize_relation(name: str, a: str, b: str):
    """
    Normalize relations:
      - rel:childOf becomes rel:parentOf with direction swapped
    Return (rel_name, source, target)
    """
    if name == "rel:childOf":
        # childOf(active=a, passive=b)  ==> parentOf(parent=b, child=a)
        return "rel:parentOf", b, a
    return name, a, b


def key_for_edge(rel_name: str, source: str, target: str, directed: bool) -> str:
    if directed:
        return f"{source}__{target}__{rel_name}"
    # undirected: canonicalize endpoints
    s, t = sorted([source, target])
    return f"{s}__{t}__{rel_name}"


def build_family_network(xml_path: Path):
    tree = ET.parse(xml_path)
    root = tree.getroot()

    # Find <relation> regardless of namespace
    relations = []
    for el in root.iter():
        if local_name(el.tag) == "relation":
            relations.append(el)

    # Accumulate nodes and edges
    nodes_set = set()
    edges_acc = {}

    # We'll sum weights for repeated relations
    weights = defaultdict(int)

    for r in relations:
        name = (r.get("name") or "").strip()
        if name not in INCLUDE:
            continue

        active = (r.get("active") or "").strip()
        passive = (r.get("passive") or "").strip()
        mutual = (r.get("mutual") or "").strip()

        # Determine endpoints
        # Prefer active/passive if present; else use mutual if present.
        if active and passive:
            a, b = active, passive
        elif mutual:
            # mutual can be "id1 id2" (space-separated). We'll take first two.
            parts = mutual.split()
            if len(parts) < 2:
                continue
            a, b = parts[0], parts[1]
        else:
            continue

        # Normalize childOf -> parentOf (swap endpoints)
        rel_name, source, target = normalize_relation(name, a, b)

        # Directed logic:
        # - If relation in UNDIRECTED => undirected
        # - Else if original has @mutual => undirected
        # - Else directed
        directed = True
        if rel_name in UNDIRECTED or (mutual and not (active and passive)):
            directed = False

        # Collect nodes (strip leading # if present, keep consistent)
        source_id = source.lstrip("#")
        target_id = target.lstrip("#")
        if not source_id or not target_id:
            continue

        nodes_set.add(source_id)
        nodes_set.add(target_id)

        # Edge id and aggregation key
        edge_key = key_for_edge(rel_name, source_id, target_id, directed)
        weights[edge_key] += 1

        if edge_key not in edges_acc:
            # For undirected, we still store source/target in canonical order (sorted),
            # for stable JSON outputs.
            if directed:
                s_id, t_id = source_id, target_id
            else:
                s_id, t_id = sorted([source_id, target_id])

            edges_acc[edge_key] = {
                "id": edge_key,
                "type": rel_name,
                "source": s_id,
                "target": t_id,
                "directed": bool(directed),
                "evidence": [],
            }

    # Materialize JSON
    nodes = [{"id": nid} for nid in sorted(nodes_set)]
    edges = []
    for k, e in edges_acc.items():
        e_out = dict(e)
        e_out["weight"] = int(weights[k])
        edges.append(e_out)

    # Sort edges for stable diffs
    edges.sort(key=lambda x: (x["type"], x["source"], x["target"]))

    return {"nodes": nodes, "edges": edges}


def main():
    ap = argparse.ArgumentParser(
        description="Generate family network JSON from standoff_relations.xml"
    )
    ap.add_argument(
        "--in",
        dest="infile",
        required=True,
        help="Path to standoff_relations.xml",
    )
    ap.add_argument(
        "--out",
        dest="outfile",
        required=True,
        help="Output JSON path (e.g., data/network/network_family.json)",
    )
    args = ap.parse_args()

    in_path = Path(args.infile).expanduser().resolve()
    out_path = Path(args.outfile).expanduser().resolve()

    data = build_family_network(in_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"OK: wrote {out_path}")
    print(f"  nodes: {len(data['nodes'])}")
    print(f"  edges: {len(data['edges'])}")


if __name__ == "__main__":
    main()