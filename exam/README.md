# 모의고사 생성기

## Part5 모의고사

ETS 기출 Part5 문제(5권, 약 1,500문제)에서 랜덤 출제하여 풀이용 HTML을 생성합니다.

### 사용법

```bash
# 기본 (30문제, 전권, 전 카테고리)
python exam/generate_part5_test.py

# 1권과 2권에서만 20문제
python exam/generate_part5_test.py --count 20 --vol 1 2

# 품사·어휘 문제만 30문제
python exam/generate_part5_test.py --category 품사 어휘

# 선택지 순서 랜덤화
python exam/generate_part5_test.py --shuffle
```

### 출력

`exam/result/part5_test_YYYYMMDD_HHMM.html`을 브라우저에서 열어 풀이합니다.

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
