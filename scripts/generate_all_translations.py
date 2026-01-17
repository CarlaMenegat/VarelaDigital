from pathlib import Path
import json
import requests

API_URL = "http://127.0.0.1:8000/translate"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
XML_DIR = PROJECT_ROOT / "data" / "documents_XML"

TARGET_LANG = "en"

def main():
    xml_files = sorted(XML_DIR.glob("CV-*.xml"))

    total = len(xml_files)
    print(f"Found {total} documents.")

    for i, xml_path in enumerate(xml_files, start=1):
        file_name = xml_path.name
        print(f"[{i}/{total}] Translating {file_name}...")

        try:
            resp = requests.post(
                API_URL,
                json={
                    "file": file_name,
                    "target": TARGET_LANG,
                    "force": True
                },
                timeout=300
            )

            if resp.status_code != 200:
                print(f"  ERROR {file_name}: {resp.text}")
                continue

            data = resp.json()

            # sanity check
            if not data.get("translation"):
                print(f"  WARN {file_name}: empty translation")
                continue

            print(f"  OK {file_name}")

        except Exception as e:
            print(f"  ERROR {file_name}: {e}")

    print("Done.")

if __name__ == "__main__":
    main()