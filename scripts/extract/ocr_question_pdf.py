"""
ETS 기출문제 PDF 텍스트 추출 파이프라인.

각 권(Volume)의 PDF를 페이지 단위로 처리한다:
  1. PyMuPDF 내장 텍스트 추출 시도 (page.get_text())
  2. 추출 텍스트가 너무 짧으면 (< 50자, 스캔 이미지) OCR 폴백
  3. 결과를 data/raw/question/ocr_cache/vol{N}/page_{NNNN}.txt 에 저장

사용 예시:
  # 전 권 처리
  py -3 scripts/extract/ocr_question_pdf.py

  # 특정 권만
  py -3 scripts/extract/ocr_question_pdf.py --vol 1 3 5

  # 강제 재추출 (캐시 무시)
  py -3 scripts/extract/ocr_question_pdf.py --vol 2 --force

  # 특정 페이지부터 재개
  py -3 scripts/extract/ocr_question_pdf.py --vol 1 --start-page 50
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 경로 설정 — 프로젝트 루트를 sys.path에 추가하여 ocr_utils import 가능하게 함
# ---------------------------------------------------------------------------

_SCRIPT_DIR = Path(__file__).resolve().parent          # scripts/extract/
_PROJECT_ROOT = _SCRIPT_DIR.parent.parent              # 프로젝트 루트

if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------

PDF_DIR = _PROJECT_ROOT / "data" / "raw" / "question"
CACHE_ROOT = PDF_DIR / "ocr_cache"

TEXT_MIN_LEN = 50       # 이보다 짧으면 스캔 페이지로 간주, OCR 폴백
OCR_DPI = 200           # OCR 렌더링 해상도

# ---------------------------------------------------------------------------
# 로깅
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 핵심 처리 함수
# ---------------------------------------------------------------------------


def process_volume(
    vol: int,
    force: bool = False,
    start_page: int = 1,
) -> dict[str, int]:
    """단일 권 PDF를 처리하여 페이지별 텍스트를 캐시에 저장한다.

    Args:
        vol: 권 번호 (1–5)
        force: True이면 기존 캐시를 무시하고 재추출
        start_page: 처리를 시작할 페이지 번호 (1-indexed)

    Returns:
        통계 dict: pages_processed, cache_hits, ocr_pages, text_pages
    """
    from ocr_utils import get_or_ocr_page, require_fitz

    fitz = require_fitz()

    pdf_path = PDF_DIR / f"ets_vol{vol}.pdf"
    if not pdf_path.exists():
        logger.error(f"PDF 파일을 찾을 수 없습니다: {pdf_path}")
        return {"pages_processed": 0, "cache_hits": 0, "ocr_pages": 0, "text_pages": 0}

    cache_dir = CACHE_ROOT / f"vol{vol}"
    cache_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)

    # start_page는 1-indexed이므로 0-indexed로 변환
    start_idx = max(0, start_page - 1)

    stats = {"pages_processed": 0, "cache_hits": 0, "ocr_pages": 0, "text_pages": 0}

    logger.info(
        f"[Vol {vol}] {total_pages} 페이지 PDF 열기 완료. "
        f"처리 시작: {start_idx + 1}페이지"
    )

    for page_num in range(start_idx, total_pages):
        display_num = page_num + 1          # 사람이 읽는 1-indexed
        cache_file = cache_dir / f"page_{display_num:04d}.txt"

        # 캐시 히트 처리
        if cache_file.exists() and not force:
            stats["cache_hits"] += 1
            stats["pages_processed"] += 1
            if display_num % 50 == 0 or display_num == total_pages:
                logger.info(
                    f"[Vol {vol}] {display_num}/{total_pages}  "
                    f"(캐시: {stats['cache_hits']}, "
                    f"텍스트: {stats['text_pages']}, "
                    f"OCR: {stats['ocr_pages']})"
                )
            continue

        # 1단계: PyMuPDF 내장 텍스트 추출 시도
        page = doc[page_num]
        native_text: str = page.get_text()  # type: ignore[attr-defined]

        if len(native_text.strip()) >= TEXT_MIN_LEN:
            # 충분한 텍스트가 있으면 그대로 사용
            cache_file.write_text(native_text, encoding="utf-8")
            stats["text_pages"] += 1
            method = "텍스트"
        else:
            # 2단계: OCR 폴백
            # get_or_ocr_page는 page_num (0-indexed)을 받으며,
            # 내부에서 page_{page_num+1:04d}.txt 로 저장하므로
            # cache_dir을 그대로 넘기면 동일 경로에 저장된다.
            ocr_text, from_cache = get_or_ocr_page(
                doc=doc,
                page_num=page_num,
                dpi=OCR_DPI,
                use_ocr=True,
                cache_dir=cache_dir,
            )
            # get_or_ocr_page가 이미 캐시에 저장했으므로 별도 저장 불필요.
            # force 모드에서 캐시가 이미 존재하면 from_cache=True일 수 있으나
            # 위 캐시 히트 분기에서 걸렸어야 하므로 여기선 항상 False.
            stats["ocr_pages"] += 1
            method = "OCR"

        stats["pages_processed"] += 1

        # 진행 상황 출력 (매 10페이지 또는 마지막 페이지)
        if display_num % 10 == 0 or display_num == total_pages:
            logger.info(
                f"[Vol {vol}] {display_num}/{total_pages}  [{method}]  "
                f"(캐시: {stats['cache_hits']}, "
                f"텍스트: {stats['text_pages']}, "
                f"OCR: {stats['ocr_pages']})"
            )

    doc.close()
    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ETS 기출문제 PDF 텍스트 추출 파이프라인",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--vol",
        nargs="+",
        type=int,
        choices=[1, 2, 3, 4, 5],
        default=[1, 2, 3, 4, 5],
        metavar="N",
        help="처리할 권 번호 (기본값: 1 2 3 4 5)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="기존 캐시를 무시하고 강제 재추출",
    )
    parser.add_argument(
        "--start-page",
        type=int,
        default=1,
        metavar="N",
        help="처리를 시작할 페이지 번호, 1-indexed (기본값: 1). "
             "--vol 을 단일 권으로 지정했을 때 유효",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    volumes: list[int] = sorted(set(args.vol))
    force: bool = args.force
    start_page: int = args.start_page

    if start_page != 1 and len(volumes) > 1:
        logger.warning(
            "--start-page 옵션은 단일 권 처리 시에만 의미가 있습니다. "
            "복수 권 처리 시에는 첫 번째 권에만 적용됩니다."
        )

    logger.info(
        f"처리 대상 권: {volumes}  |  force={force}  |  start_page={start_page}"
    )
    logger.info(f"PDF 디렉토리: {PDF_DIR}")
    logger.info(f"캐시 루트: {CACHE_ROOT}")

    total_stats: dict[str, int] = {
        "pages_processed": 0,
        "cache_hits": 0,
        "ocr_pages": 0,
        "text_pages": 0,
    }

    for i, vol in enumerate(volumes):
        # start_page는 첫 번째 권에만 적용
        effective_start = start_page if i == 0 else 1
        vol_stats = process_volume(vol, force=force, start_page=effective_start)
        for key in total_stats:
            total_stats[key] += vol_stats[key]

    # 최종 요약
    print("\n" + "=" * 60)
    print("처리 완료 요약")
    print("=" * 60)
    print(f"  총 처리 페이지  : {total_stats['pages_processed']}")
    print(f"  캐시 히트       : {total_stats['cache_hits']}")
    print(f"  텍스트 추출     : {total_stats['text_pages']}")
    print(f"  OCR 처리        : {total_stats['ocr_pages']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
