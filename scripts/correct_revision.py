import os
import re
from pathlib import Path

INPUT_DIR = Path("data/documents_XML")

# Padrão que detecta <seg type="folio">[1v.]</seg>
FOLIO_PATTERN = re.compile(
    r'(?P<pb><pb\s+[^>]*n="1v"\s*/>\s*)?(?P<seg><seg\s+type="folio">\s*\[1v\.\]\s*</seg>)'
)

def insert_pb(text):
    def repl(match):
        has_pb = match.group("pb") is not None
        seg = match.group("seg")

        # se já tem <pb n="1v"/>, mantém como está
        if has_pb:
            return match.group(0)

        # senão, insere antes do seg
        return f'<pb n="1v"/>\n{seg}'

    return FOLIO_PATTERN.sub(repl, text)


def main():
    xml_files = list(INPUT_DIR.glob("*.xml"))
    if not xml_files:
        print("[AVISO] Nenhum arquivo XML encontrado.")
        return

    for file in xml_files:
        print(f"[✔] Processando {file.name}")

        original = file.read_text(encoding="utf-8")
        updated = insert_pb(original)

        if updated != original:
            file.write_text(updated, encoding="utf-8")
            print("    → <pb n=\"1v\"/> inserido quando necessário")
        else:
            print("    → Nenhuma alteração necessária")

    print("\n[✓] Finalizado.")


if __name__ == "__main__":
    main()