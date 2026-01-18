#!/usr/bin/env python3
import csv
import json
from pathlib import Path

def main(csv_path: str, out_json: str) -> None:
    p = Path(csv_path).expanduser().resolve()
    if not p.exists():
        raise SystemExit(f"CSV not found: {p}")

    rows_by_id = {}
    with p.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cv_id = (row.get("cv_id") or "").strip()
            if not cv_id:
                continue
            rows_by_id[cv_id] = row

    out = Path(out_json).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows_by_id, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(rows_by_id)} records -> {out}")

if __name__ == "__main__":
    CSV = "data/metadata/metadata_all.csv"
    OUT = "data/indexes/metadata.json"
    main(CSV, OUT)