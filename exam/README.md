# 모의고사 생성기

## Part5 모의고사

ETS 기출 Part5 문제(5권, 약 1,500문제)에서 랜덤 출제하여 풀이용 HTML을 생성합니다.

### 전체 워크플로우

```
1. 모의고사 HTML 생성
       ↓
2. 브라우저에서 문제 풀기 → 채점하기
       ↓
3. 💾 결과 저장 (JSON) 버튼 클릭
       ↓
4. 취약점 핵심요약집 생성
```

### 1단계 — 모의고사 생성

```bash
# 기본 (30문제, 전권, 전 카테고리)
python exam/generate_part5_test.py

# 1·2권에서만 20문제
python exam/generate_part5_test.py --count 20 --vol 1 2

# 품사·어휘 문제만 30문제
python exam/generate_part5_test.py --category 품사 어휘

# 선택지 순서 랜덤화
python exam/generate_part5_test.py --shuffle
```

**출력:** `exam/result/part5_test_YYYYMMDD_HHMM.html`

### 2단계 — 문제 풀기 & 결과 저장

1. 생성된 HTML을 브라우저에서 열기
2. 문제를 모두 풀고 **채점하기** 클릭
3. 결과 화면에서 **💾 결과 저장 (JSON)** 버튼 클릭
4. `result_YYYYMMDD_HHMM.json` 파일이 다운로드됨
5. 다운로드된 JSON을 `exam/result/` 폴더로 이동

### 3단계 — 취약점 핵심요약집 생성

```bash
# 기본 (정답률 70% 미만 카테고리를 취약으로 판정)
python exam/generate_weakness_summary.py exam/result/result_YYYYMMDD_HHMM.json

# 취약 기준을 60%로 낮추기
python exam/generate_weakness_summary.py exam/result/result_YYYYMMDD_HHMM.json --threshold 60
```

**출력:** `exam/result/summary_YYYYMMDD_HHMM.html`

요약집에는 취약 카테고리별로 해커스 토익 RC 기본서의 **핵심 개념, 핵심 공식/패턴, 출제 포인트**와 해당 카테고리의 **오답 문제** (정답 vs 내가 선택한 답)가 포함됩니다.

---

## 단어장 퀴즈

노랭이 단어장(Day 1~30, 약 4,000단어)에서 4지선다 퀴즈를 생성합니다.

### 사용법

```bash
# 기본 (50문제, 영어→한국어)
python exam/generate_vocab_quiz.py

# Day 1~5에서 30문제, 기출 예문 포함
python exam/generate_vocab_quiz.py --count 30 --day 1 2 3 4 5 --with-examples

# 한국어→영어 모드, 900점 레벨만
python exam/generate_vocab_quiz.py --mode kr2en --level 900점
```

### 출력

`exam/result/vocab_quiz_YYYYMMDD_HHMM.html`을 브라우저에서 열어 풀이합니다.
