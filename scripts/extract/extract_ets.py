"""
ETS 기출문제 1000제 PDF에서 Part별 문제를 추출하여 JSON으로 변환한다.
입력: 00. Reference/ets_vol{1-5}.pdf
출력: data/json/questions/vol{N}_part{5,6,7}.json
"""

import sys
sys.stdout.reconfigure(encoding="utf-8")

import argparse
import json
import logging
import re
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
import yaml

# ---------------------------------------------------------------------------
# Logging setup — force UTF-8 on Windows to avoid UnicodeEncodeError
# ---------------------------------------------------------------------------
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
)
logging.basicConfig(level=logging.INFO, handlers=[_handler])
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]  # C:\Data\Toeic Brain

# Blank markers found across all volumes:
#   Vol1-4: "-------" or "--------" (hyphens)
#   Vol5:   "//////" or "///////" (slashes)
#   Blank-line style: sentence split by an empty line (Vol1 pages)
BLANK_PATTERN = re.compile(r"[-]{3,}|[/]{3,}")
NORMALIZED_BLANK = "-------"

# Footer noise that appears at the bottom of pages
FOOTER_PATTERN = re.compile(
    r"(GO ON TO THE NEXT PAGE|STOP\. Do not go on|TEST\s+\d+\s+\d+|^\d{1,3}\s*$)",
    re.MULTILINE,
)

# OCR misread corrections: maps misread number string → correct number string
# Vol5 consistently misreads "121." as "343." (digit-level OCR confusion)
OCR_NUMBER_FIXES: dict[str, str] = {
    "343.": "121.",
}

# Question number at start: "101. " through "200. "
Q_NUMBER_RE = re.compile(r"(?<!\d)([1-2]\d{2})\.\s+")

# Choice line patterns
CHOICE_RE = re.compile(
    r"\(A\)\s*(.*?)\s*\(B\)\s*(.*?)\s*\(C\)\s*(.*?)\s*\(D\)\s*(.*?)$",
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_config() -> dict:
    config_path = PROJECT_ROOT / "config.yaml"
    with config_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# PDF structure detection
# ---------------------------------------------------------------------------

def find_section_pages(doc: fitz.Document) -> list[dict]:
    """
    Return a list of test-section dicts for every test in the PDF.

    Each dict has keys:
        test         int   1-based test index within the volume
        part5_start  int   page index where READING TEST / PART 5 begins
        part6_start  int   page index where PART 6 begins
        part7_start  int   page index where PART 7 begins  (or PART 9 for Vol5)
        part7_end    int   exclusive end page (next READING TEST or len(doc))

    Heuristic: a "real" PART 5 page contains both "READING TEST" and "PART 5".
    A "real" PART 6/7 page contains "Directions:" (skips pre-test analysis pages).
    Vol5 uses the heading "PART 8" for Part-6-equivalent and "PART 9" for Part-7-equivalent.
    """
    part5_pages: list[int] = []
    part6_pages: list[int] = []
    part7_pages: list[int] = []

    for i in range(len(doc)):
        text = doc[i].get_text()
        if "READING TEST" in text and "PART 5" in text:
            part5_pages.append(i)
        # PART 6 or PART 8 with actual test Directions
        if re.search(r"PART [68]\n", text) and "Directions:" in text:
            part6_pages.append(i)
        # PART 7 or PART 9 with actual test Directions
        if re.search(r"PART [79]\n", text) and "Directions:" in text:
            part7_pages.append(i)

    if not part5_pages:
        raise ValueError("No READING TEST pages found in PDF")

    n_tests = len(part5_pages)
    sections: list[dict] = []

    for idx in range(n_tests):
        p5_start = part5_pages[idx]
        # Find the matching PART 6 page: first p6 page that comes after p5_start
        p6_start = next((p for p in part6_pages if p > p5_start), None)
        # Find the matching PART 7 page: first p7 page after p6_start
        p7_start = next((p for p in part7_pages if p7_start_after(p, p6_start)), None)
        # End of this test: next READING TEST or EOF
        p7_end = part5_pages[idx + 1] if idx + 1 < n_tests else len(doc)

        if p6_start is None or p7_start is None:
            log.warning("Test %d: could not find PART 6 or PART 7 boundary", idx + 1)
            p6_start = p6_start or p7_end
            p7_start = p7_start or p7_end

        sections.append(
            {
                "test": idx + 1,
                "part5_start": p5_start,
                "part6_start": p6_start,
                "part7_start": p7_start,
                "part7_end": p7_end,
            }
        )

    return sections


def p7_start_after(page_idx: int, p6_start: Optional[int]) -> bool:
    """Helper: page_idx must be strictly after p6_start (or any positive page if None)."""
    if p6_start is None:
        return page_idx > 0
    return page_idx > p6_start


# ---------------------------------------------------------------------------
# Text cleaning helpers
# ---------------------------------------------------------------------------

def clean_text(raw: str) -> str:
    """Strip footers, normalize blank markers, and fix known OCR number errors."""
    text = FOOTER_PATTERN.sub("", raw)
    # Normalize blank markers to canonical form
    text = BLANK_PATTERN.sub(NORMALIZED_BLANK, text)
    # Fix known OCR misread question numbers (e.g. Vol5 "343." -> "121.")
    for wrong, right in OCR_NUMBER_FIXES.items():
        text = text.replace(wrong, right)
    return text


def collapse_whitespace(s: str) -> str:
    """Collapse runs of spaces/newlines into a single space and strip."""
    return re.sub(r"[ \t]*\n[ \t]*", " ", s).strip()
    # Note: keeps internal punctuation intact but flattens line breaks


def normalize_sentence(s: str) -> str:
    """
    Flatten multi-line question text.
    Handles the 'blank-line' style where the blank is represented by
    an empty line between two halves of the sentence (Vol1 style).
    """
    # Replace blank-line gaps (surrounding the blank) with the blank marker
    # Pattern: "text \n \n more text" → "text ------- more text"
    s = re.sub(r"([ \t]*\n){2,}", f" {NORMALIZED_BLANK} ", s)
    # Now collapse remaining single newlines
    s = re.sub(r"\s*\n\s*", " ", s)
    # Collapse multiple spaces
    s = re.sub(r" {2,}", " ", s)
    return s.strip()


# ---------------------------------------------------------------------------
# Part 5 parsing
# ---------------------------------------------------------------------------

def extract_part5_text(doc: fitz.Document, section: dict) -> str:
    """Concatenate raw text from all Part 5 pages for one test."""
    pages_text: list[str] = []
    for pg in range(section["part5_start"], section["part6_start"]):
        raw = doc[pg].get_text()
        pages_text.append(clean_text(raw))
    return "\n".join(pages_text)


def split_into_raw_questions(text: str) -> list[tuple[int, str]]:
    """
    Split the combined Part 5 text into (question_number, raw_block) tuples.
    Uses the 3-digit question number as the delimiter.
    Returns only questions in the 101-130 range.
    """
    # Find all positions of question numbers
    matches = list(Q_NUMBER_RE.finditer(text))
    blocks: list[tuple[int, str]] = []

    for i, match in enumerate(matches):
        q_num = int(match.group(1))
        if q_num < 101 or q_num > 200:
            continue
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end]
        blocks.append((q_num, block))

    return blocks


def parse_question_block(q_num: int, block: str) -> Optional[dict]:
    """
    Parse one raw question block into a structured dict.

    Block looks like:
        101. Ms. Durkin asked for volunteers to help

        with the employee fitness program.
        (A) she
        (B) her
        (C) hers
        (D) herself

    or inline blank:
        103. -------a year, Tarrin Industrial Supply audits
        the accounts of all of its factories.
        (A) Once
        ...
    """
    # Strip the leading "NNN. " prefix
    block = re.sub(r"^[1-2]\d{2}\.\s*", "", block.strip())

    # Find the position of "(A)" which marks the start of choices
    choice_start = block.find("(A)")
    if choice_start == -1:
        log.debug("Q%d: no choices found, skipping", q_num)
        return None

    sentence_raw = block[:choice_start]
    choices_raw = block[choice_start:]

    # --- Parse sentence ---
    sentence = normalize_sentence(sentence_raw)

    # Remove stray leading blank markers if sentence starts with one
    # (already normalized to "-------")
    sentence = re.sub(r"^-{7}\s*", f"{NORMALIZED_BLANK} ", sentence)

    # Clean up artifacts: superscript numbers that appear as OCR noise
    # e.g. "Electronics1 staff" → keep as-is (minor)
    sentence = re.sub(r"[ \t]{2,}", " ", sentence).strip()

    # --- Parse choices ---
    # Flatten the choices section to a single line for easier regex
    choices_flat = re.sub(r"\s*\n\s*", " ", choices_raw).strip()

    m = re.match(
        r"\(A\)\s*(.*?)\s*\(B\)\s*(.*?)\s*\(C\)\s*(.*?)\s*\(D\)\s*(.*?)$",
        choices_flat,
        re.DOTALL,
    )
    if not m:
        log.debug("Q%d: could not parse choices from: %r", q_num, choices_flat[:80])
        return None

    choices = {
        "A": m.group(1).strip(),
        "B": m.group(2).strip(),
        "C": m.group(3).strip(),
        "D": m.group(4).strip(),
    }

    # Sanity-check: each choice should be non-empty
    if any(not v for v in choices.values()):
        log.debug("Q%d: empty choice detected: %s", q_num, choices)

    return {"sentence": sentence, "choices": choices}


def parse_part5(
    doc: fitz.Document,
    section: dict,
    volume: int,
    answers: dict,
) -> list[dict]:
    """Extract and parse all Part 5 questions for one test section."""
    text = extract_part5_text(doc, section)
    raw_blocks = split_into_raw_questions(text)

    questions: list[dict] = []
    test_num = section["test"]

    for q_num, block in raw_blocks:
        parsed = parse_question_block(q_num, block)
        if parsed is None:
            log.warning("Vol%d Test%02d Q%d: parse failed", volume, test_num, q_num)
            continue

        q_id = f"vol{volume}_test{test_num:02d}_part5_{q_num}"
        answer_key = f"vol{volume}_test{test_num:02d}_{q_num}"

        question = {
            "id": q_id,
            "volume": volume,
            "test": test_num,
            "part": 5,
            "question_number": q_num,
            "sentence": parsed["sentence"],
            "choices": parsed["choices"],
            "answer": answers.get(answer_key),
            "category": None,
            "explanation": None,
        }
        questions.append(question)

    log.info(
        "  Vol%d Test%02d Part5: %d questions extracted",
        volume, test_num, len(questions),
    )
    return questions


# ---------------------------------------------------------------------------
# Part 6 / Part 7 — raw text extraction (complex structure, store as-is)
# ---------------------------------------------------------------------------

def extract_raw_blocks(
    doc: fitz.Document,
    start_page: int,
    end_page: int,
    volume: int,
    test_num: int,
    part: int,
) -> list[dict]:
    """
    Concatenate pages and store as a single raw text block per test.
    Part 6 and Part 7 passage structures are too varied for generic parsing;
    store raw text for downstream processing.
    """
    pages_text: list[str] = []
    for pg in range(start_page, end_page):
        raw = doc[pg].get_text()
        pages_text.append(clean_text(raw))

    combined = "\n".join(pages_text).strip()
    if not combined:
        return []

    q_id = f"vol{volume}_test{test_num:02d}_part{part}_raw"
    return [
        {
            "id": q_id,
            "volume": volume,
            "test": test_num,
            "part": part,
            "raw_text": combined,
        }
    ]


# ---------------------------------------------------------------------------
# Volume processing
# ---------------------------------------------------------------------------

def process_volume(
    volume: int,
    pdf_path: Path,
    out_dir: Path,
    answers: dict,
) -> None:
    log.info("Opening Vol%d: %s", volume, pdf_path)
    doc = fitz.open(str(pdf_path))
    log.info("  %d pages total", len(doc))

    sections = find_section_pages(doc)
    log.info("  %d tests found", len(sections))

    all_part5: list[dict] = []
    all_part6: list[dict] = []
    all_part7: list[dict] = []

    for section in sections:
        test_num = section["test"]
        log.info(
            "  Test %02d  P5:[%d,%d)  P6:[%d,%d)  P7:[%d,%d)",
            test_num,
            section["part5_start"], section["part6_start"],
            section["part6_start"], section["part7_start"],
            section["part7_start"], section["part7_end"],
        )

        # --- Part 5 ---
        all_part5.extend(parse_part5(doc, section, volume, answers))

        # --- Part 6 (raw) ---
        all_part6.extend(
            extract_raw_blocks(
                doc,
                section["part6_start"],
                section["part7_start"],
                volume,
                test_num,
                6,
            )
        )

        # --- Part 7 (raw) ---
        all_part7.extend(
            extract_raw_blocks(
                doc,
                section["part7_start"],
                section["part7_end"],
                volume,
                test_num,
                7,
            )
        )

    doc.close()

    # Save outputs
    out_dir.mkdir(parents=True, exist_ok=True)

    for part_label, data in [("part5", all_part5), ("part6", all_part6), ("part7", all_part7)]:
        out_path = out_dir / f"vol{volume}_{part_label}.json"
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        log.info("  Saved %d records → %s", len(data), out_path.relative_to(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Answer key loading
# ---------------------------------------------------------------------------

def load_answers(path: Optional[Path]) -> dict:
    """Load optional answer key JSON. Returns empty dict if not provided."""
    if path is None:
        return {}
    if not path.exists():
        log.warning("Answer key not found: %s", path)
        return {}
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    log.info("Loaded %d answers from %s", len(data), path)
    return data


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract ETS TOEIC questions from PDF volumes"
    )
    parser.add_argument(
        "--volume",
        type=int,
        metavar="N",
        help="Process only this volume (1-5). Default: all volumes.",
    )
    parser.add_argument(
        "--answers",
        type=Path,
        metavar="FILE",
        help='Path to answer key JSON {"vol1_test01_101": "B", ...}',
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    config = load_config()
    raw_dir = PROJECT_ROOT / "00. Reference"
    out_dir = PROJECT_ROOT / "data" / "json" / "questions"
    file_pattern: str = config["ets"]["file_pattern"]
    all_volumes: list[int] = config["ets"]["volumes"]

    answers = load_answers(args.answers)

    volumes = [args.volume] if args.volume else all_volumes

    for vol in volumes:
        pdf_path = raw_dir / file_pattern.format(volume=vol)
        if not pdf_path.exists():
            log.warning("PDF not found, skipping Vol%d: %s", vol, pdf_path)
            continue
        try:
            process_volume(vol, pdf_path, out_dir, answers)
        except Exception as exc:
            log.error("Vol%d failed: %s", vol, exc, exc_info=True)

    log.info("Done.")


if __name__ == "__main__":
    main()
