import fitz  # PyMuPDF

def test_extract(pdf_path):
    doc = fitz.open(pdf_path)
    for i in range(len(doc)):
        page = doc[i]
        text = page.get_text()
        print(f"--- Page {i+1} ---")
        if text.strip():
            print(text.strip()[:500])
        else:
            print("NO TEXT (Images only?)")
            
if __name__ == "__main__":
    test_extract("美客多运费.pdf")
