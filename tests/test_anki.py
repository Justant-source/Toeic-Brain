"""
Anki 덱 생성 테스트
Tests for Anki deck generation helpers – no genanki deck I/O required.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

# ---------------------------------------------------------------------------
# Import helpers from generate_part5_deck.
# genanki must be installed; if not, the whole module will sys.exit – we
# guard against that with a try/except so we can give a clear skip message.
# ---------------------------------------------------------------------------
try:
    from scripts.anki.generate_part5_deck import (
        make_tags,
        build_model,
        load_text,
        TEMPLATES_DIR,
        STYLES_DIR,
        PART5_MODEL_ID,
        PART5_DECK_ID,
    )
    import genanki
    GENANKI_AVAILABLE = True
except SystemExit:
    GENANKI_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not GENANKI_AVAILABLE,
    reason="genanki not installed – skipping Anki tests",
)


# ---------------------------------------------------------------------------
# 1. Template / CSS files exist on disk
# ---------------------------------------------------------------------------

class TestTemplateFiles:
    def test_front_html_exists(self):
        path = TEMPLATES_DIR / "part5_front.html"
        assert path.exists(), f"Missing: {path}"

    def test_back_html_exists(self):
        path = TEMPLATES_DIR / "part5_back.html"
        assert path.exists(), f"Missing: {path}"

    def test_css_exists(self):
        path = STYLES_DIR / "card_style.css"
        assert path.exists(), f"Missing: {path}"

    def test_front_html_nonempty(self):
        path = TEMPLATES_DIR / "part5_front.html"
        assert path.read_text(encoding="utf-8").strip(), "part5_front.html is empty"

    def test_back_html_nonempty(self):
        path = TEMPLATES_DIR / "part5_back.html"
        assert path.read_text(encoding="utf-8").strip(), "part5_back.html is empty"


# ---------------------------------------------------------------------------
# 2. load_text helper
# ---------------------------------------------------------------------------

class TestLoadText:
    def test_loads_existing_file(self, tmp_path):
        f = tmp_path / "sample.txt"
        f.write_text("hello", encoding="utf-8")
        assert load_text(f) == "hello"

    def test_raises_for_missing_file(self, tmp_path):
        missing = tmp_path / "nonexistent.txt"
        with pytest.raises(FileNotFoundError):
            load_text(missing)


# ---------------------------------------------------------------------------
# 3. build_model – returns a genanki.Model with correct fields
# ---------------------------------------------------------------------------

class TestBuildModel:
    def setup_method(self):
        front = TEMPLATES_DIR / "part5_front.html"
        back  = TEMPLATES_DIR / "part5_back.html"
        css   = STYLES_DIR   / "card_style.css"
        self.model = build_model(
            load_text(front),
            load_text(back),
            load_text(css),
        )

    def test_returns_genanki_model(self):
        assert isinstance(self.model, genanki.Model)

    def test_model_id_is_stable(self):
        assert self.model.model_id == PART5_MODEL_ID

    def test_model_has_required_fields(self):
        field_names = [f["name"] for f in self.model.fields]
        for required in ("Sentence", "ChoiceA", "ChoiceB", "ChoiceC", "ChoiceD", "Answer"):
            assert required in field_names, f"Field '{required}' missing from model"

    def test_model_has_one_template(self):
        assert len(self.model.templates) == 1


# ---------------------------------------------------------------------------
# 4. make_tags – tag generation from question dicts
# ---------------------------------------------------------------------------

class TestMakeTags:
    def _q(self, **kwargs):
        base = {"volume": 1, "test": 3, "category": "어휘"}
        base.update(kwargs)
        return base

    def test_returns_list(self):
        assert isinstance(make_tags(self._q()), list)

    def test_volume_tag(self):
        tags = make_tags(self._q(volume=2))
        assert "ets::vol2" in tags

    def test_part_tag_always_5(self):
        tags = make_tags(self._q())
        assert "part::5" in tags

    def test_test_tag_zero_padded(self):
        tags = make_tags(self._q(test=3))
        assert "test::03" in tags

    def test_category_tag_spaces_replaced(self):
        tags = make_tags(self._q(category="품사 어형"))
        assert "category::품사_어형" in tags

    def test_missing_category_uses_default(self):
        tags = make_tags(self._q(category=None))
        assert any("category::" in t for t in tags)

    def test_invalid_test_number_uses_00(self):
        tags = make_tags(self._q(test="bad"))
        assert "test::00" in tags
