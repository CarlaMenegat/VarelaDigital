#!/usr/bin/env python3
import csv
import json
from pathlib import Path


def split_semicolon(s: str) -> list[str]:
    s = (s or "").strip()
    if not s:
        return []
    return [x.strip() for x in s.split(";") if x.strip()]


def unpack_entity(packed: str) -> dict:
    packed = (packed or "").strip()
    if not packed:
        return {"label": "", "uri": "", "aliases": []}

    parts = packed.split("|")
    label = (parts[0] if len(parts) > 0 else "").strip()
    uri = (parts[1] if len(parts) > 1 else "").strip()

    aliases = []
    if len(parts) > 2 and parts[2].strip():
        aliases = [a.strip() for a in parts[2].split("§") if a.strip()]

    return {"label": label, "uri": uri, "aliases": aliases}


def to_int_or_none(x: str):
    x = (x or "").strip()
    if not x:
        return None
    try:
        return int(x)
    except Exception:
        return None


def to_float_or_none(x: str):
    x = (x or "").strip()
    if not x:
        return None
    try:
        return float(x)
    except Exception:
        return None


def year_from_date(date_str: str):
    date_str = (date_str or "").strip()
    if len(date_str) >= 4 and date_str[:4].isdigit():
        return int(date_str[:4])
    return None


def main(csv_path: str, out_json: str) -> None:
    p = Path(csv_path).expanduser().resolve()
    if not p.exists():
        raise SystemExit(f"CSV not found: {p}")

    records = []

    with p.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cv_id = (row.get("cv_id") or "").strip()
            if not cv_id:
                continue

            subject = (row.get("subject") or "").strip()

            author = {
                "label": (row.get("author_name") or "").strip(),
                "uri": (row.get("author_uri") or "").strip(),
                "aliases": [],
            }

            recipient = {
                "label": (row.get("recipient_name") or "").strip(),
                "uri": (row.get("recipient_uri") or "").strip(),
                "aliases": [],
            }

            date = (row.get("date") or "").strip()
            year = to_int_or_none(row.get("year") or "") or year_from_date(date)

            lat = to_float_or_none(row.get("lat") or "")
            lon = to_float_or_none(row.get("long") or "")

            place = {
                "label": (row.get("place_label") or "").strip(),
                "uri": (row.get("place_uri") or "").strip(),
                "aliases": [],
                "lat": lat if lat is not None else None,
                "long": lon if lon is not None else None,
            }

            mentioned_people = [unpack_entity(x) for x in split_semicolon(row.get("mentioned_people") or "")]
            mentioned_orgs = [unpack_entity(x) for x in split_semicolon(row.get("mentioned_orgs") or "")]
            mentioned_places = [unpack_entity(x) for x in split_semicolon(row.get("mentioned_places") or "")]
            mentioned_events = [unpack_entity(x) for x in split_semicolon(row.get("mentioned_events") or "")]
            mentioned_dates = split_semicolon(row.get("mentioned_dates") or "")

            text_file = (row.get("text_file") or "").strip() or f"{cv_id}.xml"
            viewer_url = f"viewer.html?file={text_file}"

            rec = {
                "cv_id": cv_id,
                "subject": subject,
                "author": author,
                "recipient": recipient,
                "date": date,
                "year": year,
                "place": place,
                "mentioned_people": mentioned_people,
                "mentioned_orgs": mentioned_orgs,
                "mentioned_places": mentioned_places,
                "mentioned_events": mentioned_events,
                "mentioned_dates": mentioned_dates,
                "text_file": text_file,
                "viewer_url": viewer_url,
            }

            records.append(rec)

    records.sort(key=lambda d: d.get("cv_id", ""))

    out = Path(out_json).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(records)} records -> {out}")


if __name__ == "__main__":
    CSV = "data/metadata/metadata_all.csv"
    OUT = "data/indexes/indexes.json"
    main(CSV, OUT)