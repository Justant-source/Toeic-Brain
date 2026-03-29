"""
ETS 정답 및 해설 PDF에 OCR을 적용하여 검색 가능한 PDF로 변환한다.
원본 이미지 위에 투명 텍스트 레이어를 삽입하는 방식.

Usage:
    python ocr_answer_pdf.py --volume 1
    python ocr_answer_pdf.py --all
"""

import sys
sys.stdout.reconfigure(encoding="utf-8")

import argparse
import os
import tempfile
import time
from pathlib import Path

# Set environment before imports
TESSDATA = str(Path(__file__).resolve().parents[2] / "tessdata")
os.environ["TESSDATA_PREFIX"] = TESSDATA
os.environ["TMPDIR"] = str(Path(__file__).resolve().parents[2] / "data" / "raw" / "answer" / "_tmp")
os.environ["TEMP"] = os.environ["TMPDIR"]
os.environ["TMP"] = os.environ["TMPDIR"]
tempfile.tempdir = os.environ["TMPDIR"]

import fitz  # PyMuPDF
import pytesseract
from PIL import Image

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ANSWER_DIR = PROJECT_ROOT / "data" / "raw" / "answer"
DPI = 300
LANG = "kor+eng"


def ocr_single_volume(volume: int) -> None:
    """Apply OCR to a single volume's answer PDF."""
    input_path = ANSWER_DIR / f"ets_vol{volume}_anwer.pdf"
    output_path = ANSWER_DIR / f"ets_vol{volume}_anwer_ocr.pdf"

    if not input_path.exists():
        print(f"[Vol{volume}] 파일 없음: {input_path}")
        return

    # Ensure tmp dir
    tmp_dir = Path(os.environ["TMPDIR"])
    tmp_dir.mkdir(parents=True, exist_ok=True)

    print(f"[Vol{volume}] 시작: {input_path.name} ({input_path.stat().st_size // 1024 // 1024}MB)")
    start = time.time()

    src = fitz.open(str(input_path))
    total_pages = len(src)
    print(f"[Vol{volume}] 총 {total_pages} 페이지")

    # Process each page: render → OCR → get PDF bytes → collect
    pdf_page_bytes_list = []

    for pg_num in range(total_pages):
        page = src[pg_num]
        pix = page.get_pixmap(dpi=DPI)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        try:
            pdf_bytes = pytesseract.image_to_pdf_or_hocr(img, lang=LANG, extension="pdf")
            pdf_page_bytes_list.append(pdf_bytes)
        except Exception as e:
            print(f"  [Vol{volume}] 페이지 {pg_num + 1} OCR 실패: {e}")
            # Fallback: create image-only page
            fallback = fitz.open()
            fp = fallback.new_page(width=page.rect.width, height=page.rect.height)
            fp.show_pdf_page(fp.rect, src, pg_num)
            fallback_bytes = fallback.tobytes()
            pdf_page_bytes_list.append(fallback_bytes)
            fallback.close()

        if (pg_num + 1) % 10 == 0 or pg_num == total_pages - 1:
            elapsed = time.time() - start
            rate = (pg_num + 1) / elapsed
            eta = (total_pages - pg_num - 1) / rate if rate > 0 else 0
            print(f"  [Vol{volume}] {pg_num + 1}/{total_pages} 완료 ({elapsed:.0f}s, ETA {eta:.0f}s)")

    src.close()

    # Merge all OCR'd pages into single PDF
    print(f"[Vol{volume}] PDF 병합 중...")
    merged = fitz.open()
    for pdf_bytes in pdf_page_bytes_list:
        page_doc = fitz.open("pdf", pdf_bytes)
        merged.insert_pdf(page_doc)
        page_doc.close()

    merged.save(str(output_path), deflate=True, garbage=4)
    merged.close()

    elapsed = time.time() - start
    size_mb = output_path.stat().st_size / 1024 / 1024
    print(f"[Vol{volume}] 완료: {output_path.name} ({size_mb:.1f}MB, {elapsed:.0f}s)")


def main():
    parser = argparse.ArgumentParser(description="ETS 정답 PDF OCR 적용")
    parser.add_argument("--volume", type=int, help="처리할 볼륨 번호 (1-5)")
    parser.add_argument("--all", action="store_true", help="모든 볼륨 처리")
    args = parser.parse_args()

    if args.volume:
        ocr_single_volume(args.volume)
    elif args.all:
        for v in range(1, 6):
            ocr_single_volume(v)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
