#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Generate organization hierarchy JSON from TEI standoff_orgs.xml.

Inputs:
  - standoff_orgs.xml (TEI, with <org xml:id="..."> and <affiliation ref="#..."/>)

Outputs:
  1) Tree JSON (nested) for a collapsible hierarchy view (D3, etc.)
  2) Graph JSON (nodes + edges) for future reuse (Cytoscape, etc.)

Notes:
  - Structural hierarchy is taken ONLY from <org><affiliation ref="#PARENT"/></org>
  - Contextual/temporal affiliations in <state type="roleInTime"><affiliation .../></state>
    are preserved on the node as "roleInTime" entries (not used to build the tree).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET


TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"
NS = {"tei": TEI_NS}


def strip_hash(ref: str) -> str:
  ref = (ref or "").strip()
  return ref[1:] if ref.startswith("#") else ref


def first_text(el: Optional[ET.Element]) -> str:
  if el is None:
    return ""
  return " ".join((el.itertext() or [])).strip()


@dataclass
class RoleInTime:
  stateId: str
  roleName: str
  affiliation: Optional[str] = None


@dataclass
class OrgNode:
  id: str
  label: str
  type: Optional[str] = None
  parent: Optional[str] = None  # structural parent org id (from direct <org>/<affiliation>)
  roleInTime: List[RoleInTime] = None


def parse_orgs(xml_path: Path) -> Tuple[Dict[str, OrgNode], List[str]]:
  """
  Returns:
    nodes_by_id: dict[org_id] = OrgNode(...)
    warnings: list[str]
  """
  warnings: List[str] = []

  tree = ET.parse(xml_path)
  root = tree.getroot()

  nodes_by_id: Dict[str, OrgNode] = {}

  org_elems = root.findall(".//tei:org", NS)
  if not org_elems:
    warnings.append("No <org> elements found. Check TEI namespace and file content.")

  for org in org_elems:
    org_id = org.get(f"{{{XML_NS}}}id") or org.get("xml:id") or org.get("id")
    if not org_id:
      warnings.append("Found <org> without xml:id; skipping.")
      continue

    org_type = org.get("type")

    # Prefer orgName without @type; fallback to first orgName.
    org_names = org.findall("./tei:orgName", NS)
    primary_name_el = None
    for n in org_names:
      if not (n.get("type") or "").strip():
        primary_name_el = n
        break
    if primary_name_el is None and org_names:
      primary_name_el = org_names[0]

    label = first_text(primary_name_el) or org_id

    # Structural affiliation: direct child <affiliation ref="#..."/>
    # (do NOT take nested state affiliations as structural parent)
    direct_affs = org.findall("./tei:affiliation", NS)
    parent_id: Optional[str] = None
    if direct_affs:
      # If multiple, keep first, warn.
      parent_id = strip_hash(direct_affs[0].get("ref", ""))
      if len(direct_affs) > 1:
        refs = [strip_hash(a.get("ref", "")) for a in direct_affs]
        warnings.append(f'Org "{org_id}" has multiple direct affiliations {refs}. Using first: {parent_id!r}')

    # Role in time states (contextual affiliations)
    rit_list: List[RoleInTime] = []
    for st in org.findall("./tei:state[@type='roleInTime']", NS):
      st_id = st.get(f"{{{XML_NS}}}id") or st.get("xml:id") or ""
      role_name = first_text(st.find("./tei:roleName", NS))
      st_aff = st.find("./tei:affiliation", NS)
      aff_id = strip_hash(st_aff.get("ref", "")) if st_aff is not None else None
      rit_list.append(RoleInTime(stateId=st_id or "", roleName=role_name or "", affiliation=aff_id or None))

    nodes_by_id[org_id] = OrgNode(
      id=org_id,
      label=label,
      type=org_type,
      parent=parent_id or None,
      roleInTime=rit_list,
    )

  # Validate parents exist (structural)
  for oid, node in nodes_by_id.items():
    if node.parent and node.parent not in nodes_by_id:
      warnings.append(f'Org "{oid}" points to missing parent "{node.parent}". Keeping it as-is (will become a root).')

  return nodes_by_id, warnings


def build_graph(nodes_by_id: Dict[str, OrgNode]) -> Dict[str, Any]:
  nodes = []
  edges = []

  for n in nodes_by_id.values():
    nodes.append(
      {
        "id": n.id,
        "label": n.label,
        "type": n.type,
        "parent": n.parent,
        "roleInTime": [asdict(x) for x in (n.roleInTime or [])],
      }
    )

  # Structural edges: child -> parent
  for n in nodes_by_id.values():
    if n.parent:
      edges.append(
        {
          "id": f"{n.id}__{n.parent}__schema:subOrganizationOf",
          "type": "schema:subOrganizationOf",
          "source": n.id,
          "target": n.parent,
          "directed": True,
          "evidence": [],
          "weight": 1,
        }
      )

  # Stable sort for readability
  nodes.sort(key=lambda x: (x.get("label") or x["id"]).lower())
  edges.sort(key=lambda x: x["id"].lower())

  return {"nodes": nodes, "edges": edges}


def build_tree(nodes_by_id: Dict[str, OrgNode]) -> Dict[str, Any]:
  # Build children index from structural parent
  children: Dict[str, List[str]] = {oid: [] for oid in nodes_by_id.keys()}
  roots: List[str] = []

  for oid, node in nodes_by_id.items():
    p = node.parent
    if p and p in nodes_by_id:
      children[p].append(oid)
    else:
      roots.append(oid)

  # Sort children by label
  def sort_ids(ids: List[str]) -> List[str]:
    return sorted(ids, key=lambda i: (nodes_by_id[i].label or i).lower())

  for k in list(children.keys()):
    children[k] = sort_ids(children[k])
  roots = sort_ids(roots)

  def build_subtree(oid: str) -> Dict[str, Any]:
    node = nodes_by_id[oid]
    out: Dict[str, Any] = {
      "id": node.id,
      "label": node.label,
      "type": node.type,
      "roleInTime": [asdict(x) for x in (node.roleInTime or [])],
    }
    kids = children.get(oid, [])
    if kids:
      out["children"] = [build_subtree(k) for k in kids]
    return out

  # If multiple roots, wrap them under a virtual root for easier D3 rendering
  if len(roots) == 1:
    return build_subtree(roots[0])

  return {
    "id": "vd_orgs_root",
    "label": "Organizations",
    "type": "root",
    "children": [build_subtree(r) for r in roots],
  }


def write_json(path: Path, data: Any) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  with path.open("w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)


def main() -> int:
  ap = argparse.ArgumentParser(description="Generate org hierarchy JSON from standoff_orgs.xml")
  ap.add_argument("--in", dest="infile", required=True, help="Path to standoff_orgs.xml")
  ap.add_argument("--out-tree", dest="out_tree", required=True, help="Output path for tree JSON")
  ap.add_argument("--out-graph", dest="out_graph", required=True, help="Output path for graph JSON")
  args = ap.parse_args()

  infile = Path(args.infile).expanduser().resolve()
  out_tree = Path(args.out_tree).expanduser().resolve()
  out_graph = Path(args.out_graph).expanduser().resolve()

  if not infile.exists():
    print(f"ERROR: input file not found: {infile}", file=sys.stderr)
    return 2

  nodes_by_id, warnings = parse_orgs(infile)

  tree_json = build_tree(nodes_by_id)
  graph_json = build_graph(nodes_by_id)

  write_json(out_tree, tree_json)
  write_json(out_graph, graph_json)

  if warnings:
    print("Warnings:", file=sys.stderr)
    for w in warnings:
      print(f"- {w}", file=sys.stderr)

  print(f"OK: wrote tree  -> {out_tree}")
  print(f"OK: wrote graph -> {out_graph}")
  print(f"Nodes: {len(graph_json.get('nodes', []))} | Edges: {len(graph_json.get('edges', []))}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())