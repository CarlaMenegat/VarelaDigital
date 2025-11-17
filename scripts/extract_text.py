import pdfplumber
import os

def extract_text_from_pdf(pdf_path):
    """Extract text from a PDF file using pdfplumber."""
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text()
            if page_text:
                text += f"\n\n=== Página {i} ===\n\n"
                text += page_text
    return text

def save_text_to_file(text, output_path):
    """Save extracted text to a file."""
    with open(output_path, "w", encoding="utf-8") as file:
        file.write(text)
    print(f"[✔] Texto extraído e salvo em: {output_path}")

if __name__ == "__main__":
    # Caminhos
    base_path = "/Users/carlamenegat/Documents/GitHub/Untitled/VarelaDigital"
    pdf_path = "/Users/carlamenegat/Documents/GitHub/Untitled/VarelaDigital/data/Anais_ptfinal.pdf"
    output_path = os.path.join(base_path, "data", "extracted_text_ptfinal.txt")
    
    # Executar extração
    extracted_text = extract_text_from_pdf(pdf_path)
    save_text_to_file(extracted_text, output_path)