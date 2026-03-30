"""
ocr_examples_vol{N}.json 파일들을 word_ets_examples.json 과 병합하고
Anki 덱을 재생성한다.

Usage:
  py -3 scripts/process/merge_ocr_examples.py
  py -3 scripts/process/merge_ocr_examples.py --no-regen   # Anki 재생성 건너뜀
"""

import re
import json
import sys
import argparse
import subprocess
import logging
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MAPPED_DIR   = PROJECT_ROOT / "data" / "mapped"
ETS_EXAMPLES = MAPPED_DIR / "word_ets_examples.json"
VOCAB_FILE   = PROJECT_ROOT / "data" / "processed" / "vocab" / "all_vocab.json"
ANKI_SCRIPT  = PROJECT_ROOT / "scripts" / "anki" / "generate_vocab_deck.py"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def dedup_examples(examples: list[dict]) -> list[dict]:
    seen: set[str] = set()
    result: list[dict] = []
    for ex in examples:
        key = re.sub(r"\s+", " ", ex.get("sentence", "")).strip().lower()
        key = re.sub(r"\*\*", "", key)
        if key and key not in seen:
            seen.add(key)
            result.append(ex)
    return result


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--no-regen", action="store_true", help="Anki 덱 재생성 건너뜀")
    args = p.parse_args()

    # Load existing word_ets_examples.json
    if ETS_EXAMPLES.exists():
        base: dict = json.loads(ETS_EXAMPLES.read_text(encoding="utf-8"))
        print(f"  기존 word_ets_examples.json: {len(base):,} entries")
    else:
        base = {}
        print("  word_ets_examples.json 없음 — 새로 생성")

    # Load vocab to get canonical word → id mapping
    vocab = json.loads(VOCAB_FILE.read_text(encoding="utf-8"))
    word_to_canonical: dict[str, str] = {}  # lowercase → original casing
    word_to_id: dict[str, str] = {}
    for entry in vocab:
        w = (entry.get("word") or "").strip()
        if w:
            wl = w.lower()
            if wl not in word_to_canonical:
                word_to_canonical[wl] = w
                word_to_id[wl] = entry.get("id") or wl

    # Merge each vol file
    new_examples_total = 0
    vol_files = sorted(MAPPED_DIR.glob("ocr_examples_vol*.json"))
    if not vol_files:
        print("[ERROR] ocr_examples_vol*.json 파일이 없습니다. find_examples_from_ocr_cache.py 를 먼저 실행하세요.")
        sys.exit(1)

    print(f"  병합할 파일: {[f.name for f in vol_files]}")

    for vol_file in vol_files:
        vol_data: dict = json.loads(vol_file.read_text(encoding="utf-8"))
        added = 0
        for word_key, vol_entry in vol_data.items():
            canonical = word_to_canonical.get(word_key, word_key)
            new_exs = vol_entry.get("examples") or []
            if not new_exs:
                continue

            if canonical not in base:
                # New word entry
                base[canonical] = {
                    "vocab_id": word_to_id.get(word_key, ""),
                    "chapter": None,
                    "total_count": 0,
                    "examples": [],
                    "parts_appeared": [],
                }

            existing_exs = base[canonical].get("examples") or []
            before = len(existing_exs)
            merged = dedup_examples(existing_exs + new_exs)
            base[canonical]["examples"] = merged
            base[canonical]["total_count"] = len(merged)

            # Update parts_appeared
            parts = set(base[canonical].get("parts_appeared") or [])
            for ex in new_exs:
                if ex.get("part"):
                    parts.add(ex["part"])
            base[canonical]["parts_appeared"] = sorted(parts)

            added += len(merged) - before

        new_examples_total += added
        print(f"  {vol_file.name}: +{added:,} 새 예문 추가")

    # Re-sort all examples
    for word, entry in base.items():
        entry["examples"].sort(key=lambda e: (
            e.get("volume", 0),
            e.get("page", 0) or (e.get("test", 0) * 1000 + (e.get("question_number") or 0)),
        ))
        entry["total_count"] = len(entry["examples"])

    # Save merged file
    ETS_EXAMPLES.write_text(
        json.dumps(base, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    words_with_ex = sum(1 for v in base.values() if v["total_count"] > 0)
    total_ex = sum(v["total_count"] for v in base.values())
    vocab_total = len(vocab)
    coverage = words_with_ex / vocab_total * 100 if vocab_total else 0

    print(f"\n  ── 병합 결과 ──────────────────────────────────")
    print(f"  전체 단어 수       : {vocab_total:,}")
    print(f"  예문 있는 단어     : {words_with_ex:,}  ({coverage:.1f}%)")
    print(f"  총 예문 수         : {total_ex:,}")
    print(f"  새로 추가된 예문   : {new_examples_total:,}")
    print(f"  저장 → {ETS_EXAMPLES}")

    if not args.no_regen:
        print(f"\n  Anki 덱 재생성 중...")
        result = subprocess.run(
            [sys.executable, str(ANKI_SCRIPT), "--vocab", str(VOCAB_FILE)],
            capture_output=False,
            text=True,
        )
        if result.returncode != 0:
            print(f"  [ERROR] Anki 재생성 실패 (exit code {result.returncode})")
        else:
            print(f"  Anki 덱 재생성 완료")


if __name__ == "__main__":
    main()
