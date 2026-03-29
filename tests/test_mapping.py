"""
단어-기출 매핑 테스트
Tests for word mapping logic – no data files required.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from scripts.process.map_words import (
    _fallback_lemma,
    _build_word_family,
    build_inverted_index,
    get_lemma,
)


# ---------------------------------------------------------------------------
# 1. _fallback_lemma – suffix stripping
# ---------------------------------------------------------------------------

class TestFallbackLemma:
    @pytest.mark.parametrize("word,expected_base", [
        ("running",     "runn"),      # -ing stripped
        ("knowledge",   "knowledge"), # no matching suffix → unchanged
        ("quickly",     "quick"),     # -ly stripped
        ("happiness",   "happi"),     # -ness stripped
        ("beautiful",   "beauti"),    # -ful stripped
        ("development", "develop"),   # -ment stripped
    ])
    def test_suffix_stripped(self, word, expected_base):
        result = _fallback_lemma(word)
        assert result == expected_base

    def test_short_word_unchanged(self):
        # stems < 3 chars must not be stripped
        assert _fallback_lemma("go") == "go"

    def test_returns_lowercase(self):
        assert _fallback_lemma("Running") == "runn"


# ---------------------------------------------------------------------------
# 2. _build_word_family – expansion
# ---------------------------------------------------------------------------

class TestBuildWordFamily:
    def test_original_word_in_family(self):
        family = _build_word_family("manage", "manage", [])
        assert "manage" in family

    def test_lemma_in_family(self):
        family = _build_word_family("managing", "manage", [])
        assert "manage" in family

    def test_synonyms_in_family(self):
        family = _build_word_family("manage", "manage", ["handle", "control"])
        assert "handle" in family
        assert "control" in family

    def test_family_is_lowercase(self):
        family = _build_word_family("Manage", "Manage", [])
        for form in family:
            assert form == form.lower(), f"Non-lowercase form: {form}"

    def test_minimum_length_enforced(self):
        family = _build_word_family("manage", "manage", [])
        for form in family:
            assert len(form) >= 3, f"Form too short: {form!r}"

    def test_derivatives_generated(self):
        # "manage" should produce forms like "management", "manager", etc.
        family = _build_word_family("manage", "manage", [])
        # At minimum the original + some derivatives should exist
        assert len(family) > 1


# ---------------------------------------------------------------------------
# 3. build_inverted_index
# ---------------------------------------------------------------------------

SAMPLE_VOCAB = [
    {"id": "v001", "word": "manage",  "synonyms": ["handle"]},
    {"id": "v002", "word": "produce", "synonyms": []},
    {"id": "v003", "word": "quickly", "synonyms": ["swiftly"]},
]


class TestBuildInvertedIndex:
    def setup_method(self):
        self.form_to_ids, self.id_to_forms = build_inverted_index(
            SAMPLE_VOCAB, use_spacy=False
        )

    def test_all_vocab_ids_present(self):
        for entry in SAMPLE_VOCAB:
            assert entry["id"] in self.id_to_forms

    def test_original_word_maps_to_its_id(self):
        assert "v001" in self.form_to_ids.get("manage", set())

    def test_synonym_maps_to_vocab_id(self):
        # "handle" is a synonym of v001
        assert "v001" in self.form_to_ids.get("handle", set())

    def test_id_to_forms_is_nonempty(self):
        for vid in ("v001", "v002", "v003"):
            assert len(self.id_to_forms[vid]) > 0

    def test_no_empty_forms_in_index(self):
        for form in self.form_to_ids:
            assert form.strip() != "", f"Empty form key found"
            assert len(form) >= 3, f"Form too short: {form!r}"


# ---------------------------------------------------------------------------
# 4. get_lemma – falls back gracefully when spaCy unavailable
# ---------------------------------------------------------------------------

class TestGetLemma:
    def test_returns_string(self):
        result = get_lemma("running")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_lowercase_output(self):
        result = get_lemma("Running")
        assert result == result.lower()
