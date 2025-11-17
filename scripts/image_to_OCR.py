import pytesseract
from pdf2image import convert_from_path
import os

pdf_path = "/Users/carlamenegat/Documents/GitHub/Untitled/VarelaDigital/data/Anais_ptfinal.pdf"
output_path = "/Users/carlamenegat/Documents/GitHub/Untitled/VarelaDigital/data/extracted_text_ptfinal.txt"

# converte pdf em imagens (uma por página)
pages = convert_from_path(pdf_path, 300)

full_text = ""

for i, page in enumerate(pages, start=1):
    text = pytesseract.image_to_string(page, lang="por")
    full_text += f"\n\n=== Página {i} ===\n\n{text}"

with open(output_path, "w", encoding="utf-8") as f:
    f.write(full_text)

print("[✔] OCR concluído e texto salvo em:", output_path)