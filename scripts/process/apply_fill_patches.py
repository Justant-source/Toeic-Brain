"""
fill_patches_vol{N}.json 패치를 word_ets_examples.json 에 적용하고 Anki 덱을 재생성한다.

Usage:
  py -3 scripts/process/apply_fill_patches.py
  py -3 scripts/process/apply_fill_patches.py --no-regen
"""

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
JSON_DIR     = PROJECT_ROOT / "data" / "json"
ETS_EXAMPLES = JSON_DIR / "word_ets_examples.json"
VOCAB_FILE   = JSON_DIR / "hackers_vocab.json"
ANKI_SCRIPT  = PROJECT_ROOT / "scripts" / "anki" / "generate_vocab_deck.py"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--no-regen", action="store_true")
    args = p.parse_args()

    ets_data: dict = json.loads(ETS_EXAMPLES.read_text(encoding="utf-8"))
    print(f"  Loaded {len(ets_data):,} words")

    patch_files = sorted(JSON_DIR.glob("fill_patches_vol*.json"))
    if not patch_files:
        print("[ERROR] fill_patches_vol*.json 파일이 없습니다.")
        sys.exit(1)

    total_applied = 0
    total_unfilled_removed = 0

    for pf in patch_files:
        patches: dict = json.loads(pf.read_text(encoding="utf-8"))
        applied = 0

        for word, patch_list in patches.items():
            if word not in ets_data:
                continue
            examples = ets_data[word].get("examples") or []
            for patch in patch_list:
                idx = patch["idx"]
                new_sent = patch["new_sentence"]
                if idx < len(examples):
                    examples[idx]["sentence"] = new_sent
                    applied += 1

        total_applied += applied
        print(f"  {pf.name}: {applied:,} sentences updated")

    # Remove any remaining examples that still have ------- (unfillable)
    BLANK = "-------"
    for word, entry in ets_data.items():
        examples = entry.get("examples") or []
        kept = [ex for ex in examples if BLANK not in ex.get("sentence", "")]
        removed = len(examples) - len(kept)
        if removed > 0:
            entry["examples"] = kept
            entry["total_count"] = len(kept)
            total_unfilled_removed += removed

    # Recount total_count
    for entry in ets_data.values():
        entry["total_count"] = len(entry.get("examples") or [])

    print(f"\n  ── 적용 결과 ──────────────────────────────────")
    print(f"  채워진 빈칸       : {total_applied:,}")
    print(f"  미매칭 예문 제거  : {total_unfilled_removed:,}")

    words_with_ex = sum(1 for v in ets_data.values() if v.get("total_count", 0) > 0)
    total_ex = sum(v.get("total_count", 0) for v in ets_data.values())
    print(f"  예문 있는 단어    : {words_with_ex:,}")
    print(f"  총 예문 수        : {total_ex:,}")

    ETS_EXAMPLES.write_text(json.dumps(ets_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  저장 → {ETS_EXAMPLES}")

    if not args.no_regen:
        print("\n  Anki 덱 재생성 중...")
        subprocess.run([sys.executable, str(ANKI_SCRIPT), "--vocab", str(VOCAB_FILE)])
        print("  완료")


if __name__ == "__main__":
    main()
