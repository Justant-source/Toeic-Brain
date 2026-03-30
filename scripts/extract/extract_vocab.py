"""
해커스 노랭이 단어장 PDF에서 단어 데이터를 추출하여 JSON으로 변환한다.
입력: data/raw/hackers_vocab.pdf
출력: data/processed/vocab/hackers_vocab.json

사용법:
  python extract_vocab.py                    # 전체 PDF 처리
  python extract_vocab.py --pages 5-20       # 특정 페이지 범위 처리
  python extract_vocab.py --dpi 200          # DPI 지정
  python extract_vocab.py --no-ocr           # OCR 생략, 캐시 텍스트만 사용
  python extract_vocab.py --render-only      # 이미지 렌더링만 수행 (OCR 없이)
"""

import sys
import re
import json
import argparse
import logging
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

# Windows에서 UTF-8 출력 강제
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass  # Python 3.7 미만에서는 무시

# ---------------------------------------------------------------------------
# 프로젝트 경로 설정
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent  # scripts/extract/ → project root

RAW_PDF_PATH = PROJECT_ROOT / "data" / "raw" / "hackers_vocab.pdf"
OUTPUT_JSON_PATH = PROJECT_ROOT / "data" / "processed" / "vocab" / "hackers_vocab.json"
OCR_CACHE_DIR = PROJECT_ROOT / "data" / "processed" / "vocab" / "_ocr_cache"
RENDER_DIR = PROJECT_ROOT / "data" / "processed" / "vocab" / "_rendered"

# ---------------------------------------------------------------------------
# ロギング設定
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 데이터 구조
# ---------------------------------------------------------------------------


@dataclass
class VocabEntry:
    id: str
    word: str
    pos: str
    meaning_kr: str
    meaning_en: Optional[str]
    example_sentence: Optional[str]
    example_translation: Optional[str]
    day: int
    synonyms: list[str]
    frequency: str  # "★★★" | "★★" | "★"
    related_words: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExtractionStats:
    pages_processed: int = 0
    pages_skipped: int = 0
    pages_from_cache: int = 0
    ocr_errors: int = 0
    words_found: int = 0
    days_found: set = field(default_factory=set)

    def report(self) -> str:
        return (
            f"페이지 처리: {self.pages_processed} "
            f"(캐시: {self.pages_from_cache}, 스킵: {self.pages_skipped}, OCR 오류: {self.ocr_errors})\n"
            f"발견된 단어: {self.words_found}\n"
            f"발견된 Day: {sorted(self.days_found)}"
        )


# ---------------------------------------------------------------------------
# 공통 OCR 유틸리티 (ocr_utils.py에서 임포트)
# ---------------------------------------------------------------------------

from scripts.extract.ocr_utils import (
    require_fitz,
    require_pytesseract,
    require_pil,
    render_page_to_image,
    ocr_page,
    get_or_ocr_page,
)


def render_all_pages(
    pdf_path: Path,
    dpi: int,
    page_range: Optional[tuple[int, int]],
    render_dir: Path,
) -> None:
    """--render-only 모드: 페이지를 이미지로 저장한다."""
    fitz = require_fitz()
    _ = require_pil()

    doc = fitz.open(str(pdf_path))
    total = doc.page_count

    start, end = _resolve_page_range(page_range, total)

    render_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"렌더링 시작: 페이지 {start + 1}–{end} / 전체 {total}페이지, DPI={dpi}")
    logger.info(f"출력 디렉토리: {render_dir}")

    for i in range(start, end):
        render_page_to_image(doc, i, dpi=dpi, render_dir=render_dir)
        if (i - start + 1) % 10 == 0 or i == end - 1:
            logger.info(f"  {i - start + 1}/{end - start} 페이지 렌더링 완료")

    doc.close()
    logger.info(f"렌더링 완료. 이미지 저장 위치: {render_dir}")


# ---------------------------------------------------------------------------
# 텍스트 파싱
# ---------------------------------------------------------------------------

# 자주 쓰는 정규식 패턴들
_RE_DAY = re.compile(r"\bDAY\s*(\d+)\b", re.IGNORECASE)
_RE_PRONUNCIATION = re.compile(r"\[([^\]]+)\]")
_RE_POS = re.compile(
    r"\b(n\.|v\.|adj\.|adv\.|prep\.|conj\.|pron\.|det\.|aux\.|interj\.)\b"
)
_RE_KOREAN = re.compile(r"[\uAC00-\uD7A3]")
_RE_MEANING_BULLET = re.compile(r"^[•★\-]\s*(.+)$")

# 빈도 표시 패턴
_FREQ_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\*{3}|★{3}"), "★★★"),
    (re.compile(r"\*{2}|★{2}"), "★★"),
    (re.compile(r"\*{1}|★{1}"), "★"),
]

# 품사 정규화 매핑
_POS_MAP: dict[str, str] = {
    "n.": "noun",
    "v.": "verb",
    "adj.": "adjective",
    "adv.": "adverb",
    "prep.": "preposition",
    "conj.": "conjunction",
    "pron.": "pronoun",
    "det.": "determiner",
    "aux.": "auxiliary verb",
    "interj.": "interjection",
}


def _normalize_pos(raw: str) -> str:
    """약어를 정식 품사명으로 변환한다."""
    raw = raw.strip()
    return _POS_MAP.get(raw, raw)


def _detect_frequency(line: str) -> str:
    """줄에서 빈도 표시(★ / *)를 감지한다."""
    for pattern, label in _FREQ_PATTERNS:
        if pattern.search(line):
            return label
    return ""


def _strip_frequency(line: str) -> str:
    """빈도 기호를 제거한 단어 텍스트를 반환한다."""
    line = re.sub(r"[\*★]+", "", line)
    line = re.sub(r"\s+", " ", line)
    return line.strip()


def _is_english_word_line(line: str) -> bool:
    """줄이 영단어 항목의 시작인지 판단한다.

    조건:
    - 알파벳으로 시작하거나 * / ★ 뒤에 알파벳
    - 라인 전체에서 한글 비율이 낮음
    - 충분한 알파벳 포함
    """
    stripped = line.strip()
    if not stripped:
        return False

    # 빈도 기호 제거 후 첫 문자가 알파벳인지 확인
    candidate = _strip_frequency(stripped)
    if not candidate:
        return False

    # 첫 문자가 대소문자 알파벳이어야 함
    if not candidate[0].isalpha():
        return False

    # 한글 비율이 낮아야 함 (예문이 아닌 단어 줄)
    korean_count = len(_RE_KOREAN.findall(candidate))
    total = len(candidate)
    if total == 0:
        return False
    if korean_count / total > 0.3:
        return False

    # 알파벳 문자가 최소 2개 이상
    alpha_count = sum(1 for c in candidate if c.isalpha() and ord(c) < 256)
    return alpha_count >= 2


def _looks_like_new_entry(line: str) -> bool:
    """줄이 새 단어 항목의 시작처럼 보이는지 판단한다."""
    stripped = line.strip()
    # 영단어이고, 발음 기호나 품사 표시 없음
    return _is_english_word_line(stripped) and not _RE_PRONUNCIATION.search(stripped)


def _extract_related_words(block: list[str]) -> list[str]:
    """블록에서 관련어/파생어를 추출한다."""
    related: list[str] = []
    in_related = False

    for line in block:
        stripped = line.strip()
        # 관련어 섹션 표시 감지
        if re.search(r"(관련어|파생어|어구|숙어|토익 이렇게|이렇게 나온다)", stripped):
            in_related = True
            continue
        if in_related and stripped:
            # 영어 단어처럼 보이는 항목을 관련어로 수집
            if _is_english_word_line(stripped):
                word = _strip_frequency(stripped).split()[0]
                if word:
                    related.append(word)
    return related


def _extract_synonyms(block: list[str]) -> list[str]:
    """블록에서 유의어/반의어를 추출한다."""
    synonyms: list[str] = []
    for line in block:
        stripped = line.strip()
        if re.search(r"(유의어|syn\.|유사어|동의어)", stripped, re.IGNORECASE):
            # 같은 줄 또는 다음 줄의 단어들을 수집
            parts = re.split(r"[:|,/]", stripped)
            for part in parts[1:]:
                word = part.strip()
                if word and _is_english_word_line(word):
                    synonyms.append(_strip_frequency(word).split()[0])
    return synonyms


def parse_word_block(
    lines: list[str],
    day: int,
    entry_id: str,
) -> Optional[VocabEntry]:
    """OCR로 추출한 단어 블록을 VocabEntry로 파싱한다.

    Args:
        lines: 단어 항목에 해당하는 텍스트 줄 목록
        day: 현재 처리 중인 Day 번호
        entry_id: 할당할 ID 문자열 (예: "hw_0001")

    Returns:
        파싱된 VocabEntry, 실패 시 None
    """
    if not lines:
        return None

    # 1) 단어 및 빈도 추출 (첫 번째 유효 줄)
    word_line = lines[0].strip()
    frequency = _detect_frequency(word_line)
    word = _strip_frequency(word_line)
    # 공백으로 분리된 경우 첫 토큰만 단어
    word = word.split()[0] if word.split() else word
    word = re.sub(r"[^\w\-\'\.]", "", word)  # 특수문자 제거

    if not word or not any(c.isalpha() for c in word):
        return None

    # 2) 나머지 필드 파싱
    pronunciation: Optional[str] = None
    pos_raw: Optional[str] = None
    meaning_kr: Optional[str] = None
    meaning_en: Optional[str] = None
    example_sentence: Optional[str] = None
    example_translation: Optional[str] = None
    synonyms: list[str] = []
    related_words: list[str] = []

    example_candidate: Optional[str] = None  # 영어 예문 후보

    for line in lines[1:]:
        stripped = line.strip()
        if not stripped:
            continue

        # 발음 기호
        if pronunciation is None:
            pron_match = _RE_PRONUNCIATION.search(stripped)
            if pron_match:
                pronunciation = pron_match.group(1)
                continue

        # 품사
        if pos_raw is None:
            pos_match = _RE_POS.search(stripped)
            if pos_match:
                pos_raw = pos_match.group(1)

        # 한국어 의미 (• 또는 ★ 시작)
        if meaning_kr is None:
            bullet_match = _RE_MEANING_BULLET.match(stripped)
            if bullet_match:
                candidate_meaning = bullet_match.group(1).strip()
                if _RE_KOREAN.search(candidate_meaning):
                    meaning_kr = candidate_meaning
                    continue

        # 관련어/유의어 섹션
        if re.search(r"(관련어|파생어|유의어|syn\.)", stripped, re.IGNORECASE):
            synonyms.extend(_extract_synonyms([stripped]))
            related_words.extend(_extract_related_words([stripped]))
            continue

        # 영어 예문 후보 (알파벳 비율 높음, 단어를 포함)
        alpha_ratio = sum(1 for c in stripped if c.isalpha() and ord(c) < 256) / max(
            len(stripped), 1
        )
        korean_ratio = len(_RE_KOREAN.findall(stripped)) / max(len(stripped), 1)

        if (
            alpha_ratio > 0.5
            and korean_ratio < 0.1
            and len(stripped) > 15
            and not _RE_PRONUNCIATION.search(stripped)
        ):
            if example_candidate is None:
                example_candidate = stripped
            # 예문 (단어 포함 여부 확인)
            if example_sentence is None and re.search(
                re.escape(word), stripped, re.IGNORECASE
            ):
                example_sentence = stripped

        # 한국어 예문 번역
        elif (
            korean_ratio > 0.3
            and example_sentence is not None
            and example_translation is None
            and len(stripped) > 5
        ):
            example_translation = stripped

    # 예문 후보 보완: 단어 포함 예문이 없으면 첫 영어 문장 사용
    if example_sentence is None and example_candidate is not None:
        example_sentence = example_candidate

    # 관련어 추출 (블록 전체에서)
    if not related_words:
        related_words = _extract_related_words(lines)
    if not synonyms:
        synonyms = _extract_synonyms(lines)

    return VocabEntry(
        id=entry_id,
        word=word,
        pos=_normalize_pos(pos_raw) if pos_raw else "",
        meaning_kr=meaning_kr or "",
        meaning_en=meaning_en,
        example_sentence=example_sentence,
        example_translation=example_translation,
        day=day,
        synonyms=synonyms,
        frequency=frequency,
        related_words=related_words,
    )


def split_page_into_blocks(page_text: str) -> list[list[str]]:
    """OCR 텍스트 한 페이지를 단어 블록 목록으로 분리한다.

    단어 항목의 시작: 영단어로 시작하는 줄 (발음/품사/한글 아님)
    블록 구분: 빈 줄 또는 새 단어 줄 감지 시
    """
    lines = page_text.splitlines()
    blocks: list[list[str]] = []
    current_block: list[str] = []

    for line in lines:
        stripped = line.strip()

        # DAY 헤더는 건너뜀
        if _RE_DAY.match(stripped):
            if current_block:
                blocks.append(current_block)
                current_block = []
            continue

        # 새 단어 항목 시작 감지
        if _looks_like_new_entry(stripped):
            if current_block:
                blocks.append(current_block)
            current_block = [line]
        elif stripped:
            current_block.append(line)
        # 빈 줄: 블록 경계로 처리 (단, 짧은 블록은 무시)
        else:
            if current_block and len(current_block) >= 2:
                blocks.append(current_block)
                current_block = []
            elif current_block:
                # 너무 짧은 블록은 그냥 이어 붙임
                pass

    if current_block:
        blocks.append(current_block)

    # 빈 블록 및 너무 짧은 블록 필터링
    return [b for b in blocks if len(b) >= 2 and _looks_like_new_entry(b[0].strip())]


def detect_day_from_text(page_text: str) -> Optional[int]:
    """텍스트에서 현재 Day 번호를 감지한다."""
    match = _RE_DAY.search(page_text)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def is_comic_page(page_text: str) -> bool:
    """만화/일러스트 페이지인지 판단한다 (단어 항목 없음).

    OCR 텍스트가 거의 없거나 단어 항목이 전혀 감지되지 않으면 True.
    """
    if not page_text.strip():
        return True
    lines = [l.strip() for l in page_text.splitlines() if l.strip()]
    # 텍스트 줄이 5줄 미만이면 만화 페이지로 간주
    if len(lines) < 5:
        return True
    # 영단어 항목이 전혀 없으면 만화 페이지
    has_word = any(_looks_like_new_entry(l) for l in lines)
    return not has_word


# ---------------------------------------------------------------------------
# 메인 추출 로직
# ---------------------------------------------------------------------------


def _resolve_page_range(
    page_range: Optional[tuple[int, int]], total_pages: int
) -> tuple[int, int]:
    """페이지 범위를 0-based 인덱스로 변환한다."""
    if page_range is None:
        return 0, total_pages
    start = max(0, page_range[0] - 1)  # 1-based → 0-based
    end = min(total_pages, page_range[1])
    return start, end


def extract_vocab(
    pdf_path: Path = RAW_PDF_PATH,
    output_path: Path = OUTPUT_JSON_PATH,
    page_range: Optional[tuple[int, int]] = None,
    dpi: int = 200,
    use_ocr: bool = True,
    cache_dir: Path = OCR_CACHE_DIR,
) -> list[VocabEntry]:
    """PDF에서 단어 데이터를 추출하여 JSON으로 저장한다.

    Args:
        pdf_path: 입력 PDF 경로
        output_path: 출력 JSON 경로
        page_range: (시작, 끝) 1-based 페이지 번호, None이면 전체
        dpi: OCR 렌더링 DPI
        use_ocr: OCR 수행 여부 (False이면 캐시만 사용)
        cache_dir: OCR 캐시 디렉토리

    Returns:
        추출된 VocabEntry 목록
    """
    if not pdf_path.exists():
        logger.error(f"PDF 파일을 찾을 수 없습니다: {pdf_path}")
        sys.exit(1)

    fitz = require_fitz()
    if use_ocr:
        _ = require_pytesseract()
        _ = require_pil()

    doc = fitz.open(str(pdf_path))
    total_pages = doc.page_count
    start, end = _resolve_page_range(page_range, total_pages)

    logger.info(f"PDF 로드 완료: {pdf_path.name} ({total_pages}페이지)")
    logger.info(f"처리 범위: 페이지 {start + 1}–{end} (총 {end - start}페이지)")
    logger.info(f"DPI: {dpi}, OCR: {'활성' if use_ocr else '캐시만 사용'}")

    stats = ExtractionStats()
    entries: list[VocabEntry] = []
    current_day: int = 0
    word_counter: int = 0

    for page_idx in range(start, end):
        page_num_display = page_idx + 1

        # 진행 상황 출력 (10페이지마다)
        if (page_idx - start) % 10 == 0:
            logger.info(
                f"  [{page_idx - start}/{end - start}] 페이지 {page_num_display} 처리 중... "
                f"(단어 {stats.words_found}개 발견)"
            )

        try:
            page_text, from_cache = get_or_ocr_page(
                doc, page_idx, dpi, use_ocr, cache_dir
            )
        except Exception as exc:
            logger.warning(f"페이지 {page_num_display} OCR 실패: {exc}")
            stats.ocr_errors += 1
            continue

        if from_cache:
            stats.pages_from_cache += 1
        stats.pages_processed += 1

        if not page_text.strip():
            stats.pages_skipped += 1
            continue

        # Day 번호 감지 및 업데이트
        detected_day = detect_day_from_text(page_text)
        if detected_day is not None:
            current_day = detected_day
            stats.days_found.add(current_day)
            logger.info(f"  → Day {current_day} 시작 (페이지 {page_num_display})")

        # 만화/일러스트 페이지 건너뜀
        if is_comic_page(page_text):
            stats.pages_skipped += 1
            logger.debug(f"  페이지 {page_num_display}: 만화 페이지 감지, 건너뜀")
            continue

        # 단어 블록 파싱
        blocks = split_page_into_blocks(page_text)
        if not blocks:
            logger.debug(f"  페이지 {page_num_display}: 단어 블록 없음")
            continue

        for block in blocks:
            word_counter += 1
            entry_id = f"hw_{word_counter:04d}"
            entry = parse_word_block(block, day=current_day, entry_id=entry_id)
            if entry is not None and entry.word:
                entries.append(entry)
                stats.words_found += 1
                logger.debug(
                    f"    단어 추출: [{entry_id}] {entry.word} "
                    f"({entry.pos}) — {entry.meaning_kr[:20] if entry.meaning_kr else '?'}"
                )

    doc.close()

    # JSON 저장
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_data = [e.to_dict() for e in entries]
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    logger.info(f"\n추출 완료!")
    logger.info(stats.report())
    logger.info(f"JSON 저장 위치: {output_path}")

    return entries


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_page_range(value: str) -> tuple[int, int]:
    """'5-20' 형식의 문자열을 (5, 20) 튜플로 변환한다."""
    pattern = re.compile(r"^(\d+)-(\d+)$")
    match = pattern.match(value.strip())
    if not match:
        raise argparse.ArgumentTypeError(
            f"페이지 범위 형식 오류: '{value}'. '시작-끝' 형식을 사용하세요 (예: 5-20)."
        )
    start, end = int(match.group(1)), int(match.group(2))
    if start < 1:
        raise argparse.ArgumentTypeError("시작 페이지는 1 이상이어야 합니다.")
    if start > end:
        raise argparse.ArgumentTypeError("시작 페이지가 끝 페이지보다 클 수 없습니다.")
    return start, end


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="해커스 노랭이 단어장 PDF → JSON 변환 스크립트",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  python extract_vocab.py                     # 전체 PDF 처리
  python extract_vocab.py --pages 1-50        # 1~50 페이지만 처리
  python extract_vocab.py --dpi 300           # 300 DPI로 OCR
  python extract_vocab.py --no-ocr            # OCR 건너뜀, 캐시 텍스트 사용
  python extract_vocab.py --render-only       # 이미지 렌더링만 수행
  python extract_vocab.py --render-only --pages 1-10 --dpi 150
        """,
    )
    parser.add_argument(
        "--pages",
        type=parse_page_range,
        default=None,
        metavar="START-END",
        help="처리할 페이지 범위 (예: 5-20). 기본값: 전체",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=200,
        metavar="DPI",
        help="OCR 렌더링 DPI. 높을수록 정확하지만 느림 (기본값: 200)",
    )
    parser.add_argument(
        "--no-ocr",
        action="store_true",
        help="OCR 수행 없이 기존 캐시 텍스트만 사용",
    )
    parser.add_argument(
        "--render-only",
        action="store_true",
        help="OCR 없이 PDF 페이지를 이미지로만 저장",
    )
    parser.add_argument(
        "--pdf",
        type=Path,
        default=RAW_PDF_PATH,
        metavar="PATH",
        help=f"입력 PDF 경로 (기본값: {RAW_PDF_PATH})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_JSON_PATH,
        metavar="PATH",
        help=f"출력 JSON 경로 (기본값: {OUTPUT_JSON_PATH})",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=OCR_CACHE_DIR,
        metavar="DIR",
        help=f"OCR 캐시 디렉토리 (기본값: {OCR_CACHE_DIR})",
    )
    parser.add_argument(
        "--render-dir",
        type=Path,
        default=RENDER_DIR,
        metavar="DIR",
        help=f"렌더링 이미지 저장 디렉토리 (기본값: {RENDER_DIR})",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="디버그 로그 출력",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.render_only:
        # 이미지 렌더링 전용 모드
        render_all_pages(
            pdf_path=args.pdf,
            dpi=args.dpi,
            page_range=args.pages,
            render_dir=args.render_dir,
        )
        return

    # 일반 추출 모드
    extract_vocab(
        pdf_path=args.pdf,
        output_path=args.output,
        page_range=args.pages,
        dpi=args.dpi,
        use_ocr=not args.no_ocr,
        cache_dir=args.cache_dir,
    )


if __name__ == "__main__":
    main()
