import os
import re
from pathlib import Path

INPUT_DIR = Path("data/documents_XML")

# Lista de padrões → expansão
ABBREVIATIONS = [
    # Vossa Senhoria (todas variantes)
    (re.compile(r'(?<!<abbr>)(V\.?\s*S\.?ª\.?|V\.?\s*S[aã]\.?|V\.?\s*S\.)(?!</abbr>)'), "Vossa Senhoria"),

    # Vossa Excelência (todas variantes)
    (re.compile(r'(?<!<abbr>)(V\.?\s*Ex\.?ª?\.?|V\.?\s*Exa\.?|V\.?\s*Ex\.?º\.?)(?!</abbr>)'), "Vossa Excelência"),

    # Sua Senhoria
    (re.compile(r'(?<!<abbr>)(S\.?\s*S\.?ª?\.?)(?!</abbr>)'), "Sua Senhoria"),

    # Sua Excelência
    (re.compile(r'(?<!<abbr>)(S\.?\s*Ex\.?ª?\.?|S\.?\s*Exa\.?|S\.?\s*Ex\.?º\.?)(?!</abbr>)'), "Sua Excelência"),

    # Vossa Mercê (todas variantes)
    (re.compile(r'(?<!<abbr>)(V\.?\s*Mcê\.?|V\.?\s*Meê\.?|V\.?\s*Mc\.?e\.?)(?!</abbr>)'), "Vossa Mercê"),

    # Senhor
    (re.compile(r'(?<!<abbr>)(Sr\.)(?!</abbr>)'), "Senhor"),

    # Señor (grafia castelhana)
    (re.compile(r'(?<!<abbr>)(Sõr)(?!</abbr>)'), "Señor"),

    # Senhora
    (re.compile(r'(?<!<abbr>)(Sra\.)(?!</abbr>)'), "Senhora"),

    # Post Data
    (re.compile(r'(?<!<abbr>)(P\.D\.)(?!</abbr>)'), "Post Data"),
    
     # Post scriptum  ← NOVO
    (re.compile(r'(?<!<abbr>)(P\.S\.)(?!</abbr>)'), "Post scriptum"),

    # Secretaria da Presidência da República (já usávamos)
    (re.compile(r'(?<!<abbr>)(S\.?\s*da\s*R\.?|S\.?\s*R\.)(?!</abbr>)'), 
     "Secretaria da Presidência da República"),
    
    # Ilmo. → Ilustríssimo
    (re.compile(r'(?<!<abbr>)(Ilmo\.)(?!</abbr>)'),
        "Ilustríssimo"),

    # Exmo. → Excelentíssimo
    (re.compile(r'(?<!<abbr>)(Exmo\.)(?!</abbr>)'),
        "Excelentíssimo"),
]

def make_choice(abbr, expan):
    return f"<choice><abbr>{abbr}</abbr><expan>{expan}</expan></choice>"

def process(xml):
    for pattern, expan in ABBREVIATIONS:
        def repl(match):
            return make_choice(match.group(0), expan)
        xml = pattern.sub(repl, xml)
    return xml

def main():
    if not INPUT_DIR.exists():
        print(f"[ERRO] Pasta não existe: {INPUT_DIR.resolve()}")
        return

    xml_files = list(INPUT_DIR.glob("*.xml"))
    if not xml_files:
        print(f"[AVISO] Nenhum XML encontrado.")
        return

    for file in xml_files:
        print(f"[✔] Processando {file.name}")
        text = file.read_text(encoding="utf-8")
        new = process(text)

        if new != text:
            file.write_text(new, encoding="utf-8")
            print("    → Atualizado")
        else:
            print("    → Sem mudanças")

    print("\n[✓] Finalizado.")

if __name__ == "__main__":
    main()