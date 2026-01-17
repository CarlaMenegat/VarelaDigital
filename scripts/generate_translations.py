#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from lxml import etree
from openai import OpenAI

# ------------------------------------------------------------
# Paths (ajuste se teu layout mudar)
# ------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
XML_DIR = DATA_DIR / "documents_XML"
INDEX_DIR = DATA_DIR / "indexes"
MANIFEST_PATH = INDEX_DIR / "collection.json"   # tua ordem principal
OUT_DIR = DATA_DIR / "translations" / "en"

TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}

DISCLAIMER = (
    "AI-assisted translation\n"
    "This English translation was generated automatically using a large language model.\n"
    "It has not undergone full human revision and is provided for accessibility and reading purposes only.\n"
    "The authoritative version of this document remains the original Portuguese transcription."
)

# Modelo recomendado (barato e bom p/ tradução). Se preferir, exporta OPENAI_TRANSLATION_MODEL.
DEFAULT_MODEL = os.getenv("OPENAI_TRANSLATION_MODEL", "gpt-4o-mini")

client = OpenAI()

# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def stem(file: str) -> str:
    return re.sub(r"\.xml$", "", file.strip(), flags=re.I)

def load_manifest_files() -> list[str]:
    if not MANIFEST_PATH.exists():
        raise SystemExit(f"Manifest not found: {MANIFEST_PATH}")

    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit("collection.json must be a JSON list")

    files: list[str] = []
    for item in data:
        if isinstance(item, str):
            files.append(item.strip())
        elif isinstance(item, dict):
            # aceita {file:"CV-1.xml"} etc
            f = (item.get("file") or item.get("xml") or item.get("path") or "").strip()
            if f:
                files.append(f)
    return [f for f in files if f]

def read_tei(file_name: str) -> etree._ElementTree:
    path = XML_DIR / file_name
    if not path.exists():
        raise FileNotFoundError(f"XML not found: {path}")
    parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=False)
    return etree.parse(str(path), parser)

def extract_reading_text(doc: etree._ElementTree) -> str:
    """
    Reading-friendly extraction:
    - inside <choice>, prefer <expan> when present
    - drop <pb> and <seg type="folio">
    - keep paragraph breaks
    """
    div = doc.xpath("//tei:text/tei:body/tei:div[1]", namespaces=TEI_NS)
    if not div:
        return ""
    div = div[0]

    div_copy = etree.fromstring(etree.tostring(div))

    # choice -> expan
    for choice in div_copy.xpath(".//tei:choice", namespaces=TEI_NS):
        expan = choice.xpath("./tei:expan", namespaces=TEI_NS)
        if expan:
            choice.getparent().replace(choice, expan[0])

    # remove pb
    for pb in div_copy.xpath(".//tei:pb", namespaces=TEI_NS):
        pb.getparent().remove(pb)

    # remove folio seg
    for seg in div_copy.xpath(".//tei:seg[@type='folio']", namespaces=TEI_NS):
        seg.getparent().remove(seg)

    ps = div_copy.xpath(".//tei:p", namespaces=TEI_NS)
    if ps:
        out = []
        for p in ps:
            t = " ".join(" ".join(p.itertext()).split())
            if t:
                out.append(t)
        return "\n\n".join(out).strip()

    return "\n".join(" ".join(div_copy.itertext()).split()).strip()

def detect_src_lang(text: str) -> str:
    # heurística leve (só metadata)
    low = text.lower()
    es = len(re.findall(r"\b(usted|señor|señora|muy|del|una|por|con)\b", low))
    pt = len(re.findall(r"\b(vossa|senhor|senhora|muito|do|da|uma|por|com)\b", low))
    return "es" if es > pt + 2 else "pt"

def translate_openai(text: str, src_lang: str) -> dict[str, Any]:
    instructions = (
        "You are a careful translation engine for a historical letters corpus.\n"
        "Translate the input text to English.\n"
        "Rules:\n"
        "- Keep proper names as they appear; do not modernize spelling.\n"
        "- Preserve paragraph breaks.\n"
        "- Do not add commentary, headings, or notes.\n"
        "- If the source is Spanish or Portuguese (or mixed), translate everything to English.\n"
        "Return ONLY the translated text.\n"
    )

    # Responses API: peça output só texto (evita “vazio” / formatos estranhos)
    resp = client.responses.create(
        model=DEFAULT_MODEL,
        instructions=instructions,
        input=text,
        text={"format": {"type": "text"}},
        # evita “reasoning.effort” etc (alguns modelos não suportam)
    )

    # Forma mais robusta: usar o atalho `.output_text` quando disponível
    out = getattr(resp, "output_text", None)
    if not out:
        # fallback: varre blocos
        pieces = []
        for item in (resp.output or []):
            if getattr(item, "type", None) == "message":
                for c in getattr(item, "content", []) or []:
                    if getattr(c, "type", None) == "output_text":
                        pieces.append(getattr(c, "text", ""))
        out = "".join(pieces).strip()

    if not out or not out.strip():
        raise RuntimeError("Empty translation output from model.")
    return {"model": DEFAULT_MODEL, "source_lang": src_lang, "target_lang": "en", "translation": out.strip()}

def write_json(out_path: Path, payload: dict[str, Any]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

# ------------------------------------------------------------
# Main
# ------------------------------------------------------------
def main() -> None:
    files = load_manifest_files()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    total = len(files)
    done = 0
    skipped = 0

    for i, f in enumerate(files, start=1):
        out_path = OUT_DIR / f"{stem(f)}.json"
        if out_path.exists():
            skipped += 1
            print(f"[{i}/{total}] SKIP {f} (cached)")
            continue

        try:
            doc = read_tei(f)
            src_text = extract_reading_text(doc)
            if not src_text:
                print(f"[{i}/{total}] WARN {f}: empty extracted text")
                continue

            src_lang = detect_src_lang(src_text)
            tr = translate_openai(src_text, src_lang)

            payload = {
                "file": f,
                "stem": stem(f),
                "disclaimer": DISCLAIMER,
                **tr,
            }
            write_json(out_path, payload)
            done += 1
            print(f"[{i}/{total}] OK   {f} -> {out_path.relative_to(PROJECT_ROOT)}")

            # throttle leve pra não tomar 429
            time.sleep(0.25)

        except Exception as e:
            print(f"[{i}/{total}] ERROR {f}: {e}")
            # backoff básico
            time.sleep(2.0)

    print(f"\nDone. Generated: {done}, skipped: {skipped}, total in manifest: {total}")
    print(f"Output dir: {OUT_DIR}")

if __name__ == "__main__":
    main()