"""
build_vocab_cards.py
====================
노랭이 단어장(hackers_vocab.json)과 기출 예문(word_ets_examples.json)을 결합하여
Anki 카드 데이터 JSON을 생성한다.

출력: data/anki/vocab_cards.json

Usage
-----
  python build_vocab_cards.py
  python build_vocab_cards.py --vocab path/to/vocab.json --examples path/to/examples.json
  python build_vocab_cards.py --output path/to/output.json
"""

import sys

sys.stdout.reconfigure(encoding="utf-8")

import argparse
import json
from pathlib import Path

# ── Project root ─────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# ── 기본 경로 ────────────────────────────────────────────────────────────────
DEFAULT_VOCAB = PROJECT_ROOT / "data" / "json" / "hackers_vocab.json"
DEFAULT_EXAMPLES = PROJECT_ROOT / "data" / "json" / "word_ets_examples.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "anki" / "vocab_cards.json"

MAX_EXAMPLES = 5


# ── Helpers ──────────────────────────────────────────────────────────────────

def load_json(path: Path) -> list | dict | None:
    """JSON 파일을 읽어 반환한다. 파일이 없으면 None."""
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def select_examples(examples: list) -> list[dict]:
    """예문 목록에서 최대 MAX_EXAMPLES개를 선별한다.

    선별 기준:
    1. Part5 예문 우선
    2. volume 오름차순
    """
    def sort_key(ex: dict):
        part = ex.get("part", 99)
        # Part5를 최우선으로
        part_priority = 0 if part == 5 else 1
        volume = ex.get("volume", 99)
        return (part_priority, volume)

    sorted_examples = sorted(examples, key=sort_key)
    result = []
    for ex in sorted_examples[:MAX_EXAMPLES]:
        result.append({
            "sentence": (ex.get("sentence") or "").strip(),
            "source": (ex.get("source") or "").strip(),
            "part": ex.get("part"),
        })
    return result


def build_card(entry: dict, ets_entry: dict | None) -> dict:
    """단어장 항목과 ETS 예문을 결합하여 카드 데이터를 생성한다."""
    card: dict = {
        "id": entry.get("id", ""),
        "word": entry.get("word", ""),
        "meaning_kr": entry.get("meaning_kr", ""),
        "pos": entry.get("pos", []),
        "day": entry.get("day"),
        "level": entry.get("level", ""),
        "ets_count": 0,
        "examples": [],
    }

    if ets_entry is not None:
        card["ets_count"] = ets_entry.get("total_count", 0)
        raw_examples = ets_entry.get("examples") or []
        card["examples"] = select_examples(raw_examples)

    return card


# ── Main ─────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    """커맨드라인 인자를 파싱한다."""
    p = argparse.ArgumentParser(
        description="노랭이 단어장 + 기출 예문을 결합하여 Anki 카드 JSON을 생성한다.",
    )
    p.add_argument(
        "--vocab",
        type=Path,
        default=DEFAULT_VOCAB,
        help=f"단어장 JSON 경로 (기본: {DEFAULT_VOCAB.relative_to(PROJECT_ROOT)})",
    )
    p.add_argument(
        "--examples",
        type=Path,
        default=DEFAULT_EXAMPLES,
        help=f"기출 예문 JSON 경로 (기본: {DEFAULT_EXAMPLES.relative_to(PROJECT_ROOT)})",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"출력 JSON 경로 (기본: {DEFAULT_OUTPUT.relative_to(PROJECT_ROOT)})",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    # ── 단어장 로드 ──────────────────────────────────────────────────────────
    vocab_data = load_json(args.vocab)
    if vocab_data is None:
        print(f"[ERROR] 단어장 파일을 찾을 수 없습니다: {args.vocab}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(vocab_data, list):
        print("[ERROR] 단어장 JSON은 배열이어야 합니다.", file=sys.stderr)
        sys.exit(1)
    print(f"[INFO] 단어장 로드 완료: {len(vocab_data)}개 단어")

    # ── 기출 예문 로드 ───────────────────────────────────────────────────────
    ets_raw = load_json(args.examples)
    if ets_raw is None:
        print(f"[INFO] 기출 예문 파일 없음 ({args.examples.name}). 예문 없이 생성합니다.")
        ets_by_word: dict[str, dict] = {}
    elif isinstance(ets_raw, dict):
        ets_by_word = {k.lower(): v for k, v in ets_raw.items()}
        print(f"[INFO] 기출 예문 로드 완료: {len(ets_by_word)}개 단어")
    else:
        print("[WARN] 기출 예문 JSON이 딕셔너리가 아닙니다. 예문 없이 진행합니다.")
        ets_by_word = {}

    # ── 카드 생성 ────────────────────────────────────────────────────────────
    cards: list[dict] = []
    matched_count = 0

    for entry in vocab_data:
        word_lower = (entry.get("word") or "").lower()
        ets_entry = ets_by_word.get(word_lower)

        card = build_card(entry, ets_entry)
        cards.append(card)

        if card["ets_count"] > 0:
            matched_count += 1

    # ── Day, word 기준 정렬 ──────────────────────────────────────────────────
    def sort_key(c: dict):
        try:
            day = int(c.get("day") or 0)
        except (ValueError, TypeError):
            day = 0
        return (day, (c.get("word") or "").lower())

    cards.sort(key=sort_key)

    # ── 출력 ─────────────────────────────────────────────────────────────────
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        json.dump(cards, f, ensure_ascii=False, indent=2)

    # ── 통계 출력 ────────────────────────────────────────────────────────────
    total = len(cards)
    no_examples = total - matched_count
    total_examples = sum(len(c["examples"]) for c in cards)

    print(f"\n{'='*50}")
    print(f"  출력 파일      : {args.output}")
    print(f"  총 카드 수     : {total}")
    print(f"  기출 매핑 있음 : {matched_count}")
    print(f"  기출 매핑 없음 : {no_examples}")
    print(f"  총 예문 수     : {total_examples}")
    print(f"{'='*50}")

    # 레벨별 분포
    level_counts: dict[str, int] = {}
    for c in cards:
        level = c.get("level") or "미지정"
        level_counts[level] = level_counts.get(level, 0) + 1

    print("\n  레벨별 분포:")
    for level in sorted(level_counts):
        print(f"    {level:<10} {level_counts[level]:>5}개")

    # Day별 카드 수
    day_counts: dict[int, int] = {}
    for c in cards:
        try:
            day = int(c.get("day") or 0)
        except (ValueError, TypeError):
            day = 0
        day_counts[day] = day_counts.get(day, 0) + 1

    print(f"\n  Day 범위: Day {min(day_counts)}-{max(day_counts)} ({len(day_counts)}개 Day)")
    print()


if __name__ == "__main__":
    main()
