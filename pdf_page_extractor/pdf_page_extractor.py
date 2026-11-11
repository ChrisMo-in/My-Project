from __future__ import annotations

import os
import re
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

import fitz  # PyMuPDF
from pypdf import PdfReader, PdfWriter

try:
    import pytesseract
    from PIL import Image
    OCR_AVAILABLE = True
except Exception:
    pytesseract = None
    Image = None
    OCR_AVAILABLE = False


NUMBER_RE = re.compile(r"^(?:\d{1,5}|[ivxlcdm]{1,12})$", re.IGNORECASE)
TOKEN_RE = re.compile(r"(?<![A-Za-z0-9])(?:\d{1,5}|[ivxlcdm]{1,12})(?![A-Za-z0-9])", re.IGNORECASE)


def normalize_label(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip().casefold()


def candidate_score(x_center: float, y_center: float, width: float, height: float) -> float:
    """Higher is better: favor page edges and horizontal center."""
    horizontal = 1.0 - min(abs(x_center - width / 2) / max(width / 2, 1), 1.0)
    distance_to_edge = min(y_center, height - y_center) / max(height, 1)
    edge_score = 1.0 - min(distance_to_edge / 0.18, 1.0)
    return 0.65 * horizontal + 0.35 * edge_score


def detect_from_pdf_text(page: fitz.Page) -> str | None:
    rect = page.rect
    words = page.get_text("words")
    found: list[tuple[float, str]] = []
    for word in words:
        x0, y0, x1, y1, text = word[:5]
        token = str(text).strip().strip(".,:;()[]")
        if not NUMBER_RE.fullmatch(token):
            continue
        y_center = (y0 + y1) / 2
        # Page numbers are normally placed in the outer 16% of a page.
        if y_center > rect.height * 0.16 and y_center < rect.height * 0.84:
            continue
        x_center = (x0 + x1) / 2
        score = candidate_score(x_center, y_center, rect.width, rect.height)
        found.append((score, token))
    if not found:
        return None
    found.sort(key=lambda item: item[0], reverse=True)
    return found[0][1]


def detect_with_ocr(page: fitz.Page) -> str | None:
    if not OCR_AVAILABLE:
        return None

    rect = page.rect
    scale = 2.5
    clips = [
        fitz.Rect(0, 0, rect.width, rect.height * 0.20),
        fitz.Rect(0, rect.height * 0.80, rect.width, rect.height),
    ]
    found: list[tuple[float, str]] = []

    for clip in clips:
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=clip, alpha=False)
        image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        data = pytesseract.image_to_data(
            image,
            config="--psm 6 -c tessedit_char_whitelist=0123456789ivxlcdmIVXLCDM",
            output_type=pytesseract.Output.DICT,
        )
        for i, raw in enumerate(data.get("text", [])):
            token = str(raw).strip().strip(".,:;()[]")
            if not NUMBER_RE.fullmatch(token):
                continue
            conf_text = str(data.get("conf", ["0"])[i])
            try:
                confidence = max(0.0, min(float(conf_text), 100.0)) / 100.0
            except ValueError:
                confidence = 0.0
            x = float(data["left"][i]) + float(data["width"][i]) / 2
            y = float(data["top"][i]) + float(data["height"][i]) / 2
            # Convert OCR coordinates from the clipped render back to PDF coordinates.
            x_pdf = x / scale
            y_pdf = y / scale + clip.y0
            score = candidate_score(x_pdf, y_pdf, rect.width, rect.height)
            found.append((0.75 * score + 0.25 * confidence, token))

    if not found:
        return None
    found.sort(key=lambda item: item[0], reverse=True)
    return found[0][1]


def get_pdf_page_labels(pdf_path: str) -> list[str]:
    try:
        reader = PdfReader(pdf_path, strict=False)
        labels = reader.page_labels
        if labels and len(labels) == len(reader.pages):
            return [str(x) if x is not None else "" for x in labels]
    except Exception:
        pass
    return []


def detect_page_numbers(pdf_path: str, progress_callback=None) -> list[dict[str, str]]:
    labels = get_pdf_page_labels(pdf_path)
    rows: list[dict[str, str]] = []
    doc = fitz.open(pdf_path)
    try:
        for index, page in enumerate(doc):
            detected = detect_from_pdf_text(page)
            method = "Văn bản trong PDF" if detected else ""
            if not detected:
                detected = detect_with_ocr(page)
                if detected:
                    method = "OCR"
            if not detected and labels and labels[index]:
                detected = labels[index]
                method = "Nhãn trang PDF (cần kiểm tra)"
            rows.append({
                "physical": str(index + 1),
                "printed": detected or "",
                "method": method or "Chưa nhận diện",
            })
            if progress_callback:
                progress_callback(index + 1, len(doc))
    finally:
        doc.close()
    return rows


def parse_requested_pages(expression: str) -> list[str]:
    """Accept comma/semicolon-separated labels and numeric ranges, e.g. 2, 5-8, ix."""
    result: list[str] = []
    parts = [p.strip() for p in re.split(r"[,;\n]+", expression) if p.strip()]
    for part in parts:
        match = re.fullmatch(r"(\d+)\s*-\s*(\d+)", part)
        if match:
            start, end = int(match.group(1)), int(match.group(2))
            if start > end:
                raise ValueError(f"Khoảng trang không hợp lệ: {part}")
            if end - start > 10000:
                raise ValueError(f"Khoảng trang quá lớn: {part}")
            result.extend(str(n) for n in range(start, end + 1))
        else:
            result.append(part)
    # Remove repeated requests without changing the requested order.
    deduped: list[str] = []
    seen: set[str] = set()
    for item in result:
        key = normalize_label(item)
        if key not in seen:
            deduped.append(item)
            seen.add(key)
    return deduped


def export_selected_pages(source_path: str, output_path: str, rows: list[dict[str, str]], expression: str) -> int:
    requested = parse_requested_pages(expression)
    if not requested:
        raise ValueError("Bạn chưa nhập số trang cần tách.")

    page_map: dict[str, list[int]] = {}
    for row in rows:
        label = normalize_label(row["printed"])
        if label:
            page_map.setdefault(label, []).append(int(row["physical"]) - 1)

    selected_indices: list[int] = []
    unresolved: list[str] = []
    ambiguous: list[str] = []
    for label in requested:
        key = normalize_label(label)
        matches = page_map.get(key, [])
        if not matches:
            unresolved.append(label)
        elif len(matches) > 1:
            ambiguous.append(label)
        else:
            selected_indices.append(matches[0])

    if unresolved or ambiguous:
        details = []
        if unresolved:
            details.append("Không tìm thấy số trang: " + ", ".join(unresolved))
        if ambiguous:
            details.append("Số trang bị trùng, chưa thể xác định duy nhất: " + ", ".join(ambiguous))
        details.append("Hãy kiểm tra bảng nhận diện và sửa số trang bằng cách nhấp đúp vào cột 'Số in trên trang'.")
        raise ValueError("\n\n".join(details))

    # Preserve the original document order, rather than the order typed by the user.
    selected_indices = sorted(set(selected_indices))

    reader = PdfReader(source_path, strict=False)
    if reader.is_encrypted:
        raise ValueError("PDF đang được mã hóa. Hãy mở khóa PDF trước khi tách.")

    writer = PdfWriter()
    for index in selected_indices:
        writer.add_page(reader.pages[index])

    try:
        metadata = reader.metadata
        if metadata:
            writer.add_metadata({
                "/Title": (str(metadata.title) + " - Trang trích xuất") if metadata.title else "PDF trang trích xuất",
                "/Producer": "PDF Page Extractor (pypdf)",
            })
    except Exception:
        pass

    output_dir = os.path.dirname(os.path.abspath(output_path)) or "."
    fd, temp_path = tempfile.mkstemp(suffix=".pdf", dir=output_dir)
    os.close(fd)
    try:
        with open(temp_path, "wb") as output_file:
            writer.write(output_file)
        # Verify output page count before publishing the file.
        check = PdfReader(temp_path, strict=False)
        if len(check.pages) != len(selected_indices):
            raise RuntimeError("Kiểm tra sau khi xuất không khớp số trang được yêu cầu.")
        os.replace(temp_path, output_path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    return len(selected_indices)


class PDFPageExtractorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("PDF Page Extractor - Tách theo số trang in")
        self.root.geometry("900x650")
        self.root.minsize(760, 520)
        self.pdf_path = ""
        self.rows: list[dict[str, str]] = []
        self.scanning = False

        self._build_ui()

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=14)
        main.pack(fill="both", expand=True)

        ttk.Label(main, text="TÁCH PDF THEO SỐ TRANG ĐƯỢC IN TRÊN TÀI LIỆU", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        ttk.Label(
            main,
            text="Ứng dụng dò số trang ở đầu/cuối trang, cho phép kiểm tra và sửa ánh xạ trước khi xuất.",
            wraplength=850,
        ).pack(anchor="w", pady=(4, 12))

        file_row = ttk.Frame(main)
        file_row.pack(fill="x", pady=(0, 8))
        ttk.Button(file_row, text="1. Chọn file PDF", command=self.choose_pdf).pack(side="left")
        self.file_label = ttk.Label(file_row, text="Chưa chọn file", wraplength=680)
        self.file_label.pack(side="left", padx=10, fill="x", expand=True)

        action_row = ttk.Frame(main)
        action_row.pack(fill="x", pady=(0, 8))
        self.scan_button = ttk.Button(action_row, text="2. Nhận diện số trang", command=self.scan_pages, state="disabled")
        self.scan_button.pack(side="left")
        self.progress = ttk.Progressbar(action_row, mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True, padx=10)
        self.status_label = ttk.Label(action_row, text="Sẵn sàng")
        self.status_label.pack(side="right")

        table_frame = ttk.LabelFrame(main, text="Bảng đối chiếu số trang", padding=8)
        table_frame.pack(fill="both", expand=True, pady=(0, 10))
        columns = ("physical", "printed", "method")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=13)
        self.tree.heading("physical", text="Vị trí trong PDF")
        self.tree.heading("printed", text="Số in trên trang (có thể sửa)")
        self.tree.heading("method", text="Cách nhận diện")
        self.tree.column("physical", width=130, anchor="center")
        self.tree.column("printed", width=210, anchor="center")
        self.tree.column("method", width=400, anchor="w")
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", self.edit_cell)

        ttk.Label(main, text="3. Nhập số trang cần lấy (ví dụ: 2, 5-8, 12 hoặc i, ii, iii):").pack(anchor="w")
        input_row = ttk.Frame(main)
        input_row.pack(fill="x", pady=(4, 8))
        self.pages_entry = ttk.Entry(input_row)
        self.pages_entry.pack(side="left", fill="x", expand=True)
        self.export_button = ttk.Button(input_row, text="4. Xuất PDF", command=self.export_pdf, state="disabled")
        self.export_button.pack(side="left", padx=(8, 0))

        hint = "Lưu ý: Nhấp đúp vào ô 'Số in trên trang' để sửa kết quả nhận diện."
        if not OCR_AVAILABLE:
            hint += " OCR chưa khả dụng; hãy cài pytesseract, Pillow và Tesseract OCR để nhận diện PDF scan."
        ttk.Label(main, text=hint, foreground="#555555", wraplength=850).pack(anchor="w")

    def choose_pdf(self):
        path = filedialog.askopenfilename(title="Chọn PDF nguồn", filetypes=[("PDF files", "*.pdf")])
        if not path:
            return
        self.pdf_path = path
        self.rows = []
        self.file_label.configure(text=path)
        self.tree.delete(*self.tree.get_children())
        self.scan_button.configure(state="normal")
        self.export_button.configure(state="disabled")
        self.status_label.configure(text="Đã chọn PDF")

    def scan_pages(self):
        if not self.pdf_path or self.scanning:
            return
        self.scanning = True
        self.scan_button.configure(state="disabled")
        self.export_button.configure(state="disabled")
        self.progress.configure(value=0, maximum=100)
        self.status_label.configure(text="Đang quét...")

        def run_scan():
            try:
                rows = detect_page_numbers(self.pdf_path, self._scan_progress)
                self.root.after(0, lambda: self._scan_done(rows, None))
            except Exception as exc:
                self.root.after(0, lambda: self._scan_done(None, exc))

        threading.Thread(target=run_scan, daemon=True).start()

    def _scan_progress(self, current: int, total: int):
        value = int(current * 100 / max(total, 1))
        self.root.after(0, lambda: self.progress.configure(value=value))
        self.root.after(0, lambda: self.status_label.configure(text=f"Đang quét {current}/{total}"))

    def _scan_done(self, rows, error):
        self.scanning = False
        self.scan_button.configure(state="normal")
        if error:
            self.status_label.configure(text="Quét thất bại")
            messagebox.showerror("Lỗi đọc PDF", str(error))
            return
        self.rows = rows
        self.tree.delete(*self.tree.get_children())
        for row in rows:
            self.tree.insert("", "end", values=(row["physical"], row["printed"], row["method"]))
        found = sum(1 for row in rows if row["printed"])
        self.status_label.configure(text=f"Đã nhận diện {found}/{len(rows)} trang")
        self.export_button.configure(state="normal")

    def edit_cell(self, event):
        item_id = self.tree.identify_row(event.y)
        column = self.tree.identify_column(event.x)
        if not item_id or column != "#2":
            return
        values = list(self.tree.item(item_id, "values"))
        old_value = values[1]
        new_value = tk.simpledialog.askstring("Sửa số trang", "Nhập số trang được in trên trang này:", initialvalue=old_value, parent=self.root)
        if new_value is None:
            return
        values[1] = new_value.strip()
        self.tree.item(item_id, values=values)
        row_index = int(values[0]) - 1
        self.rows[row_index]["printed"] = values[1]
        self.rows[row_index]["method"] = "Người dùng xác nhận/chỉnh sửa"
        values[2] = self.rows[row_index]["method"]
        self.tree.item(item_id, values=values)

    def export_pdf(self):
        if not self.rows or not self.pdf_path:
            messagebox.showwarning("Thiếu dữ liệu", "Hãy chọn PDF và nhận diện số trang trước.")
            return
        expression = self.pages_entry.get().strip()
        if not expression:
            messagebox.showwarning("Thiếu số trang", "Hãy nhập số trang cần tách.")
            return
        base = Path(self.pdf_path)
        default_name = base.stem + "_extracted.pdf"
        output_path = filedialog.asksaveasfilename(
            title="Lưu PDF đã tách",
            defaultextension=".pdf",
            initialfile=default_name,
            filetypes=[("PDF files", "*.pdf")],
        )
        if not output_path:
            return
        try:
            count = export_selected_pages(self.pdf_path, output_path, self.rows, expression)
            self.status_label.configure(text=f"Đã xuất {count} trang")
            messagebox.showinfo("Hoàn tất", f"Đã tạo PDF gồm {count} trang:\n{output_path}\n\nNội dung trang và ảnh nhúng được sao chép trực tiếp, không chuyển trang thành ảnh raster.")
        except Exception as exc:
            messagebox.showerror("Không thể xuất PDF", str(exc))


def main():
    root = tk.Tk()
    # Import here to keep the rest of the app usable on Python distributions with Tk.
    import tkinter.simpledialog  # noqa: F401
    PDFPageExtractorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
