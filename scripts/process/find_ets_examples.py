"""
ETS 기출문제 5권에서 단어별 예문을 전수 검색한다.

Input:
  data/processed/vocab/chapter_map.json     — 챕터별 단어 목록 (Phase 1 산출물)
  data/processed/questions/vol*_part5.json  — Part 5 구조화된 문제
  data/processed/questions/vol*_part6.json  — Part 6 원문 (raw_text)
  data/processed/questions/vol*_part7.json  — Part 7 원문 (raw_text)

Output:
  data/mapped/word_ets_examples.json        — 단어별 ETS 예문 매핑

Usage:
  python find_ets_examples.py                           # Default paths
  python find_ets_examples.py --chapter-map path.json   # Custom chapter map
  python find_ets_examples.py --questions-dir path/     # Custom questions dir
  python find_ets_examples.py --output path.json        # Custom output
  python find_ets_examples.py --no-spacy                # Disable spaCy
  python find_ets_examples.py --verbose                 # Debug logging
"""

import sys
import re
import json
import argparse
import logging
from pathlib import Path
from collections import defaultdict
from typing import Optional

# Windows UTF-8
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

# ── Project paths ────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_CHAPTER_MAP = PROJECT_ROOT / "data" / "processed" / "vocab" / "chapter_map.json"
DEFAULT_QUESTIONS_DIR = PROJECT_ROOT / "data" / "processed" / "questions"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "mapped" / "word_ets_examples.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── ANSI colours ─────────────────────────────────────────────────────────────

GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RED    = "\033[91m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def green(s: str)  -> str: return f"{GREEN}{s}{RESET}"
def yellow(s: str) -> str: return f"{YELLOW}{s}{RESET}"
def cyan(s: str)   -> str: return f"{CYAN}{s}{RESET}"
def red(s: str)    -> str: return f"{RED}{s}{RESET}"
def bold(s: str)   -> str: return f"{BOLD}{s}{RESET}"


# ── Import word-family utilities from shared NLP module ──────────────────────

from scripts.utils.nlp import (
    _build_word_family,
    get_lemma,
    _fallback_lemma,
    _load_spacy,
)


# ── Loading functions ────────────────────────────────────────────────────────


def load_chapter_map(path: Path) -> list[dict]:
    """Load chapter_map.json and return list of chapter dicts."""
    if not path.exists():
        logger.warning("Chapter map not found: %s", path)
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Could not read chapter map: %s", exc)
        return []
    if not isinstance(data, list):
        logger.warning("Unexpected chapter_map format (expected list)")
        return []
    total_words = sum(len(ch.get("words", [])) for ch in data)
    print(f"  Loaded {len(data)} chapters, {total_words:,} words from {path.name}")
    return data


def load_part5_questions(questions_dir: Path) -> list[dict]:
    """Load all vol*_part5.json files (structured questions)."""
    files = sorted(questions_dir.glob("vol*_part5.json"))
    if not files:
        logger.warning("No Part 5 files found in %s", questions_dir)
        return []
    questions: list[dict] = []
    for fp in files:
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            if isinstance(data, list):
                questions.extend(data)
            else:
                logger.warning("Unexpected format in %s — skipping", fp.name)
        except Exception as exc:
            logger.warning("Could not read %s: %s", fp.name, exc)
    print(f"  Loaded {len(questions):,} Part 5 questions from {len(files)} file(s)")
    return questions


def load_part67_data(questions_dir: Path, part: int) -> list[dict]:
    """Load all vol*_part{6,7}.json files (raw_text entries)."""
    files = sorted(questions_dir.glob(f"vol*_part{part}.json"))
    if not files:
        logger.warning("No Part %d files found in %s", part, questions_dir)
        return []
    entries: list[dict] = []
    for fp in files:
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            if isinstance(data, list):
                entries.extend(data)
            else:
                logger.warning("Unexpected format in %s — skipping", fp.name)
        except Exception as exc:
            logger.warning("Could not read %s: %s", fp.name, exc)
    print(f"  Loaded {len(entries):,} Part {part} entries from {len(files)} file(s)")
    return entries


# ── Part 6/7 passage extraction ──────────────────────────────────────────────

# Pattern to match "Questions NNN-NNN refer to the following ..."
_QUESTIONS_HEADER_RE = re.compile(
    r"Questions\s+(\d{2,3})\s*[-–—]\s*(\d{2,3})\s+refer\s+to\s+the\s+following\s+([^.\n]+)[.\n]",
    re.IGNORECASE,
)

# OCR noise characters
_OCR_NOISE_RE = re.compile(r"[■•▪▶►◄◆◇○●離什교丁니뇨쁘尺亍\u25A0\u25CF\u2022]")


def extract_passages(
    raw_text: str, volume: int, test: int, part: int,
) -> list[dict]:
    """
    Extract clean passage text from Part 6/7 raw_text.

    The raw_text contains:
    - "PART 6/7\\nDirections: ..." header (strip this)
    - "Questions NNN-NNN refer to the following ..." headers (passage boundaries)
    - Passage text (KEEP)
    - Question numbers + choice blocks like "131. (A) ...\\n(B) ...\\n(C) ...\\n(D) ..." (strip)
    - OCR noise characters (strip)

    Returns list of dicts:
    [{"text": "clean passage text...", "volume": 1, "test": 1, "part": 6,
      "questions_range": "131-134"}]
    """
    if not raw_text:
        return []

    # Strip directions header (up to "answer sheet.")
    directions_end = raw_text.find("answer sheet.")
    if directions_end != -1:
        raw_text = raw_text[directions_end + len("answer sheet."):]

    # Find all passage boundaries
    splits = list(_QUESTIONS_HEADER_RE.finditer(raw_text))
    if not splits:
        # No headers found — treat entire text as one passage
        cleaned = _clean_passage_block(raw_text)
        if len(cleaned.strip()) > 20:
            return [{
                "text": cleaned.strip(),
                "volume": volume,
                "test": test,
                "part": part,
                "questions_range": None,
            }]
        return []

    passages: list[dict] = []
    for i, match in enumerate(splits):
        q_start = match.group(1)
        q_end = match.group(2)
        questions_range = f"{q_start}-{q_end}"

        # Extract block from after this header to next header (or end)
        block_start = match.end()
        block_end = splits[i + 1].start() if i + 1 < len(splits) else len(raw_text)
        block = raw_text[block_start:block_end]

        cleaned = _clean_passage_block(block)

        if cleaned and len(cleaned.strip()) > 20:
            passages.append({
                "text": cleaned.strip(),
                "volume": volume,
                "test": test,
                "part": part,
                "questions_range": questions_range,
            })

    return passages


def _clean_passage_block(block: str) -> str:
    """Remove choice blocks, OCR noise, and excess whitespace from a passage block."""
    lines = block.split("\n")
    clean_lines: list[str] = []
    skip_choices = False

    for line in lines:
        stripped = line.strip()

        # Skip empty lines
        if not stripped:
            skip_choices = False
            continue

        # Detect start of a choice block: "131. (A) ..." or "NNN. (A) ..."
        if re.match(r"^\d{2,3}\.\s*\([A-D]\)", stripped):
            skip_choices = True
            continue

        # Standalone choice continuation: "(A) ...", "(B) ...", "(C) ...", "(D) ..."
        if re.match(r"^\([A-D]\)\s", stripped):
            skip_choices = True
            continue

        # Continuation of choice block (short lines after choice start)
        if skip_choices:
            if re.match(r"^\([A-D]\)", stripped):
                continue
            # End of choice block — resume normal processing
            skip_choices = False

        # Skip lines that are just question numbers (e.g., "131." or "132.")
        if re.match(r"^\d{2,3}\.\s*$", stripped):
            continue

        # Remove OCR noise characters
        cleaned = _OCR_NOISE_RE.sub("", stripped)

        # Remove inline question number markers: "131." at start/end of line
        cleaned = re.sub(r"\b\d{3}\.\s*$", "", cleaned)
        cleaned = re.sub(r"^\s*\d{3}\.\s*", "", cleaned)

        # Remove stray OCR artefacts: isolated I/O patterns
        cleaned = re.sub(r"\bI\s+O\s*[0-9a-zA-Z]*\s*", "", cleaned)

        # Remove stray single CJK characters (isolated, surrounded by spaces/boundaries)
        cleaned = re.sub(r"(?<!\S)[\u2E80-\u9FFF\uF900-\uFAFF](?!\S)", "", cleaned)

        # Keep blanks as ------- (normalize varying dash lengths)
        cleaned = re.sub(r"-{3,}", "-------", cleaned)

        if cleaned.strip():
            clean_lines.append(cleaned.strip())

    return " ".join(clean_lines)


def split_into_sentences(text: str) -> list[str]:
    """Split passage text into individual sentences.

    Uses regex: split on sentence-ending punctuation followed by space + capital letter.
    Also handles quotes and parentheses.
    """
    if not text:
        return []

    # Normalize line breaks to spaces
    text = re.sub(r"\n+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    # Split on sentence-ending punctuation followed by space and uppercase or quote
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z"(])', text)

    # Filter out very short fragments (< 10 chars)
    return [s.strip() for s in sentences if s.strip() and len(s.strip()) >= 10]


# ── Word family index ────────────────────────────────────────────────────────


def build_word_families(
    chapter_map: list[dict],
) -> tuple[dict[str, set[str]], dict[str, dict]]:
    """
    For each word in chapter_map, build the word family using _build_word_family().

    Returns:
        form_to_words: {word_form_lowercase: set of original_word_keys it belongs to}
        word_info: {original_word_lower: {"vocab_id": ..., "chapter": ..., "word": ...}}
    """
    form_to_words: dict[str, set[str]] = defaultdict(set)
    word_info: dict[str, dict] = {}

    for chapter in chapter_map:
        chapter_num = chapter.get("chapter", 0)
        for entry in chapter.get("words", []):
            word = entry.get("word", "").strip()
            if not word:
                continue

            word_key = word.lower()
            vocab_id = entry.get("id", "")
            related = entry.get("related_words") or []
            synonyms = entry.get("synonyms") or []

            # First occurrence wins if duplicate word across chapters
            if word_key not in word_info:
                word_info[word_key] = {
                    "vocab_id": vocab_id,
                    "chapter": chapter_num,
                    "word": word,
                }

            # Build word family: includes morphological variants
            lemma = get_lemma(word)
            family = _build_word_family(word, lemma, related + synonyms)

            # Map each form back to the original word
            for form in family:
                form_to_words[form].add(word_key)

    print(f"  Built index: {len(word_info):,} words, {len(form_to_words):,} distinct forms")
    return dict(form_to_words), word_info


# ── Searching ────────────────────────────────────────────────────────────────

# Minimum token length to avoid matching stopwords like "a", "an", "to"
_MIN_MATCH_LEN = 3


def search_sentence(
    sentence: str,
    form_to_words: dict[str, set[str]],
) -> list[tuple[str, str]]:
    """
    Check one sentence for word family matches.

    Tokenize with re.findall(r'[a-zA-Z]+', sentence).
    Returns list of (original_word_key, matched_form) tuples.
    Use word boundary matching: only match complete tokens.
    """
    if not sentence:
        return []

    tokens = re.findall(r"[a-zA-Z]+", sentence)
    matches: list[tuple[str, str]] = []
    seen_keys: set[str] = set()  # one match per original word per sentence

    for token in tokens:
        if len(token) < _MIN_MATCH_LEN:
            continue
        token_lc = token.lower()
        if token_lc not in form_to_words:
            continue
        for word_key in form_to_words[token_lc]:
            if word_key not in seen_keys:
                seen_keys.add(word_key)
                matches.append((word_key, token))  # preserve original case

    return matches


def search_part5(
    questions: list[dict],
    form_to_words: dict[str, set[str]],
) -> dict[str, list[dict]]:
    """
    Search Part 5 structured questions.

    For each question, tokenize sentence + choices, check against form_to_words.
    Record: sentence (with blank filled if answer known), source, matched_form.
    """
    matches: dict[str, list[dict]] = defaultdict(list)
    total = 0

    for q in questions:
        volume = q.get("volume", 0)
        test = q.get("test", 0)
        qnum = q.get("question_number", 0)
        sentence = q.get("sentence", "") or ""
        choices: dict[str, str] = q.get("choices") or {}
        answer = q.get("answer")

        # Combine sentence + all choice texts for searching
        full_text = sentence + " " + " ".join(str(v) for v in choices.values())

        # If answer is known, build a filled sentence for display
        display_sentence = sentence
        if answer and answer in choices and "-------" in sentence:
            display_sentence = sentence.replace("-------", choices[answer], 1)

        source = f"Vol {volume}, TEST {test:02d}, Q.{qnum}"

        found = search_sentence(full_text, form_to_words)
        for word_key, matched_form in found:
            matches[word_key].append({
                "sentence": display_sentence,
                "source": source,
                "volume": volume,
                "test": test,
                "question_number": qnum,
                "part": 5,
                "matched_form": matched_form,
            })
            total += 1

    logger.info("Part 5: %d matches across %d questions", total, len(questions))
    return dict(matches)


def search_part67(
    entries: list[dict],
    form_to_words: dict[str, set[str]],
    part: int,
) -> dict[str, list[dict]]:
    """
    Search Part 6/7 raw_text data.

    1. Extract passages from raw_text
    2. Split into sentences
    3. For each sentence, tokenize and check against form_to_words
    4. Record: sentence, source (Vol/Test/Part), matched_form
    """
    matches: dict[str, list[dict]] = defaultdict(list)
    total = 0
    passage_count = 0
    sentence_count = 0

    for entry in entries:
        raw_text = entry.get("raw_text", "") or ""
        volume = entry.get("volume", 0)
        test = entry.get("test", 0)

        if not raw_text:
            continue

        passages = extract_passages(raw_text, volume, test, part)
        passage_count += len(passages)

        for passage in passages:
            text = passage["text"]
            sentences = split_into_sentences(text)
            sentence_count += len(sentences)

            source = f"Vol {volume}, TEST {test:02d}, Part {part}"

            for sent in sentences:
                found = search_sentence(sent, form_to_words)
                for word_key, matched_form in found:
                    matches[word_key].append({
                        "sentence": sent,
                        "source": source,
                        "volume": volume,
                        "test": test,
                        "question_number": None,
                        "part": part,
                        "matched_form": matched_form,
                    })
                    total += 1

    logger.info(
        "Part %d: %d entries -> %d passages -> %d sentences -> %d matches",
        part, len(entries), passage_count, sentence_count, total,
    )
    print(f"    {passage_count} passages, {sentence_count:,} sentences")
    return dict(matches)


# ── Output assembly ──────────────────────────────────────────────────────────


def bold_matched_form(sentence: str, form: str) -> str:
    """Replace matched word form with **bold** in sentence. Case-insensitive."""
    return re.sub(
        r"\b(" + re.escape(form) + r")\b",
        r"**\1**",
        sentence,
        flags=re.IGNORECASE,
    )


def deduplicate_examples(examples: list[dict]) -> list[dict]:
    """Remove duplicate sentences (same sentence text, keep first occurrence)."""
    seen: set[str] = set()
    result: list[dict] = []
    for ex in examples:
        key = re.sub(r"\s+", " ", ex.get("sentence", "")).strip().lower()
        if key not in seen:
            seen.add(key)
            result.append(ex)
    return result


def assemble_output(
    word_info: dict[str, dict],
    all_matches: dict[str, list[dict]],
) -> dict[str, dict]:
    """Build the final output dict keyed by word.

    Merges Part 5/6/7 matches, deduplicates, applies bold formatting,
    computes summary statistics.
    """
    output: dict[str, dict] = {}

    for word_key, info in word_info.items():
        examples = all_matches.get(word_key, [])

        # Deduplicate by sentence text
        examples = deduplicate_examples(examples)

        # Sort by volume, test, part, question_number
        examples.sort(key=lambda e: (
            e.get("volume", 0),
            e.get("test", 0),
            e.get("part", 0),
            e.get("question_number") or 0,
        ))

        # Apply **bold** to matched forms in sentences
        for ex in examples:
            ex["sentence"] = bold_matched_form(ex["sentence"], ex["matched_form"])

        # Compute parts_appeared
        parts_appeared = sorted(set(ex["part"] for ex in examples))

        canonical_word = info["word"]  # original casing from chapter_map
        output[canonical_word] = {
            "vocab_id": info["vocab_id"],
            "chapter": info["chapter"],
            "total_count": len(examples),
            "examples": examples,
            "parts_appeared": parts_appeared,
        }

    return output


# ── Output writing ───────────────────────────────────────────────────────────


def _write_output(data: dict, output_path: Path) -> None:
    """Ensure parent directory exists and write JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    entry_count = len(data) if isinstance(data, dict) else 0
    print(f"  Written -> {output_path}  ({entry_count:,} entries)")


# ── CLI & main ───────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ETS 기출문제 5권에서 단어별 예문을 전수 검색한다.",
    )
    parser.add_argument(
        "--chapter-map",
        type=Path,
        default=DEFAULT_CHAPTER_MAP,
        metavar="PATH",
        help="Path to chapter_map.json (default: %(default)s)",
    )
    parser.add_argument(
        "--questions-dir",
        type=Path,
        default=DEFAULT_QUESTIONS_DIR,
        metavar="DIR",
        help="Directory containing vol*_part{5,6,7}.json files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        metavar="PATH",
        help="Output JSON path (default: %(default)s)",
    )
    parser.add_argument(
        "--no-spacy",
        action="store_true",
        help="Disable spaCy; use fallback suffix-stripping lemmatiser",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    print()
    print(bold("=== ETS 기출 예문 검색 (find_ets_examples) ==="))
    print()

    # ── spaCy setup ──────────────────────────────────────────────────────────
    use_spacy = not args.no_spacy
    if use_spacy:
        print("  Loading spaCy model ... ", end="", flush=True)
        if _load_spacy():
            print(green("ok"))
        else:
            use_spacy = False
            print(yellow("not available — using fallback lemmatiser"))
    else:
        print(yellow("  spaCy disabled — using fallback lemmatiser"))

    # ── Load chapter map ─────────────────────────────────────────────────────
    chapter_map = load_chapter_map(args.chapter_map)
    if not chapter_map:
        print(yellow("[WARN] No chapter data found. Writing empty output."))
        _write_output({}, args.output)
        return

    # ── Build word family index ──────────────────────────────────────────────
    print("  Building word-family index ... ", end="", flush=True)
    form_to_words, word_info = build_word_families(chapter_map)
    print(green("done"))

    # ── Load ETS question data ───────────────────────────────────────────────
    print()
    print(bold("  Loading ETS data..."))
    part5_questions = load_part5_questions(args.questions_dir)
    part6_data = load_part67_data(args.questions_dir, part=6)
    part7_data = load_part67_data(args.questions_dir, part=7)

    if not part5_questions and not part6_data and not part7_data:
        print(yellow("[WARN] No ETS data found. Writing output with zero examples."))
        output = assemble_output(word_info, {})
        _write_output(output, args.output)
        return

    # ── Search all parts ─────────────────────────────────────────────────────
    print()
    print(bold("  Searching ETS questions..."))

    all_matches: dict[str, list[dict]] = defaultdict(list)

    # Part 5
    if part5_questions:
        print(f"  Part 5: searching {len(part5_questions):,} questions ... ", end="", flush=True)
        p5_matches = search_part5(part5_questions, form_to_words)
        p5_total = sum(len(v) for v in p5_matches.values())
        for word_key, examples in p5_matches.items():
            all_matches[word_key].extend(examples)
        print(f"{green(f'{p5_total:,}')} matches across {len(p5_matches):,} words")

    # Part 6
    if part6_data:
        print(f"  Part 6: searching {len(part6_data):,} entries ... ", flush=True)
        p6_matches = search_part67(part6_data, form_to_words, part=6)
        p6_total = sum(len(v) for v in p6_matches.values())
        for word_key, examples in p6_matches.items():
            all_matches[word_key].extend(examples)
        print(f"    -> {green(f'{p6_total:,}')} matches across {len(p6_matches):,} words")

    # Part 7
    if part7_data:
        print(f"  Part 7: searching {len(part7_data):,} entries ... ", flush=True)
        p7_matches = search_part67(part7_data, form_to_words, part=7)
        p7_total = sum(len(v) for v in p7_matches.values())
        for word_key, examples in p7_matches.items():
            all_matches[word_key].extend(examples)
        print(f"    -> {green(f'{p7_total:,}')} matches across {len(p7_matches):,} words")

    # ── Assemble output ──────────────────────────────────────────────────────
    print()
    print("  Merging and deduplicating ... ", end="", flush=True)
    words_matched = len([k for k in all_matches if all_matches[k]])
    print(f"{words_matched:,} words with at least one match")

    output = assemble_output(word_info, dict(all_matches))

    # ── Write output ─────────────────────────────────────────────────────────
    print()
    _write_output(output, args.output)

    # ── Summary stats ────────────────────────────────────────────────────────
    total_words = len(word_info)
    words_with_examples = sum(1 for v in output.values() if v["total_count"] > 0)
    total_examples = sum(v["total_count"] for v in output.values())
    coverage = (words_with_examples / total_words * 100) if total_words else 0.0

    # Per-part breakdown
    part_counts: dict[int, int] = defaultdict(int)
    part_word_counts: dict[int, set[str]] = defaultdict(set)
    for word, v in output.items():
        for ex in v["examples"]:
            p = ex.get("part", 0)
            part_counts[p] += 1
            part_word_counts[p].add(word)

    print()
    print(bold("── Summary ──────────────────────────────────────"))
    print(f"  Total vocab words      : {cyan(f'{total_words:,}')}")
    print(f"  Words with examples    : {green(f'{words_with_examples:,}')}")
    print(f"  Total examples found   : {cyan(f'{total_examples:,}')}")
    print(f"  Coverage               : {green(f'{coverage:.1f}%')}")
    print()
    print(f"  Part 5 matches         : {part_counts.get(5, 0):,} examples ({len(part_word_counts.get(5, set())):,} words)")
    print(f"  Part 6 matches         : {part_counts.get(6, 0):,} examples ({len(part_word_counts.get(6, set())):,} words)")
    print(f"  Part 7 matches         : {part_counts.get(7, 0):,} examples ({len(part_word_counts.get(7, set())):,} words)")
    print(f"  Output                 : {args.output}")
    print(bold("─────────────────────────────────────────────────"))
    print()


if __name__ == "__main__":
    main()
