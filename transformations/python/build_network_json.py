#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import itertools
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional

from rdflib import Graph, URIRef, Literal
from rdflib.namespace import RDF, RDFS

# -----------------------------
# Paths (fixed)
# -----------------------------

BASE_DIR = Path("/Users/carlamenegat/Documents/GitHub/Untitled/VarelaDigital")
IN_RDF = BASE_DIR / "data/rdf/graph.ttl"         
OUT_DIR = BASE_DIR / "data/network"
OUT_JSON = OUT_DIR / "network.json"

# -----------------------------
# URI bases / predicates
# -----------------------------

DCTERMS_BASE = "http://purl.org/dc/terms/"
PRO_BASE = "http://purl.org/spar/pro/"
SCHEMA_BASE = "http://schema.org/"
FOAF_BASE = "http://xmlns.com/foaf/0.1/"

P_CREATOR = URIRef(DCTERMS_BASE + "creator")
P_DATE = URIRef(DCTERMS_BASE + "date")
P_ADDRESSEE = URIRef(PRO_BASE + "addressee")
P_MENTIONS = URIRef(SCHEMA_BASE + "mentions")
P_SAMEAS = URIRef(SCHEMA_BASE + "sameAs")

FOAF_PERSON = URIRef(FOAF_BASE + "Person")

PERSON_BASE = "https://carlamenegat.github.io/VarelaDigital/person/"
LETTER_BASE = "https://carlamenegat.github.io/VarelaDigital/letter/"

# No teu site: viewer.html?file=CV-1.xml
VIEWER_URL_PATTERN = "viewer.html?file={cv_id}.xml"

# -----------------------------
# Helpers
# -----------------------------

def is_uri(x) -> bool:
    return isinstance(x, URIRef)

def is_person_internal(u: URIRef) -> bool:
    return str(u).startswith(PERSON_BASE)

def is_letter(u: URIRef) -> bool:
    return str(u).startswith(LETTER_BASE)

def cv_id_from_letter_uri(u: URIRef) -> str:
    return str(u).rsplit("/", 1)[-1]

def label_from_literals(vals: List[Literal]) -> str:
    if not vals:
        return ""
    # prefer pt / pt-BR
    for v in vals:
        if isinstance(v, Literal) and (v.language in ("pt", "pt-BR")):
            return str(v)
    return str(vals[0])

def literal_to_str(o) -> Optional[str]:
    if o is None:
        return None
    return str(o) if isinstance(o, Literal) else str(o)

def minmax_date_str(existing_min: Optional[str], existing_max: Optional[str], new_val: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    if not new_val:
        return existing_min, existing_max
    mn = existing_min
    mx = existing_max
    if mn is None or new_val < mn:
        mn = new_val
    if mx is None or new_val > mx:
        mx = new_val
    return mn, mx

# -----------------------------
# sameAs canonicalization
# -----------------------------

def build_person_sameas_index(g: Graph) -> Dict[str, str]:
    """
    external_uri -> internal_person_uri
    from: (internal_person schema:sameAs external_uri)
    """
    idx: Dict[str, str] = {}
    for s in g.subjects(RDF.type, FOAF_PERSON):
        if not is_uri(s) or not is_person_internal(s):
            continue
        for o in g.objects(s, P_SAMEAS):
            if is_uri(o):
                idx[str(o)] = str(s)
    return idx

def canonical_person_uri(g: Graph, u: URIRef, sameas_idx: Dict[str, str]) -> Optional[str]:
    """
    Return canonical person URI string:
    - if internal /person/ -> keep
    - else if external mapped via sameAs -> mapped
    - else if typed as foaf:Person -> keep external
    - else None
    """
    if not is_uri(u):
        return None

    us = str(u)
    if us.startswith(PERSON_BASE):
        return us

    mapped = sameas_idx.get(us)
    if mapped:
        return mapped

    if (u, RDF.type, FOAF_PERSON) in g:
        return us

    return None

# -----------------------------
# Data structures
# -----------------------------

@dataclass
class EdgeAgg:
    weight: int = 0
    evidence: Set[str] = None
    date_min: Optional[str] = None
    date_max: Optional[str] = None

    def __post_init__(self):
        if self.evidence is None:
            self.evidence = set()

    def add_evidence(self, cv_id: str, date_str: Optional[str]) -> None:
        self.weight += 1
        self.evidence.add(cv_id)
        self.date_min, self.date_max = minmax_date_str(self.date_min, self.date_max, date_str)

# -----------------------------
# Build network
# -----------------------------

def build_network() -> dict:
    g = Graph()
    g.parse(str(IN_RDF), format="turtle")

    sameas_idx = build_person_sameas_index(g)

    # 1) Person labels
    person_labels: Dict[str, str] = {}

    for s in set(g.subjects(RDF.type, FOAF_PERSON)):
        if not is_uri(s):
            continue

        s_str = str(s)
        labels = list(g.objects(s, RDFS.label))
        person_labels[s_str] = label_from_literals(labels) or s_str.rsplit("/", 1)[-1]

        # Project internal label onto external sameAs keys (helps UI if any external slips in)
        if is_person_internal(s):
            for o in g.objects(s, P_SAMEAS):
                if is_uri(o):
                    o_str = str(o)
                    if o_str not in person_labels:
                        person_labels[o_str] = person_labels[s_str]

    corr: Dict[Tuple[str, str], EdgeAgg] = defaultdict(EdgeAgg)
    com: Dict[Tuple[str, str], EdgeAgg] = defaultdict(EdgeAgg)

    letters: Set[URIRef] = set()
    for s in g.subjects(P_CREATOR, None):
        if is_uri(s) and is_letter(s):
            letters.add(s)
    for s in g.subjects(P_ADDRESSEE, None):
        if is_uri(s) and is_letter(s):
            letters.add(s)
    for s in g.subjects(P_MENTIONS, None):
        if is_uri(s) and is_letter(s):
            letters.add(s)

    for letter in letters:
        cv_id = cv_id_from_letter_uri(letter)

        date_vals = list(g.objects(letter, P_DATE))
        date_str = literal_to_str(date_vals[0]) if date_vals else None

        creators = []
        for o in g.objects(letter, P_CREATOR):
            if is_uri(o):
                cu = canonical_person_uri(g, o, sameas_idx)
                if cu:
                    creators.append(cu)

        addressees = []
        for o in g.objects(letter, P_ADDRESSEE):
            if is_uri(o):
                au = canonical_person_uri(g, o, sameas_idx)
                if au:
                    addressees.append(au)

        for c in creators:
            for a in addressees:
                if c != a:
                    corr[(c, a)].add_evidence(cv_id, date_str)

        mentioned_people: Set[str] = set()
        for o in g.objects(letter, P_MENTIONS):
            if not is_uri(o):
                continue
            mu = canonical_person_uri(g, o, sameas_idx)
            if mu:
                mentioned_people.add(mu)

        for u, v in itertools.combinations(sorted(mentioned_people), 2):
            if u == v:
                continue
            key = (u, v) if u < v else (v, u)
            com[key].add_evidence(cv_id, date_str)

    node_ids: Set[str] = set()
    for (s, t) in corr.keys():
        node_ids.add(s)
        node_ids.add(t)
    for (s, t) in com.keys():
        node_ids.add(s)
        node_ids.add(t)

    nodes = []
    for pid in sorted(node_ids):
        nodes.append({
            "id": pid,
            "label": person_labels.get(pid, pid.rsplit("/", 1)[-1]),
            "type": "Person",
        })

    edges = []

    for (s, t), agg in corr.items():
        edges.append({
            "id": f"corr:{s}->{t}",
            "type": "correspondence",
            "source": s,
            "target": t,
            "directed": True,
            "weight": agg.weight,
            "evidence": sorted(agg.evidence),
            "dateMin": agg.date_min,
            "dateMax": agg.date_max,
        })

    for (s, t), agg in com.items():
        edges.append({
            "id": f"com:{s}--{t}",
            "type": "comention",
            "source": s,
            "target": t,
            "directed": False,
            "weight": agg.weight,
            "evidence": sorted(agg.evidence),
            "dateMin": agg.date_min,
            "dateMax": agg.date_max,
        })

    return {
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "source": "graph.ttl",
            "input": str(IN_RDF),
            "viewerUrlPattern": VIEWER_URL_PATTERN,
            "note": {
                "comention": "Derived: two persons are connected if they are mentioned in the same letter.",
                "correspondence": "Derived from dcterms:creator and pro:addressee on letters.",
                "canonicalization": "External person URIs are mapped to internal /person/ URIs via schema:sameAs when available."
            }
        }
    }

def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    network = build_network()
    OUT_JSON.write_text(json.dumps(network, ensure_ascii=False, indent=2), encoding="utf-8")
    print("✔ network.json generated:")
    print("  ", OUT_JSON)

if __name__ == "__main__":
    main()