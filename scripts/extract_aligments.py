#!/usr/bin/env python3
"""
Generate /data/indexes/alignments.json from TEI standoff_persons.xml

- uri-first matching (Wikidata/VIAF/project URIs)
- time-aware segments from <state type="roleInTime"> + <affiliation ref="#..."> + <date .../>
- fallback: <person><affiliation/></person> generates a segment spanning the conflict window
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET


TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}

# ----------------------------
# Configure project URI pattern
# ----------------------------

PROJECT_PERSON_BASE = "https://carlamenegat.github.io/VarelaDigital/person/"

# ----------------------------
# Configure affiliations
# ----------------------------

IMPERIO = {
    "imperio_brasil",
    "justica_imperial",
    "arsenal_guerra",
    "guardas_nacionais_3corpo",
    "primeiro_batalhao_fuzileiros",
    "segundo_corpo",
    "conselho_supremo_militar",
    "cavalaria_3regimento",
    "exercito_imperial",
}

FARROUPILHA = {
    "republica_rio_grandense",
    "corpo_lanceiros_negros",
    "exercito_farroupilha",
    "procuradoria_fiscal",
    "contadoria_geral",
    "4corpo_1brigada",
    "3cia_esquadrao_pelotas",
    "jornal_o_povo",
    "republica_juliana",
    "tesouro",
    "marinha_farroupilha",
    "secretaria_guerra",
    "corpo_cavalaria_2",
    "corpo_5_farroupilhas",
}

CONFLICT_FROM = "1835-01-01"
CONFLICT_TO = "1845-12-31"


# ----------------------------
# Helpers
# ----------------------------

def strip_hash(s: str) -> str:
    s = (s or "").strip()
    return s[1:] if s.startswith("#") else s

def looks_like_url(s: str) -> bool:
    return bool(re.match(r"^https?://", (s or "").strip(), re.I))

def normalize_when(s: str) -> Optional[str]:
    """
    Accept: YYYY, YYYY-MM, YYYY-MM-DD
    Return ISO YYYY-MM-DD (best-effort), or None.
    """
    s = (s or "").strip()
    if not s:
        return None

    # YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s

    # YYYY-MM -> YYYY-MM-01
    if re.match(r"^\d{4}-\d{2}$", s):
        return f"{s}-01"

    # YYYY -> YYYY-01-01
    if re.match(r"^\d{4}$", s):
        return f"{s}-01-01"

    return None

def pick_best_persname(person_el: ET.Element) -> str:
    """
    Prefer persName without @type="popular". Fallback to first persName.
    """
    names = person_el.findall("tei:persName", TEI_NS)
    if not names:
        return ""

    for n in names:
        if (n.get("type") or "").strip().lower() != "popular":
            return (n.text or "").strip()

    return (names[0].text or "").strip()

def collect_uris(person_el: ET.Element, xml_id: str) -> List[str]:
    """
    Collect:
      1) Project URI (always)
      2) Any idno that looks like a URL (wikidata/viaf/project, etc.)
      3) Any @ref attributes that look like URLs
    """
    uris: List[str] = []

    # 1) Always include project URI based on xml:id
    if xml_id:
        uris.append(f"{PROJECT_PERSON_BASE}{xml_id}")

    # 2) idno elements can hold URLs
    for idno in person_el.findall("tei:idno", TEI_NS):
        val = (idno.text or "").strip()
        if looks_like_url(val):
            uris.append(val)

    # 3) Sometimes canonical URI is stored in @ref on persName/other elements
    for el in person_el.findall(".//*[@ref]", TEI_NS):
        ref = (el.get("ref") or "").strip()
        if looks_like_url(ref):
            uris.append(ref)

    # De-dupe while preserving order
    seen = set()
    out = []
    for u in uris:
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out

def find_affiliations(el: ET.Element) -> List[str]:
    """
    Return normalized affiliation refs inside `el` (stripped of leading #).
    """
    out = []
    for a in el.findall("tei:affiliation", TEI_NS):
        ref = strip_hash(a.get("ref") or "")
        if ref:
            out.append(ref)
    return out

def side_from_affiliations(affs: List[str]) -> Optional[str]:
    has_imp = any(a in IMPERIO for a in affs)
    has_far = any(a in FARROUPILHA for a in affs)
    if has_imp and has_far:
        return "mixed"
    if has_imp:
        return "imperio"
    if has_far:
        return "farroupilha"
    return None

def extract_state_dates(state_el: ET.Element) -> Tuple[Optional[str], Optional[str]]:
    """
    Try to read a time span from:
      - <date type="begin" when="..."/>
      - <date type="end" when="..."/>
      - <date from="..." to="..."/>
      - <date when="..."/>
    Return (from_iso, to_iso) possibly None.
    """
    from_iso = None
    to_iso = None

    # date[@from]/[@to]
    for d in state_el.findall("tei:date", TEI_NS):
        f = normalize_when(d.get("from") or "")
        t = normalize_when(d.get("to") or "")
        if f and not from_iso:
            from_iso = f
        if t and not to_iso:
            to_iso = t

    # date[@type=begin/end]
    for d in state_el.findall("tei:date", TEI_NS):
        typ = (d.get("type") or "").strip().lower()
        w = normalize_when(d.get("when") or "")
        if typ == "begin" and w:
            from_iso = w
        elif typ == "end" and w:
            to_iso = w

    # date[@when] fallback
    if not from_iso:
        for d in state_el.findall("tei:date", TEI_NS):
            w = normalize_when(d.get("when") or "")
            if w:
                from_iso = w
                break

    return from_iso, to_iso

@dataclass
class Segment:
    side: str
    from_: str
    to: str

    def as_dict(self) -> Dict[str, str]:
        return {"side": self.side, "from": self.from_, "to": self.to}

def clamp_to_conflict_window(from_iso: Optional[str], to_iso: Optional[str]) -> Tuple[str, str]:
    """
    Ensure every segment stays within [CONFLICT_FROM, CONFLICT_TO] and is fully defined.
    """
    f = from_iso or CONFLICT_FROM
    t = to_iso or CONFLICT_TO

    # naive string compare works for ISO dates
    if f < CONFLICT_FROM:
        f = CONFLICT_FROM
    if t > CONFLICT_TO:
        t = CONFLICT_TO

    # If reversed, swap (defensive)
    if t < f:
        f, t = t, f

    return f, t

def extract_timeline(person_el: ET.Element) -> List[Segment]:
    """
    Build segments from roleInTime states. If none yield a side, fallback to person-level affiliation.
    """
    segments: List[Segment] = []

    # roleInTime states first
    for st in person_el.findall("tei:state", TEI_NS):
        if (st.get("type") or "").strip() != "roleInTime":
            continue

        affs = find_affiliations(st)
        side = side_from_affiliations(affs)
        if not side:
            continue

        f, t = extract_state_dates(st)
        f2, t2 = clamp_to_conflict_window(f, t)
        segments.append(Segment(side=side, from_=f2, to=t2))

    # fallback: person-level affiliation (no time, so clamp to conflict window)
    if not segments:
        affs = find_affiliations(person_el)
        side = side_from_affiliations(affs)
        if side:
            f2, t2 = clamp_to_conflict_window(None, None)
            segments.append(Segment(side=side, from_=f2, to=t2))

    return segments

def build_alignments(standoff_xml: Path) -> Dict[str, Any]:
    tree = ET.parse(standoff_xml)
    root = tree.getroot()

    persons = root.findall(".//tei:person", TEI_NS)

    by_id: Dict[str, Any] = {}
    by_uri: Dict[str, Any] = {}

    for p in persons:
        xml_id = (p.get("{http://www.w3.org/XML/1998/namespace}id") or "").strip()
        if not xml_id:
            continue

        label = pick_best_persname(p) or xml_id
        uris = collect_uris(p, xml_id)
        timeline = [seg.as_dict() for seg in extract_timeline(p)]

        by_id[xml_id] = {
            "label": label,
            "uris": uris,
            "timeline": timeline,
        }

        for u in uris:
            if u not in by_uri:
                by_uri[u] = {"label": label, "timeline": []}

            existing = {json.dumps(x, sort_keys=True) for x in by_uri[u]["timeline"]}
            for seg in timeline:
                key = json.dumps(seg, sort_keys=True)
                if key not in existing:
                    by_uri[u]["timeline"].append(seg)
                    existing.add(key)

    return {
        "byUri": by_uri,
        "byId": by_id,
        "meta": {
            "conflictWindow": {"from": CONFLICT_FROM, "to": CONFLICT_TO},
            "sides": ["farroupilha", "imperio", "mixed"],
            "projectPersonBase": PROJECT_PERSON_BASE,
        },
    }

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--standoff", required=True, help="Path to standoff_persons.xml")
    parser.add_argument("--out", required=True, help="Path to write alignments.json")
    args = parser.parse_args()

    standoff = Path(args.standoff).expanduser().resolve()
    out = Path(args.out).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    data = build_alignments(standoff)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote: {out}  (byUri={len(data['byUri'])}, byId={len(data['byId'])})")

if __name__ == "__main__":
    main()