"""
generate_part5_deck.py
======================
Read processed Part5 question JSON files and generate an Anki .apkg deck.

Usage
-----
  python generate_part5_deck.py                      # all volumes
  python generate_part5_deck.py --volume 1           # specific volume
  python generate_part5_deck.py --output path.apkg   # custom output path
"""

import sys
import json
import html
import argparse
from pathlib import Path
from collections import defaultdict

# ---------------------------------------------------------------------------
# Ensure UTF-8 output on Windows
# ---------------------------------------------------------------------------
sys.stdout.reconfigure(encoding="utf-8")

try:
    import genanki
except ImportError:
    sys.exit(
        "ERROR: genanki is not installed.\n"
        "Run: pip install genanki"
    )

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT  = Path(r"C:\Data\Toeic Brain")
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed" / "questions"
OUTPUT_DIR    = PROJECT_ROOT / "output" / "anki"
TEMPLATES_DIR = PROJECT_ROOT / "scripts" / "anki" / "templates"
STYLES_DIR    = PROJECT_ROOT / "scripts" / "anki" / "styles"

DEFAULT_OUTPUT = OUTPUT_DIR / "toeic_part5.apkg"

# ---------------------------------------------------------------------------
# Fixed Anki IDs  (must stay constant so existing decks can be updated)
# ---------------------------------------------------------------------------
PART5_MODEL_ID = 1607392320
PART5_DECK_ID  = 2026032902


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_text(path: Path) -> str:
    """Read a text file and return its contents, or raise with a helpful message."""
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")
    return path.read_text(encoding="utf-8")


def build_model(front_html: str, back_html: str, css: str) -> genanki.Model:
    return genanki.Model(
        PART5_MODEL_ID,
        "Toeic Brain Part5",
        fields=[
            {"name": "Volume"},
            {"name": "QuestionNumber"},
            {"name": "Category"},
            {"name": "Sentence"},
            {"name": "ChoiceA"},
            {"name": "ChoiceB"},
            {"name": "ChoiceC"},
            {"name": "ChoiceD"},
            {"name": "Answer"},
            {"name": "AnswerText"},
            {"name": "Explanation"},
            {"name": "VocabInfo"},
        ],
        templates=[
            {
                "name": "Part5 Card",
                "qfmt": front_html,
                "afmt": back_html,
            }
        ],
        css=css,
    )


def make_tags(q: dict) -> list:
    """Return the Anki tags for a question dict."""
    volume   = str(q.get("volume", "0"))
    test     = q.get("test", 0)
    category = q.get("category") or "미분류"

    # Normalise category for a tag: strip whitespace, replace spaces with _
    category_tag = category.strip().replace(" ", "_")

    # Zero-pad test number to 2 digits
    try:
        test_tag = f"{int(test):02d}"
    except (TypeError, ValueError):
        test_tag = "00"

    return [
        f"ets::vol{volume}",
        "part::5",
        f"category::{category_tag}",
        f"test::{test_tag}",
    ]


def escape_field(text: str) -> str:
    """HTML-escape plain text and convert newlines to <br> for Anki display."""
    return html.escape(text).replace("\n", "<br>")


def question_to_note(q: dict, model: genanki.Model) -> genanki.Note:
    """Convert a question dict to a genanki.Note."""
    choices  = q.get("choices") or {}
    answer   = q.get("answer") or ""
    category = q.get("category") or "미분류"

    # Resolve the answer text from the choices dict
    if answer and answer in choices:
        answer_text = choices[answer]
    else:
        answer_text = ""

    explanation_raw = q.get("explanation") or "해설 준비 중"

    # Stable GUID from the question's unique ID so re-imports update, not duplicate
    note_id = q.get("id") or f"vol{q.get('volume',0)}_part5_{q.get('question_number',0)}"
    note = genanki.Note(
        guid=genanki.guid_for(note_id),
        model=model,
        fields=[
            str(q.get("volume", "")),
            str(q.get("question_number", "")),
            category,
            escape_field(q.get("sentence", "")),
            escape_field(choices.get("A", "")),
            escape_field(choices.get("B", "")),
            escape_field(choices.get("C", "")),
            escape_field(choices.get("D", "")),
            answer,
            escape_field(answer_text),
            escape_field(explanation_raw),
            "",  # VocabInfo — will be populated later by mapping
        ],
        tags=make_tags(q),
    )
    return note


def load_questions(volume_filter) -> list:
    """
    Glob for vol*_part5.json files, load them all (or only the specified
    volume), skip questions with no sentence, and return them sorted.
    """
    pattern = "vol*_part5.json"
    files = sorted(PROCESSED_DIR.glob(pattern))

    if not files:
        print(f"WARNING: No files matched '{PROCESSED_DIR / pattern}'")
        return []

    questions = []
    for filepath in files:
        # Extract volume number from filename, e.g. "vol3_part5.json" -> 3
        stem = filepath.stem  # "vol3_part5"
        try:
            vol_num = int(stem.replace("vol", "").split("_")[0])
        except ValueError:
            print(f"WARNING: Could not parse volume from filename '{filepath.name}', skipping.")
            continue

        if volume_filter is not None and vol_num != volume_filter:
            continue

        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"WARNING: Failed to parse '{filepath}': {exc}")
            continue
        except OSError as exc:
            print(f"WARNING: Could not read '{filepath}': {exc}")
            continue

        if not isinstance(data, list):
            print(
                f"WARNING: Expected a list in '{filepath}', "
                f"got {type(data).__name__}. Skipping."
            )
            continue

        before   = len(data)
        deleted  = [q for q in data if q.get("deleted")]
        active   = [q for q in data if not q.get("deleted")]
        valid    = [q for q in active if q.get("sentence", "").strip()]
        skipped  = len(active) - len(valid)
        if deleted:
            print(f"  [{filepath.name}] Skipped {len(deleted)} deleted card(s).")
        if skipped:
            print(f"  [{filepath.name}] Skipped {skipped} question(s) with no sentence.")
        if not deleted and not skipped:
            print(f"  [{filepath.name}] Loaded {len(valid)} question(s).")
        else:
            print(f"  [{filepath.name}] Loaded {len(valid)} question(s) (of {before}).")

        questions.extend(valid)

    # Sort by volume -> test -> question_number
    def sort_key(q: dict):
        try:
            vol = int(q.get("volume", 0))
        except (TypeError, ValueError):
            vol = 0
        try:
            test = int(q.get("test", 0))
        except (TypeError, ValueError):
            test = 0
        try:
            qnum = int(q.get("question_number", 0))
        except (TypeError, ValueError):
            qnum = 0
        return (vol, test, qnum)

    questions.sort(key=sort_key)
    return questions


def print_stats(questions: list) -> None:
    """Print a summary of what was loaded."""
    total = len(questions)
    print(f"\n{'='*50}")
    print(f"  Total cards:  {total}")
    print(f"{'='*50}")

    # Per-volume counts
    vol_counts = defaultdict(int)
    for q in questions:
        vol_counts[str(q.get("volume", "?"))] += 1

    print("\n  Per-volume breakdown:")
    for vol in sorted(vol_counts):
        print(f"    Vol.{vol}: {vol_counts[vol]} cards")

    # Category distribution
    cat_counts = defaultdict(int)
    for q in questions:
        cat = q.get("category") or "미분류"
        cat_counts[cat] += 1

    print("\n  Category distribution:")
    for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
        bar = "\u2588" * min(count // 5, 40)
        print(f"    {cat:<20} {count:>4}  {bar}")

    print(f"{'='*50}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate an Anki .apkg deck for TOEIC Part5 questions."
    )
    parser.add_argument(
        "--volume",
        type=int,
        metavar="N",
        help="Only include questions from this volume (1-5).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        metavar="PATH",
        default=DEFAULT_OUTPUT,
        help=f"Output .apkg path (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()

    # ------------------------------------------------------------------
    # Load templates
    # ------------------------------------------------------------------
    print("Loading card templates and styles...")
    front_html = load_text(TEMPLATES_DIR / "part5_front.html")
    back_html  = load_text(TEMPLATES_DIR / "part5_back.html")
    css        = load_text(STYLES_DIR    / "card_style.css")

    model = build_model(front_html, back_html, css)

    # ------------------------------------------------------------------
    # Load questions
    # ------------------------------------------------------------------
    if args.volume is not None:
        print(f"Loading questions for volume {args.volume}...")
    else:
        print("Loading questions for all volumes...")

    questions = load_questions(args.volume)

    if not questions:
        print("ERROR: No valid questions found. Aborting.")
        sys.exit(1)

    # ------------------------------------------------------------------
    # Build deck
    # ------------------------------------------------------------------
    deck = genanki.Deck(PART5_DECK_ID, "Toeic Brain::Part5 기출")

    for q in questions:
        note = question_to_note(q, model)
        deck.add_note(note)

    # ------------------------------------------------------------------
    # Write .apkg
    # ------------------------------------------------------------------
    output_path = args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    package = genanki.Package(deck)
    package.write_to_file(str(output_path))

    print(f"\nDeck written to: {output_path}")

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------
    print_stats(questions)


if __name__ == "__main__":
    main()
