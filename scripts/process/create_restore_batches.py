"""
OCR 복원 배치 파일 생성기

규칙 기반 수정 후에도 남은 깨진 문장들을 추출하여
AI 에이전트가 처리할 수 있는 배치 JSON 파일로 저장.

사용법:
  py scripts/process/create_restore_batches.py
  # 결과: data/json/restore_batches/batch_001.json, ...
"""

import json
import re
from pathlib import Path
import sys

BASE_DIR = Path(__file__).parent.parent.parent
INPUT_FILE = BASE_DIR / "data" / "json" / "word_ets_examples.json"
BATCHES_DIR = BASE_DIR / "data" / "json" / "restore_batches"
BATCHES_DIR.mkdir(exist_ok=True)

# OCR 오류 감지 정규식
RE_KOREAN    = re.compile(r'[\uac00-\ud7af\u1100-\u11ff\u3130-\u318f]')
RE_CJK       = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf]')
RE_UI_SYMBOLS = re.compile(r'[▼▲☐☑✓✔◆●◀►★☆□■]')
RE_LINE_DRAW  = re.compile(r'[─│├┤═║┌┐└┘]')


def has_ocr_error(sentence: str) -> bool:
    if RE_KOREAN.search(sentence): return True
    if RE_CJK.search(sentence): return True
    if RE_UI_SYMBOLS.search(sentence): return True
    if RE_LINE_DRAW.search(sentence): return True
    if re.search(r'[^\w\s\.,;:!?\'"()\-/\[\]@#%&*+]{3,}', sentence): return True
    return False


def main():
    print(f"로딩: {INPUT_FILE}")
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    total_words = len(data)
    print(f"전체 단어: {total_words:,}")

    # 깨진 문장 수집
    broken = []
    for word, entry in data.items():
        for ex_idx, ex in enumerate(entry.get('examples', [])):
            sentence = ex.get('sentence', '')
            if sentence and has_ocr_error(sentence):
                broken.append({
                    'word': word,
                    'ex_idx': ex_idx,
                    'sentence': sentence[:300],  # 너무 긴 문장은 자름
                    'source': ex.get('source', ''),
                })

    total_broken = len(broken)
    print(f"OCR 오류 예문: {total_broken:,}")

    # 배치 크기: 에이전트당 80개 (컨텍스트 고려)
    BATCH_SIZE = 80
    num_batches = (total_broken + BATCH_SIZE - 1) // BATCH_SIZE
    print(f"배치 수: {num_batches} (배치 크기: {BATCH_SIZE})")

    # 기존 배치 파일 삭제
    for f in BATCHES_DIR.glob("batch_*.json"):
        f.unlink()

    # 배치 파일 생성
    for i in range(num_batches):
        batch = broken[i * BATCH_SIZE:(i + 1) * BATCH_SIZE]
        out_path = BATCHES_DIR / f"batch_{i+1:04d}.json"
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump({
                'batch_id': i + 1,
                'total_batches': num_batches,
                'count': len(batch),
                'items': batch,
                'done': False,  # 처리 완료 여부
            }, f, ensure_ascii=False, indent=2)

    print(f"\n배치 파일 생성 완료: {BATCHES_DIR}")
    print(f"총 {num_batches}개 파일")

    # 진행 인덱스 파일 생성
    index = {
        'total_batches': num_batches,
        'total_sentences': total_broken,
        'batch_size': BATCH_SIZE,
        'completed': [],
    }
    with open(BATCHES_DIR / 'index.json', 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print("인덱스 파일 생성: index.json")


if __name__ == '__main__':
    main()
