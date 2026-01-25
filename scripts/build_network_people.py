#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import itertools
from collections import defaultdict
from pathlib import Path
from typing import Dict, Set, Tuple, Optional

from rdflib import Graph, URIRef, Literal
from rdflib.namespace import RDF, RDFS

# --------------------------------------------------
# Paths
# --------------------------------------------------

BASE_DIR = Path("/Users/carlamenegat/Documents/GitHub/Untitled/VarelaDigital")
IN_RDF = BASE_DIR / "data/rdf/graph.ttl"
OUT_DIR = BASE_DIR / "data/network"
OUT_JSON = OUT_DIR / "network_people.json"

# --------------------------------------------------
# Namespaces / predicates
# --------------------------------------------------

DCTERMS_CREATOR = URIRef("http://purl.org/dc/terms/creator")
PRO_ADDRESSEE = URIRef("http://purl.org/spar/pro/addressee")
SCHEMA_MENTIONS = URIRef("http://schema.org/mentions")
SCHEMA_SAMEAS = URIRef("http://schema.org/sameAs")

FOAF_PERSON = URIRef("http://xmlns.com/foaf/0.1/Person")

PERSON_BASE = "https://carlamenegat.github.io/VarelaDigital/person/"
LETTER_BASE = "https://carlamenegat.github.io/VarelaDigital/letter/"

# --------------------------------------------------
# Helpers
# --------------------------------------------------

def is_uri(x) -> bool:
    return isinstance(x, URIRef)

def is_person_internal(u: URIRef) -> bool:
    return str(u).startswith(PERSON_BASE)

def is_letter(u: URIRef) -> bool:
    return str(u).startswith(LETTER_BASE)

def cv_id(letter_uri: URIRef) -> str:
    return str(letter_uri).rsplit("/", 1)[-1]

def literal_to_str(v) -> str:
    return str(v) if isinstance(v, Literal) else str(v)

# --------------------------------------------------
# Canonicalization (sameAs)
# --------------------------------------------------

def build_person_sameas_index(g: Graph) -> Dict[str, str]:
    """
    Returns a mapping: external_uri -> internal_person_uri
    based on (internal_person schema:sameAs external_uri).
    """
    idx: Dict[str, str] = {}

    # only for internal persons
    for s in g.subjects(RDF.type, FOAF_PERSON):
        if not is_uri(s):
            continue
        if not is_person_internal(s):
            continue

        for o in g.objects(s, SCHEMA_SAMEAS):
            if is_uri(o):
                idx[str(o)] = str(s)

    return idx

def canonical_person_uri(g: Graph, u: URIRef, sameas_idx: Dict[str, str]) -> Optional[str]:
    """
    Return a canonical person URI string, preferring internal /person/ URIs.

    Accept if:
    - already internal person URI
    - external URI that maps via sameAs -> internal
    - external URI typed as foaf:Person (fallback, keep as-is)

    Otherwise return None.
    """
    if not is_uri(u):
        return None

    us = str(u)

    if us.startswith(PERSON_BASE):
        return us

    # try sameAs mapping
    mapped = sameas_idx.get(us)
    if mapped:
        return mapped

    # fallback: accept as person if typed as foaf:Person
    if (u, RDF.type, FOAF_PERSON) in g:
        return us

    return None

# --------------------------------------------------
# Main
# --------------------------------------------------

def build_network() -> dict:
    g = Graph()
    g.parse(str(IN_RDF), format="turtle")

    sameas_idx = build_person_sameas_index(g)

    # ---- labels ----
    # Build labels for internal persons, and also allow fallback for external persons if they appear.
    labels: Dict[str, str] = {}

    # Prefer labels from internal persons
    for s in g.subjects(RDF.type, FOAF_PERSON):
        if not is_uri(s):
            continue

        s_str = str(s)
        lbls = list(g.objects(s, RDFS.label))
        if lbls:
            labels[s_str] = literal_to_str(lbls[0]).strip() or s_str.rsplit("/", 1)[-1]
        else:
            labels[s_str] = s_str.rsplit("/", 1)[-1]

        # If internal has sameAs, also project that label onto the external URI key (helps UI if external slips in)
        if is_person_internal(s):
            for o in g.objects(s, SCHEMA_SAMEAS):
                if is_uri(o):
                    o_str = str(o)
                    if o_str not in labels:
                        labels[o_str] = labels[s_str]

    # ---- edge aggregators ----
    corr = defaultdict(lambda: {"weight": 0, "evidence": set()})  # key=(s,t)
    com = defaultdict(lambda: {"weight": 0, "evidence": set()})   # key=(u,v) undirected

    # ---- iterate letters ----
    letters = set(g.subjects(DCTERMS_CREATOR, None)) | set(g.subjects(PRO_ADDRESSEE, None))

    for letter in letters:
        if not is_uri(letter) or not is_letter(letter):
            continue

        cid = cv_id(letter)

        creators_raw = list(g.objects(letter, DCTERMS_CREATOR))
        addressees_raw = list(g.objects(letter, PRO_ADDRESSEE))

        creators = []
        for o in creators_raw:
            if is_uri(o):
                cu = canonical_person_uri(g, o, sameas_idx)
                if cu:
                    creators.append(cu)

        addressees = []
        for o in addressees_raw:
            if is_uri(o):
                au = canonical_person_uri(g, o, sameas_idx)
                if au:
                    addressees.append(au)

        # correspondence edges (directed)
        for c in creators:
            for a in addressees:
                if c != a:
                    key = (c, a)
                    corr[key]["weight"] += 1
                    corr[key]["evidence"].add(cid)

        # co-mentions edges (undirected)
        mentioned_set: Set[str] = set()
        for o in g.objects(letter, SCHEMA_MENTIONS):
            if not is_uri(o):
                continue
            mu = canonical_person_uri(g, o, sameas_idx)
            if mu:
                mentioned_set.add(mu)

        for u, v in itertools.combinations(sorted(mentioned_set), 2):
            key = (u, v)
            com[key]["weight"] += 1
            com[key]["evidence"].add(cid)

    # ---- nodes ----
    node_ids: Set[str] = set()
    for s, t in corr.keys():
        node_ids.update([s, t])
    for s, t in com.keys():
        node_ids.update([s, t])

    nodes = [
        {"id": pid, "label": labels.get(pid, pid.rsplit("/", 1)[-1])}
        for pid in sorted(node_ids)
    ]

    # ---- edges ----
    edges = []

    for (s, t), data in corr.items():
        edges.append({
            "id": f"corr:{s}->{t}",
            "type": "correspondence",
            "source": s,
            "target": t,
            "directed": True,
            "weight": data["weight"],
            "evidence": sorted(data["evidence"])
        })

    for (s, t), data in com.items():
        edges.append({
            "id": f"com:{s}--{t}",
            "type": "comention",
            "source": s,
            "target": t,
            "directed": False,
            "weight": data["weight"],
            "evidence": sorted(data["evidence"])
        })

    return {
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "scope": "people-only",
            "note": "Social network derived from correspondence and co-mentions (with sameAs canonicalization)."
        }
    }

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    network = build_network()
    OUT_JSON.write_text(json.dumps(network, ensure_ascii=False, indent=2), encoding="utf-8")
    print("✔ network_people.json generated:")
    print("  ", OUT_JSON)

if __name__ == "__main__":
    main()