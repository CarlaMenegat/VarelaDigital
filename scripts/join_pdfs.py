from pypdf import PdfWriter
import os

base_path = "/Users/carlamenegat/Documents/GitHub/Untitled/VarelaDigital/data"

pdf_files = [
    "Anais_pt1.pdf",
    "Anais_pt2.pdf",
    "Anais_pt3.pdf",
    "Anais_pt4.pdf",
]

output_pdf = os.path.join(base_path, "Anais_full.pdf")

writer = PdfWriter()

for pdf_name in pdf_files:
    pdf_path = os.path.join(base_path, pdf_name)
    try:
        with open(pdf_path, "rb") as f:
            writer.append(f)
        print(f"[✔] Adicionado: {pdf_name}")
    except FileNotFoundError:
        print(f"[⚠] Arquivo não encontrado: {pdf_name}")

with open(output_pdf, "wb") as f_out:
    writer.write(f_out)

print(f"\n[🎉] PDF final criado em: {output_pdf}")