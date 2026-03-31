"""
build_part5_cards.py
====================
ETS 기출 Part5 문제 JSON 파일(vol1~5)을 읽어 단일 Anki 카드 데이터 JSON으로 통합한다.

출력: data/anki/part5_cards.json

Usage
-----
  python build_part5_cards.py
  python build_part5_cards.py --input-dir path/to/questions
  python build_part5_cards.py --output path/to/output.json
"""

import sys

sys.stdout.reconfigure(encoding="utf-8")

import argparse
import json
from collections import defaultdict
from pathlib import Path

# ── Project root ─────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# ── 기본 경로 ────────────────────────────────────────────────────────────────
DEFAULT_INPUT_DIR = PROJECT_ROOT / "data" / "json" / "questions"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "anki" / "part5_cards.json"


# ── Helpers ──────────────────────────────────────────────────────────────────

def load_questions(input_dir: Path) -> list[dict]:
    """vol*_part5.json 파일들을 읽어 Part5 문제만 필터링하여 반환한다."""
    pattern = "vol*_part5.json"
    files = sorted(input_dir.glob(pattern))

    if not files:
        print(f"[WARN] '{input_dir / pattern}'에 해당하는 파일이 없습니다.")
        return []

    questions: list[dict] = []

    for filepath in files:
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"[WARN] JSON 파싱 실패 '{filepath.name}': {exc}")
            continue
        except OSError as exc:
            print(f"[WARN] 파일 읽기 실패 '{filepath.name}': {exc}")
            continue

        if not isinstance(data, list):
            print(f"[WARN] '{filepath.name}'의 데이터가 배열이 아닙니다. 건너뜁니다.")
            continue

        # Part5만 필터링
        part5 = [q for q in data if q.get("part") == 5]
        skipped = len(data) - len(part5)
        if skipped:
            print(f"  [{filepath.name}] Part5 외 {skipped}문항 제외")
        print(f"  [{filepath.name}] {len(part5)}문항 로드")
        questions.extend(part5)

    return questions


def build_card(q: dict) -> dict:
    """문제 데이터에서 카드 데이터를 생성한다."""
    card: dict = {
        "id": q.get("id", ""),
        "volume": q.get("volume"),
        "test": q.get("test"),
        "question_number": q.get("question_number"),
        "sentence": q.get("sentence", ""),
        "choices": q.get("choices", {}),
        "answer": q.get("answer", ""),
        "category": q.get("category", ""),
    }

    # 선택적 필드: 있으면 포함
    for field in ("explanation", "translation", "vocabulary"):
        value = q.get(field)
        if value is not None:
            card[field] = value

    return card


# ── Main ─────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    """커맨드라인 인자를 파싱한다."""
    p = argparse.ArgumentParser(
        description="ETS 기출 Part5 문제를 단일 Anki 카드 JSON으로 통합한다.",
    )
    p.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help=f"문제 JSON 디렉토리 (기본: {DEFAULT_INPUT_DIR.relative_to(PROJECT_ROOT)})",
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

    # ── 문제 로드 ────────────────────────────────────────────────────────────
    print(f"Part5 문제 로드 중: {args.input_dir}")
    questions = load_questions(args.input_dir)

    if not questions:
        print("[ERROR] 유효한 Part5 문제가 없습니다.", file=sys.stderr)
        sys.exit(1)

    # ── 카드 생성 ────────────────────────────────────────────────────────────
    cards: list[dict] = []
    for q in questions:
        cards.append(build_card(q))

    # ── volume → test → question_number 순 정렬 ─────────────────────────────
    def sort_key(c: dict):
        try:
            vol = int(c.get("volume") or 0)
        except (TypeError, ValueError):
            vol = 0
        try:
            test = int(c.get("test") or 0)
        except (TypeError, ValueError):
            test = 0
        try:
            qnum = int(c.get("question_number") or 0)
        except (TypeError, ValueError):
            qnum = 0
        return (vol, test, qnum)

    cards.sort(key=sort_key)

    # ── 출력 ─────────────────────────────────────────────────────────────────
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        json.dump(cards, f, ensure_ascii=False, indent=2)

    # ── 통계 출력 ────────────────────────────────────────────────────────────
    total = len(cards)

    print(f"\n{'='*50}")
    print(f"  출력 파일    : {args.output}")
    print(f"  총 카드 수   : {total}")
    print(f"{'='*50}")

    # 권별 분포
    vol_counts: defaultdict[str, int] = defaultdict(int)
    for c in cards:
        vol_counts[str(c.get("volume", "?"))] += 1

    print("\n  권별 분포:")
    for vol in sorted(vol_counts):
        print(f"    Vol.{vol}: {vol_counts[vol]}문항")

    # 카테고리 분포
    cat_counts: defaultdict[str, int] = defaultdict(int)
    for c in cards:
        cat = c.get("category") or "미분류"
        cat_counts[cat] += 1

    print("\n  카테고리 분포:")
    for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
        print(f"    {cat:<25} {count:>4}문항")

    # explanation 유무
    with_explanation = sum(1 for c in cards if c.get("explanation"))
    with_translation = sum(1 for c in cards if c.get("translation"))
    with_vocabulary = sum(1 for c in cards if c.get("vocabulary"))

    print(f"\n  해설 있음    : {with_explanation}/{total}")
    print(f"  번역 있음    : {with_translation}/{total}")
    print(f"  어휘 있음    : {with_vocabulary}/{total}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
