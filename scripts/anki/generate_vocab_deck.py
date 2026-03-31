"""
노랭이 단어 + 기출 예문을 결합한 Anki 단어장 덱(.apkg)을 생성한다. 출력: output/anki/toeic_vocab.apkg
"""

import sys
sys.stdout.reconfigure(encoding='utf-8')

import argparse
import html
import json
import re
from pathlib import Path

import genanki
import yaml

# ── Project root ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[2]  # scripts/anki/../../

# ── Stable model ID (never change) ───────────────────────────────────────────
VOCAB_MODEL_ID = 1607392319


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_config() -> dict:
    cfg_path = PROJECT_ROOT / "config.yaml"
    if cfg_path.exists():
        with cfg_path.open(encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {}


def load_json(path: Path) -> list | dict | None:
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def read_text(path: Path) -> str:
    with path.open(encoding="utf-8") as f:
        return f.read()


# ── Tag generation ────────────────────────────────────────────────────────────

def make_tags(entry: dict, has_mapping: bool) -> list[str]:
    tags: list[str] = []

    # Day tag
    day = entry.get("day")
    if day is not None:
        try:
            tags.append(f"hackers::day{int(day):02d}")
        except (ValueError, TypeError):
            tags.append(f"hackers::day{day}")

    # Frequency tag — supports ★ symbols or level string (기초/중급/고급)
    freq = entry.get("frequency", "") or entry.get("level", "")
    if "★★★" in freq or freq in ("고급", "high"):
        tags.append("frequency::high")
    elif "★★" in freq or freq in ("중급", "mid"):
        tags.append("frequency::mid")
    elif "★" in freq or freq in ("기초", "low"):
        tags.append("frequency::low")

    # POS tag — supports both string and list shapes
    pos_val = entry.get("pos") or ""
    if isinstance(pos_val, list):
        pos_raw = " ".join(pos_val).lower()
    else:
        pos_raw = str(pos_val).lower()
    if "verb" in pos_raw or "동사" in pos_raw:
        tags.append("pos::verb")
    elif "noun" in pos_raw or "명사" in pos_raw:
        tags.append("pos::noun")
    elif "adj" in pos_raw or "형용사" in pos_raw:
        tags.append("pos::adj")
    elif "adv" in pos_raw or "부사" in pos_raw:
        tags.append("pos::adv")

    # 기출 tag
    tags.append("기출등장::있음" if has_mapping else "기출등장::없음")

    return tags


# ── Field value builders ──────────────────────────────────────────────────────

def build_exam_examples(
    mapping_entry: dict | None,
    ets_entry: dict | None = None,
    word: str = "",
) -> str:
    """Return an HTML string of numbered exam examples, or a fallback message.

    Uses word_ets_examples.json: ets_entry with examples[].sentence + source
    """
    MAX_EXAMPLES = 20

    # ── New format: word_ets_examples.json ───────────────────────────────────
    if ets_entry is not None:
        examples = ets_entry.get("examples") or []
        if examples:
            parts: list[str] = []
            for i, ex in enumerate(examples[:MAX_EXAMPLES], start=1):
                raw_sent = (ex.get("sentence") or "").strip()
                # Convert **bold** before escaping so we can preserve it
                raw_sent = re.sub(r'\*\*(.+?)\*\*', lambda m: '\x00' + m.group(1) + '\x01', raw_sent)
                sentence = html.escape(raw_sent)
                # Restore bold placeholders → <b>...</b>
                sentence = re.sub('\x00(.+?)\x01', r'<b>\1</b>', sentence)
                source = (ex.get("source") or "").strip()
                matched_form = (ex.get("matched_form") or "").strip()

                meta_parts: list[str] = []
                if source:
                    meta_parts.append(source)
                if matched_form and matched_form.lower() != word.lower():
                    meta_parts.append(f"형태: {matched_form}")

                meta_str = (
                    f' <span style="color:#9CA3AF;font-size:12px;">({", ".join(meta_parts)})</span>'
                    if meta_parts else ""
                )
                parts.append(f'<div style="margin-bottom:6px;">{i}. {sentence}{meta_str}</div>')
            return "\n".join(parts)

    return "기출 예문 없음"


def build_book_example(entry: dict) -> str:
    sentence = (entry.get("example_sentence") or "").strip()
    translation = (entry.get("example_translation") or "").strip()
    if sentence and translation:
        return f"{sentence}<br><span style='color:#6B7280;font-size:13px;'>{translation}</span>"
    return sentence or translation or ""


def build_synonyms(entry: dict) -> str:
    synonyms = entry.get("synonyms") or []
    if not synonyms:
        return ""
    items = "".join(
        f'<span class="synonym-item">{s.strip()}</span>'
        for s in synonyms
        if s.strip()
    )
    return f'<div class="synonyms">{items}</div>'


# ── Card builder ──────────────────────────────────────────────────────────────

def build_note(
    model: genanki.Model,
    entry: dict,
    mapping_entry: dict | None,
    ets_entry: dict | None = None,
) -> genanki.Note:
    # has_mapping: True if either old mapping or new ets_examples has data
    old_has = mapping_entry is not None and bool(mapping_entry.get("occurrences"))
    new_has = ets_entry is not None and bool(ets_entry.get("examples"))
    has_mapping = old_has or new_has

    # exam_count: prefer new format's total_count, fall back to old
    if ets_entry is not None:
        exam_count = ets_entry.get("total_count", 0)
    elif mapping_entry is not None:
        exam_count = mapping_entry.get("total_count", 0)
    else:
        exam_count = 0

    pos_val = entry.get("pos") or ""
    pos_str = ", ".join(pos_val) if isinstance(pos_val, list) else str(pos_val)
    freq_str = entry.get("frequency") or entry.get("level") or ""
    word_str = entry.get("word") or ""

    fields = [
        html.escape(word_str),
        pos_str,
        entry.get("meaning_kr") or "",
        freq_str,
        str(exam_count),
        build_synonyms(entry),
        build_exam_examples(mapping_entry, ets_entry=ets_entry, word=word_str),
        build_book_example(entry),
        str(entry.get("day") or ""),
        entry.get("id") or "",
    ]

    # Stable GUID from vocab ID so re-imports update, not duplicate
    note_id = entry.get("id") or entry.get("word") or ""
    tags = make_tags(entry, has_mapping)
    return genanki.Note(
        guid=genanki.guid_for(note_id),
        model=model,
        fields=fields,
        tags=tags,
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate Anki vocab deck (.apkg) from processed JSON files."
    )
    p.add_argument(
        "--vocab",
        type=Path,
        default=PROJECT_ROOT / "data/json/hackers_vocab.json",
        help="Path to vocab JSON (default: data/json/hackers_vocab.json)",
    )
    p.add_argument(
        "--ets-examples",
        type=Path,
        default=PROJECT_ROOT / "data/json/word_ets_examples.json",
        help="Path to word_ets_examples.json (default: data/json/word_ets_examples.json)",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "output/anki/toeic_vocab.apkg",
        help="Output .apkg path (default: output/anki/toeic_vocab.apkg)",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    cfg = load_config()

    # ── Load templates & CSS ──────────────────────────────────────────────────
    templates_dir = PROJECT_ROOT / "scripts/anki/templates"
    styles_dir = PROJECT_ROOT / "scripts/anki/styles"

    front_html = read_text(templates_dir / "vocab_front.html")
    back_html = read_text(templates_dir / "vocab_back.html")
    css = read_text(styles_dir / "card_style.css")

    # ── Load vocab ────────────────────────────────────────────────────────────
    vocab_data = load_json(args.vocab)
    if vocab_data is None:
        print(f"[ERROR] Vocab file not found: {args.vocab}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(vocab_data, list):
        print("[ERROR] Vocab JSON must be a list of objects.", file=sys.stderr)
        sys.exit(1)

    # ── Load ETS examples ──────────────────────────────────────────────────────
    ets_raw = load_json(args.ets_examples)
    if ets_raw is None:
        print(f"[INFO] ETS examples file not found ({args.ets_examples.name}). Skipping.")
        ets_by_word: dict[str, dict] = {}
    else:
        # word_ets_examples.json is a dict keyed by word (original casing)
        if isinstance(ets_raw, dict):
            ets_by_word = {k.lower(): v for k, v in ets_raw.items()}
        else:
            ets_by_word = {}
        words_with_examples = sum(1 for v in ets_by_word.values() if v.get("total_count", 0) > 0)
        print(f"[INFO] ETS examples loaded: {len(ets_by_word)} words, {words_with_examples} with examples.")

    # ── Build genanki model ───────────────────────────────────────────────────
    model = genanki.Model(
        VOCAB_MODEL_ID,
        "Toeic Brain Vocab",
        fields=[
            {"name": "Word"},
            {"name": "POS"},
            {"name": "MeaningKR"},
            {"name": "Frequency"},
            {"name": "ExamCount"},
            {"name": "Synonyms"},
            {"name": "ExamExamples"},
            {"name": "BookExample"},
            {"name": "Day"},
            {"name": "VocabID"},
        ],
        templates=[
            {
                "name": "Vocab Card",
                "qfmt": front_html,
                "afmt": back_html,
            }
        ],
        css=css,
    )

    # ── Deck ID from config ───────────────────────────────────────────────────
    deck_id: int = (
        cfg.get("anki", {}).get("vocab_deck", {}).get("id", 2026032901)
    )
    deck_name: str = (
        cfg.get("anki", {}).get("vocab_deck", {}).get("name", "Toeic Brain::단어장")
    )
    deck = genanki.Deck(deck_id, deck_name)

    # ── Sort vocab entries: Day asc, then word asc ────────────────────────────
    def sort_key(e: dict):
        try:
            day = int(e.get("day") or 0)
        except (ValueError, TypeError):
            day = 0
        return (day, (e.get("word") or "").lower())

    # Filter out deleted entries
    active_vocab = [e for e in vocab_data if not e.get("deleted")]
    deleted_count = len(vocab_data) - len(active_vocab)
    if deleted_count:
        print(f"[INFO] Skipped {deleted_count} deleted vocab entry/entries.")
    sorted_vocab = sorted(active_vocab, key=sort_key)

    # ── Build cards ───────────────────────────────────────────────────────────
    tag_stats: dict[str, int] = {}

    for entry in sorted_vocab:
        word_lower = (entry.get("word") or "").lower()

        # Lookup in ETS examples format (case-insensitive by word)
        ets_entry = ets_by_word.get(word_lower)

        note = build_note(model, entry, None, ets_entry=ets_entry)
        deck.add_note(note)
        for tag in note.tags:
            tag_stats[tag] = tag_stats.get(tag, 0) + 1

    # ── Write output ──────────────────────────────────────────────────────────
    args.output.parent.mkdir(parents=True, exist_ok=True)
    genanki.Package(deck).write_to_file(str(args.output))

    # ── Stats ─────────────────────────────────────────────────────────────────
    total = len(sorted_vocab)
    print(f"\n✓ Deck generated: {args.output}")
    print(f"  Total cards   : {total}")
    print(f"  Deck name     : {deck_name}  (id={deck_id})")

    # Tag breakdown (sorted)
    print("\n  Tag breakdown:")
    for tag in sorted(tag_stats):
        print(f"    {tag:<35} {tag_stats[tag]:>5} cards")


if __name__ == "__main__":
    main()
