"""
ETS 정답 및 해설 PDF에서 정답, 카테고리, 해설을 추출하여
기존 문제 JSON에 병합한다.

OCR 완료된 PDF(ets_vol{N}_anwer_ocr.pdf)에서 텍스트를 추출하거나,
원본 이미지 PDF에서 직접 OCR을 수행할 수 있다.

Usage:
    python extract_answers.py --volume 1              # Process vol1
    python extract_answers.py --all                   # Process all volumes
    python extract_answers.py --volume 1 --ocr        # OCR from original PDF
    python extract_answers.py --volume 1 --dry-run    # Show without saving
"""

import sys

sys.stdout.reconfigure(encoding="utf-8")

import argparse
import json
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Environment setup (must precede library imports that use temp dirs)
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]  # C:\Data\Toeic Brain

os.environ["TESSDATA_PREFIX"] = str(PROJECT_ROOT / "tessdata")
_tmp_dir = str(PROJECT_ROOT / "data" / "raw" / "answer" / "_tmp")
os.environ["TMPDIR"] = _tmp_dir
os.environ["TEMP"] = _tmp_dir
os.environ["TMP"] = _tmp_dir
tempfile.tempdir = _tmp_dir

import fitz  # PyMuPDF

# Lazy import for pytesseract (only needed with --ocr)
_pytesseract = None


def _get_pytesseract():
    global _pytesseract
    if _pytesseract is None:
        import pytesseract

        pytesseract.pytesseract.tesseract_cmd = (
            r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        )
        _pytesseract = pytesseract
    return _pytesseract


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
)
logging.basicConfig(level=logging.INFO, handlers=[_handler])
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants / Paths
# ---------------------------------------------------------------------------
ANSWER_DIR = PROJECT_ROOT / "data" / "raw" / "answer"
QUESTIONS_DIR = PROJECT_ROOT / "data" / "processed" / "questions"

DPI = 300
LANG = "kor+eng"

# Part 5 question numbers
Q_START = 101
Q_END = 130

# Full test question range (Parts 5–7, used for answer grid scanning)
FULL_Q_START = 101
FULL_Q_END = 200

# ---------------------------------------------------------------------------
# OCR correction: characters commonly misread by Tesseract / Acrobat OCR
# Applied to answer grid letters only.
# '0' (zero) and 'O' (letter O) are ambiguous between C and D;
# resolved using the explanation text when possible.
# ---------------------------------------------------------------------------
OCR_LETTER_MAP = {
    "8": "B",
    "4": "A",
    "ㅁ": "D",
    "o": "C",  # lowercase o
    "0": "C",  # zero -> default C, may be overridden
    "O": "C",  # uppercase O -> default C, may be overridden
}

VALID_ANSWERS = {"A", "B", "C", "D"}

# ---------------------------------------------------------------------------
# Category normalization
# ---------------------------------------------------------------------------
CATEGORY_MAP = {
    # 품사 (part of speech position)
    "형용사자리": "품사",
    "명사자리": "품사",
    "부사자리": "품사",
    "동사자리": "품사",
    "분사자리": "품사",
    "형용사": "품사",
    "명사": "품사",
    "부사": "품사",
    "동사": "품사",
    "분사": "품사",
    "품사": "품사",
    # 어휘 (vocabulary)
    "형용사어휘": "어휘",
    "명사어휘": "어휘",
    "부사어휘": "어휘",
    "동사어휘": "어휘",
    "어휘": "어휘",
    # 접속사/전치사
    "접속사자리": "접속사/전치사",
    "전치사자리": "접속사/전치사",
    "접속사": "접속사/전치사",
    "전치사": "접속사/전치사",
    "접속부사": "접속사/전치사",
    # 대명사
    "인칭대명사": "대명사",
    "재귀대명사": "대명사",
    "대명사자리": "대명사",
    "대명사": "대명사",
    "지시대명사": "대명사",
    # 관계대명사
    "관계대명사": "관계대명사",
    "관계부사": "관계대명사",
    # 동사 시제/태
    "시제": "동사시제/태",
    "태": "동사시제/태",
    "수동태": "동사시제/태",
    "능동태": "동사시제/태",
    "동사시제": "동사시제/태",
    "동사의태": "동사시제/태",
    "동사의수": "동사시제/태",
    "수일치": "동사시제/태",
    # 비교급/최상급
    "비교급": "비교급/최상급",
    "최상급": "비교급/최상급",
    "비교구문": "비교급/최상급",
}


def normalize_category(raw: str) -> str:
    """Normalize a raw OCR category string to a standard category."""
    # Remove all whitespace (OCR adds spaces between Korean chars)
    cleaned = re.sub(r"\s+", "", raw).strip()
    # Remove trailing punctuation / underscores
    cleaned = re.sub(r"[_\-.,。·]+$", "", cleaned)
    # Remove leading punctuation / underscores
    cleaned = re.sub(r"^[_\-.,。·]+", "", cleaned)

    # Try direct map
    if cleaned in CATEGORY_MAP:
        return CATEGORY_MAP[cleaned]

    # Try partial matching: check if any key is a substring of cleaned
    for key, val in CATEGORY_MAP.items():
        if key in cleaned:
            return val

    # Return cleaned as-is if no match
    return cleaned if cleaned else "기타문법"


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------


def load_text_from_ocr_pdf(path: Path) -> str:
    """Extract full text from an OCR'd (searchable) PDF using PyMuPDF."""
    log.info("텍스트 추출 (OCR PDF): %s", path.name)
    doc = fitz.open(str(path))
    pages = []
    for i, page in enumerate(doc):
        text = page.get_text("text")
        pages.append(f"\n===PAGE {i + 1}===\n{text}")
    doc.close()
    full = "\n".join(pages)
    log.info("  총 %d 페이지, %d 문자 추출", len(pages), len(full))
    return full


def ocr_from_original(path: Path) -> str:
    """OCR an original image PDF page by page, return concatenated text."""
    pytesseract = _get_pytesseract()
    from PIL import Image

    log.info("직접 OCR 수행: %s", path.name)
    Path(_tmp_dir).mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(path))
    total = len(doc)
    pages = []

    for i in range(total):
        page = doc[i]
        pix = page.get_pixmap(dpi=DPI)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        try:
            text = pytesseract.image_to_string(img, lang=LANG)
        except Exception as e:
            log.warning("  페이지 %d OCR 실패: %s", i + 1, e)
            text = ""
        pages.append(f"\n===PAGE {i + 1}===\n{text}")

        if (i + 1) % 20 == 0 or i == total - 1:
            log.info("  OCR 진행: %d/%d 페이지", i + 1, total)

    doc.close()
    full = "\n".join(pages)
    log.info("  총 %d 페이지, %d 문자 추출", total, len(full))
    return full


def get_text_for_volume(volume: int, use_ocr: bool = False) -> str:
    """
    Get full text for a volume, either from Acrobat OCR PDF or by OCR'ing
    the original image PDF directly with Tesseract.

    Raises FileNotFoundError with a descriptive message if neither PDF is found.
    """
    ocr_path = ANSWER_DIR / f"ets_vol{volume}_anwer_ocr.pdf"
    orig_path = ANSWER_DIR / f"ets_vol{volume}_anwer.pdf"

    if not use_ocr and ocr_path.exists():
        return load_text_from_ocr_pdf(ocr_path)

    if orig_path.exists():
        if not use_ocr and not ocr_path.exists():
            log.info(
                "OCR PDF 없음 (%s) — 원본에서 직접 OCR 수행. "
                "Acrobat으로 OCR 처리한 파일을 %s 에 저장하면 더 나은 결과를 얻을 수 있습니다.",
                ocr_path.name,
                ocr_path,
            )
        return ocr_from_original(orig_path)

    # Neither file found: provide clear guidance
    raise FileNotFoundError(
        f"Vol{volume}: 정답 PDF를 찾을 수 없습니다.\n"
        f"  OCR PDF 경로: {ocr_path}\n"
        f"  원본 PDF 경로: {orig_path}\n"
        f"Adobe Acrobat으로 OCR 처리 후 {ocr_path.name} 으로 저장하거나,\n"
        f"원본 이미지 PDF를 {orig_path.name} 으로 저장하십시오."
    )


# ---------------------------------------------------------------------------
# Answer grid parsing
# ---------------------------------------------------------------------------

# Strict pattern: 101(B), 102(C) etc.
_GRID_STRICT = re.compile(
    r"(\d{3})\s*\(\s*([A-Da-d])\s*\)"
)

# Fuzzy pattern: includes OCR misreads (8=B, 4=A, 0/O/o=C, ㅁ=D)
_GRID_FUZZY = re.compile(
    r"(\d{3})\s*[\(\[]\s*([A-Da-d0-9ㅁOo])\s*[\)\]]"
)


def _correct_letter(raw: str) -> str:
    """Apply OCR correction to a single answer letter."""
    c = raw.strip()
    if c in VALID_ANSWERS:
        return c
    upper = c.upper()
    if upper in VALID_ANSWERS:
        return upper
    corrected = OCR_LETTER_MAP.get(c)
    return corrected if corrected else c


def parse_answer_grid(text: str) -> dict[int, str]:
    """
    Parse answer grid from OCR text.
    Tries strict ABCD pattern first; falls back to fuzzy OCR-corrected pattern.
    Returns {question_number: answer_letter} for all question numbers found.
    Grid answers are the most reliable source; duplicates keep first occurrence.
    """
    results: dict[int, str] = {}

    # First pass: strict pattern (clean OCR, no corrections needed)
    for m in _GRID_STRICT.finditer(text):
        qnum = int(m.group(1))
        letter = m.group(2).upper()
        if qnum not in results:
            results[qnum] = letter

    # Second pass: fuzzy pattern for any missed questions
    for m in _GRID_FUZZY.finditer(text):
        qnum = int(m.group(1))
        if qnum in results:
            continue  # already found by strict pass
        raw_letter = m.group(2)
        letter = _correct_letter(raw_letter)
        results[qnum] = letter

    return results


# ---------------------------------------------------------------------------
# Explanation parsing
# ---------------------------------------------------------------------------

# Test boundary markers (OCR may insert spaces between Korean chars)
_TEST_BOUNDARY = re.compile(
    r"(?:기\s*출\s*)?TEST\s*(\d+)", re.IGNORECASE
)

# Question block start: 3-digit number at start of line / after newline
_Q_BLOCK_SPLIT = re.compile(r"\n\s*(\d{3})\s+")

# Answer within explanation: (A)/(B)/(C)/(D) followed by Korean/English text then 정답
_ANSWER_IN_EXPL = re.compile(
    r"\(([A-D])\)\s*\S+.*?정\s*답", re.DOTALL
)

# Section markers (with possible OCR spacing between Korean chars)
_HAESUL = re.compile(r"해\s*설")
_BUNYUK = re.compile(r"번\s*역")
_EOHWI = re.compile(r"어\s*휘")


def _remove_spaces_korean(s: str) -> str:
    """Remove spaces between Korean characters (OCR artifact)."""
    return re.sub(r"([\uac00-\ud7a3])\s+([\uac00-\ud7a3])", r"\1\2", s)


def _clean_korean_spaces(s: str) -> str:
    """Iteratively remove spaces between Korean chars until stable."""
    prev = ""
    while prev != s:
        prev = s
        s = _remove_spaces_korean(s)
    return s


def split_by_test(text: str) -> dict[int, str]:
    """
    Split full PDF text into per-test chunks.
    Returns {test_number: text_chunk}.
    """
    markers = list(_TEST_BOUNDARY.finditer(text))
    if not markers:
        log.warning("테스트 경계를 찾을 수 없음 — 전체 텍스트를 TEST 1로 처리")
        return {1: text}

    tests: dict[int, str] = {}
    for i, m in enumerate(markers):
        test_num = int(m.group(1))
        start = m.start()
        end = markers[i + 1].start() if i + 1 < len(markers) else len(text)
        if test_num not in tests:
            tests[test_num] = text[start:end]
        else:
            # Append if test marker appears multiple times
            # (e.g., answer grid page + explanation pages)
            tests[test_num] += "\n" + text[start:end]

    log.info("  테스트 경계 감지: %s", sorted(tests.keys()))
    return tests


def parse_explanations(text: str) -> dict[int, dict]:
    """
    Parse explanation blocks from a single test's text.
    Only returns entries for Part 5 questions (Q_START–Q_END).
    Returns {question_number: {category, answer, explanation, translation}}.
    """
    results: dict[int, dict] = {}

    # Split into question blocks
    # parts[0] = pre-amble, then alternating [qnum_str, block_text, ...]
    parts = _Q_BLOCK_SPLIT.split(text)

    i = 1
    while i < len(parts) - 1:
        qnum_str = parts[i]
        block = parts[i + 1]
        i += 2

        try:
            qnum = int(qnum_str)
        except ValueError:
            continue

        # Only Part 5 questions
        if qnum < Q_START or qnum > Q_END:
            continue

        # Keep first occurrence
        if qnum in results:
            continue

        info: dict = {
            "question_number": qnum,
            "category": None,
            "answer": None,
            "explanation": None,
            "translation": None,
        }

        # --- Category: first line before 해설 ---
        haesul_m = _HAESUL.search(block)
        if haesul_m:
            category_raw = block[: haesul_m.start()]
        else:
            first_line_end = block.find("\n")
            category_raw = block[:first_line_end] if first_line_end > 0 else block[:40]

        cat_clean = _clean_korean_spaces(category_raw).strip()
        cat_clean = re.sub(r"^[\s_\-.,。·]+", "", cat_clean)
        cat_clean = re.sub(r"[\s_\-.,。·]+$", "", cat_clean)
        if cat_clean:
            info["category"] = normalize_category(cat_clean)

        # --- Answer from explanation text (secondary source) ---
        answer_m = _ANSWER_IN_EXPL.search(block)
        if answer_m:
            info["answer"] = answer_m.group(1)

        # --- Explanation: text between 해설 and 번역 ---
        if haesul_m:
            bunyuk_m2 = _BUNYUK.search(block)
            eohwi_m2 = _EOHWI.search(block)
            end_markers = []
            if bunyuk_m2 and bunyuk_m2.start() > haesul_m.end():
                end_markers.append(bunyuk_m2.start())
            if eohwi_m2 and eohwi_m2.start() > haesul_m.end():
                end_markers.append(eohwi_m2.start())

            expl_end = min(end_markers) if end_markers else len(block)
            expl_raw = block[haesul_m.end() : expl_end]
            expl_clean = _clean_korean_spaces(expl_raw).strip()
            if expl_clean:
                info["explanation"] = expl_clean

        # --- Translation: text after 번역 until 어휘 or end ---
        bunyuk_m = _BUNYUK.search(block)
        if bunyuk_m:
            remainder = block[bunyuk_m.end() :]
            eohwi_m = _EOHWI.search(remainder)
            trans_raw = remainder[: eohwi_m.start()] if eohwi_m else remainder
            trans_clean = _clean_korean_spaces(trans_raw).strip()
            if trans_clean:
                info["translation"] = trans_clean

        results[qnum] = info

    return results


# ---------------------------------------------------------------------------
# Answer resolution: grid takes priority
# ---------------------------------------------------------------------------


def resolve_answers(
    grid: dict[int, str],
    explanations: dict[int, dict],
) -> dict[int, str]:
    """
    Resolve final answers for each question.

    Priority (highest to lowest):
      1. Answer grid (strict A-D) — most reliable
      2. Answer grid (OCR-corrected, possibly ambiguous)
      3. Explanation-derived answer

    Cross-validation: if both grid and explanation are valid ABCD and differ,
    log a warning but keep grid answer (grid is authoritative).
    """
    merged: dict[int, str] = {}

    all_qnums = sorted(set(grid.keys()) | set(explanations.keys()))
    for qnum in all_qnums:
        grid_ans = grid.get(qnum)
        expl_ans = explanations.get(qnum, {}).get("answer")

        if grid_ans and grid_ans in VALID_ANSWERS:
            # Grid has a clean answer — use it unconditionally
            merged[qnum] = grid_ans
            # Cross-validate for logging only
            if (
                expl_ans
                and expl_ans in VALID_ANSWERS
                and expl_ans != grid_ans
            ):
                log.warning(
                    "  Q%d: 그리드(%s) vs 해설(%s) 불일치 — 그리드 정답 우선",
                    qnum,
                    grid_ans,
                    expl_ans,
                )
        elif expl_ans and expl_ans in VALID_ANSWERS:
            # No valid grid answer; fall back to explanation
            merged[qnum] = expl_ans
        elif grid_ans:
            # Grid answer present but not clean ABCD (OCR ambiguous)
            merged[qnum] = grid_ans
        elif expl_ans:
            merged[qnum] = expl_ans

    return merged


# ---------------------------------------------------------------------------
# Backup helper
# ---------------------------------------------------------------------------


def _backup_json(json_path: Path) -> Path:
    """Create a .bak copy of a JSON file. Returns backup path."""
    bak_path = json_path.with_suffix(".json.bak")
    shutil.copy2(str(json_path), str(bak_path))
    log.info("  백업 생성: %s", bak_path.name)
    return bak_path


# ---------------------------------------------------------------------------
# Merge with existing question JSONs
# ---------------------------------------------------------------------------


def merge_into_volume(
    volume: int,
    answers_by_test: dict[int, dict[int, str]],
    explanations_by_test: dict[int, dict[int, dict]],
    dry_run: bool = False,
) -> dict:
    """
    Load the volume's Part 5 JSON once, apply all test updates, save once.
    Creates a .bak backup before writing.

    answers_by_test:      {test_num: {qnum: answer_letter}}
    explanations_by_test: {test_num: {qnum: expl_info_dict}}

    Returns aggregate stats dict.
    """
    json_path = QUESTIONS_DIR / f"vol{volume}_part5.json"
    if not json_path.exists():
        log.warning("JSON 파일 없음: %s", json_path)
        return {"error": "file_not_found"}

    with open(json_path, "r", encoding="utf-8") as f:
        questions = json.load(f)

    total_stats = {
        "updated_answer": 0,
        "updated_category": 0,
        "updated_explanation": 0,
        "skipped": 0,
    }

    for q in questions:
        test_num = q["test"]
        qnum = q["question_number"]

        answers = answers_by_test.get(test_num, {})
        explanations = explanations_by_test.get(test_num, {})

        # -- Answer (grid priority already resolved before calling this) --
        if qnum in answers:
            new_ans = answers[qnum]
            if new_ans in VALID_ANSWERS:
                if q.get("answer") != new_ans:
                    q["answer"] = new_ans
                    total_stats["updated_answer"] += 1
            else:
                log.warning(
                    "  TEST%d Q%d: 유효하지 않은 정답 '%s' — 건너뜀",
                    test_num, qnum, new_ans,
                )
                total_stats["skipped"] += 1

        # -- Category (from explanation) --
        expl_info = explanations.get(qnum, {})
        if expl_info.get("category"):
            new_cat = expl_info["category"]
            if q.get("category") != new_cat:
                old_cat = q.get("category")
                q["category"] = new_cat
                total_stats["updated_category"] += 1
                if old_cat:
                    log.debug(
                        "  TEST%d Q%d: 카테고리 변경 '%s' → '%s'",
                        test_num, qnum, old_cat, new_cat,
                    )

        # -- Explanation (with translation appended) --
        if expl_info.get("explanation"):
            expl_text = expl_info["explanation"]
            if expl_info.get("translation"):
                expl_text += "\n\n[번역] " + expl_info["translation"]
            if q.get("explanation") != expl_text:
                q["explanation"] = expl_text
                total_stats["updated_explanation"] += 1

    if not dry_run:
        # Create backup before overwriting
        _backup_json(json_path)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(questions, f, ensure_ascii=False, indent=2)
        log.info("  저장 완료: %s", json_path)
    else:
        log.info("  [DRY RUN] 변경사항 미저장 (백업 생성 안 함)")

    return total_stats


# ---------------------------------------------------------------------------
# Main processing
# ---------------------------------------------------------------------------


def process_volume(volume: int, use_ocr: bool = False, dry_run: bool = False) -> None:
    """Extract answers from a volume's answer PDF and merge into question JSON."""
    log.info("=" * 60)
    log.info("Vol%d 처리 시작 (ocr=%s, dry_run=%s)", volume, use_ocr, dry_run)
    log.info("=" * 60)

    # Get text — handle missing PDF gracefully
    try:
        text = get_text_for_volume(volume, use_ocr)
    except FileNotFoundError as e:
        log.error("파일 없음: %s", e)
        return

    # Parse global answer grid across entire text
    global_grid = parse_answer_grid(text)
    log.info("전역 답안 그리드: %d개 항목", len(global_grid))

    # Split text into per-test chunks
    test_chunks = split_by_test(text)
    if not test_chunks:
        log.error("Vol%d: 텍스트에서 테스트 경계를 찾을 수 없음", volume)
        return

    # Collect per-test answers and explanations, then merge once
    answers_by_test: dict[int, dict[int, str]] = {}
    explanations_by_test: dict[int, dict[int, dict]] = {}

    for test_num in sorted(test_chunks.keys()):
        if test_num < 1 or test_num > 10:
            log.debug("테스트 번호 범위 초과, 건너뜀: %d", test_num)
            continue

        chunk = test_chunks[test_num]
        log.info("-" * 40)
        log.info("TEST %d 처리 중", test_num)

        # Answer grid from this test's chunk
        test_grid = parse_answer_grid(chunk)

        # Supplement from global grid for Part 5 questions not found in chunk
        for qnum in range(FULL_Q_START, FULL_Q_END + 1):
            if qnum not in test_grid and qnum in global_grid:
                test_grid[qnum] = global_grid[qnum]

        # Explanation blocks
        test_expl = parse_explanations(chunk)

        # Resolve final answers (grid takes priority)
        final_answers = resolve_answers(test_grid, test_expl)

        # Per-test stats
        grid_count = sum(1 for q in range(Q_START, Q_END + 1) if q in test_grid)
        expl_count = sum(1 for q in range(Q_START, Q_END + 1) if q in test_expl)
        answer_count = sum(1 for q in range(Q_START, Q_END + 1) if q in final_answers)
        cat_count = sum(
            1 for q in range(Q_START, Q_END + 1)
            if test_expl.get(q, {}).get("category")
        )

        log.info(
            "  그리드 정답(Part5): %d/30, 해설 블록: %d/30, "
            "최종 정답: %d/30, 카테고리: %d/30",
            grid_count, expl_count, answer_count, cat_count,
        )

        if log.isEnabledFor(logging.DEBUG):
            for qnum in sorted(final_answers.keys()):
                if Q_START <= qnum <= Q_END:
                    ans = final_answers[qnum]
                    cat = test_expl.get(qnum, {}).get("category", "-")
                    log.debug("    Q%d: %s [%s]", qnum, ans, cat)

        answers_by_test[test_num] = final_answers
        explanations_by_test[test_num] = test_expl

    # Single load-update-save cycle for the entire volume
    total_stats = merge_into_volume(
        volume, answers_by_test, explanations_by_test, dry_run=dry_run
    )

    # Summary
    log.info("=" * 60)
    log.info("Vol%d 처리 완료:", volume)
    log.info(
        "  정답 업데이트: %d | 카테고리 업데이트: %d | 해설 업데이트: %d | 건너뜀: %d",
        total_stats.get("updated_answer", 0),
        total_stats.get("updated_category", 0),
        total_stats.get("updated_explanation", 0),
        total_stats.get("skipped", 0),
    )
    log.info("=" * 60)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="ETS 정답/해설 PDF에서 정답 추출 및 기존 문제 JSON에 병합"
    )
    parser.add_argument("--volume", type=int, choices=range(1, 6), metavar="N",
                        help="처리할 볼륨 번호 (1–5)")
    parser.add_argument("--all", action="store_true",
                        help="모든 볼륨 처리 (1–5)")
    parser.add_argument(
        "--ocr", action="store_true",
        help="원본 이미지 PDF에서 직접 Tesseract OCR 수행 (Acrobat OCR PDF 무시)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="추출 결과만 표시, JSON 파일 및 백업 수정 없음",
    )
    parser.add_argument("--debug", action="store_true", help="디버그 로그 출력")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.volume:
        process_volume(args.volume, use_ocr=args.ocr, dry_run=args.dry_run)
    elif args.all:
        for v in range(1, 6):
            process_volume(v, use_ocr=args.ocr, dry_run=args.dry_run)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
