"""
Shared NLP utilities for lemmatisation and word-family expansion.

Uses spaCy (en_core_web_sm) as the sole lemmatization engine.
Provides both single-token and context-aware sentence lemmatization.
"""

import json
from collections import defaultdict
from pathlib import Path

import spacy

# spaCy 모델 로드 (모듈 임포트 시 즉시 로드)
_nlp = spacy.load("en_core_web_sm", disable=["ner"])

# ── 문법 대용어 / 패턴 마커 ──────────────────────────────────────────────────

# 문법 대용어 → 실제 출현 형태 매핑
GRAMMAR_PLACEHOLDERS = {
    "be": {"be", "is", "are", "was", "were", "been", "being", "am"},
    "oneself": {
        "oneself", "myself", "yourself", "himself", "herself",
        "itself", "ourselves", "yourselves", "themselves",
    },
    "one's": {"my", "your", "his", "her", "its", "our", "their"},
    "someone": {"someone", "somebody", "anyone", "anybody", "everyone", "everybody"},
    "do": {"do", "does", "did", "done", "doing"},
    "have": {"have", "has", "had", "having"},
}

# 문법 패턴 표기로 사용되어 매칭에서 제외해야 하는 토큰
PATTERN_MARKERS = {"do", "doing", "sth", "sb", "something", "somebody"}


# ── Lemmatisation ────────────────────────────────────────────────────────────

def get_lemma(word: str) -> str:
    """Return the lemma of a single word using spaCy."""
    doc = _nlp(word.lower())
    if doc:
        return doc[0].lemma_
    return word.lower()


# Sentence lemma cache (LRU-style, bounded)
_sentence_lemma_cache: dict[str, dict[str, str]] = {}
_CACHE_MAX_SIZE = 50000


def get_sentence_lemmas(sentence: str) -> dict[str, str]:
    """문장 전체를 spaCy로 처리하여 {token_lower: lemma} 매핑을 반환한다.

    문장 단위로 처리하면 POS 태깅이 정확해져 lemma 품질이 향상된다.
    예: "left" → 문맥에 따라 "leave"(동사) 또는 "left"(형용사)
    """
    cache_key = sentence
    if cache_key in _sentence_lemma_cache:
        return _sentence_lemma_cache[cache_key]

    doc = _nlp(sentence)
    result: dict[str, str] = {}
    for token in doc:
        tl = token.text.lower()
        # 같은 토큰이 여러 번 나오면 첫 번째 lemma 유지
        if tl not in result:
            result[tl] = token.lemma_.lower()

    # Cache management
    if len(_sentence_lemma_cache) >= _CACHE_MAX_SIZE:
        # Remove oldest 20% of entries
        keys_to_remove = list(_sentence_lemma_cache.keys())[:_CACHE_MAX_SIZE // 5]
        for k in keys_to_remove:
            del _sentence_lemma_cache[k]
    _sentence_lemma_cache[cache_key] = result

    return result


# ── Word-family expansion ─────────────────────────────────────────────────────

# Derivation patterns: (suffix_to_detect, replacements_to_try)
_DERIV_PATTERNS = [
    ("e",    ["ion", "tion", "ation", "er", "or", "ment", "ence", "ance",
               "ed", "es", "ing", "ings"]),
    ("",     ["ion", "tion", "ation", "ment", "ence", "ance", "er", "or",
               "ness", "ity", "al", "ous", "ive", "able", "ible", "ful", "ly",
               "s", "es", "ed", "ing", "ings"]),
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

    for seed in (word.lower(), lemma.lower()):
        add_base(seed)

    for syn in synonyms:
        if syn:
            forms.add(syn.lower().strip())

    forms = {f for f in forms if len(f) >= _MIN_STEM}
    return forms


# ── Inverted index ────────────────────────────────────────────────────────────

def build_inverted_index(
    vocab: list[dict],
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

        lemma = get_lemma(word)
        synonyms = entry.get("synonyms") or []
        family = _build_word_family(word, lemma, synonyms)

        id_to_forms[vid] = family
        for form in family:
            form_to_ids[form].add(vid)

    return dict(form_to_ids), id_to_forms


# ── Chapter map builder ──────────────────────────────────────────────────────

def build_chapter_map_from_vocab(vocab_path: Path) -> list[dict]:
    """hackers_vocab.json → chapter_map 형식 변환"""
    with open(vocab_path, encoding="utf-8") as f:
        vocab = json.load(f)
    by_day: dict[int, list[dict]] = {}
    for entry in vocab:
        day = entry.get("day", 0)
        by_day.setdefault(day, []).append({
            "word": entry["word"],
            "id": entry["id"],
            "related_words": [],
            "synonyms": []
        })
    return [{"chapter": d, "words": by_day[d]} for d in sorted(by_day)]
