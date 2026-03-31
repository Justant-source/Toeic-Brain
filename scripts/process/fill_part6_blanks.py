"""
Part 6 예문의 ------- 빈칸을 정답 텍스트(**bold**)로 채우는 스크립트.

처리 흐름:
1. Part 6 raw_text 파싱 → {(vol, test, q_num): 정답_텍스트}
2. word_ets_examples.json 순회 → ------- 있는 예문 찾기
3. source에서 (vol, test) 추출 → 해당 지문에서 빈칸 위치로 q_num 특정
4. 정답 텍스트로 ------- 치환

사용법:
  py scripts/process/fill_part6_blanks.py
"""

import json
import re
import sys
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path(__file__).parent.parent.parent
QUESTIONS_DIR = BASE_DIR / "data/processed/questions"
EXAMPLES_FILE = BASE_DIR / "data/mapped/word_ets_examples.json"

BLANK_RE = re.compile(r'-{5,}')

# ─────────────────────────────────────────────
# 1. Part 6 데이터 파싱
# ─────────────────────────────────────────────

def parse_choices(raw_text: str, q_nums: list[int]) -> dict[int, dict]:
    """
    raw_text에서 각 q_num의 (A)(B)(C)(D) 선택지를 추출.
    반환: {q_num: {"A": "...", "B": "...", "C": "...", "D": "..."}}
    """
    choices = {}
    other_nums = '|'.join(str(n) for n in q_nums)

    for q_num in q_nums:
        # q_num. 이후 (A)부터 시작하는 블록을 통째로 잡음
        pattern = re.compile(
            rf'\b{q_num}\s*[\.\)]\s*(\(A\>.*?)(?=\b(?:{other_nums})\s*[\.\)]|\Z)',
            re.DOTALL | re.IGNORECASE
        )
        # 실제 패턴: q_num 뒤 (A)로 시작하는 블록
        pattern2 = re.compile(
            rf'\b{q_num}[\.\s]{{1,3}}(\(A\).*?)(?=\b(?:{other_nums})[\.\s]|\Z)',
            re.DOTALL
        )
        m = pattern2.search(raw_text)
        if not m:
            continue

        block = m.group(1)  # "(A) text\n(B) text\n..." 전체

        q_choices = {}
        letter_pat = re.compile(r'\(([A-D])\)\s*(.*?)(?=\s*\([A-D]\)|\Z)', re.DOTALL)
        for lm in letter_pat.finditer(block):
            letter = lm.group(1)
            text = lm.group(2).strip()
            text = re.sub(r'\s+', ' ', text).strip()
            # 다음 질문번호가 섞인 경우 잘라내기
            cutoff = re.search(rf'\b(?:{other_nums})\s*[\.\)]', text)
            if cutoff:
                text = text[:cutoff.start()].strip()
            q_choices[letter] = text

        if len(q_choices) >= 2:
            choices[q_num] = q_choices

    return choices


def build_answer_map() -> dict[tuple, dict]:
    """
    모든 Part 6 파일을 파싱하여 반환:
    {(vol, test, q_num): {"choices": {...}, "correct": "A", "correct_text": "..."}}
    """
    answer_map = {}

    for vol in range(1, 6):
        path = QUESTIONS_DIR / f"vol{vol}_part6.json"
        if not path.exists():
            continue
        with open(path, 'r', encoding='utf-8') as f:
            entries = json.load(f)

        for entry in entries:
            test = entry.get('test')
            raw = entry.get('raw_text', '')
            answers = entry.get('answer', {})

            if not test or not answers:
                continue

            q_nums = sorted(int(k) for k in answers.keys())
            choices_by_q = parse_choices(raw, q_nums)

            for q_num in q_nums:
                correct_letter = answers[str(q_num)]
                choices = choices_by_q.get(q_num, {})
                correct_text = choices.get(correct_letter, '')
                answer_map[(vol, test, q_num)] = {
                    'choices': choices,
                    'correct': correct_letter,
                    'correct_text': correct_text,
                }

    print(f"정답 맵 구축 완료: {len(answer_map):,}개 질문")
    return answer_map


def get_passage_for_test(vol: int, test: int) -> str | None:
    """해당 (vol, test)의 Part 6 raw_text 반환."""
    path = QUESTIONS_DIR / f"vol{vol}_part6.json"
    if not path.exists():
        return None
    with open(path, 'r', encoding='utf-8') as f:
        entries = json.load(f)
    for entry in entries:
        if entry.get('test') == test:
            return entry.get('raw_text', '')
    return None


# ─────────────────────────────────────────────
# 2. 빈칸 예문 → q_num 매핑
# ─────────────────────────────────────────────

def extract_source(source: str) -> tuple[int, int] | None:
    """
    "Vol 2, TEST 05, Part 6" → (2, 5)
    "Vol 2, p.123" → None (Part 6 아님)
    """
    m = re.search(r'Vol\s*(\d+).*?TEST\s*0?(\d+)', source, re.IGNORECASE)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


def strip_bold(text: str) -> str:
    """**word** 마크다운 마커 제거."""
    return re.sub(r'\*\*(.+?)\*\*', r'\1', text)


def find_blank_in_passage(sentence: str, passage: str) -> int:
    """
    sentence의 ------- 위치를 passage에서 찾아 passage 내 위치(int) 반환.
    실패 시 -1.
    """
    clean = strip_bold(sentence)
    m = BLANK_RE.search(clean)
    if not m:
        return -1

    before = clean[:m.start()].strip()
    after  = clean[m.end():].strip()

    def make_pattern(text: str) -> str:
        """단어 사이 임의 공백을 허용하는 regex 패턴 생성."""
        words = text.split()
        if not words:
            return ''
        return r'\s+'.join(re.escape(w) for w in words)

    # 빈칸 앞 텍스트로 검색 → 바로 뒤의 ------- 위치
    if len(before) >= 10:
        key = make_pattern(before[-25:].strip())
        if key:
            pm = re.search(key, passage, re.IGNORECASE)
            if pm:
                local = passage[pm.end(): pm.end() + 60]
                bm = BLANK_RE.search(local)
                if bm:
                    return pm.end() + bm.start()

    # 빈칸 뒤 텍스트로 검색 → 바로 앞의 ------- 위치
    if len(after) >= 10:
        key2 = make_pattern(after[:25].strip())
        if key2:
            pm2 = re.search(key2, passage, re.IGNORECASE)
            if pm2:
                local2 = passage[max(0, pm2.start() - 80): pm2.start()]
                bm2 = list(BLANK_RE.finditer(local2))
                if bm2:
                    return max(0, pm2.start() - 80) + bm2[-1].start()

    return -1


def find_q_num_for_blank(sentence: str, vol: int, test: int,
                          passage: str, answer_map: dict) -> int | None:
    """
    sentence 내의 ------- 이 passage의 몇 번 질문인지 찾는다.
    """
    if not passage:
        return None

    passage_pos = find_blank_in_passage(sentence, passage)
    if passage_pos < 0:
        return None

    # 가장 가까운 앞쪽 "Questions N-M" 범위 찾기
    range_matches = list(re.finditer(r'Questions?\s+(\d+)[–\-]\s*(\d+)', passage, re.IGNORECASE))
    q_start, q_end, range_start = None, None, 0
    for rm in reversed(range_matches):
        if rm.start() <= passage_pos:
            q_start = int(rm.group(1))
            q_end   = int(rm.group(2))
            range_start = rm.end()
            break

    if q_start is None:
        return None

    # 이 범위 구간의 passage 텍스트 (다음 Questions 전까지)
    next_range = re.search(r'Questions?\s+\d+[–\-]\s*\d+', passage[range_start:], re.IGNORECASE)
    section_end = range_start + next_range.start() if next_range else len(passage)
    passage_section = passage[range_start:section_end]

    blank_positions_abs = [range_start + m.start() for m in BLANK_RE.finditer(passage_section)]
    if not blank_positions_abs:
        return None

    # 가장 가까운 빈칸 인덱스
    dists = [(abs(bp - passage_pos), i) for i, bp in enumerate(blank_positions_abs)]
    blank_idx = min(dists, key=lambda x: x[0])[1]
    bp = blank_positions_abs[blank_idx]

    # 빈칸 바로 뒤 inline 라벨 확인: "-------\n144.\n"
    nearby_after = passage[bp: bp + 35]
    lm = re.search(r'(\d{3})\s*[\.\)]', nearby_after)
    if lm:
        q_num = int(lm.group(1))
        if q_start <= q_num <= q_end:
            return q_num

    # 빈칸 바로 앞 라벨 확인
    nearby_before = passage[max(0, bp - 12): bp + 5]
    lm2 = re.search(r'(\d{3})\s*[\.\)]\s*$', nearby_before)
    if lm2:
        q_num = int(lm2.group(1))
        if q_start <= q_num <= q_end:
            return q_num

    # 라벨 없으면 순서 기반 (1번째 빈칸 = q_start, 2번째 = q_start+1, ...)
    q_num = q_start + blank_idx
    if q_start <= q_num <= q_end:
        return q_num

    return None


# ─────────────────────────────────────────────
# 3. 메인 처리
# ─────────────────────────────────────────────

def fill_blanks():
    print("Part 6 정답 맵 구축 중...")
    answer_map = build_answer_map()

    # passage 캐시
    passage_cache: dict[tuple, str] = {}

    print(f"예문 데이터 로딩: {EXAMPLES_FILE}")
    with open(EXAMPLES_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    stats = {
        'total_blank': 0,
        'filled': 0,
        'no_source': 0,
        'no_match': 0,
        'no_text': 0,
    }

    for word, entry in data.items():
        for ex in entry.get('examples', []):
            sentence = ex.get('sentence', '')
            if not BLANK_RE.search(sentence):
                continue

            stats['total_blank'] += 1
            source = ex.get('source', '')

            parsed = extract_source(source)
            if not parsed:
                stats['no_source'] += 1
                continue

            vol, test = parsed

            # passage 캐시
            if (vol, test) not in passage_cache:
                passage_cache[(vol, test)] = get_passage_for_test(vol, test) or ''

            passage = passage_cache[(vol, test)]

            q_num = find_q_num_for_blank(sentence, vol, test, passage, answer_map)

            if q_num is None:
                stats['no_match'] += 1
                continue

            info = answer_map.get((vol, test, q_num))
            if not info:
                stats['no_match'] += 1
                continue

            correct_text = info.get('correct_text', '').strip()
            if not correct_text:
                stats['no_text'] += 1
                continue

            # ------- 치환 (문장에 빈칸 하나만 있는 경우가 대부분)
            new_sentence = BLANK_RE.sub(f'**{correct_text}**', sentence, count=1)
            ex['sentence'] = new_sentence
            stats['filled'] += 1

    # 저장
    print(f"\n저장 중: {EXAMPLES_FILE}")
    with open(EXAMPLES_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("\n=== 완료 ===")
    print(f"  빈칸 예문 총계:  {stats['total_blank']:,}")
    print(f"  채움 성공:       {stats['filled']:,}")
    print(f"  소스 없음:       {stats['no_source']:,}")
    print(f"  매핑 실패:       {stats['no_match']:,}")
    print(f"  정답텍스트 없음: {stats['no_text']:,}")
    print(f"  성공률:          {stats['filled']/max(stats['total_blank'],1)*100:.1f}%")


if __name__ == '__main__':
    fill_blanks()
