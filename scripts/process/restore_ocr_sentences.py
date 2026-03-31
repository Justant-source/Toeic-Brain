"""
OCR 실패 예문 복원 스크립트

사용법:
  # 전체 처리 (단일 실행)
  py scripts/process/restore_ocr_sentences.py

  # 병렬 실행 (멀티 에이전트용) - 단어 인덱스 범위 지정
  py scripts/process/restore_ocr_sentences.py --start 0 --end 700
  py scripts/process/restore_ocr_sentences.py --start 700 --end 1400
  ...

  # 최종 병합 (병렬 실행 완료 후)
  py scripts/process/restore_ocr_sentences.py --merge

처리 흐름:
  1. 규칙 기반 자동 수정 (斤→fr, 한글 잘라내기, UI기호 제거 등)
  2. Claude API 기반 AI 재구성 (나머지 깨진 문장들)
  3. 배치마다 진행 저장
"""

import json
import re
import sys
import os
import argparse
import time
from pathlib import Path
from typing import Optional
import anthropic

# ─────────────────────────────────────────────
# 경로 설정
# ─────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent.parent
INPUT_FILE  = BASE_DIR / "data/mapped/word_ets_examples.json"
BACKUP_FILE = BASE_DIR / "data/mapped/word_ets_examples.backup.json"
PROGRESS_DIR = BASE_DIR / "data/mapped/restore_progress"

PROGRESS_DIR.mkdir(exist_ok=True)

# ─────────────────────────────────────────────
# OCR 오류 감지
# ─────────────────────────────────────────────
RE_KOREAN    = re.compile(r'[\uac00-\ud7af\u1100-\u11ff\u3130-\u318f]')
RE_CJK       = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf\u3000-\u303f]')
RE_UI_SYMBOLS = re.compile(r'[▼▲☐☑✓✔◆●◀►★☆□■▪▫]')
RE_LINE_DRAW  = re.compile(r'[─│├┤═║┌┐└┘╔╗╚╝┼]')
RE_CTRL_CHARS = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]')

KNOWN_CJK_MAP = {
    # 斤 → fr (가장 흔한 패턴)
    '斤om': 'from',  '斤ee': 'free',  '斤esh': 'fresh',
    '斤ozen': 'frozen', '斤ont': 'front', '斤equent': 'frequent',
    '斤equently': 'frequently', '斤ame': 'frame', '斤agile': 'fragile',
    '斤aud': 'fraud', '斤acture': 'fracture',
    # 一 → - (수평선/하이픈)
    # 이건 문맥상 복잡해서 특정 패턴만 처리
}

def has_ocr_error(sentence: str) -> bool:
    """OCR 오류가 있는 문장 감지."""
    if RE_KOREAN.search(sentence):
        return True
    if RE_CJK.search(sentence):
        return True
    if RE_UI_SYMBOLS.search(sentence):
        return True
    if RE_LINE_DRAW.search(sentence):
        return True
    if RE_CTRL_CHARS.search(sentence):
        return True
    # 연속 특수문자 3개 이상
    if re.search(r'[^\w\s\.,;:!?\'"()\-/]{3,}', sentence):
        return True
    return False

# ─────────────────────────────────────────────
# 규칙 기반 수정 (Phase 1)
# ─────────────────────────────────────────────

def apply_rule_fixes(sentence: str) -> str:
    """알려진 패턴으로 수정 가능한 케이스 처리."""
    result = sentence

    # 1. 알려진 CJK 치환 패턴 복원
    for wrong, correct in KNOWN_CJK_MAP.items():
        result = result.replace(wrong, correct)

    # 2. 나머지 斤X 패턴 → frX (斤 다음에 소문자가 오는 경우)
    result = re.sub(r'斤([a-z])', r'fr\1', result)

    # 3. UI 기호 제거 (체크박스, 화살표 등)
    result = RE_UI_SYMBOLS.sub('', result)
    result = RE_LINE_DRAW.sub('', result)
    result = RE_CTRL_CHARS.sub('', result)

    # 4. 한글이 포함된 경우 → 한글 이전 영어 부분만 추출
    if RE_KOREAN.search(result):
        result = extract_english_before_korean(result)

    # 5. 나머지 CJK 문자 (한자 등) - 문장 내 CJK 블록 제거 시도
    if RE_CJK.search(result):
        result = remove_cjk_blocks(result)

    # 6. 연속 공백 정규화
    result = re.sub(r'  +', ' ', result).strip()

    # 7. 문장 끝 특수문자 정리
    result = re.sub(r'[\s\-_=\.]{3,}$', '.', result)
    result = result.strip()

    return result


def extract_english_before_korean(sentence: str) -> str:
    """한글 이전의 영어 부분을 추출."""
    # 한글이 처음 나오는 위치 찾기
    match = RE_KOREAN.search(sentence)
    if not match:
        return sentence

    english_part = sentence[:match.start()].strip()

    # 영어 부분이 너무 짧으면 (<= 15자) 의미없는 조각
    if len(english_part) <= 15:
        return ""

    # 마지막 완전한 문장까지만 사용
    # 마침표/느낌표/물음표로 끝나는 위치 찾기
    last_punct = max(
        english_part.rfind('.'),
        english_part.rfind('!'),
        english_part.rfind('?'),
    )

    if last_punct > len(english_part) * 0.4:
        return english_part[:last_punct + 1].strip()

    return english_part.strip()


def remove_cjk_blocks(sentence: str) -> str:
    """연속된 CJK 블록 제거 (영어 단어들 사이의 CJK는 보존 시도)."""
    # CJK 문자 하나씩 제거 (영어 문장 내 삽입된 경우)
    result = RE_CJK.sub('', sentence)
    result = re.sub(r'  +', ' ', result).strip()
    return result

# ─────────────────────────────────────────────
# AI 기반 복원 (Phase 2) — Claude API 사용
# ─────────────────────────────────────────────

def build_ai_prompt(batch: list[dict]) -> str:
    """Claude에게 보낼 복원 요청 프롬프트 생성."""
    lines = []
    for i, item in enumerate(batch):
        lines.append(f"{i+1}. 단어: {item['word']} | 깨진문장: {item['sentence']}")

    prompt = f"""당신은 TOEIC 교재 전문가입니다.
아래는 OCR 인식 오류로 깨진 TOEIC 기출 예문들입니다.
각 예문을 문맥과 해당 단어를 고려하여 올바른 영어 문장으로 복원해주세요.

규칙:
- TOEIC RC 시험에 등장하는 비즈니스/일상 영어 문장으로 복원
- 해당 단어(word)가 자연스럽게 포함되어야 함
- 복원 불가능한 경우 빈 문자열("") 반환
- 반드시 JSON 배열 형식으로만 응답 (다른 텍스트 없이)
- 형식: [{{"idx": 1, "restored": "복원된 문장"}}, ...]

깨진 예문 목록:
{chr(10).join(lines)}

JSON 응답:"""
    return prompt


def ai_restore_batch(client: anthropic.Anthropic, batch: list[dict]) -> dict[str, str]:
    """Claude API를 통해 배치 복원. {sentence_key: restored_text} 반환."""
    if not batch:
        return {}

    prompt = build_ai_prompt(batch)

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        )
        text = response.content[0].text.strip()

        # JSON 파싱
        # ```json ... ``` 블록이 있으면 제거
        text = re.sub(r'^```(?:json)?\n?', '', text)
        text = re.sub(r'\n?```$', '', text)

        results_raw = json.loads(text)
        results = {}
        for item in results_raw:
            idx = item.get('idx', 0) - 1
            if 0 <= idx < len(batch):
                key = batch[idx]['_key']
                results[key] = item.get('restored', '').strip()
        return results

    except Exception as e:
        print(f"  [AI 오류] {e}", file=sys.stderr)
        return {}

# ─────────────────────────────────────────────
# 진행 상황 관리
# ─────────────────────────────────────────────

def load_progress(start: int, end: int) -> set:
    """처리 완료된 단어 목록 로드."""
    path = PROGRESS_DIR / f"done_{start}_{end}.json"
    if path.exists():
        with open(path, 'r', encoding='utf-8') as f:
            return set(json.load(f))
    return set()


def save_progress(done_words: set, start: int, end: int):
    """처리 완료된 단어 목록 저장."""
    path = PROGRESS_DIR / f"done_{start}_{end}.json"
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(list(done_words), f, ensure_ascii=False)


def load_data() -> dict:
    """메인 데이터 로드."""
    print(f"데이터 로딩: {INPUT_FILE}")
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_data(data: dict):
    """메인 데이터 저장."""
    with open(INPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"저장 완료: {INPUT_FILE}")

# ─────────────────────────────────────────────
# 메인 처리 로직
# ─────────────────────────────────────────────

def process_range(start: int, end: int, use_ai: bool = True,
                  ai_batch_size: int = 50, save_every: int = 200):
    """
    지정된 단어 인덱스 범위를 처리.
    start, end: word 목록의 슬라이스 인덱스
    """
    data = load_data()
    words = list(data.keys())
    total_words = len(words)

    end = min(end, total_words)
    target_words = words[start:end]

    print(f"처리 범위: {start}~{end} ({len(target_words)}개 단어 / 전체 {total_words}개)")

    # 이미 처리된 단어 로드
    done_words = load_progress(start, end)
    print(f"이미 완료: {len(done_words)}개 단어")

    # Claude API 클라이언트
    client = anthropic.Anthropic() if use_ai else None

    stats = {'rule_fixed': 0, 'ai_fixed': 0, 'unrestorable': 0, 'clean': 0}
    modified_count = 0
    ai_pending = []  # AI 처리 대기 배치

    def flush_ai_batch():
        """대기중인 AI 배치 처리."""
        nonlocal modified_count
        if not ai_pending or not client:
            ai_pending.clear()
            return
        print(f"  [AI] {len(ai_pending)}개 문장 복원 중...")
        results = ai_restore_batch(client, ai_pending)
        for item in ai_pending:
            restored = results.get(item['_key'], '')
            if restored:
                # 데이터에 반영
                word = item['word']
                ex_idx = item['ex_idx']
                data[word]['examples'][ex_idx]['sentence'] = restored
                stats['ai_fixed'] += 1
                modified_count += 1
            else:
                stats['unrestorable'] += 1
        ai_pending.clear()

    for i, word in enumerate(target_words):
        if word in done_words:
            continue

        entry = data.get(word, {})
        examples = entry.get('examples', [])
        word_modified = False

        for ex_idx, ex in enumerate(examples):
            sentence = ex.get('sentence', '')
            if not sentence:
                continue

            if not has_ocr_error(sentence):
                stats['clean'] += 1
                continue

            # Phase 1: 규칙 기반 수정
            fixed = apply_rule_fixes(sentence)

            if fixed and not has_ocr_error(fixed):
                # 규칙으로 완전히 수정됨
                if fixed != sentence:
                    ex['sentence'] = fixed
                    stats['rule_fixed'] += 1
                    modified_count += 1
                    word_modified = True
            elif fixed and len(fixed) > 15:
                # 규칙으로 부분 수정 후 AI 필요
                ex['sentence'] = fixed  # 부분 수정 먼저 반영
                if use_ai and client:
                    key = f"{word}_{ex_idx}"
                    ai_pending.append({
                        '_key': key, 'word': word, 'ex_idx': ex_idx,
                        'sentence': fixed
                    })
                    word_modified = True
            else:
                # 복원 불가
                if fixed != sentence:
                    ex['sentence'] = fixed if fixed else sentence
                stats['unrestorable'] += 1

            # AI 배치 플러시
            if len(ai_pending) >= ai_batch_size:
                flush_ai_batch()

        done_words.add(word)

        # 주기적 저장
        if (i + 1) % save_every == 0:
            flush_ai_batch()
            save_data(data)
            save_progress(done_words, start, end)
            pct = (i + 1) / len(target_words) * 100
            print(f"  진행: {i+1}/{len(target_words)} ({pct:.1f}%) | "
                  f"규칙:{stats['rule_fixed']} AI:{stats['ai_fixed']} "
                  f"불가:{stats['unrestorable']}")

    # 마지막 플러시 및 저장
    flush_ai_batch()
    save_data(data)
    save_progress(done_words, start, end)

    print(f"\n=== 완료 (범위 {start}~{end}) ===")
    print(f"  규칙 수정:    {stats['rule_fixed']:,}")
    print(f"  AI 수정:      {stats['ai_fixed']:,}")
    print(f"  복원 불가:    {stats['unrestorable']:,}")
    print(f"  정상 (수정불필요): {stats['clean']:,}")
    print(f"  총 수정:      {modified_count:,}")


def merge_progress():
    """병렬 실행 결과 확인 (실제 데이터는 이미 각 실행에서 저장됨)."""
    progress_files = list(PROGRESS_DIR.glob("done_*.json"))
    total_done = set()
    for f in progress_files:
        with open(f, 'r', encoding='utf-8') as fp:
            total_done.update(json.load(fp))
    print(f"병렬 실행 완료 단어 수: {len(total_done):,}")

    # 진행률 확인
    data = load_data()
    total_words = len(data)
    print(f"전체 단어 수: {total_words:,}")
    print(f"미처리 단어: {total_words - len(total_done):,}")


def create_backup():
    """원본 백업 생성."""
    if not BACKUP_FILE.exists():
        import shutil
        print(f"백업 생성: {BACKUP_FILE}")
        shutil.copy2(INPUT_FILE, BACKUP_FILE)
        print("백업 완료")
    else:
        print(f"백업 이미 존재: {BACKUP_FILE}")


# ─────────────────────────────────────────────
# CLI 진입점
# ─────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='OCR 예문 복원 스크립트')
    parser.add_argument('--start', type=int, default=0, help='시작 단어 인덱스')
    parser.add_argument('--end',   type=int, default=9999999, help='끝 단어 인덱스')
    parser.add_argument('--no-ai', action='store_true', help='AI 복원 비활성화 (규칙 기반만)')
    parser.add_argument('--ai-batch', type=int, default=50, help='AI 배치 크기 (기본 50)')
    parser.add_argument('--save-every', type=int, default=200, help='N개 단어마다 저장 (기본 200)')
    parser.add_argument('--merge', action='store_true', help='병렬 실행 결과 병합 (진행률 확인)')
    parser.add_argument('--backup', action='store_true', help='원본 백업 생성')

    args = parser.parse_args()

    if args.backup:
        create_backup()
        sys.exit(0)

    if args.merge:
        merge_progress()
        sys.exit(0)

    # 백업 먼저
    create_backup()

    process_range(
        start=args.start,
        end=args.end,
        use_ai=not args.no_ai,
        ai_batch_size=args.ai_batch,
        save_every=args.save_every,
    )
