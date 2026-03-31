"""
00. Reference/ocr_cache/ 의 OCR 텍스트에서 단어별 예문을 검색한다.

find_ets_examples.py 와 달리, 구조화된 JSON 대신 OCR 원문을 직접 파싱하므로
JSON 추출 시 누락된 문장까지 포괄적으로 검색한다.

Input:
  00. Reference/ocr_cache/vol{N}/page_XXXX.txt
  data/json/hackers_vocab.json

Output:
  data/json/ocr_examples_vol{N}.json  — 볼륨별 중간 결과
  (merge_ocr_examples.py 가 최종 병합)

Usage:
  py -3 scripts/process/find_examples_from_ocr_cache.py --vol 1
  py -3 scripts/process/find_examples_from_ocr_cache.py --vol 1 2 3
  py -3 scripts/process/find_examples_from_ocr_cache.py --vol 1 2 3 4 5
"""

import re
import json
import sys
import argparse
import logging
from pathlib import Path
from collections import defaultdict

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

OCR_CACHE_DIR  = PROJECT_ROOT / "00. Reference" / "ocr_cache"
VOCAB_FILE     = PROJECT_ROOT / "data" / "json" / "hackers_vocab.json"
OUTPUT_DIR     = PROJECT_ROOT / "data" / "json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Noise patterns to remove / skip ─────────────────────────────────────────

# Answer choices: "(A) ..." lines
_CHOICE_RE    = re.compile(r"^\s*\([A-D]\)\s")
# Question stem: "NNN. ..." at start of line
_QSTEM_RE     = re.compile(r"^\s*\d{2,3}\.\s")
# Page header/footer: "TEST N  NNN" or "GO ON TO ..."
_HEADER_RE    = re.compile(r"^\s*(GO ON TO|STOP|TEST\s+\d|PART\s+[1-7]|Directions?:)", re.IGNORECASE)
# Standalone numbers / page numbers
_PAGENUM_RE   = re.compile(r"^\s*\d{1,3}\s*$")
# CJK noise characters
_CJK_RE       = re.compile(r"[\u2E80-\u9FFF\uF900-\uFAFF]")
# OCR artefacts: isolated non-alpha
_NOISE_RE     = re.compile(r"[■•▪▶►◄◆◇○●]")
# Blank placeholder
_BLANK_RE     = re.compile(r"-{3,}")

# Sentence splitter: split after . ! ? followed by space + capital
_SENT_SPLIT_RE = re.compile(r'(?<=[.!?])\s+(?=[A-Z"(])')

_MIN_SENT_LEN = 20   # chars
_MIN_TOKEN_LEN = 3   # skip tokens shorter than this


# ── Simple word-family builder (no spaCy required) ──────────────────────────

_IRREGULAR_PLURALS = {
    "woman": "women", "man": "men", "child": "children",
    "person": "people", "foot": "feet", "tooth": "teeth",
    "mouse": "mice", "goose": "geese", "ox": "oxen",
    "analysis": "analyses", "criterion": "criteria",
    "datum": "data", "phenomenon": "phenomena",
    "medium": "media", "index": "indices",
}

_IRREGULAR_VERBS = {
    "buy": ["bought"], "sell": ["sold"], "tell": ["told"],
    "find": ["found"], "make": ["made"], "take": ["took", "taken"],
    "give": ["gave", "given"], "come": ["came"], "go": ["went", "gone"],
    "know": ["knew", "known"], "think": ["thought"],
    "bring": ["brought"], "teach": ["taught"], "catch": ["caught"],
    "run": ["ran", "run"], "begin": ["began", "begun"],
    "write": ["wrote", "written"], "speak": ["spoke", "spoken"],
    "hold": ["held"], "build": ["built"], "send": ["sent"],
    "spend": ["spent"], "lend": ["lent"], "lead": ["led"],
    "meet": ["met"], "feel": ["felt"], "keep": ["kept"],
    "leave": ["left"], "lose": ["lost"], "pay": ["paid"],
    "say": ["said"], "hear": ["heard"], "read": ["read"],
    "win": ["won"], "sit": ["sat"], "stand": ["stood"],
    "understand": ["understood"], "withdraw": ["withdrew", "withdrawn"],
    "arise": ["arose", "arisen"], "drive": ["drove", "driven"],
    "prove": ["proved", "proven"], "rise": ["rose", "risen"],
    "choose": ["chose", "chosen"], "freeze": ["froze", "frozen"],
}


def _word_variants(word: str) -> set[str]:
    """Generate common morphological variants of an English word."""
    w = word.lower()
    forms: set[str] = {w}

    # Irregular plural
    if w in _IRREGULAR_PLURALS:
        forms.add(_IRREGULAR_PLURALS[w])

    # Irregular verb
    if w in _IRREGULAR_VERBS:
        forms.update(_IRREGULAR_VERBS[w])

    # Regular rules
    if w.endswith("y") and len(w) > 2 and w[-2] not in "aeiou":
        stem = w[:-1]
        forms.update({stem + "ies", stem + "ied", stem + "ier", stem + "iest"})
    if w.endswith("e") and len(w) > 2:
        stem = w[:-1]
        forms.update({stem + "ing", stem + "ed", stem + "er", stem + "est",
                      stem + "ion", stem + "ions"})
    if w.endswith(("ss", "sh", "ch", "x", "z")):
        forms.add(w + "es")
    if len(w) >= 3 and w[-1] not in "aeiouywh" and w[-2] in "aeiou" and w[-3] not in "aeiou":
        # CVC doubling: plan→planning
        forms.update({w + w[-1] + "ing", w + w[-1] + "ed", w + w[-1] + "er"})

    # Default suffixes
    forms.update({
        w + "s", w + "es", w + "ed", w + "ing",
        w + "er", w + "ers", w + "est",
        w + "ly", w + "ment", w + "ments",
        w + "tion", w + "tions", w + "ness",
        w + "al", w + "ive", w + "ity",
    })

    return forms


def build_word_index(vocab: list[dict]) -> tuple[dict[str, str], dict[str, str]]:
    """
    Returns:
        form_to_word: {lowercase_form: canonical_word_key (lowercase)}
        word_to_id:   {canonical_word_key (lowercase): vocab_id}
    """
    form_to_word: dict[str, str] = {}
    word_to_id: dict[str, str] = {}

    for entry in vocab:
        word = (entry.get("word") or "").strip()
        if not word:
            continue
        wk = word.lower()
        vid = entry.get("id") or wk
        if wk not in word_to_id:
            word_to_id[wk] = vid

        for form in _word_variants(word):
            if form not in form_to_word:
                form_to_word[form] = wk

    return form_to_word, word_to_id


# ── Text cleaning ────────────────────────────────────────────────────────────


def clean_line(line: str) -> str:
    line = _CJK_RE.sub("", line)
    line = _NOISE_RE.sub("", line)
    line = _BLANK_RE.sub("-------", line)
    return line.strip()


def should_skip_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if _CHOICE_RE.match(stripped):
        return True
    if _QSTEM_RE.match(stripped):
        return True
    if _HEADER_RE.match(stripped):
        return True
    if _PAGENUM_RE.match(stripped):
        return True
    if len(stripped) < 8:
        return True
    return False


def extract_sentences_from_text(text: str) -> list[str]:
    """Extract clean, sentence-like strings from raw OCR page text."""
    lines = text.split("\n")
    kept: list[str] = []
    for line in lines:
        if should_skip_line(line):
            continue
        cleaned = clean_line(line)
        if cleaned and len(cleaned) >= 8:
            kept.append(cleaned)

    # Join kept lines into a paragraph, then split into sentences
    paragraph = " ".join(kept)
    paragraph = re.sub(r"\s+", " ", paragraph).strip()

    sentences = _SENT_SPLIT_RE.split(paragraph)
    result: list[str] = []
    for s in sentences:
        s = s.strip()
        if len(s) >= _MIN_SENT_LEN and re.search(r"[a-zA-Z]{3}", s):
            result.append(s)
    return result


# ── Sentence search ──────────────────────────────────────────────────────────


def search_sentence(sentence: str, form_to_word: dict[str, str]) -> list[tuple[str, str]]:
    """Returns list of (word_key, matched_form) for vocab words found in sentence."""
    tokens = re.findall(r"[a-zA-Z]+", sentence)
    matches: list[tuple[str, str]] = []
    seen: set[str] = set()
    for token in tokens:
        if len(token) < _MIN_TOKEN_LEN:
            continue
        tl = token.lower()
        if tl in form_to_word:
            wk = form_to_word[tl]
            if wk not in seen:
                seen.add(wk)
                matches.append((wk, token))
    return matches


def bold_matched(sentence: str, form: str) -> str:
    return re.sub(
        r"\b(" + re.escape(form) + r")\b",
        r"**\1**",
        sentence,
        flags=re.IGNORECASE,
    )


# ── Per-volume processing ────────────────────────────────────────────────────


def process_volume(
    vol: int,
    form_to_word: dict[str, str],
    word_to_id: dict[str, str],
) -> dict[str, list[dict]]:
    """Process all OCR cache pages for one volume. Returns word_key → list of match dicts."""
    cache_dir = OCR_CACHE_DIR / f"vol{vol}"
    if not cache_dir.exists():
        logger.warning("Cache dir not found: %s", cache_dir)
        return {}

    page_files = sorted(cache_dir.glob("page_*.txt"))
    if not page_files:
        logger.warning("No page files in %s", cache_dir)
        return {}

    matches: dict[str, list[dict]] = defaultdict(list)
    total_sentences = 0
    total_matches = 0

    for page_file in page_files:
        page_num = int(page_file.stem.split("_")[1])
        try:
            text = page_file.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            logger.warning("Could not read %s: %s", page_file.name, exc)
            continue

        sentences = extract_sentences_from_text(text)
        total_sentences += len(sentences)

        for sent in sentences:
            found = search_sentence(sent, form_to_word)
            for word_key, matched_form in found:
                matches[word_key].append({
                    "sentence": bold_matched(sent, matched_form),
                    "source": f"Vol {vol}, p.{page_num}",
                    "volume": vol,
                    "page": page_num,
                    "part": None,
                    "question_number": None,
                    "matched_form": matched_form,
                })
                total_matches += 1

    logger.info(
        "Vol %d: %d pages → %d sentences → %d matches across %d words",
        vol, len(page_files), total_sentences, total_matches, len(matches),
    )
    return dict(matches)


# ── Deduplication ────────────────────────────────────────────────────────────


def deduplicate(examples: list[dict]) -> list[dict]:
    seen: set[str] = set()
    result: list[str] = []
    for ex in examples:
        key = re.sub(r"\s+", " ", ex.get("sentence", "")).strip().lower()
        key = re.sub(r"\*\*", "", key)  # ignore bold markers for dedup
        if key not in seen:
            seen.add(key)
            result.append(ex)
    return result


# ── Main ─────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="OCR 캐시에서 단어별 예문을 검색한다."
    )
    p.add_argument(
        "--vol", type=int, nargs="+", default=[1, 2, 3, 4, 5],
        metavar="N", help="처리할 볼륨 번호 (기본값: 1 2 3 4 5)",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    # Load vocab
    if not VOCAB_FILE.exists():
        logger.error("Vocab file not found: %s", VOCAB_FILE)
        sys.exit(1)
    vocab = json.loads(VOCAB_FILE.read_text(encoding="utf-8"))
    print(f"  Vocab loaded: {len(vocab):,} entries")

    # Build word index
    form_to_word, word_to_id = build_word_index(vocab)
    print(f"  Word index: {len(word_to_id):,} words, {len(form_to_word):,} forms")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for vol in sorted(args.vol):
        print(f"\n  Processing Vol {vol}...")
        matches = process_volume(vol, form_to_word, word_to_id)

        # Build output structure per word
        output: dict[str, dict] = {}
        for word_key, examples in matches.items():
            examples = deduplicate(examples)
            examples.sort(key=lambda e: (e["volume"], e.get("page", 0)))
            vocab_id = word_to_id.get(word_key, "")
            output[word_key] = {
                "vocab_id": vocab_id,
                "total_count": len(examples),
                "examples": examples,
            }

        out_path = OUTPUT_DIR / f"ocr_examples_vol{vol}.json"
        out_path.write_text(
            json.dumps(output, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        words_with_examples = len(output)
        total_ex = sum(v["total_count"] for v in output.values())
        print(f"  Vol {vol}: {words_with_examples:,} words, {total_ex:,} examples → {out_path.name}")


if __name__ == "__main__":
    main()
