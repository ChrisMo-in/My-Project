import fitz
from pathlib import Path


PDF_FILE = Path("input/giaotrinh.pdf")
OUTPUT_DIR = Path("output")

MD_FILE = OUTPUT_DIR / "giaotrinh.md"
IMAGE_DIR = OUTPUT_DIR / "images"


def pdf_to_markdown(pdf_file, md_file):
    doc = fitz.open(pdf_file)

    OUTPUT_DIR.mkdir(exist_ok=True)
    IMAGE_DIR.mkdir(exist_ok=True)

    markdown = []

    markdown.append(f"# {pdf_file.stem}\n")

    for page_number, page in enumerate(doc, start=1):

        markdown.append(f"\n---\n")
        markdown.append(f"## Trang {page_number}\n\n")

        # =========================
        # 1. Lấy text
        # =========================

        text = page.get_text("text")

        if text.strip():
            markdown.append(text.strip())
            markdown.append("\n")

        # =========================
        # 2. Lấy hình ảnh
        # =========================

        images = page.get_images(full=True)

        for image_index, image in enumerate(images):

            xref = image[0]

            image_data = doc.extract_image(xref)

            image_bytes = image_data["image"]
            image_ext = image_data["ext"]

            image_name = (
                f"page_{page_number:03d}"
                f"_image_{image_index + 1:02d}"
                f".{image_ext}"
            )

            image_path = IMAGE_DIR / image_name

            with open(image_path, "wb") as f:
                f.write(image_bytes)

            markdown.append(
                f"![Hình trang {page_number}]"
                f"(images/{image_name})\n\n"
            )

    with open(md_file, "w", encoding="utf-8") as f:
        f.write("\n".join(markdown))

    doc.close()

    print("Hoàn tất!")
    print(f"Markdown: {md_file}")
    print(f"Hình ảnh: {IMAGE_DIR}")


if __name__ == "__main__":
    pdf_to_markdown(PDF_FILE, MD_FILE)