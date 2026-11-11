PDF PAGE EXTRACTOR - TACH THEO SO TRANG IN TREN TAI LIEU
=======================================================

1. CHUC NANG
- Mo mot file PDF dai.
- Tu dong tim so trang nam o vung dau/cuoi trang bang cach doc text trong PDF.
- Neu khong co text (PDF scan), co the dung OCR neu da cai Tesseract OCR.
- Hien thi bang doi chieu: vi tri trang trong PDF va so trang in tren trang.
- Cho phep nhap/sua thu cong so trang neu nhan dien sai.
- Nhap trang can tach, vi du: 2, 5-8, 12 hoac i, ii, iii.
- Xuat mot PDF moi chi gom cac trang da chon.

2. CAI DAT (WINDOWS)
Can Python 3.10 tro len.

Mo PowerShell tai thu muc chua project va chay:
    py -m pip install -r requirements.txt

Neu muon OCR cac PDF scan, cai them Tesseract OCR cho Windows, sau do dam bao lenh
'tesseract' co trong PATH. OCR la tuy chon; khong co OCR thi van tach duoc PDF co text.

3. CHAY CHUONG TRINH
    py pdf_page_extractor.py

Cac buoc:
1) Chon file PDF.
2) Nhan "Nhan dien so trang".
3) Kiem tra bang doi chieu. Nhan dup vao cot "So in tren trang" de sua neu can.
4) Nhap so trang can lay, vi du 10, 12-16, 23.
5) Bam "Xuat PDF" va chon noi luu.

4. QUY TAC NHAP TRANG
- So Arabic: 1, 2, 3...
- Khoang lien tuc: 10-15 (bao gom ca 10 va 15).
- So La Ma: i, ii, iii. So La Ma nhap tung so, khong nhap khoang.
- Phan tach cac so bang dau phay hoac cham phay.
- Neu mot so trang in xuat hien nhieu lan (vi du cac chuong deu bat dau lai tu trang 1), chuong trinh se dung va bao trung. Hay sua nhan trong bang thanh nhan duy nhat, vi du Chuong2-1, roi nhap dung nhan do.

5. BAO TOAN CHAT LUONG
Chuong trinh khong chup/man hinh hoa trang PDF. No sao chep truc tiep doi tuong trang va cac tai nguyen PDF bang pypdf, nen text/vector va image stream duoc giu lai, khong co buoc giam DPI hay nen lai anh.

Luu y: Neu PDF nguon co mat khau, hay mo khoa truoc. Neu so trang duoc in khong nam o dau/cuoi trang hoac OCR doc sai, sua cot so trang trong bang truoc khi xuat. Hay kiem tra lai PDF dau ra, nhat la voi tai lieu scan hoac tai lieu co bo cuc dac biet.

6. CAU TRUC
pdf_page_extractor.py   Chuong trinh giao dien
requirements.txt        Thu vien can cai
README_VI.txt           Huong dan su dung
