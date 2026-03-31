"""
Part5 explanation 필드 분리 마이그레이션

기존 combined explanation 필드를 explanation, translation, vocabulary 세 필드로 분리한다.

기존 형식:
  "explanation": "해설...\n[번역] 번역...\n[어휘] 어휘..."

변환 후:
  "explanation": "해설...",
  "translation": "번역...",
  "vocabulary": "어휘..."
"""

import json
import re
from pathlib import Path


def split_explanation(text: str) -> dict:
    """explanation 문자열을 세 부분으로 분리한다."""
    explanation = text
    translation = ""
    vocabulary = ""

    # [어휘] 분리 (먼저 처리 — [번역] 뒤에 올 수도 있으므로)
    vocab_match = re.split(r"\n?\[어휘\]\s*", explanation, maxsplit=1)
    if len(vocab_match) == 2:
        explanation = vocab_match[0]
        vocabulary = vocab_match[1].strip()

    # [번역] 분리
    trans_match = re.split(r"\n?\[번역\]\s*", explanation, maxsplit=1)
    if len(trans_match) == 2:
        explanation = trans_match[0]
        translation = trans_match[1].strip()

    return {
        "explanation": explanation.strip(),
        "translation": translation,
        "vocabulary": vocabulary,
    }


def migrate_file(filepath: Path) -> dict:
    """단일 파일을 마이그레이션하고 통계를 반환한다."""
    with open(filepath, "r", encoding="utf-8") as f:
        questions = json.load(f)

    migrated = 0
    skipped = 0
    no_markers = 0

    for q in questions:
        # 이미 분리된 경우 스킵
        if "translation" in q and "vocabulary" in q:
            skipped += 1
            continue

        raw = q.get("explanation", "")
        if "[번역]" not in raw and "[어휘]" not in raw:
            no_markers += 1
            continue

        parts = split_explanation(raw)
        q["explanation"] = parts["explanation"]
        q["translation"] = parts["translation"]
        q["vocabulary"] = parts["vocabulary"]
        migrated += 1

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(questions, f, ensure_ascii=False, indent=2)

    return {
        "total": len(questions),
        "migrated": migrated,
        "skipped": skipped,
        "no_markers": no_markers,
    }


def main():
    base = Path(__file__).resolve().parent.parent.parent / "data" / "processed" / "questions"
    files = sorted(base.glob("vol*_part5.json"))

    if not files:
        print("No vol*_part5.json files found.")
        return

    print(f"Found {len(files)} file(s) to process.\n")

    grand_total = 0
    grand_migrated = 0

    for fp in files:
        stats = migrate_file(fp)
        grand_total += stats["total"]
        grand_migrated += stats["migrated"]
        print(f"{fp.name}:")
        print(f"  Total questions: {stats['total']}")
        print(f"  Migrated:        {stats['migrated']}")
        print(f"  Skipped (already done): {stats['skipped']}")
        print(f"  No markers:      {stats['no_markers']}")
        print()

    print(f"=== Grand total: {grand_migrated}/{grand_total} questions migrated ===")


if __name__ == "__main__":
    main()
