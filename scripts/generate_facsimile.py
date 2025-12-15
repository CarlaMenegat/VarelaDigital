import sys
import re
from pathlib import Path


# ============================================================
# 1. Extract folios explicitly marked in the body of the text
#    - detects [2r.], [15v.]
#    - detects <pb n="2r"/> or <pb n="15v"/>
# ============================================================
def extract_body_folios(xml: str) -> set[str]:
    folios = set()

    # Pattern: [2r.]
    for f in re.findall(r"\[(\d+[rv])\.\]", xml):
        folios.add(f)

    # Pattern: <pb n="2r" ...>
    for f in re.findall(r'<pb[^>]*\bn="(\d+[rv])"[^>]*>', xml):
        folios.add(f)

    return folios


# ============================================================
# 2. Extract folios from endorsements:
#    Looks for <note type="endorsement" place="2v">
#    Extracts only folios with explicit numbering (e.g. 2r, 2v)
# ============================================================
def extract_endorsement_folios(xml: str) -> set[str]:
    folios = set()

    # Capture @place attribute in endorsement notes
    places = re.findall(
        r'<note[^>]*type="endorsement"[^>]*\bplace="([^"]+)"[^>]*>',
        xml,
        flags=re.DOTALL,
    )

    for place in places:
        # Extract any "2r", "15v", etc.
        for f in re.findall(r"(\d+[rv])", place):
            folios.add(f)

    return folios


# ============================================================
# 3. Build the final list of surfaces:
#    - The maximum folio number is defined by the largest explicit
#      folio found in the body or in endorsements.
#    - Always generate surfaces from 1 to max, for both "r" and "v".
#    - NEW BEHAVIOR:
#         If no folios exist at all, return ["1r"]
# ============================================================
def build_surface_list(body_folios: set[str], endorsement_folios: set[str]) -> list[str]:
    all_folios = body_folios | endorsement_folios

    # NEW: If absolutely no folios exist, create minimal facsimile with only 1r
    if not all_folios:
        return ["1r"]   # minimal possible facsimile

    # Extract only the numeric portion of each folio (before r/v)
    nums = {int(f[:-1]) for f in all_folios if f[:-1].isdigit()}

    # Safety check (unlikely, but consistent)
    if not nums:
        return ["1r"]

    max_num = max(nums)

    surfaces = []
    for n in range(1, max_num + 1):
        surfaces.append(f"{n}r")
        surfaces.append(f"{n}v")

    return surfaces


# ============================================================
# 4. Main function: insert <facsimile> block after </teiHeader>
# ============================================================
def generate_facsimile_if_missing(xml_path: Path, carta_id: str):
    with xml_path.open("r", encoding="utf-8") as f:
        xml = f.read()

    # Do nothing if facsimile already exists
    if "<facsimile" in xml:
        print(f"[=] {carta_id}: facsimile already present.")
        return

    body_folios = extract_body_folios(xml)
    endorsement_folios = extract_endorsement_folios(xml)

    surfaces_folios = build_surface_list(body_folios, endorsement_folios)

    # Build <surface> lines
    surface_lines = [
        f'        <surface xml:id="{carta_id}_{folio}" n="{folio}"/>'
        for folio in surfaces_folios
    ]

    facsimile_block = (
        "    <facsimile>\n" +
        "\n".join(surface_lines) +
        "\n    </facsimile>\n"
    )

    # Insert facsimile right after </teiHeader>
    if "</teiHeader>" not in xml:
        print(f"[!] {carta_id}: missing </teiHeader>; facsimile not inserted.")
        return

    new_xml = xml.replace("</teiHeader>", "</teiHeader>\n\n" + facsimile_block, 1)

    # Write the updated file
    with xml_path.open("w", encoding="utf-8") as f:
        f.write(new_xml)

    max_folio = surfaces_folios[-1]
    print(
        f"[+] {carta_id}: facsimile created with {len(surfaces_folios)} surfaces "
        f"(from {surfaces_folios[0]} to {max_folio})."
    )


# ============================================================
# 5. CLI
# ============================================================
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python generate_facsimile.py <folder_path>")
        sys.exit(1)

    folder = Path(sys.argv[1])

    if not folder.exists():
        print(f"[ERROR] Folder not found: {folder}")
        sys.exit(1)

    # Adjust range as needed for the Coleção Varela
    for i in range(1, 559):
        carta_id = f"CV-{i}"
        xml_file = folder / f"{carta_id}.xml"

        if xml_file.exists():
            generate_facsimile_if_missing(xml_file, carta_id)
        else:
            print(f"[!] File not found: {xml_file}")