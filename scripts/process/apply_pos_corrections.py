"""모든 corrections 파일을 합쳐 vocab day JSON 파일에 적용."""
import json
import glob
from pathlib import Path
from collections import Counter

BASE = Path("C:/Data/Toeic Brain/data/processed/vocab")

# 1. corrections 병합
corrections = {}
for cf in sorted(BASE.glob("_corrections_*.json")):
    with open(cf, encoding="utf-8") as f:
        corrections.update(json.load(f))
print(f"총 corrections: {len(corrections)}개")

# 2. day 파일 로드 및 적용
valid_pos = {"noun","verb","adjective","adverb","preposition","conjunction"}
stats = {"updated": 0, "unchanged": 0, "missing": 0}

file_map = {}
for path in sorted(BASE.glob("day*.json")):
    with open(path, encoding="utf-8") as f:
        words = json.load(f)
    file_map[path] = words

for path, words in file_map.items():
    for w in words:
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
for path, words in file_map.items():
    with open(path, "w", encoding="utf-8") as f:
        json.dump(words, f, ensure_ascii=False, indent=2)

# 4. all_vocab.json 재생성
all_words = []
for words in file_map.values():
    all_words.extend(words)
all_words.sort(key=lambda w: w["id"])
with open(BASE / "all_vocab.json", "w", encoding="utf-8") as f:
    json.dump(all_words, f, ensure_ascii=False, indent=2)

print(f"변경: {stats['updated']}개 | 유지(리스트변환): {stats['unchanged']}개 | 미처리: {stats['missing']}개")

# 5. 검증: demand 확인
for w in all_words:
    if w["word"] == "demand":
        print(f"[검증] demand → pos: {w['pos']}")
        break

# 6. 새 품사 분포
all_pos = []
for w in all_words:
    p = w.get("pos", [])
    if isinstance(p, list):
        all_pos.extend(p)
    else:
        all_pos.append(p)
print("품사 분포:", Counter(all_pos).most_common())
print("멀티품사 단어 수:", sum(1 for w in all_words if isinstance(w.get("pos"), list) and len(w["pos"]) > 1))
