"""
해커스 노랭이 단어장 PDF에서 Chapter별 구조와 900점 완성 단어를 추출한다.

PDF 구조:
  - 각 DAY = 하나의 Chapter (주제별)
  - 각 Day 내 기본 단어 → Daily Checkup → 800점 완성 단어 → 900점 완성 단어
  - 900점 완성 단어 페이지 내에 LC / Part5,6 / Part7 섹션
  - Part5,6과 Part7 섹션의 단어만 추출 (LC 제외)

사용법:
  python extract_chapters.py                        # 전체 PDF 처리
  python extract_chapters.py --pages 1-40           # 특정 페이지 범위
  python extract_chapters.py --topics-override t.json # 챕터 주제명 수동 지정
"""

import sys
import re
import json
import argparse
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

# Windows에서 UTF-8 출력 강제
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

# ---------------------------------------------------------------------------
# 프로젝트 경로 설정
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

RAW_PDF_PATH = PROJECT_ROOT / "data" / "raw" / "hackers_vocab.pdf"
OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "vocab" / "chapter_map.json"
OCR_CACHE_DIR = PROJECT_ROOT / "data" / "processed" / "vocab" / "_ocr_cache"

# ---------------------------------------------------------------------------
# 로깅 설정
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tesseract 설정
# ---------------------------------------------------------------------------

import os as _os

_TESSDATA_DIR = PROJECT_ROOT / "tessdata"
if _TESSDATA_DIR.exists():
    _os.environ["TESSDATA_PREFIX"] = str(_TESSDATA_DIR)


def _setup_tesseract() -> None:
    try:
        import pytesseract
        tesseract_path = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
        if tesseract_path.exists():
            pytesseract.pytesseract.tesseract_cmd = str(tesseract_path)
    except ImportError:
        pass


_setup_tesseract()

# ---------------------------------------------------------------------------
# 감지 패턴
# ---------------------------------------------------------------------------

_RE_DAY = re.compile(r"\bDAY\s*(\d+)\b", re.IGNORECASE)
_RE_KOREAN = re.compile(r"[\uAC00-\uD7A3]+")
_RE_DAY_HEADER = re.compile(r"\bDAY\s*\d+\b", re.IGNORECASE)
_RE_PART56 = re.compile(r"Part\s*5\s*[,.]?\s*6", re.IGNORECASE)
_RE_PART7 = re.compile(r"Part\s*7\b", re.IGNORECASE)
_RE_LC_LINE = re.compile(r"^\s*(?:Lc|LC)\b", re.IGNORECASE)

# 단어 리스트 라인 패턴:
# [symbol] english_word [pos] meaning
# 예: "ㅁ devoted 레 헌 신 적 인"
#     "O questionably adv 의 심 스 럽 게"
_RE_WORD_LINE = re.compile(
    r"^[\s]*"                           # 앞 공백
    r"[ㅁㅇOoCCㄴ디0①②③④⑤⑥\[\]|]*"  # 기호 (OCR 변환)
    r"[\s]*"
    r"([a-zA-Z][a-zA-Z\s\-']+)"        # 영어 단어/구문
    r"[\s]+"
    r"(.+)$"                             # 나머지 (품사+의미)
)

# 품사 패턴
_RE_POS_ABBR = re.compile(
    r"\b(n|v|adj|adv|phr|prep|conj|ad|adi|ag)\b"
)
_POS_NORM = {
    "n": "noun", "v": "verb", "adj": "adjective", "adv": "adverb",
    "phr": "phrase", "prep": "preposition", "conj": "conjunction",
    "ad": "adjective", "adi": "adjective", "ag": "adjective",
}


# ---------------------------------------------------------------------------
# 데이터 구조
# ---------------------------------------------------------------------------

@dataclass
class ChapterInfo:
    chapter: int
    title: str
    start_page: int   # 0-based inclusive
    end_page: int      # 0-based exclusive


# ---------------------------------------------------------------------------
# PDF 텍스트 추출 (Tesseract OCR)
# ---------------------------------------------------------------------------


def get_page_text(doc, page_num: int, dpi: int = 200,
                  cache_dir: Optional[Path] = None) -> str:
    """PDF 페이지에서 Tesseract OCR로 전체 텍스트를 추출한다."""
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / f"page_{page_num + 1:04d}.txt"
        if cache_file.exists():
            return cache_file.read_text(encoding="utf-8")

    try:
        import fitz
        import pytesseract
        from PIL import Image
        import io

        page = doc[page_num]
        matrix = fitz.Matrix(dpi / 72.0, dpi / 72.0)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        img = Image.open(io.BytesIO(pixmap.tobytes("png")))
        text = pytesseract.image_to_string(img, lang="kor+eng")

        if cache_dir is not None:
            cache_file = cache_dir / f"page_{page_num + 1:04d}.txt"
            cache_file.write_text(text, encoding="utf-8")

        return text
    except Exception as exc:
        logger.warning(f"페이지 {page_num + 1} OCR 실패: {exc}")
        return ""


def detect_page_level(doc, page_num: int, dpi: int = 400) -> Optional[int]:
    """페이지 상단 헤더에서 800점/900점 완성 단어 레벨을 감지한다.

    Returns:
        800, 900, 또는 None (감지 실패)
    """
    try:
        import fitz
        import pytesseract
        from PIL import Image
        import io

        page = doc[page_num]
        matrix = fitz.Matrix(dpi / 72.0, dpi / 72.0)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        img = Image.open(io.BytesIO(pixmap.tobytes("png")))
        w, h = img.size

        # 페이지 상단 6~9% 영역 크롭 (헤더 박스 위치)
        header = img.crop((0, int(h * 0.05), int(w * 0.5), int(h * 0.09)))
        text = pytesseract.image_to_string(header, lang="kor+eng", config="--psm 7")

        if "900" in text:
            return 900
        if "800" in text:
            return 800
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 챕터 제목 추출
# ---------------------------------------------------------------------------


def extract_chapter_topic(page_text: str) -> str:
    """DAY 타이틀 페이지에서 챕터 주제명(한국어)을 추출한다."""
    lines = page_text.splitlines()

    day_line_idx: Optional[int] = None
    for idx, line in enumerate(lines):
        if _RE_DAY.search(line):
            day_line_idx = idx
            break

    if day_line_idx is None:
        return ""

    candidates: list[tuple[int, str]] = []
    search_start = max(0, day_line_idx - 5)
    search_end = min(len(lines), day_line_idx + 6)

    for idx in range(search_start, search_end):
        line = lines[idx].strip()
        if not line:
            continue
        if _RE_DAY.search(line):
            remainder = _RE_DAY_HEADER.sub("", line).strip()
            if remainder:
                korean_parts = _RE_KOREAN.findall(remainder)
                for kp in korean_parts:
                    if 2 <= len(kp) <= 10:
                        candidates.append((0, kp))
            continue

        korean_parts = _RE_KOREAN.findall(line)
        for kp in korean_parts:
            if 2 <= len(kp) <= 10:
                distance = abs(idx - day_line_idx)
                candidates.append((distance, kp))

    if not candidates:
        return ""

    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


# ---------------------------------------------------------------------------
# 단어 리스트 파싱
# ---------------------------------------------------------------------------


def parse_word_list_line(line: str) -> Optional[dict]:
    """단어 리스트 형식의 한 줄을 파싱한다.

    형식 예: "ㅁ devoted 레 헌 신 적 인"
             "O questionably adv 의 심 스 럽 게"
             "ㅁ credential 『 신 임 장 , 자 격 증 명"
    """
    stripped = line.strip()
    if not stripped or len(stripped) < 5:
        return None

    # 반드시 한국어 의미가 포함되어야 함 (예문/잡음 제외)
    if not _RE_KOREAN.search(stripped):
        return None

    # 줄에서 영어 단어/구문 추출
    match = _RE_WORD_LINE.match(stripped)
    if not match:
        return None

    word_phrase = match.group(1).strip()
    rest = match.group(2).strip()

    # 영어 단어의 마지막 토큰이 품사 약어이면 분리
    word_tokens = word_phrase.split()
    pos = ""

    if len(word_tokens) >= 2:
        last_token = word_tokens[-1].rstrip(".")
        if last_token in _POS_NORM or last_token in ("n", "v", "adj", "adv", "phr",
                                                       "ad", "adi", "ag"):
            pos = _POS_NORM.get(last_token, last_token)
            word_tokens = word_tokens[:-1]
            word_phrase = " ".join(word_tokens)

    # 영어 단어는 최대 4단어 (그 이상이면 예문일 가능성 높음)
    if len(word_tokens) > 4:
        return None

    # 2글자 미만 제외
    if len(word_phrase) < 2:
        return None

    # 숫자로 시작하면 제외
    if word_phrase[0].isdigit():
        return None

    # rest에서도 품사 추출 시도 (word에서 못 찾은 경우)
    if not pos:
        pos_match = _RE_POS_ABBR.search(rest)
        if pos_match:
            pos_raw = pos_match.group(1)
            pos = _POS_NORM.get(pos_raw, pos_raw)

    # 한국어 의미 추출 — 개별 한국어 토큰을 쉼표로 구분
    korean_parts = _RE_KOREAN.findall(rest)
    meaning_kr = ", ".join(korean_parts) if korean_parts else ""

    return {
        "word": word_phrase,
        "pos": pos,
        "meaning_kr": meaning_kr,
    }


def extract_words_from_page(page_text: str) -> dict:
    """페이지 텍스트에서 Part5,6 / Part7 섹션의 단어를 추출한다.

    Returns:
        {"part56": [word_dicts], "part7": [word_dicts], "lc": [word_dicts]}
    """
    lines = page_text.splitlines()
    result: dict[str, list[dict]] = {"lc": [], "part56": [], "part7": []}
    current_section = "lc"  # 기본적으로 LC 섹션으로 시작

    for line in lines:
        stripped = line.strip()

        # 섹션 마커 감지
        if _RE_PART56.search(stripped):
            current_section = "part56"
            # Part5,6 마커 줄 자체에 단어가 포함될 수 있음
            after_marker = _RE_PART56.sub("", stripped).strip()
            if after_marker:
                word = parse_word_list_line(after_marker)
                if word:
                    result[current_section].append(word)
            continue

        if _RE_PART7.search(stripped):
            current_section = "part7"
            after_marker = _RE_PART7.sub("", stripped).strip()
            if after_marker:
                word = parse_word_list_line(after_marker)
                if word:
                    result[current_section].append(word)
            continue

        # LC 마커
        if _RE_LC_LINE.match(stripped):
            current_section = "lc"
            continue

        # 페이지 하단 푸터/잡음 제거
        if re.search(r"Hackers\.co\.kr|토\s*익\s*자\s*료|해\s*커\s*스", stripped):
            break

        # 단어 파싱
        word = parse_word_list_line(stripped)
        if word:
            result[current_section].append(word)

    return result


# ---------------------------------------------------------------------------
# 페이지 범위 해석
# ---------------------------------------------------------------------------


def _resolve_page_range(
    page_range: Optional[tuple[int, int]], total_pages: int
) -> tuple[int, int]:
    if page_range is None:
        return 0, total_pages
    start = max(0, page_range[0] - 1)
    end = min(total_pages, page_range[1])
    return start, end


# ---------------------------------------------------------------------------
# 주제명 오버라이드 로드
# ---------------------------------------------------------------------------


def load_topics_override(path: Optional[Path]) -> Optional[dict[int, str]]:
    if path is None:
        return None
    if not path.exists():
        logger.warning(f"주제명 오버라이드 파일을 찾을 수 없습니다: {path}")
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(f"주제명 오버라이드 파일 로드 실패: {exc}")
        return None

    result: dict[int, str] = {}
    if isinstance(data, dict):
        for key, val in data.items():
            try:
                result[int(key)] = str(val)
            except (ValueError, TypeError):
                pass
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and "chapter" in item and "title" in item:
                try:
                    result[int(item["chapter"])] = str(item["title"])
                except (ValueError, TypeError):
                    pass
    return result if result else None


# ---------------------------------------------------------------------------
# 메인 추출 로직
# ---------------------------------------------------------------------------


def extract_chapters(
    pdf_path: Path = RAW_PDF_PATH,
    output_path: Path = OUTPUT_PATH,
    page_range: Optional[tuple[int, int]] = None,
    dpi: int = 200,
    cache_dir: Path = OCR_CACHE_DIR,
    topics_override: Optional[dict[int, str]] = None,
) -> list[dict]:
    """PDF에서 챕터 구조와 900점 완성 단어를 추출하여 JSON으로 저장한다.

    3-Pass 알고리즘:
      Pass 1: 전체 페이지 OCR + DAY 경계 감지
      Pass 2: 보충 단어 페이지(DAY 헤더 없음) 에서 900점 헤더 감지
      Pass 3: 900점 페이지에서 Part5,6 / Part7 단어 추출
    """
    import fitz

    if not pdf_path.exists():
        logger.error(f"PDF 파일을 찾을 수 없습니다: {pdf_path}")
        sys.exit(1)

    doc = fitz.open(str(pdf_path))
    total_pages = doc.page_count
    start, end = _resolve_page_range(page_range, total_pages)

    logger.info(f"PDF 로드 완료: {pdf_path.name} ({total_pages}페이지)")
    logger.info(f"처리 범위: 페이지 {start + 1}–{end} (총 {end - start}페이지)")

    override = topics_override or {}

    # ── Pass 1: 전체 OCR + DAY 경계 감지 ──────────────────────────────────
    logger.info("=" * 60)
    logger.info("Pass 1: 전체 페이지 OCR + DAY 경계 감지")
    logger.info("=" * 60)

    page_texts: dict[int, str] = {}  # page_idx → ocr text
    day_starts: list[tuple[int, int, str]] = []  # (day_num, page_idx, topic)

    for page_idx in range(start, end):
        if (page_idx - start) % 20 == 0:
            logger.info(f"  OCR 진행: {page_idx - start}/{end - start} 페이지")

        text = get_page_text(doc, page_idx, dpi=dpi, cache_dir=cache_dir)
        page_texts[page_idx] = text

        if not text.strip():
            continue

        day_num = _detect_day(text)
        if day_num is not None:
            topic = override.get(day_num, "") or extract_chapter_topic(text)
            day_starts.append((day_num, page_idx, topic))
            logger.info(
                f"  → Day {day_num} (페이지 {page_idx + 1})"
                + (f" — {topic}" if topic else "")
            )

    if not day_starts:
        logger.warning("DAY 헤더를 찾지 못했습니다.")
        _write_empty(output_path)
        doc.close()
        return []

    # 프론트매터 필터링: Day 1이 최초로 감지된 위치 이전은 무시
    first_day1_idx = None
    for idx, (day_num, page_idx, topic) in enumerate(day_starts):
        if day_num == 1:
            first_day1_idx = idx
            break
    if first_day1_idx is not None and first_day1_idx > 0:
        logger.info(
            f"  프론트매터 필터: Day 1 이전 {first_day1_idx}개 감지 제거"
        )
        day_starts = day_starts[first_day1_idx:]

    # DAY 경계 중복 제거 (같은 DAY가 여러 페이지에 감지될 수 있음)
    seen_days: set[int] = set()
    unique_starts: list[tuple[int, int, str]] = []
    for day_num, page_idx, topic in day_starts:
        if day_num not in seen_days:
            seen_days.add(day_num)
            unique_starts.append((day_num, page_idx, topic))
    day_starts = unique_starts

    logger.info(f"총 {len(day_starts)}개 Day 감지")

    # ── Pass 2: 보충 단어 페이지에서 900점 감지 ──────────────────────────
    logger.info("=" * 60)
    logger.info("Pass 2: 900점 완성 페이지 감지")
    logger.info("=" * 60)

    # 각 Day의 페이지 범위 계산
    chapters: list[ChapterInfo] = []
    for i, (day_num, page_idx, topic) in enumerate(day_starts):
        if i + 1 < len(day_starts):
            end_page = day_starts[i + 1][1]
        else:
            end_page = end
        chapters.append(ChapterInfo(
            chapter=day_num, title=topic,
            start_page=page_idx, end_page=end_page,
        ))

    # 각 Day 내에서 900점 페이지 찾기
    # 보충 단어 페이지 = DAY 타이틀 아닌 + 기본 단어 아닌 페이지 (리스트 형식)
    day_900_pages: dict[int, list[int]] = {}  # day_num → [page_indices]

    for ch in chapters:
        pages_900: list[int] = []
        for page_idx in range(ch.start_page, ch.end_page):
            text = page_texts.get(page_idx, "")
            if not text.strip():
                continue

            # DAY 타이틀 페이지 건너뜀 (상단에서만 감지)
            if _detect_day(text) is not None:
                continue

            # 단어 리스트 형식 감지 (Part5,6 또는 Part7 마커가 있거나
            # 다수의 리스트 라인이 있는 페이지)
            has_part = bool(_RE_PART56.search(text) or _RE_PART7.search(text))
            if not has_part:
                continue

            # 헤더에서 800/900 감지
            level = detect_page_level(doc, page_idx, dpi=400)

            if level == 900:
                pages_900.append(page_idx)
                logger.info(
                    f"  Day {ch.chapter}: 900점 완성 페이지 발견 "
                    f"(페이지 {page_idx + 1})"
                )
            elif level == 800:
                logger.debug(
                    f"  Day {ch.chapter}: 800점 완성 페이지 "
                    f"(페이지 {page_idx + 1}) — 건너뜀"
                )
            elif has_part:
                # 레벨 감지 실패 — 포함하지 않음 (보수적 접근)
                logger.debug(
                    f"  Day {ch.chapter}: 레벨 미확인 Part 페이지 "
                    f"(페이지 {page_idx + 1}) — 건너뜀"
                )

        day_900_pages[ch.chapter] = pages_900

    # ── Pass 3: 900점 페이지에서 Part5,6 / Part7 단어 추출 ──────────────
    logger.info("=" * 60)
    logger.info("Pass 3: 900점 완성 단어 추출")
    logger.info("=" * 60)

    results: list[dict] = []
    total_words = 0

    for ch in chapters:
        pages = day_900_pages.get(ch.chapter, [])
        words: list[dict] = []
        word_counter = 0

        for page_idx in pages:
            text = page_texts.get(page_idx, "")
            if not text.strip():
                continue

            extracted = extract_words_from_page(text)
            # Part5,6과 Part7 단어만 수집 (LC 제외)
            for section in ["part56", "part7"]:
                for w in extracted[section]:
                    word_counter += 1
                    w["id"] = f"ch{ch.chapter:02d}_{word_counter:03d}"
                    w["section"] = section
                    if not w.get("related_words"):
                        w["related_words"] = []
                    if not w.get("synonyms"):
                        w["synonyms"] = []
                    if not w.get("example_sentence"):
                        w["example_sentence"] = None
                    if not w.get("example_translation"):
                        w["example_translation"] = None
                    if not w.get("frequency"):
                        w["frequency"] = ""
                    words.append(w)

        total_words += len(words)
        results.append({
            "chapter": ch.chapter,
            "title": ch.title,
            "words": words,
        })

        if words:
            logger.info(
                f"  Day {ch.chapter:2d} [{ch.title or '?'}]: "
                f"{len(words)}개 단어 (Part5,6: "
                f"{sum(1 for w in words if w['section']=='part56')}, "
                f"Part7: {sum(1 for w in words if w['section']=='part7')})"
            )

        # 중간 저장 (5개 챕터마다)
        if len(results) % 5 == 0:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            logger.info(f"  [중간 저장] {len(results)}개 챕터, {total_words}개 단어")

    # ── JSON 저장 ─────────────────────────────────────────────────────────
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    doc.close()

    # 요약
    logger.info("")
    logger.info("=" * 60)
    logger.info("추출 완료")
    logger.info("=" * 60)
    logger.info(f"총 챕터: {len(results)}")
    logger.info(f"총 단어: {total_words}")
    for r in results:
        if r["words"]:
            logger.info(
                f"  Day {r['chapter']:2d} [{r['title'] or '?'}]: "
                f"{len(r['words'])}개"
            )
    logger.info(f"저장: {output_path}")

    return results


def _detect_day(text: str) -> Optional[int]:
    """텍스트 상단(첫 5줄)에서만 DAY 번호를 감지한다.

    푸터나 앱 참조의 "DAY" 오감지를 방지하기 위해 상단만 검사한다.
    """
    lines = text.splitlines()
    # 첫 5줄에서만 DAY 검색 (페이지 헤더/타이틀 영역)
    top_lines = "\n".join(lines[:5])
    match = _RE_DAY.search(top_lines)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def _write_empty(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump([], f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_page_range(value: str) -> tuple[int, int]:
    pattern = re.compile(r"^(\d+)-(\d+)$")
    match = pattern.match(value.strip())
    if not match:
        raise argparse.ArgumentTypeError(
            f"페이지 범위 형식 오류: '{value}'. '시작-끝' 형식 (예: 5-20)"
        )
    s, e = int(match.group(1)), int(match.group(2))
    if s < 1 or s > e:
        raise argparse.ArgumentTypeError("올바른 범위를 입력하세요.")
    return s, e


def main() -> None:
    parser = argparse.ArgumentParser(
        description="해커스 노랭이 단어장 PDF → chapter_map.json 추출",
    )
    parser.add_argument("--pages", type=parse_page_range, default=None,
                        metavar="S-E", help="처리 페이지 범위 (예: 1-40)")
    parser.add_argument("--dpi", type=int, default=200, help="OCR DPI (기본 200)")
    parser.add_argument("--cache-dir", type=Path, default=OCR_CACHE_DIR)
    parser.add_argument("--pdf", type=Path, default=RAW_PDF_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--topics-override", type=Path, default=None,
                        help='주제명 오버라이드 JSON')
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    topics = load_topics_override(args.topics_override)

    extract_chapters(
        pdf_path=args.pdf,
        output_path=args.output,
        page_range=args.pages,
        dpi=args.dpi,
        cache_dir=args.cache_dir,
        topics_override=topics,
    )


if __name__ == "__main__":
    main()
