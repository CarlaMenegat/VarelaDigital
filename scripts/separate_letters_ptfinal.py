import re
import os

# Caminho do arquivo extraído
input_txt_path = "/Users/carlamenegat/Documents/GitHub/Untitled/VarelaDigital/data/extracted_text_ptfinal.txt"
output_dir = "/Users/carlamenegat/Documents/GitHub/Untitled/VarelaDigital/data/cartas_txt"

# Cria a pasta de saída se não existir
os.makedirs(output_dir, exist_ok=True)

# Lê o texto completo
with open(input_txt_path, "r", encoding="utf-8") as f:
    full_text = f.read()

# Tentamos primeiro o padrão "bonitinho" CV-###
patterns = [
    (r"(CV-\d+)", False),                      # group(1) já é o id completo
    (r"(CV\s*[\-–—.]?\s*(\d{3}))", True),      # group(2) é só o número
]

matches = []
use_pattern = None

for pattern, has_num_group in patterns:
    matches = list(re.finditer(pattern, full_text))
    if matches:
        use_pattern = (pattern, has_num_group)
        break

if not matches:
    print("Nenhuma carta encontrada — verifique como 'CV-###' aparece no texto extraído.")
else:
    print(f"Cartas encontradas: {len(matches)} usando padrão: {use_pattern[0]}")

    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)

        # Monta o ID da carta
        if use_pattern[1]:
            # padrão flexível: usamos só o número
            numero = match.group(2)
            carta_id = f"CV-{numero}"
        else:
            # padrão CV-###
            carta_id = match.group(1)

        carta_text = full_text[start:end].strip()

        output_file = os.path.join(output_dir, f"{carta_id}.txt")

        # Se já existe, não sobrescreve
        if os.path.exists(output_file):
            print(f"{carta_id} já existe — ignorada.")
            continue

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(carta_text)

        print(f"{carta_id} salva.")