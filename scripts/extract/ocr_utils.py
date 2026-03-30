"""
스캔 이미지 기반 PDF의 OCR 처리 유틸리티.
PyMuPDF + Tesseract를 사용하여 PDF 페이지를 렌더링하고 OCR 텍스트를 추출한다.

다른 추출 스크립트에서 공통으로 사용하는 함수들을 제공한다:
  - require_fitz(), require_pytesseract(), require_pil(): 의존성 확인
  - render_page_to_image(): PDF 페이지 → PIL Image 렌더링
  - ocr_page(): PIL Image → 텍스트 OCR
  - get_or_ocr_page(): 캐시 우선 OCR (캐시 히트 시 OCR 생략)
"""

import sys
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 의존성 확인
# ---------------------------------------------------------------------------


def _check_fitz() -> bool:
    try:
        import fitz  # noqa: F401
        return True
    except ImportError:
        return False


def _check_pytesseract() -> bool:
    try:
        import pytesseract  # noqa: F401
        return True
    except ImportError:
        return False


def _check_pil() -> bool:
    try:
        from PIL import Image  # noqa: F401
        return True
    except ImportError:
        return False


def require_fitz():
    if not _check_fitz():
        logger.error(
            "PyMuPDF가 설치되지 않았습니다. 다음 명령어로 설치하세요:\n"
            '  pip install "PyMuPDF>=1.24.0"'
        )
        sys.exit(1)
    import fitz
    return fitz


def require_pytesseract():
    if not _check_pytesseract():
        logger.error(
            "pytesseract가 설치되지 않았습니다.\n"
            "1. Tesseract OCR 바이너리 설치:\n"
            "   https://github.com/UB-Mannheim/tesseract/wiki (Windows)\n"
            "   macOS: brew install tesseract tesseract-lang\n"
            "   Ubuntu: sudo apt-get install tesseract-ocr tesseract-ocr-kor\n"
            "2. Python 패키지 설치:\n"
            '   pip install "pytesseract>=0.3.10"\n'
            "3. 한국어 언어팩(kor)이 설치되어 있는지 확인하세요."
        )
        sys.exit(1)
    import pytesseract
    return pytesseract


def require_pil():
    if not _check_pil():
        logger.error(
            "Pillow가 설치되지 않았습니다. 다음 명령어로 설치하세요:\n"
            '  pip install "Pillow>=10.0.0"'
        )
        sys.exit(1)
    from PIL import Image
    return Image


# ---------------------------------------------------------------------------
# PDF 렌더링
# ---------------------------------------------------------------------------


def render_page_to_image(
    doc,
    page_num: int,
    dpi: int = 200,
    render_dir: Optional[Path] = None,
) -> "Image.Image":  # type: ignore[name-defined]
    """PDF 페이지를 PIL Image로 렌더링한다."""
    Image = require_pil()

    page = doc[page_num]
    import fitz
    matrix = fitz.Matrix(dpi / 72.0, dpi / 72.0)
    pixmap = page.get_pixmap(matrix=matrix, alpha=False)
    img_bytes = pixmap.tobytes("png")

    import io
    img = Image.open(io.BytesIO(img_bytes))

    if render_dir is not None:
        render_dir.mkdir(parents=True, exist_ok=True)
        img_path = render_dir / f"page_{page_num + 1:04d}.png"
        img.save(img_path, "PNG")

    return img


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------


def ocr_page(
    image,
    lang: str = "kor+eng",
) -> str:
    """PIL Image에 OCR을 수행하여 텍스트를 반환한다."""
    pytesseract = require_pytesseract()
    try:
        text = pytesseract.image_to_string(image, lang=lang)
        return text
    except Exception as exc:
        logger.warning(f"OCR 실패: {exc}")
        return ""


def get_or_ocr_page(
    doc,
    page_num: int,
    dpi: int,
    use_ocr: bool,
    cache_dir: Path,
) -> tuple[str, bool]:
    """캐시에서 텍스트를 불러오거나, 없으면 OCR 수행 후 캐시에 저장한다.

    Returns:
        (text, from_cache)
    """
    cache_file = cache_dir / f"page_{page_num + 1:04d}.txt"
    cache_dir.mkdir(parents=True, exist_ok=True)

    if cache_file.exists():
        text = cache_file.read_text(encoding="utf-8")
        return text, True

    if not use_ocr:
        return "", False

    img = render_page_to_image(doc, page_num, dpi=dpi)
    text = ocr_page(img)
    cache_file.write_text(text, encoding="utf-8")
    return text, False
