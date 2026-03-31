"""
hackers_vocab.json을 읽어 chapter_map.json을 생성한다.

Input:  data/json/hackers_vocab.json
Output: data/json/chapter_map.json

Format:
[
  {
    "chapter": 1,
    "words": [
      {"word": "resume", "id": "hw_0001", "related_words": [], "synonyms": []}
    ]
  }
]
"""

import sys
import json
from pathlib import Path
from collections import defaultdict

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent

INPUT_PATH = PROJECT_ROOT / "data" / "json" / "hackers_vocab.json"
OUTPUT_PATH = PROJECT_ROOT / "data" / "json" / "chapter_map.json"


def main() -> None:
    if not INPUT_PATH.exists():
        print(f"[ERROR] hackers_vocab.json not found: {INPUT_PATH}", file=sys.stderr)
        sys.exit(1)

    all_vocab: list[dict] = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    print(f"  Loaded {len(all_vocab):,} entries from {INPUT_PATH.name}")

    # Group by day
    by_day: dict[int, list[dict]] = defaultdict(list)
    for entry in all_vocab:
        try:
            day = int(entry.get("day") or 0)
        except (ValueError, TypeError):
            day = 0
        by_day[day].append(entry)

    # Build chapter_map list sorted by day
    chapter_map: list[dict] = []
    for day in sorted(by_day.keys()):
        words: list[dict] = []
        for entry in by_day[day]:
            words.append({
                "word": entry.get("word", ""),
                "id": entry.get("id", ""),
                "related_words": [],
                "synonyms": [],
            })
        chapter_map.append({
            "chapter": day,
            "words": words,
        })

    # Write output
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(chapter_map, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    total_words = sum(len(ch["words"]) for ch in chapter_map)
    print(f"  Written {len(chapter_map)} chapters, {total_words:,} words -> {OUTPUT_PATH}")

    # Spot-check: show first chapter
    if chapter_map:
        first = chapter_map[0]
        print(f"\n  Spot-check chapter {first['chapter']} (first 3 words):")
        for w in first["words"][:3]:
            print(f"    {w}")


if __name__ == "__main__":
    main()
