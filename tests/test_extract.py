"""
데이터 추출 스크립트 테스트
Tests for extraction logic – no actual PDF files required.
"""

import re
import sys
from pathlib import Path

# Make project root importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

# ---------------------------------------------------------------------------
# Import the functions under test directly from the module.
# We avoid importing fitz/yaml at the top level by importing only the
# pure-Python helpers that don't need those heavy deps.
# ---------------------------------------------------------------------------
from scripts.extract.extract_ets import (
    BLANK_PATTERN,
    NORMALIZED_BLANK,
    FOOTER_PATTERN,
    Q_NUMBER_RE,
    clean_text,
    normalize_sentence,
    split_into_raw_questions,
    parse_question_block,
)

# ---------------------------------------------------------------------------
# Sample text representing two Part 5 questions (inline blank style)
# ---------------------------------------------------------------------------
SAMPLE_PART5_TEXT = """\
101. Ms. Durkin asked for volunteers to help
------- with the employee fitness program.
(A) she
(B) her
(C) hers
(D) herself
102. Lasner Electronics staff have extensive
------- of current hardware systems.
(A) know
(B) known
(C) knowledge
(D) knowledgeable
"""

# ---------------------------------------------------------------------------
# 1. Blank normalisation
# ---------------------------------------------------------------------------

class TestBlankNormalization:
    """Various dash/slash patterns must all collapse to NORMALIZED_BLANK."""

    @pytest.mark.parametrize("raw,expected", [
        ("-------",  NORMALIZED_BLANK),   # already canonical 7 hyphens
        ("--------", NORMALIZED_BLANK),   # 8 hyphens (Vol1-4 variant)
        ("------",   NORMALIZED_BLANK),   # 6 hyphens (minimum 3 triggers match)
        ("///",      NORMALIZED_BLANK),   # Vol5 slash style
        ("///////",  NORMALIZED_BLANK),   # longer slash variant
    ])
    def test_blank_pattern_match(self, raw, expected):
        assert BLANK_PATTERN.sub(NORMALIZED_BLANK, raw) == expected

    def test_non_blank_text_unchanged(self):
        text = "hello world"
        assert BLANK_PATTERN.sub(NORMALIZED_BLANK, text) == text

    def test_clean_text_normalizes_blank(self):
        raw = "He asked for //////// a reply."
        result = clean_text(raw)
        assert NORMALIZED_BLANK in result
        assert "///////" not in result


# ---------------------------------------------------------------------------
# 2. Footer removal
# ---------------------------------------------------------------------------

class TestFooterRemoval:
    def test_go_on_removed(self):
        text = "Some question text\nGO ON TO THE NEXT PAGE\nMore text"
        result = clean_text(text)
        assert "GO ON TO THE NEXT PAGE" not in result

    def test_stop_removed(self):
        text = "Question\nSTOP. Do not go on\nend"
        result = clean_text(text)
        assert "STOP. Do not go on" not in result

    def test_test_page_number_removed(self):
        # e.g. "TEST 1 101" appearing at a page footer
        text = "valid content\nTEST 1 101\nmore content"
        result = clean_text(text)
        assert "TEST 1 101" not in result

    def test_normal_text_preserved(self):
        text = "Ms. Durkin asked for volunteers."
        assert clean_text(text) == text


# ---------------------------------------------------------------------------
# 3. Question regex / splitting
# ---------------------------------------------------------------------------

class TestSplitIntoRawQuestions:
    def test_correct_count(self):
        blocks = split_into_raw_questions(SAMPLE_PART5_TEXT)
        assert len(blocks) == 2

    def test_question_numbers(self):
        blocks = split_into_raw_questions(SAMPLE_PART5_TEXT)
        numbers = [q_num for q_num, _ in blocks]
        assert numbers == [101, 102]

    def test_out_of_range_ignored(self):
        text = "99. This should be ignored.\n(A) x\n(B) y\n(C) z\n(D) w\n" + SAMPLE_PART5_TEXT
        blocks = split_into_raw_questions(text)
        numbers = [q_num for q_num, _ in blocks]
        assert 99 not in numbers

    def test_block_contains_choices(self):
        blocks = split_into_raw_questions(SAMPLE_PART5_TEXT)
        for _, block in blocks:
            assert "(A)" in block
            assert "(D)" in block


# ---------------------------------------------------------------------------
# 4. parse_question_block – structure validation
# ---------------------------------------------------------------------------

class TestParseQuestionBlock:
    def _get_block(self, n: int) -> tuple[int, str]:
        blocks = split_into_raw_questions(SAMPLE_PART5_TEXT)
        return blocks[n]

    def test_choices_keys(self):
        q_num, block = self._get_block(0)
        result = parse_question_block(q_num, block)
        assert result is not None
        assert set(result["choices"].keys()) == {"A", "B", "C", "D"}

    def test_choices_not_empty(self):
        q_num, block = self._get_block(0)
        result = parse_question_block(q_num, block)
        assert result is not None
        for letter, text in result["choices"].items():
            assert text.strip(), f"Choice {letter} is empty"

    def test_sentence_contains_blank(self):
        q_num, block = self._get_block(0)
        result = parse_question_block(q_num, block)
        assert result is not None
        assert NORMALIZED_BLANK in result["sentence"]

    def test_correct_choices_q101(self):
        q_num, block = self._get_block(0)
        result = parse_question_block(q_num, block)
        assert result is not None
        assert result["choices"]["A"] == "she"
        assert result["choices"]["D"] == "herself"

    def test_returns_none_for_missing_choices(self):
        bad_block = "101. This question has no options at all."
        result = parse_question_block(101, bad_block)
        assert result is None


# ---------------------------------------------------------------------------
# 5. normalize_sentence
# ---------------------------------------------------------------------------

class TestNormalizeSentence:
    def test_collapses_single_newlines(self):
        s = "Ms. Durkin\nasked for volunteers"
        assert "\n" not in normalize_sentence(s)

    def test_blank_line_becomes_blank_marker(self):
        # Vol1 "blank-line" style: empty line between sentence halves
        s = "She wanted\n\nto attend."
        result = normalize_sentence(s)
        assert NORMALIZED_BLANK in result

    def test_multiple_spaces_collapsed(self):
        s = "word   word"
        result = normalize_sentence(s)
        assert "  " not in result
