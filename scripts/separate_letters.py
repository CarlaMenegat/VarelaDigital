
import re
import os

# Caminho do arquivo extraído
input_txt_path = "/Users/carlamenegat/Documents/GitHub/Untitled/VarelaDigital/data/extracted_text.txt"
output_dir = "/Users/carlamenegat/Documents/GitHub/Untitled/VarelaDigital/data/cartas_txt"

# Cria a pasta de saída se não existir
os.makedirs(output_dir, exist_ok=True)

# Lê o texto completo
with open(input_txt_path, "r", encoding="utf-8") as f:
    full_text = f.read()

# Encontra todas as ocorrências de cabeçalhos de cartas
matches = list(re.finditer(r"(CV-\d+)\s", full_text))

print(f"Cartas encontradas: {len(matches)}")

for i, match in enumerate(matches):
    start = match.start()
    end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
    carta_id = match.group(1)
    carta_text = full_text[start:end].strip()

    output_file = os.path.join(output_dir, f"{carta_id}.txt")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(carta_text)

    print(f"{carta_id} salva.")