import csv
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

INPUT = "/Users/carlamenegat/Documents/GitHub/Untitled/VarelaDigital/data/metadata/metadata_all.csv"
OUTPUT_DIR = Path("/Users/carlamenegat/Documents/GitHub/Untitled/VarelaDigital/data/indexes")
OUTPUT = OUTPUT_DIR / "indexes.json"


def to_int_year(date_str: str):
    date_str = (date_str or "").strip()
    if len(date_str) >= 4 and date_str[:4].isdigit():
        return int(date_str[:4])
    return None


def to_float_or_none(x: str):
    x = (x or "").strip()
    if not x:
        return None
    try:
        return float(x)
    except ValueError:
        return None


def split_list(value: str):
    if not value:
        return []
    return [v.strip() for v in value.split(";") if v.strip()]


def split_entities(value: str):
    if not value:
        return []

    entities = []
    for part in value.split(";"):
        part = part.strip()
        if not part:
            continue

        bits = [b.strip() for b in part.split("|")]
        label = bits[0] if len(bits) >= 1 else part
        uri = bits[1] if len(bits) >= 2 else ""
        aliases = []
        if len(bits) >= 3 and bits[2]:
            aliases = [a.strip() for a in bits[2].split("§") if a.strip()]

        entities.append({"label": label, "uri": uri, "aliases": aliases})

    return entities


def make_viewer_url(text_file: str):
    text_file = (text_file or "").strip()
    return f"viewer.html?file={text_file}" if text_file else "viewer.html"


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    items = []
    with open(INPUT, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            cv_id = (row.get("cv_id") or "").strip()
            subject = (row.get("subject") or "").strip()

            author_name = (row.get("author_name") or "").strip()
            author_uri = (row.get("author_uri") or "").strip()

            recipient_name = (row.get("recipient_name") or "").strip()
            recipient_uri = (row.get("recipient_uri") or "").strip()

            date = (row.get("date") or "").strip()
            year = to_int_year(date)

            place_label = (row.get("place_label") or "").strip()
            place_uri = (row.get("place_uri") or "").strip()

            lat = to_float_or_none(row.get("lat") or "")
            lng = to_float_or_none(row.get("long") or "")

            text_file = (row.get("text_file") or "").strip()
            file_name = Path(text_file).name if text_file else ""

            item = {
                "cv_id": cv_id,
                "subject": subject,
                "author": {"label": author_name, "uri": author_uri, "aliases": []},
                "recipient": {"label": recipient_name, "uri": recipient_uri, "aliases": []},
                "date": date or None,
                "year": year,
                "place": {"label": place_label, "uri": place_uri, "aliases": [], "lat": lat, "long": lng},
                "mentioned_people": split_entities(row.get("mentioned_people") or ""),
                "mentioned_orgs": split_entities(row.get("mentioned_orgs") or ""),
                "mentioned_places": split_entities(row.get("mentioned_places") or ""),
                "mentioned_events": split_entities(row.get("mentioned_events") or ""),
                "mentioned_dates": split_list(row.get("mentioned_dates") or ""),
                "text_file": file_name,
                "viewer_url": make_viewer_url(file_name),
            }

            items.append(item)

    with open(OUTPUT, "w", encoding="utf-8") as out:
        json.dump(items, out, ensure_ascii=False, indent=2)

    print(f"Generated: {OUTPUT}")
    print(f"Items: {len(items)}")


if __name__ == "__main__":
    main()