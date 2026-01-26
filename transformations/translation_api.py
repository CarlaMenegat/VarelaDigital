from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

import json
import os
import re
from pathlib import Path
from typing import Literal, List

from fastapi import FastAPI, HTTPException
from lxml import etree
from openai import OpenAI
from pydantic import BaseModel

# =========================================================
# Paths & constants
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
XML_DIR = DATA_DIR / "documents_XML"
TRANSLATIONS_DIR = DATA_DIR / "translations"

TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}

DISCLAIMER = (
    "AI-assisted translation\n"
    "This English translation was generated automatically using a large language model.\n"
    "It has not undergone full human revision and is provided for accessibility and reading purposes only.\n"
    "The authoritative version of this document remains the original Portuguese transcription."
)

app = FastAPI(title="Varela Digital – Translation API")

# =========================================================
# Models
# =========================================================

class TranslateReq(BaseModel):
    file: str
    target: Literal["en"] = "en"
    force: bool = False

# =========================================================
# Utilities
# =========================================================

def _stem(file: str) -> str:
    return re.sub(r"\.xml$", "", file.strip(), flags=re.I)

def _cache_path(file: str, target: str) -> Path:
    return TRANSLATIONS_DIR / target / f"{_stem(file)}.json"

def _read_tei(file: str) -> etree._ElementTree:
    path = XML_DIR / file
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"XML not found: {path}")
    parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=False)
    return etree.parse(str(path), parser)

# =========================================================
# TEI → reading text extraction
# =========================================================

def _extract_reading_text(doc: etree._ElementTree) -> str:
    """
    Extract a reading-friendly linear text for translation.

    Includes:
    - opener / closer
    - paragraphs
    - notes (including endorsement)
    - lists
    - tables

    Excludes:
    - pb
    - seg[@type='folio']
    """
    divs = doc.xpath("//tei:text//tei:body//tei:div[1]", namespaces=TEI_NS)
    if not divs:
        return ""

    div = divs[0]
    div_copy = etree.fromstring(etree.tostring(div))

    # choice → expan
    for choice in div_copy.xpath(".//tei:choice", namespaces=TEI_NS):
        expan = choice.xpath("./tei:expan", namespaces=TEI_NS)
        if expan:
            parent = choice.getparent()
            if parent is not None:
                parent.replace(choice, expan[0])

    # remove pb and folio seg
    for el in div_copy.xpath(".//tei:pb | .//tei:seg[@type='folio']", namespaces=TEI_NS):
        parent = el.getparent()
        if parent is not None:
            parent.remove(el)

    def norm(s: str) -> str:
        return " ".join((s or "").split()).strip()

    def serialize_table(table: etree._Element) -> str:
        rows: List[str] = []
        for row in table.xpath("./tei:row", namespaces=TEI_NS):
            cells = [
                norm(" ".join(cell.itertext()))
                for cell in row.xpath("./tei:cell", namespaces=TEI_NS)
            ]
            if any(cells):
                rows.append(" | ".join(cells))
        return "\n".join(rows)

    def serialize_list(lst: etree._Element) -> str:
        items_out: List[str] = []
        for item in lst.xpath("./tei:item", namespaces=TEI_NS):
            t = norm(" ".join(item.itertext()))
            if t:
                items_out.append(f"- {t}")
        return "\n".join(items_out)

    blocks: List[str] = []

    # walk top-level children in document order
    for el in div_copy.iterchildren():
        ln = etree.QName(el).localname

        if ln == "table":
            t = serialize_table(el)
            if t:
                blocks.append(t)
            continue

        if ln == "list":
            t = serialize_list(el)
            if t:
                blocks.append(t)
            continue

        t = norm(" ".join(el.itertext()))
        if t:
            blocks.append(t)

    if not blocks:
        return norm(" ".join(div_copy.itertext()))

    return "\n\n".join(blocks)

# =========================================================
# Language detection
# =========================================================

def _detect_src_lang(text: str) -> str:
    es = len(re.findall(r"\b(usted|señor|señora|muy|del|una|por|con)\b", text.lower()))
    pt = len(re.findall(r"\b(vossa|senhor|senhora|muito|do|da|uma|por|com)\b", text.lower()))
    return "es" if es > pt + 2 else "pt"

# =========================================================
# OpenAI
# =========================================================

def _get_client() -> OpenAI:
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(
            status_code=500,
            detail="OPENAI_API_KEY is not set in the environment.",
        )
    return OpenAI(timeout=120)

def _extract_response_text(resp) -> str:
    txt = getattr(resp, "output_text", None)
    if isinstance(txt, str) and txt.strip():
        return txt.strip()

    parts: List[str] = []
    for item in getattr(resp, "output", []) or []:
        if getattr(item, "type", None) == "message":
            for c in getattr(item, "content", []) or []:
                if getattr(c, "type", None) == "output_text" and c.text:
                    parts.append(c.text)

    return "\n".join(parts).strip()

def _translate_openai(text: str, src_lang: str, target: str) -> dict:
    client = _get_client()
    model = os.getenv("OPENAI_TRANSLATION_MODEL", "gpt-4.1-mini")

    instructions = (
        "You are a careful translation engine for a historical documents corpus.\n"
        "Translate the input text to English.\n"
        "Rules:\n"
        "- Keep proper names as they appear; do not modernize spelling.\n"
        "- Preserve paragraph breaks and list structure.\n"
        "- Do not add commentary, headings, or notes.\n"
        "Return ONLY the translated text."
    )

    try:
        resp = client.responses.create(
            model=model,
            instructions=instructions,
            input=text,
        )
    except Exception as e:
        msg = str(e)
        if "429" in msg:
            raise HTTPException(status_code=402, detail="OpenAI quota/rate limit error.")
        if "401" in msg:
            raise HTTPException(status_code=401, detail="OpenAI authentication error.")
        raise HTTPException(status_code=500, detail=f"OpenAI request failed: {msg}")

    out = _extract_response_text(resp)
    if not out:
        raise HTTPException(status_code=500, detail="Empty translation output from model.")

    return {
        "model": model,
        "source_lang": src_lang,
        "target_lang": target,
        "translation": out,
    }

# =========================================================
# API endpoint
# =========================================================

@app.post("/translate")
def translate(req: TranslateReq):
    cache_path = _cache_path(req.file, req.target)

    if cache_path.exists() and not req.force:
        return json.loads(cache_path.read_text(encoding="utf-8"))

    doc = _read_tei(req.file)
    src_text = _extract_reading_text(doc)
    if not src_text:
        raise HTTPException(status_code=400, detail="Could not extract text from TEI.")

    src_lang = _detect_src_lang(src_text)
    payload = _translate_openai(src_text, src_lang, req.target)

    out = {
        "file": req.file,
        "stem": _stem(req.file),
        "disclaimer": DISCLAIMER,
        **payload,
    }

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out