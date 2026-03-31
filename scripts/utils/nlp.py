"""
Shared NLP utilities for lemmatisation and word-family expansion.

Extracted from scripts/process/map_words.py so that multiple modules
(find_ets_examples, map_words, etc.) can import them without circular deps.
"""

from collections import defaultdict

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
_DERIV_PATTERNS = [
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
