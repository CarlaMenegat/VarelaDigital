#!/usr/bin/env python3
# scripts/generate_all_html.py

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def find_project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def iter_xml_files(xml_dir: Path) -> list[Path]:
    files = sorted(xml_dir.glob("*.xml"))
    return [p for p in files if p.is_file()]


def run_xsltproc(xslt_path: Path, xml_path: Path, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "xsltproc",
        "--novalid",
        "-o",
        str(out_path),
        str(xslt_path),
        str(xml_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        stdout = (proc.stdout or "").strip()
        msg = "\n".join([x for x in [stdout, stderr] if x])
        raise RuntimeError(msg or f"xsltproc failed for {xml_path.name}")


def main() -> int:
    root = find_project_root()

    default_xml_dir = root / "data" / "documents_XML"
    default_out_dir = root / "assets" / "html" / "documents_html"
    default_xslt = root / "scripts" / "xslt" / "tei2html.xsl"

    ap = argparse.ArgumentParser(
        prog="generate_all_html.py",
        description="Generate HTML documents from TEI XML using xsltproc.",
    )
    ap.add_argument("--xml-dir", type=Path, default=default_xml_dir)
    ap.add_argument("--out-dir", type=Path, default=default_out_dir)
    ap.add_argument("--xslt", type=Path, default=default_xslt)
    ap.add_argument(
        "--only",
        type=str,
        default="",
        help='Generate only one file (e.g. "CV-23.xml" or "CV-23").',
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Regenerate even if output HTML already exists.",
    )
    ap.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on first error.",
    )
    ap.add_argument(
        "--quiet",
        action="store_true",
        help="Reduce console output.",
    )

    args = ap.parse_args()

    xml_dir: Path = args.xml_dir
    out_dir: Path = args.out_dir
    xslt_path: Path = args.xslt

    if not xml_dir.exists():
        print(f"[ERROR] XML dir not found: {xml_dir}", file=sys.stderr)
        return 2
    if not xslt_path.exists():
        print(f"[ERROR] XSLT not found: {xslt_path}", file=sys.stderr)
        return 2

    try:
        subprocess.run(["xsltproc", "--version"], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        print("[ERROR] xsltproc not found. Install libxslt (xsltproc).", file=sys.stderr)
        return 2

    xml_files = iter_xml_files(xml_dir)

    if args.only.strip():
        stem = args.only.strip()
        if not stem.lower().endswith(".xml"):
            stem = stem + ".xml"
        xml_files = [p for p in xml_files if p.name == stem]
        if not xml_files:
            print(f"[ERROR] File not found in {xml_dir}: {stem}", file=sys.stderr)
            return 2

    total = len(xml_files)
    if total == 0:
        print(f"[WARN] No XML files found in {xml_dir}")
        return 0

    ok = 0
    skipped = 0
    failed = 0
    failures: list[tuple[str, str]] = []

    for i, xml_path in enumerate(xml_files, start=1):
        stem = xml_path.stem
        out_path = out_dir / f"{stem}.html"

        if out_path.exists() and not args.force:
            skipped += 1
            if not args.quiet:
                print(f"[{i}/{total}] SKIP {xml_path.name}")
            continue

        try:
            run_xsltproc(xslt_path, xml_path, out_path)
            ok += 1
            if not args.quiet:
                rel = out_path.relative_to(root) if out_path.is_absolute() else out_path
                print(f"[{i}/{total}] OK   {xml_path.name} -> {rel}")
        except Exception as e:
            failed += 1
            msg = str(e).strip()
            failures.append((xml_path.name, msg))
            print(f"[{i}/{total}] FAIL {xml_path.name}", file=sys.stderr)
            if msg:
                print(msg, file=sys.stderr)
            if args.fail_fast:
                break

    print("\n=== HTML generation summary ===")
    print(f"XML dir : {xml_dir}")
    print(f"XSLT    : {xslt_path}")
    print(f"OUT dir : {out_dir}")
    print(f"OK      : {ok}")
    print(f"SKIPPED : {skipped}")
    print(f"FAILED  : {failed}")

    if failures:
        print("\nFailures:")
        for name, msg in failures[:20]:
            print(f"- {name}: {msg.splitlines()[0] if msg else 'unknown error'}")
        if len(failures) > 20:
            print(f"... and {len(failures) - 20} more")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())