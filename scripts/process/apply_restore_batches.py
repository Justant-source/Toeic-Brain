"""
AI 에이전트가 복원한 배치 결과를 메인 JSON에 적용하는 스크립트

사용법:
  py scripts/process/apply_restore_batches.py

결과 파일 형식 (batch_XXXX_result.json):
  {
    "batch_id": 1,
    "items": [
      {"word": "resume", "ex_idx": 0, "restored": "복원된 문장"},
      ...
    ]
  }
"""

import json
from pathlib import Path
import sys

BASE_DIR = Path(__file__).parent.parent.parent
INPUT_FILE = BASE_DIR / "data" / "json" / "word_ets_examples.json"
BATCHES_DIR = BASE_DIR / "data" / "json" / "restore_batches"


def main():
    # 결과 파일 찾기
    result_files = sorted(BATCHES_DIR.glob("batch_*_result.json"))
    if not result_files:
        print("결과 파일 없음. AI 에이전트가 배치를 처리해야 합니다.")
        sys.exit(1)

    print(f"결과 파일 {len(result_files)}개 발견")

    # 메인 데이터 로드
    print(f"데이터 로딩: {INPUT_FILE}")
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    stats = {'applied': 0, 'empty': 0, 'error': 0}

    for result_file in result_files:
        with open(result_file, 'r', encoding='utf-8') as f:
            result = json.load(f)

        for item in result.get('items', []):
            word = item.get('word')
            ex_idx = item.get('ex_idx')
            restored = item.get('restored', '').strip()

            if not word or ex_idx is None:
                stats['error'] += 1
                continue

            if not restored:
                stats['empty'] += 1
                continue

            entry = data.get(word)
            if not entry:
                stats['error'] += 1
                continue

            examples = entry.get('examples', [])
            if ex_idx >= len(examples):
                stats['error'] += 1
                continue

            data[word]['examples'][ex_idx]['sentence'] = restored
            stats['applied'] += 1

    # 저장
    with open(INPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n=== 적용 완료 ===")
    print(f"  적용됨:     {stats['applied']:,}")
    print(f"  빈 결과:    {stats['empty']:,}")
    print(f"  오류:       {stats['error']:,}")
    print(f"저장: {INPUT_FILE}")


if __name__ == '__main__':
    main()
