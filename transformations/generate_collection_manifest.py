#!/usr/bin/env python3
import json
import re
from pathlib import Path
from typing import Optional, Tuple, List, Dict

CV_RE = re.compile(r"^CV-(\d+)([a-z]?)\.xml$", re.IGNORECASE)

def parse_cv_filename(name: str) -> Optional[Tuple[int, str]]:
    """
    Returns (number, suffix) where suffix is '' or 'a'..'z'.
    """
    m = CV_RE.match(name)
    if not m:
        return None
    num = int(m.group(1))
    suffix = (m.group(2) or "").lower()
    return (num, suffix)

def sort_key(item: Dict) -> Tuple[int, int]:
    """
    Sort by numeric part, then suffix ('' first, then a..z).
    """
    num = item["num"]
    suffix = item["suffix"]
    suffix_rank = 0 if suffix == "" else (ord(suffix) - ord("a") + 1)
    return (num, suffix_rank)

def main(
    xml_dir: str,
    out_json: str,
    max_num: Optional[int] = 300
) -> None:
    xml_path = Path(xml_dir).expanduser().resolve()
    if not xml_path.exists() or not xml_path.is_dir():
        raise SystemExit(f"XML dir not found: {xml_path}")

    files = []
    for p in xml_path.iterdir():
        if not p.is_file():
            continue
        parsed = parse_cv_filename(p.name)
        if not parsed:
            continue
        num, suffix = parsed
        if max_num is not None and num > max_num:
            continue
        stem = p.stem  # e.g., "CV-147a"
        files.append({"id": stem, "file": p.name, "num": num, "suffix": suffix})

    files.sort(key=sort_key)

    # remove sort-only fields
    out: List[Dict[str, str]] = [{"id": x["id"], "file": x["file"]} for x in files]

    out_path = Path(out_json).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {len(out)} items -> {out_path}")

if __name__ == "__main__":
    # Adjust defaults here if you want, but you can also pass arguments by editing variables below.
    XML_DIR = "/Users/carlamenegat/Documents/GitHub/Untitled/VarelaDigital/data/documents_XML"
    OUT_JSON = "/Users/carlamenegat/Documents/GitHub/Untitled/VarelaDigital/data/indexes/collection.json"
    MAX_NUM = 300  # set None to include all

    main(XML_DIR, OUT_JSON, MAX_NUM)