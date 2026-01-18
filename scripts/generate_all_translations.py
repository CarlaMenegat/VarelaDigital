from pathlib import Path
import json
import requests

API_URL = "http://127.0.0.1:8000/translate"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
XML_DIR = PROJECT_ROOT / "data" / "documents_XML"

TARGET_LANG = "en"
OUT_DIR = PROJECT_ROOT / "data" / "translations" / TARGET_LANG

DISCLAIMER = """AI-assisted translation

This English translation was generated offline using a large language model provided by OpenAI.
It has not undergone full human revision and is provided exclusively as a reading aid to improve accessibility.

The translation does not constitute a critical, diplomatic, or scholarly edition.
The authoritative version of this document remains the original Portuguese transcription.

Named entities, editorial decisions, and data modeling are based solely on the original source text.
"""

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    xml_files = sorted(XML_DIR.glob("CV-*.xml"))
    total = len(xml_files)
    print(f"Found {total} documents.")

    for i, xml_path in enumerate(xml_files, start=1):
        file_name = xml_path.name
        stem = xml_path.stem
        out_path = OUT_DIR / f"{stem}.json"

        print(f"[{i}/{total}] Translating {file_name}...")

        try:
            resp = requests.post(
                API_URL,
                json={"file": file_name, "target": TARGET_LANG, "force": True},
                timeout=300
            )

            if resp.status_code != 200:
                print(f"  ERROR {file_name}: {resp.text}")
                continue

            data = resp.json() or {}

            if not data.get("translation"):
                print(f"  WARN {file_name}: empty translation")
                continue

            # Force the agreed disclaimer into the cached JSON
            data["disclaimer"] = DISCLAIMER

            out_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )

            print(f"  OK {file_name} -> {out_path}")

        except Exception as e:
            print(f"  ERROR {file_name}: {e}")

    print("Done.")

if __name__ == "__main__":
    main()