"""모든 corrections 파일을 합쳐 hackers_vocab.json에 적용."""
import json
from pathlib import Path
from collections import Counter

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BASE = PROJECT_ROOT / "data" / "json"

# 1. corrections 병합
corrections = {}
for cf in sorted(BASE.glob("_corrections_*.json")):
    with open(cf, encoding="utf-8") as f:
        corrections.update(json.load(f))
print(f"총 corrections: {len(corrections)}개")

# 2. hackers_vocab.json 로드 및 적용
valid_pos = {"noun","verb","adjective","adverb","preposition","conjunction"}
stats = {"updated": 0, "unchanged": 0, "missing": 0}

vocab_path = BASE / "hackers_vocab.json"
with open(vocab_path, encoding="utf-8") as f:
    all_words = json.load(f)

for w in all_words:
    wid = w["id"]
    if wid not in corrections:
        stats["missing"] += 1
        continue
    new_pos = [p for p in corrections[wid] if p in valid_pos]
    if not new_pos:
        stats["missing"] += 1
        continue
    old = w.get("pos")
    old_set = set(old) if isinstance(old, list) else {old} if isinstance(old, str) else set()
    if set(new_pos) != old_set:
        w["pos"] = new_pos
        stats["updated"] += 1
    else:
        w["pos"] = new_pos  # 리스트로 통일
        stats["unchanged"] += 1

# 3. 저장
all_words.sort(key=lambda w: w["id"])
with open(vocab_path, "w", encoding="utf-8") as f:
    json.dump(all_words, f, ensure_ascii=False, indent=2)

print(f"변경: {stats['updated']}개 | 유지(리스트변환): {stats['unchanged']}개 | 미처리: {stats['missing']}개")

# 4. 검증: demand 확인
for w in all_words:
    if w["word"] == "demand":
        print(f"[검증] demand → pos: {w['pos']}")
        break

# 5. 새 품사 분포
all_pos = []
for w in all_words:
    p = w.get("pos", [])
    if isinstance(p, list):
        all_pos.extend(p)
    else:
        all_pos.append(p)
print("품사 분포:", Counter(all_pos).most_common())
print("멀티품사 단어 수:", sum(1 for w in all_words if isinstance(w.get("pos"), list) and len(w["pos"]) > 1))
