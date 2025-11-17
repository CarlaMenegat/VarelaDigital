import pytesseract
from pdf2image import convert_from_path
import os

pdf_path = "/Users/carlamenegat/Documents/GitHub/Untitled/VarelaDigital/data/Anais_full.pdf"
output_txt = "/Users/carlamenegat/Documents/GitHub/Untitled/VarelaDigital/data/Anais_full_OCR.txt"

pages = convert_from_path(pdf_path, 300)

full_text = ""

for i, page in enumerate(pages, start=1):
    text = pytesseract.image_to_string(page, lang="por")
    full_text += f"\n\n=== Página {i} ===\n\n{text}"

with open(output_txt, "w", encoding="utf-8") as f:
    f.write(full_text)

print("[✔] OCR concluído e texto salvo em:", output_txt)
