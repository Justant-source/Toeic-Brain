"""단어장 JSON에 품사(pos) 정보를 추가하는 스크립트.

NLTK WordNet + 영어 접미사 패턴 + 한국어 의미 패턴을 조합하여
각 단어의 품사를 판별한다.
"""

import json
import os
import re
from pathlib import Path

import nltk
from nltk.corpus import wordnet as wn

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
VOCAB_DIR = PROJECT_ROOT / "data" / "json"

# WordNet POS → 우리 POS 매핑
WN_POS_MAP = {
    wn.NOUN: "noun",
    wn.VERB: "verb",
    wn.ADJ: "adjective",
    wn.ADV: "adverb",
}

# 영어 접미사 기반 품사 판별
# 긴 접미사를 먼저 체크하여 "requirement"가 "ment"(noun)에 매칭되도록 함
SUFFIX_RULES: list[tuple[str, str]] = [
    # 5+ chars (가장 구체적)
    ("ement", "noun"),
    ("ament", "noun"),
    ("ation", "noun"),
    ("ition", "noun"),
    ("iness", "noun"),
    ("ously", "adverb"),
    ("ively", "adverb"),
    ("fully", "adverb"),
    ("ially", "adverb"),
    ("ently", "adverb"),
    ("antly", "adverb"),
    ("arily", "adverb"),
    ("ility", "noun"),
    ("ality", "noun"),
    ("ivity", "noun"),
    ("ement", "noun"),
    ("rable", "adjective"),
    ("ional", "adjective"),
    ("ative", "adjective"),
    ("itive", "adjective"),
    ("rical", "adjective"),
    ("tical", "adjective"),
    # 4 chars
    ("ment", "noun"),
    ("tion", "noun"),
    ("sion", "noun"),
    ("ness", "noun"),
    ("ance", "noun"),
    ("ence", "noun"),
    ("ical", "adjective"),
    ("able", "adjective"),
    ("ible", "adjective"),
    ("less", "adjective"),
    # 3 chars
    ("ity", "noun"),
    ("ism", "noun"),
    ("ist", "noun"),
    ("ant", "noun"),      # applicant, consultant, accountant 등 TOEIC에서 대부분 명사
    ("ent", "noun"),      # requirement, equipment, department 등
    ("ive", "adjective"),
    ("ous", "adjective"),
    ("ful", "adjective"),
    ("ial", "adjective"),
    ("ory", "adjective"),
    ("ary", "adjective"),
    ("ize", "verb"),
    ("ise", "verb"),
    ("ify", "verb"),
    ("ate", "verb"),
    ("ure", "noun"),
    # 2 chars
    ("ly", "adverb"),
    ("er", "noun"),
    ("or", "noun"),
    ("al", "adjective"),
]

# 한국어 의미 패턴 (첫 번째 의미 기준)
# 순서 중요: 구체적인 패턴이 먼저, 일반적인 패턴이 뒤에
KR_PATTERNS: list[tuple[str, str]] = [
    # --- 동사 ---
    (r"하다\s*$", "verb"),
    (r"시키다", "verb"),
    (r"되다\s*$", "verb"),
    (r"주다\s*$", "verb"),
    (r"받다\s*$", "verb"),
    (r"내다\s*$", "verb"),
    (r"보다\s*$", "verb"),
    (r"오다\s*$", "verb"),
    (r"가다\s*$", "verb"),
    (r"나다\s*$", "verb"),
    (r"넣다\s*$", "verb"),
    (r"놓다\s*$", "verb"),
    (r"듣다\s*$", "verb"),
    (r"쓰다\s*$", "verb"),
    (r"먹다\s*$", "verb"),
    (r"짓다\s*$", "verb"),
    (r"찾다\s*$", "verb"),
    (r"잡다\s*$", "verb"),
    (r"열다\s*$", "verb"),
    (r"닫다\s*$", "verb"),
    (r"이르다\s*$", "verb"),
    (r"다\s*$", "verb"),        # 모든 "~다" 어미는 동사
    # --- 형용사 (한국어 형용사 어미) ---
    (r"적인", "adjective"),
    (r"스러운", "adjective"),
    (r"있는", "adjective"),
    (r"없는", "adjective"),
    (r"같은", "adjective"),
    (r"로운\s*$", "adjective"),
    (r"다운\s*$", "adjective"),
    # --- 부사 ---
    (r"하게\s*$", "adverb"),
    (r"[적]으로\s*$", "adverb"),
    (r"히\s*$", "adverb"),
    # --- 전치사/접속사 ---
    (r"에도\s*불구하고", "preposition"),
    (r"동안에?\s*$", "preposition"),
    (r"때문에", "conjunction"),
]

# 한국어 의미에서 명사/형용사 패턴 (전체 의미 문자열 검사)
KR_NOUN_HINTS = [
    r"[서자]$",   # ~자(者), ~서(書) 등 명사 어미
    r"[비료금액]$",
    r"[성력]$",
]

KR_ADJ_HINTS = [
    r"적$",       # ~적 (형용사)
    r"적이",
]

# 수동 오버라이드 (흔한 TOEIC 단어 중 자동 판별이 어려운 것들)
MANUAL_POS: dict[str, str] = {
    # 접속사/전치사
    "although": "conjunction",
    "despite": "preposition",
    "however": "adverb",
    "therefore": "adverb",
    "nevertheless": "adverb",
    "furthermore": "adverb",
    "moreover": "adverb",
    "whereas": "conjunction",
    "unless": "conjunction",
    "whether": "conjunction",
    "while": "conjunction",
    "since": "conjunction",
    "because": "conjunction",
    "though": "conjunction",
    "once": "conjunction",
    "until": "conjunction",
    "if": "conjunction",
    "but": "conjunction",
    "and": "conjunction",
    "or": "conjunction",
    "nor": "conjunction",
    "yet": "conjunction",
    "so": "conjunction",
    "both": "adjective",
    "either": "adjective",
    "neither": "adjective",
    "between": "preposition",
    "among": "preposition",
    "during": "preposition",
    "throughout": "preposition",
    "regarding": "preposition",
    "concerning": "preposition",
    "within": "preposition",
    "without": "preposition",
    "beyond": "preposition",
    "upon": "preposition",
    "toward": "preposition",
    "towards": "preposition",
    "across": "preposition",
    "against": "preposition",
    "along": "preposition",
    "beside": "preposition",
    "besides": "preposition",
    "beneath": "preposition",
    "above": "preposition",
    "below": "preposition",
    "behind": "preposition",
    "ahead": "adverb",
    "prior": "adjective",
    # 흔히 오분류되는 단어
    "each": "adjective",
    "every": "adjective",
    "several": "adjective",
    "various": "adjective",
    "much": "adjective",
    "many": "adjective",
    "few": "adjective",
    "most": "adjective",
    "other": "adjective",
    "another": "adjective",
    "such": "adjective",
    "whole": "adjective",
    "entire": "adjective",
}


def get_wordnet_pos(word: str) -> str | None:
    """WordNet에서 가장 빈번한 품사를 가져온다."""
    synsets = wn.synsets(word)
    if not synsets:
        return None

    # 각 품사별 synset 개수를 세어 가장 많은 것을 선택
    pos_counts: dict[str, int] = {}
    for ss in synsets:
        pos = WN_POS_MAP.get(ss.pos())
        if pos:
            pos_counts[pos] = pos_counts.get(pos, 0) + 1

    if not pos_counts:
        return None

    return max(pos_counts, key=lambda p: pos_counts[p])


def get_suffix_pos(word: str) -> str | None:
    """영어 접미사 패턴으로 품사를 판별한다."""
    w = word.lower()
    for suffix, pos in SUFFIX_RULES:
        if w.endswith(suffix) and len(w) > len(suffix) + 2:
            return pos
    return None


def _extract_first_meaning(meaning_kr: str) -> str:
    """한국어 의미에서 첫 번째 의미를 추출한다.

    괄호 안의 쉼표를 무시하고 올바르게 분리한다.
    예: "(필요,요구 등을)만족시키다, 충족하다" → "만족시키다"
    """
    if not meaning_kr:
        return ""
    # 먼저 괄호 안의 내용을 임시 제거하여 올바른 쉼표 위치 찾기
    temp = re.sub(r"\([^)]*\)", "___PAREN___", meaning_kr)
    first = temp.split(",")[0].strip()
    # 원본에서 같은 위치까지의 문자열 복원
    end_pos = meaning_kr.find(",")
    if end_pos == -1 or "___PAREN___" not in first:
        first_orig = meaning_kr.split(",")[0].strip() if "___PAREN___" not in first else meaning_kr[:end_pos].strip() if end_pos > 0 else meaning_kr.strip()
    else:
        # 괄호를 고려한 분리
        depth = 0
        for i, ch in enumerate(meaning_kr):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == "," and depth == 0:
                first_orig = meaning_kr[:i].strip()
                break
        else:
            first_orig = meaning_kr.strip()
    # 괄호 내용 제거
    first_orig = re.sub(r"\([^)]*\)", "", first_orig).strip()
    return first_orig


def get_kr_pos(meaning_kr: str) -> str | None:
    """한국어 의미에서 품사를 추론한다."""
    first_meaning = _extract_first_meaning(meaning_kr)
    if not first_meaning:
        return None
    for pattern, pos in KR_PATTERNS:
        if re.search(pattern, first_meaning):
            return pos
    return None


def is_kr_noun(meaning_kr: str) -> bool:
    """한국어 의미가 명사인지 판별한다.

    한국어에서 명사는 동사(~다)/형용사(~는,~운,~된) 어미가 없다.
    """
    first = _extract_first_meaning(meaning_kr)
    if not first:
        return False
    # 동사/형용사 어미로 끝나면 명사가 아님
    if re.search(r"(하다|시키다|되다|주다|받다|내다|보다|오다|가다|나다|있는|없는|적인|스러운|한|의|운|된|난|인|하게|히)$", first):
        return False
    # 한국어 명사는 보통 받침이 있는 짧은 단어이거나 한자어
    return True


def is_kr_adjective(meaning_kr: str) -> bool:
    """한국어 의미가 형용사인지 판별한다."""
    first = _extract_first_meaning(meaning_kr)
    if not first:
        return False
    # 명확한 형용사 어미
    if re.search(r"(적인|있는|없는|스러운|로운|다운)$", first):
        return True
    # "~한", "~된", "~운", "~는" 등 관형형 어미 (2글자 이상, 동사 "~다" 어미 제외)
    if len(first) >= 2 and not first.endswith("다") and re.search(r"(한|된|운|난|큰|른|쁜|진|는|깊은|높은|좋은|많은|같은|없는)$", first):
        return True
    return False


def determine_pos(word: str, meaning_kr: str) -> str:
    """여러 방법을 조합하여 최종 품사를 결정한다.

    우선순위:
    1. 수동 오버라이드
    2. 한국어 의미 패턴 (단어장의 의미가 가장 신뢰도 높음)
    3. 접미사 + WordNet 조합
    4. 기본값: noun
    """
    w = word.lower().strip()

    # 0) 공백 포함 구(phrase)인 경우 → 한국어 의미 기반으로만 판별
    if " " in w:
        kr_pos = get_kr_pos(meaning_kr)
        if kr_pos:
            return kr_pos
        if is_kr_adjective(meaning_kr):
            return "adjective"
        return "noun"

    # 1) 수동 오버라이드
    if w in MANUAL_POS:
        return MANUAL_POS[w]

    # 1.5) "-ly" 영어 단어는 대부분 부사 (예외: timely, costly 등은 형용사)
    _LY_ADJECTIVES = {
        "timely", "costly", "likely", "unlikely", "friendly", "unfriendly",
        "lovely", "lonely", "lively", "orderly", "elderly", "daily",
        "weekly", "monthly", "yearly", "quarterly", "hourly", "homely",
        "deadly", "ugly", "holy", "silly", "early", "worldly", "leisurely",
    }
    if w.endswith("ly") and len(w) > 3:
        if w in _LY_ADJECTIVES:
            return "adjective"
        return "adverb"

    # 2) 한국어 의미 패턴 (이 단어장에서의 실제 용법)
    kr_pos = get_kr_pos(meaning_kr)
    if kr_pos:
        return kr_pos

    # 한국어 형용사 체크
    if is_kr_adjective(meaning_kr):
        return "adjective"

    # 한국어 의미가 순수 명사인지 체크 (동사/형용사 어미 없음)
    kr_is_noun = is_kr_noun(meaning_kr)

    # 3) 접미사 패턴
    suffix_pos = get_suffix_pos(w)

    # 4) WordNet
    wn_pos = get_wordnet_pos(w)

    # 접미사와 WordNet이 일치하면 확실
    if suffix_pos and wn_pos and suffix_pos == wn_pos:
        return suffix_pos

    # 한국어가 명사이고 접미사도 명사 → 확실히 명사
    if kr_is_noun and suffix_pos == "noun":
        return "noun"

    # 한국어가 명사이고 WordNet도 명사 → 명사
    if kr_is_noun and wn_pos == "noun":
        return "noun"

    # 한국어가 명사인데 다른 신호가 없으면 → 명사 (한국어 의미 우선)
    if kr_is_noun and not suffix_pos:
        return "noun"

    # 접미사가 noun/adjective/adverb이면 신뢰 (형태론적으로 명확)
    if suffix_pos and suffix_pos in ("noun", "adjective", "adverb"):
        return suffix_pos

    # WordNet 결과
    if wn_pos:
        return wn_pos

    # 접미사 (verb 포함)
    if suffix_pos:
        return suffix_pos

    # 기본값
    return "noun"


def process_file(filepath: Path) -> int:
    """단일 JSON 파일에 pos를 추가하고 저장한다. 처리한 단어 수를 반환."""
    with open(filepath, encoding="utf-8") as f:
        words = json.load(f)

    for entry in words:
        entry["pos"] = determine_pos(entry["word"], entry.get("meaning_kr", ""))

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(words, f, ensure_ascii=False, indent=2)

    return len(words)


def main():
    total = 0
    pos_stats: dict[str, int] = {}

    # hackers_vocab.json 업데이트
    vocab_path = VOCAB_DIR / "hackers_vocab.json"
    if vocab_path.exists():
        total = process_file(vocab_path)
        print(f"  hackers_vocab.json: {total} words")

        # 통계 수집
        with open(vocab_path, encoding="utf-8") as f:
            for entry in json.load(f):
                pos = entry["pos"]
                pos_stats[pos] = pos_stats.get(pos, 0) + 1

    print(f"\nTotal: {total} words processed")
    print("\nPOS distribution:")
    for pos, cnt in sorted(pos_stats.items(), key=lambda x: -x[1]):
        print(f"  {pos:15s}: {cnt:4d} ({cnt/total*100:.1f}%)")


if __name__ == "__main__":
    main()
