"""
Map vocabulary words from the hackers vocab JSON to their occurrences in ETS Part5 questions.

Input:
  data/processed/vocab/hackers_vocab.json  — vocab entries
  data/processed/questions/vol*_part5.json — Part5 questions

Output:
  data/mapped/word_question_map.json

Usage:
  python map_words.py                          # Default paths
  python map_words.py --vocab path.json        # Custom vocab
  python map_words.py --questions-dir path/    # Custom questions dir
  python map_words.py --output path.json       # Custom output
  python map_words.py --no-spacy               # Disable spaCy, use fallback
"""

import sys
import re
import json
import argparse
from pathlib import Path
from collections import defaultdict
from typing import Optional

# Windows UTF-8 fix
sys.stdout.reconfigure(encoding="utf-8")

# ── Project paths ─────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent  # scripts/process/ → project root

DEFAULT_VOCAB_PATH = PROJECT_ROOT / "data" / "processed" / "vocab" / "hackers_vocab.json"
DEFAULT_QUESTIONS_DIR = PROJECT_ROOT / "data" / "processed" / "questions"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data" / "mapped" / "word_question_map.json"

# ── ANSI colours ──────────────────────────────────────────────────────────────

GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def green(s: str)  -> str: return f"{GREEN}{s}{RESET}"
def yellow(s: str) -> str: return f"{YELLOW}{s}{RESET}"
def cyan(s: str)   -> str: return f"{CYAN}{s}{RESET}"
def bold(s: str)   -> str: return f"{BOLD}{s}{RESET}"

# ── spaCy / fallback lemmatisation ────────────────────────────────────────────

_nlp = None  # spaCy model, loaded lazily

def _load_spacy() -> bool:
    """Try to load spaCy en_core_web_sm. Returns True on success."""
    global _nlp
    try:
        import spacy  # noqa: F401
        _nlp = spacy.load("en_core_web_sm", disable=["parser", "ner"])
        return True
    except Exception:
        return False


# Ordered longest-first so greedy suffix stripping is stable.
_SUFFIXES = [
    "tion", "sion", "ment", "ness", "ity",
    "ing", "ed", "er", "est",
    "ous", "ive", "able", "ible",
    "al", "ly", "ful",
]

def _fallback_lemma(word: str) -> str:
    """Strip common English suffixes to approximate a base form."""
    w = word.lower()
    for suf in _SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[: -len(suf)]
    return w


def get_lemma(word: str) -> str:
    """Return the lemma of *word* using spaCy when available."""
    if _nlp is not None:
        doc = _nlp(word.lower())
        if doc:
            return doc[0].lemma_
    return _fallback_lemma(word)


# ── Word-family expansion ─────────────────────────────────────────────────────

# Derivation patterns: (suffix_to_detect, replacements_to_try)
# Each replacement may itself produce multiple forms.
_DERIV_PATTERNS = [
    # verb → noun
    ("e",    ["ion", "tion", "ation", "er", "or", "ment", "ence", "ance"]),
    ("",     ["ion", "tion", "ation", "ment", "ence", "ance", "er", "or",
               "ness", "ity", "al", "ous", "ive", "able", "ible", "ful", "ly"]),
    ("tion", ["t", "te", "tive", "tional", "tionally"]),
    ("sion", ["de", "se", "sive", "sional"]),
    ("ment", ["", "al", "ally"]),
    ("ness", ["", "less", "ful", "fully"]),
    ("ity",  ["", "ous", "ize", "ization"]),
    ("ly",   ["", "ness", "ful"]),
    ("ing",  ["", "e", "ed", "er", "ion", "tion", "ment"]),
    ("ed",   ["", "e", "ing", "er", "ion", "tion", "ment"]),
    ("er",   ["", "e", "ing", "ed", "ion", "tion"]),
    ("ous",  ["", "ness", "ly"]),
    ("ive",  ["", "ness", "ly", "ity"]),
    ("able", ["", "ness", "bly", "ility"]),
    ("ible", ["", "ness", "bly", "ility"]),
    ("al",   ["", "ly", "ize", "ism"]),
    ("ful",  ["", "ly", "ness"]),
]

_MIN_STEM = 3  # stems shorter than this are ignored


def _build_word_family(word: str, lemma: str, synonyms: list[str]) -> set[str]:
    """
    Return a set of word forms that belong to the same family.
    Includes: original word, its lemma, common derivations, and synonyms.
    """
    forms: set[str] = set()

    def add_base(base: str) -> None:
        """Try generating derivatives from *base* and add them."""
        if not base or len(base) < _MIN_STEM:
            return
        forms.add(base)
        for suf, replacements in _DERIV_PATTERNS:
            if suf == "" or base.endswith(suf):
                stem = base[: len(base) - len(suf)] if suf else base
                if len(stem) < _MIN_STEM:
                    continue
                for rep in replacements:
                    candidate = stem + rep
                    if len(candidate) >= _MIN_STEM:
                        forms.add(candidate)

    # Seed from the original word and its lemma
    for seed in (word.lower(), lemma.lower()):
        add_base(seed)

    # Include synonyms as additional seeds (just the words themselves; no
    # deep expansion of synonyms to keep the family focused).
    for syn in synonyms:
        if syn:
            forms.add(syn.lower().strip())

    # Remove empty strings / very short tokens
    forms = {f for f in forms if len(f) >= _MIN_STEM}
    return forms


# ── Inverted index ────────────────────────────────────────────────────────────

def build_inverted_index(
    vocab: list[dict],
    use_spacy: bool,
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """
    Build two maps:
      form_to_vocab_ids : word_form (lower) → {vocab_id, ...}
      vocab_id_to_forms : vocab_id          → {word_form, ...}

    Returns (form_to_vocab_ids, vocab_id_to_forms).
    """
    form_to_ids: dict[str, set[str]] = defaultdict(set)
    id_to_forms: dict[str, set[str]] = {}

    for entry in vocab:
        vid = entry.get("id", "")
        word = entry.get("word", "").strip()
        if not word:
            continue

        lemma = get_lemma(word) if use_spacy or True else _fallback_lemma(word)
        synonyms = entry.get("synonyms") or []
        family = _build_word_family(word, lemma, synonyms)

        id_to_forms[vid] = family
        for form in family:
            form_to_ids[form].add(vid)

    return dict(form_to_ids), id_to_forms


# ── Question loading ──────────────────────────────────────────────────────────

def load_questions(questions_dir: Path) -> list[dict]:
    """Load all vol*_part5.json files from *questions_dir*."""
    pattern = "vol*_part5.json"
    files = sorted(questions_dir.glob(pattern))
    if not files:
        print(yellow(f"[WARN] No Part5 question files found in {questions_dir}"))
        return []

    questions = []
    for fp in files:
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            if isinstance(data, list):
                questions.extend(data)
            else:
                print(yellow(f"[WARN] Unexpected format in {fp.name} — skipping"))
        except Exception as exc:
            print(yellow(f"[WARN] Could not read {fp.name}: {exc}"))

    print(f"  Loaded {len(questions):,} questions from {len(files)} file(s)")
    return questions


# ── Matching ──────────────────────────────────────────────────────────────────

def _search_text(pattern: re.Pattern, text: Optional[str]) -> bool:
    """Return True if *pattern* matches anywhere in *text*."""
    if not text:
        return False
    return bool(pattern.search(text))


def match_question(
    question: dict,
    form_to_ids: dict[str, set[str]],
    id_to_forms: dict[str, set[str]],
    vocab_index: dict[str, dict],  # vocab_id → entry
) -> list[tuple[str, dict]]:
    """
    Check one question against the inverted index.

    Returns a list of (vocab_id, occurrence_record) pairs.
    """
    qid = question.get("id", "")
    sentence = question.get("sentence", "") or ""
    choices: dict[str, str] = question.get("choices") or {}
    answer_label: Optional[str] = question.get("answer")  # "A" / "B" / "C" / "D" or None

    # Collect (label, text) pairs: None label means "in sentence"
    texts_to_check: list[tuple[Optional[str], str]] = [
        (None, sentence),
    ]
    for label, text in choices.items():
        if text:
            texts_to_check.append((label, str(text)))

    # Track which (vocab_id, label) pairs we've already recorded so we don't
    # double-count the same word in the same field.
    recorded: set[tuple[str, Optional[str]]] = set()
    results: list[tuple[str, dict]] = []

    for label, text in texts_to_check:
        if not text:
            continue
        # Tokenise naively to get candidate forms (lower-case words only)
        tokens = re.findall(r"[a-zA-Z]+", text)
        for token in tokens:
            token_lc = token.lower()
            if token_lc not in form_to_ids:
                continue
            for vid in form_to_ids[token_lc]:
                key = (vid, label)
                if key in recorded:
                    continue
                recorded.add(key)

                entry = vocab_index.get(vid, {})
                answer_label_norm = (answer_label or "").upper() or None

                # as_answer: word appeared as the correct answer choice
                if label is not None:
                    as_answer = (label.upper() == answer_label_norm) if answer_label_norm else False
                    as_choice: Optional[str] = label.upper()
                else:
                    # Word is in the sentence body, not in any choice
                    as_answer = False
                    as_choice = None

                occurrence = {
                    "question_id": qid,
                    "context": sentence,
                    "as_answer": as_answer,
                    "as_choice": as_choice,
                    "form_used": token,
                }
                results.append((vid, occurrence))

    return results


# ── Output assembly ───────────────────────────────────────────────────────────

def build_output(
    vocab: list[dict],
    id_to_forms: dict[str, set[str]],
    occurrences_by_id: dict[str, list[dict]],
) -> list[dict]:
    """Assemble the final output list, one entry per vocab word."""
    output = []
    for entry in vocab:
        vid = entry.get("id", "")
        word = entry.get("word", "").strip()
        occs = occurrences_by_id.get(vid, [])

        forms_seen: list[str] = sorted(
            {occ["form_used"] for occ in occs}
        )
        parts_appeared = ["Part5"] if occs else []

        output.append(
            {
                "word": word,
                "vocab_id": vid,
                "occurrences": occs,
                "total_count": len(occs),
                "parts_appeared": parts_appeared,
                "forms_seen": forms_seen,
            }
        )
    return output


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Map hackers vocab words to ETS Part5 question occurrences."
    )
    parser.add_argument(
        "--vocab",
        type=Path,
        default=DEFAULT_VOCAB_PATH,
        metavar="PATH",
        help="Path to hackers_vocab.json",
    )
    parser.add_argument(
        "--questions-dir",
        type=Path,
        default=DEFAULT_QUESTIONS_DIR,
        metavar="DIR",
        help="Directory containing vol*_part5.json files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        metavar="PATH",
        help="Output JSON path",
    )
    parser.add_argument(
        "--no-spacy",
        action="store_true",
        help="Disable spaCy and use the fallback suffix-stripping lemmatiser",
    )
    args = parser.parse_args()

    print(bold("=== Word–Question Mapper ==="))

    # ── spaCy setup ───────────────────────────────────────────────────────────
    use_spacy = not args.no_spacy
    if use_spacy:
        print("  Loading spaCy model … ", end="", flush=True)
        if _load_spacy():
            print(green("ok"))
        else:
            use_spacy = False
            print(yellow("not available — using fallback lemmatiser"))
    else:
        print(yellow("  spaCy disabled — using fallback lemmatiser"))

    # ── Load vocab ────────────────────────────────────────────────────────────
    vocab_path: Path = args.vocab
    if not vocab_path.exists():
        print(yellow(f"[WARN] Vocab file not found: {vocab_path}"))
        print(yellow("       Run extract_vocab.py first, or supply --vocab."))
        vocab: list[dict] = []
    else:
        try:
            vocab = json.loads(vocab_path.read_text(encoding="utf-8"))
            print(f"  Loaded {len(vocab):,} vocab entries from {vocab_path.name}")
        except Exception as exc:
            print(yellow(f"[WARN] Could not read vocab file: {exc}"))
            vocab = []

    # ── Load questions ────────────────────────────────────────────────────────
    questions = load_questions(args.questions_dir)

    # Handle graceful empty-run
    if not vocab and not questions:
        print(yellow("[WARN] No vocab and no questions found. Writing empty output."))
        _write_output([], args.output)
        return

    if not vocab:
        print(yellow("[WARN] No vocab entries — nothing to map. Writing empty output."))
        _write_output([], args.output)
        return

    if not questions:
        print(yellow("[WARN] No questions found — writing vocab entries with zero occurrences."))
        empty_output = build_output(vocab, {}, {})
        _write_output(empty_output, args.output)
        return

    # ── Build inverted index ──────────────────────────────────────────────────
    print("  Building word-family index … ", end="", flush=True)
    vocab_index = {e["id"]: e for e in vocab if e.get("id")}
    form_to_ids, id_to_forms = build_inverted_index(vocab, use_spacy)
    print(f"{len(form_to_ids):,} distinct forms indexed")

    # ── Match questions ───────────────────────────────────────────────────────
    print(f"  Matching {len(questions):,} questions … ", end="", flush=True)
    occurrences_by_id: dict[str, list[dict]] = defaultdict(list)
    total_occurrences = 0

    for question in questions:
        matches = match_question(question, form_to_ids, id_to_forms, vocab_index)
        for vid, occ in matches:
            occurrences_by_id[vid].append(occ)
            total_occurrences += 1

    print(f"{total_occurrences:,} occurrences found")

    # ── Assemble output ───────────────────────────────────────────────────────
    output = build_output(vocab, id_to_forms, occurrences_by_id)

    # ── Write output ──────────────────────────────────────────────────────────
    _write_output(output, args.output)

    # ── Summary stats ─────────────────────────────────────────────────────────
    words_with_matches = sum(1 for e in output if e["total_count"] > 0)
    total_vocab = len(vocab)
    coverage = (words_with_matches / total_vocab * 100) if total_vocab else 0.0

    print()
    print(bold("── Summary ──────────────────────────────────────"))
    print(f"  Total vocab words    : {cyan(str(total_vocab)):>10}")
    print(f"  Words with matches   : {green(str(words_with_matches)):>10}")
    print(f"  Total occurrences    : {cyan(str(total_occurrences)):>10}")
    print(f"  Coverage             : {green(f'{coverage:.1f}%'):>10}")
    print(f"  Output               : {args.output}")
    print(bold("─────────────────────────────────────────────────"))


def _write_output(data: list[dict], output_path: Path) -> None:
    """Ensure the parent directory exists and write JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  Written → {output_path}  ({len(data):,} entries)")


if __name__ == "__main__":
    main()
