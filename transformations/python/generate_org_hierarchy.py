#!/usr/bin/env python3
# -*- coding: utf-8 -*-

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
    parent: Optional[str] = None
    roleInTime: List[RoleInTime] = None


def parse_orgs(xml_path: Path) -> Tuple[Dict[str, OrgNode], List[str]]:
    warnings: List[str] = []

    tree = ET.parse(xml_path)
    root = tree.getroot()

    nodes_by_id: Dict[str, OrgNode] = {}

    org_elems = root.findall(".//tei:org", NS)

    for org in org_elems:
        org_id = org.get(f"{{{XML_NS}}}id") or org.get("xml:id") or org.get("id")
        if not org_id:
            continue

        org_type = org.get("type")

        org_names = org.findall("./tei:orgName", NS)
        primary_name_el = None
        for n in org_names:
            if not (n.get("type") or "").strip():
                primary_name_el = n
                break
        if primary_name_el is None and org_names:
            primary_name_el = org_names[0]

        label = first_text(primary_name_el) or org_id

        parent_id: Optional[str] = None

        direct_affs = org.findall("./tei:affiliation", NS)
        if direct_affs:
            parent_id = strip_hash(direct_affs[0].get("ref", ""))
        else:
            for st in org.findall("./tei:state[@type='roleInTime']", NS):
                st_aff = st.find("./tei:affiliation", NS)
                if st_aff is not None and st_aff.get("ref"):
                    parent_id = strip_hash(st_aff.get("ref", ""))
                    break

        rit_list: List[RoleInTime] = []
        for st in org.findall("./tei:state[@type='roleInTime']", NS):
            st_id = st.get(f"{{{XML_NS}}}id") or st.get("xml:id") or ""
            role_name = first_text(st.find("./tei:roleName", NS))
            st_aff = st.find("./tei:affiliation", NS)
            aff_id = strip_hash(st_aff.get("ref", "")) if st_aff is not None else None
            rit_list.append(
                RoleInTime(
                    stateId=st_id or "",
                    roleName=role_name or "",
                    affiliation=aff_id or None,
                )
            )

        nodes_by_id[org_id] = OrgNode(
            id=org_id,
            label=label,
            type=org_type,
            parent=parent_id or None,
            roleInTime=rit_list,
        )

    for oid, node in nodes_by_id.items():
        if node.parent and node.parent not in nodes_by_id:
            warnings.append(f'Org "{oid}" points to missing parent "{node.parent}".')

    return nodes_by_id, warnings


def build_tree(nodes_by_id: Dict[str, OrgNode]) -> Dict[str, Any]:
    children: Dict[str, List[str]] = {oid: [] for oid in nodes_by_id.keys()}
    roots: List[str] = []

    for oid, node in nodes_by_id.items():
        p = node.parent
        if p and p in nodes_by_id:
            children[p].append(oid)
        else:
            roots.append(oid)

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
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="infile", required=True)
    ap.add_argument("--out-tree", dest="out_tree", required=True)
    args = ap.parse_args()

    infile = Path(args.infile).expanduser().resolve()
    out_tree = Path(args.out_tree).expanduser().resolve()

    if not infile.exists():
        print(f"ERROR: input file not found: {infile}", file=sys.stderr)
        return 2

    nodes_by_id, warnings = parse_orgs(infile)
    tree_json = build_tree(nodes_by_id)
    write_json(out_tree, tree_json)

    if warnings:
        for w in warnings:
            print(w, file=sys.stderr)

    print(f"OK: wrote tree -> {out_tree}")
    print(f"Nodes: {len(nodes_by_id)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())