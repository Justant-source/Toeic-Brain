"""
ETS 기출문제 5권에서 단어별 예문을 전수 검색한다.

Input:
  data/json/hackers_vocab.json             — 단어 목록 (chapter_map을 인메모리 생성)
  data/json/questions/vol*_part5.json      — Part 5 구조화된 문제
  data/json/questions/vol*_part6.json      — Part 6 원문 (raw_text)
  data/json/questions/vol*_part7.json      — Part 7 원문 (raw_text)

Output:
  data/json/word_ets_examples.json         — 단어별 ETS 예문 매핑

Usage:
  python find_ets_examples.py                           # Default paths
  python find_ets_examples.py --vocab path.json         # Custom vocab file
  python find_ets_examples.py --questions-dir path/     # Custom questions dir
  python find_ets_examples.py --output path.json        # Custom output
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

DEFAULT_VOCAB_PATH = PROJECT_ROOT / "data" / "json" / "hackers_vocab.json"
DEFAULT_QUESTIONS_DIR = PROJECT_ROOT / "data" / "json" / "questions"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "json" / "word_ets_examples.json"

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
    get_sentence_lemmas,
    build_chapter_map_from_vocab,
    GRAMMAR_PLACEHOLDERS,
    PATTERN_MARKERS,
)


class MatchScore:
    """매칭 스코어 상수"""
    EXACT_MATCH = 1.0
    LEMMA_MATCH = 0.95
    WORD_FAMILY_MATCH = 0.85
    ALL_CONTENT_WORDS = 1.0
    ADJACENCY_BONUS = 0.05
    ORDER_BONUS = 0.03
    PLACEHOLDER_MATCH = 0.90
    SINGLE_WORD_THRESHOLD = 0.85
    PHRASE_THRESHOLD = 0.90


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


_STOP_WORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall",
    "should", "may", "might", "can", "could", "must",
    "in", "on", "at", "to", "for", "of", "with", "by", "from", "up",
    "about", "into", "through", "during", "before", "after", "above",
    "below", "between", "out", "off", "over", "under", "again",
    "and", "but", "or", "nor", "not", "so", "yet", "both", "either",
    "neither", "each", "every", "all", "any", "few", "more", "most",
    "other", "some", "such", "no", "only", "own", "same", "than",
    "too", "very", "just", "because", "as", "until", "while",
    "it", "its", "he", "she", "they", "them", "their", "his", "her",
    "we", "us", "our", "you", "your", "my", "me", "one", "ones",
    "this", "that", "these", "those", "what", "which", "who", "whom",
    "how", "when", "where", "why",
})


def _extract_content_words(phrase: str) -> list[str]:
    """Extract content words from a multi-word phrase for matching.

    For phrases like "achieve one's goal", returns ["achieve", "goal"].
    Strips stop words, possessives, and short tokens.
    """
    import re as _re
    tokens = _re.findall(r"[a-zA-Z]+", phrase.lower())
    return [t for t in tokens if len(t) >= 3 and t not in _STOP_WORDS]


def classify_phrase(word: str) -> str:
    """다중 단어 구의 유형을 분류한다."""
    w = word.lower()
    if w.startswith("be "):
        return "TYPE_A_BE"
    if "oneself" in w:
        return "TYPE_B_ONESELF"
    if "one's" in w:
        return "TYPE_C_ONES"
    if " to do" in w or w.endswith(" to do"):
        return "TYPE_D_TODO"
    tokens = w.split()
    if len(tokens) <= 3 and all(t not in _STOP_WORDS for t in tokens):
        return "TYPE_E_NOUN_PHRASE"
    return "TYPE_F_GENERAL"


_PHRASE_CONTENT_PREPOSITIONS = frozenset({
    "by", "in", "on", "at", "for", "of", "with", "from", "up",
    "out", "off", "over", "into", "through", "about", "against",
    "between", "under", "above", "below", "after", "before", "during",
})


def build_phrase_spec(word: str, phrase_type: str) -> dict:
    """다중 단어 구의 매칭 사양(spec)을 생성한다."""
    # "to do" 패턴 마커 제거 (문법 패턴 표기이므로 매칭 불필요)
    word_clean = re.sub(r"\bto\s+do\b", "", word.lower()).strip()
    tokens = re.findall(r"[a-zA-Z']+", word_clean)
    spec = {
        "phrase_type": phrase_type,
        "content_words": [],
        "content_word_families": [],
        "required_all": True,
        "placeholder_families": [],
        "require_placeholders": phrase_type in ("TYPE_A_BE", "TYPE_B_ONESELF"),
        "check_adjacency": False,
    }

    for token in tokens:
        if token in GRAMMAR_PLACEHOLDERS:
            spec["placeholder_families"].append(GRAMMAR_PLACEHOLDERS[token])
            continue
        if token in PATTERN_MARKERS:
            continue
        # Stop words 제외 — 단, 전치사는 구(phrase)에서 의미가 있으므로 유지
        if token in _STOP_WORDS and token not in _PHRASE_CONTENT_PREPOSITIONS:
            continue
        # 짧은 전치사(by, in, on 등)는 _build_word_family의 _MIN_STEM 필터에 걸리므로
        # exact match family로 직접 생성
        if len(token) < 3:
            family = {token}
        else:
            lemma = get_lemma(token)
            family = _build_word_family(token, lemma, [])
        spec["content_words"].append(token)
        spec["content_word_families"].append(family)

    # 명사구: 인접성 필수
    if phrase_type == "TYPE_E_NOUN_PHRASE":
        spec["check_adjacency"] = True
        spec["max_distance"] = len(spec["content_words"])
    # 짧은 전치사 포함 구: 근접성 확인 (false positive 방지)
    elif len(spec["content_words"]) <= 3 and any(
        w in _PHRASE_CONTENT_PREPOSITIONS and len(w) <= 3
        for w in spec["content_words"]
    ):
        spec["check_adjacency"] = True
        spec["max_distance"] = len(spec["content_words"]) + 1

    return spec


def verify_phrase_match(sentence: str, spec: dict) -> float:
    """다중 단어 구의 매칭을 정밀 검증한다. Returns 0.0 ~ 1.0 스코어."""
    tokens_lc = [t.lower() for t in re.findall(r"[a-zA-Z']+", sentence)]
    lemma_map = get_sentence_lemmas(sentence)
    token_lemmas = [lemma_map.get(t, t) for t in tokens_lc]

    content_total = len(spec["content_word_families"])
    if content_total == 0:
        return 0.0

    content_found = 0
    for family in spec["content_word_families"]:
        if any(t in family or l in family for t, l in zip(tokens_lc, token_lemmas)):
            content_found += 1

    if content_found < content_total:
        return 0.0

    score = MatchScore.ALL_CONTENT_WORDS

    # Placeholder families: required for TYPE_A_BE/TYPE_B_ONESELF, bonus for others
    for ph_family in spec["placeholder_families"]:
        ph_found = any(t in ph_family for t in tokens_lc)
        if spec.get("require_placeholders") and not ph_found:
            return 0.0  # 필수 placeholder 미발견 → 매칭 실패
        if ph_found:
            score += 0.02

    if spec["check_adjacency"]:
        positions = []
        for family in spec["content_word_families"]:
            for i, (t, l) in enumerate(zip(tokens_lc, token_lemmas)):
                if t in family or l in family:
                    positions.append(i)
                    break
        max_dist = spec.get("max_distance", len(spec["content_words"]))
        if not positions or len(positions) < content_total:
            return 0.0
        if max(positions) - min(positions) > max_dist:
            return 0.0  # content words가 너무 멀리 떨어져 있음
        if max(positions) - min(positions) <= len(positions):
            score += MatchScore.ADJACENCY_BONUS

    return min(score, 1.0)


def build_word_families(
    chapter_map: list[dict],
) -> tuple[dict[str, set[str]], dict[str, dict], dict[str, dict]]:
    """
    Build word family index. For multi-word phrases, also builds phrase_specs.

    Returns:
        form_to_words: {word_form_lowercase: set of original_word_keys}
        word_info: {original_word_lower: {"vocab_id": ..., "chapter": ..., "word": ...}}
        phrase_specs: {word_key: spec_dict} for multi-word phrases
    """
    form_to_words: dict[str, set[str]] = defaultdict(set)
    word_info: dict[str, dict] = {}
    phrase_specs: dict[str, dict] = {}

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

            if word_key not in word_info:
                word_info[word_key] = {
                    "vocab_id": vocab_id,
                    "chapter": chapter_num,
                    "word": word,
                }

            if " " not in word:
                # === 단일 단어: 기존 로직 유지 ===
                lemma = get_lemma(word)
                family = _build_word_family(word, lemma, related + synonyms)
                for form in family:
                    form_to_words[form].add(word_key)
            else:
                # === 다중 단어 구: 신규 로직 ===
                phrase_type = classify_phrase(word)
                spec = build_phrase_spec(word, phrase_type)
                phrase_specs[word_key] = spec

                for cw_family in spec["content_word_families"]:
                    for form in cw_family:
                        form_to_words[form].add(word_key)

                for ph_family in spec["placeholder_families"]:
                    for form in ph_family:
                        form_to_words[form].add(word_key)

    print(f"  Built index: {len(word_info):,} words, {len(form_to_words):,} distinct forms, {len(phrase_specs):,} phrase specs")
    return dict(form_to_words), word_info, phrase_specs


# ── Searching ────────────────────────────────────────────────────────────────

# Minimum token length to avoid matching stopwords like "a", "an", "to"
_MIN_MATCH_LEN = 3


def search_sentence(
    sentence: str,
    form_to_words: dict[str, set[str]],
    phrase_specs: dict[str, dict] | None = None,
) -> list[tuple[str, str]]:
    """
    Check one sentence for word family matches.
    For multi-word phrases, performs 2-stage verification.
    """
    if not sentence:
        return []

    tokens = re.findall(r"[a-zA-Z]+", sentence)
    lemma_map = get_sentence_lemmas(sentence)
    matches: list[tuple[str, str]] = []
    seen_keys: set[str] = set()

    for token in tokens:
        if len(token) < _MIN_MATCH_LEN:
            continue
        token_lc = token.lower()
        token_lemma = lemma_map.get(token_lc, token_lc)

        candidates: set[str] = set()
        if token_lc in form_to_words:
            candidates.update(form_to_words[token_lc])
        if token_lemma != token_lc and token_lemma in form_to_words:
            candidates.update(form_to_words[token_lemma])

        for word_key in candidates:
            if word_key in seen_keys:
                continue

            if phrase_specs and word_key in phrase_specs:
                score = verify_phrase_match(sentence, phrase_specs[word_key])
                if score < MatchScore.PHRASE_THRESHOLD:
                    continue

            seen_keys.add(word_key)
            matches.append((word_key, token))

    return matches


def search_part5(
    questions: list[dict],
    form_to_words: dict[str, set[str]],
    phrase_specs: dict[str, dict] | None = None,
) -> dict[str, list[dict]]:
    """Search Part 5 structured questions."""
    matches: dict[str, list[dict]] = defaultdict(list)
    total = 0

    for q in questions:
        volume = q.get("volume", 0)
        test = q.get("test", 0)
        qnum = q.get("question_number", 0)
        sentence = q.get("sentence", "") or ""
        choices: dict[str, str] = q.get("choices") or {}
        answer = q.get("answer")

        # Bug 1 fix: search display_sentence only (not full_text with all choices)
        display_sentence = sentence
        if answer and answer in choices and "-------" in sentence:
            display_sentence = sentence.replace("-------", choices[answer], 1)

        source = f"Vol {volume}, TEST {test:02d}, Q.{qnum}"

        found = search_sentence(display_sentence, form_to_words, phrase_specs)
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
    phrase_specs: dict[str, dict] | None = None,
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
                found = search_sentence(sent, form_to_words, phrase_specs)
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
        "--vocab",
        type=Path,
        default=DEFAULT_VOCAB_PATH,
        metavar="PATH",
        help="Path to hackers_vocab.json (default: %(default)s)",
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

    print("  spaCy lemmatiser: " + green("loaded"))

    # ── Load chapter map (built from vocab) ─────────────────────────────────
    chapter_map = build_chapter_map_from_vocab(args.vocab) if args.vocab.exists() else []
    if chapter_map:
        total_words = sum(len(ch.get("words", [])) for ch in chapter_map)
        print(f"  Loaded {len(chapter_map)} chapters, {total_words:,} words from {args.vocab.name}")
    if not chapter_map:
        print(yellow("[WARN] No chapter data found. Writing empty output."))
        _write_output({}, args.output)
        return

    # ── Build word family index ──────────────────────────────────────────────
    print("  Building word-family index ... ", end="", flush=True)
    form_to_words, word_info, phrase_specs = build_word_families(chapter_map)
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
        p5_matches = search_part5(part5_questions, form_to_words, phrase_specs)
        p5_total = sum(len(v) for v in p5_matches.values())
        for word_key, examples in p5_matches.items():
            all_matches[word_key].extend(examples)
        print(f"{green(f'{p5_total:,}')} matches across {len(p5_matches):,} words")

    # Part 6
    if part6_data:
        print(f"  Part 6: searching {len(part6_data):,} entries ... ", flush=True)
        p6_matches = search_part67(part6_data, form_to_words, part=6, phrase_specs=phrase_specs)
        p6_total = sum(len(v) for v in p6_matches.values())
        for word_key, examples in p6_matches.items():
            all_matches[word_key].extend(examples)
        print(f"    -> {green(f'{p6_total:,}')} matches across {len(p6_matches):,} words")

    # Part 7
    if part7_data:
        print(f"  Part 7: searching {len(part7_data):,} entries ... ", flush=True)
        p7_matches = search_part67(part7_data, form_to_words, part=7, phrase_specs=phrase_specs)
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
