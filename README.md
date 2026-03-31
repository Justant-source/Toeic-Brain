# Toeic Brain

> ETS 기출문제 1000제 (5권, 총 5,000문제) + 해커스 노랭이 단어장 → Anki 기반 토익 RC 학습 시스템

## 프로젝트 목표

1. **단어-기출 매핑** — 노랭이 단어가 ETS 기출 어디에 등장하는지 전수 추적 (`word_ets_examples.json`)
2. **Anki 단어장 덱** — 노랭이 단어 + 기출 예문(정답 볼드 처리) 플래시카드
3. **Anki Part5 덱** — ETS Part5 기출문제 반복 풀이용 플래시카드
4. **모의고사** — Part5 모의고사 + 단어장 퀴즈 HTML 생성

---

## 디렉토리 구조

```
Toeic Brain/
│
├── 00. Reference/                    # 원본 PDF/Excel (git 미추적, 저작권)
│
├── data/
│   ├── json/                         # 구조화 JSON (git 미추적)
│   │   ├── questions/                # 기출문제 JSON (vol1~5 × part5/6/7, 15개)
│   │   ├── hackers_vocab.json        # 단어장 통합 JSON
│   │   └── word_ets_examples.json    # 단어별 기출 예문 매핑 (4,206단어, 298,393예문)
│   └── anki/                         # Anki 덱 생성용 중간 데이터
│
├── scripts/
│   ├── extract/                      # Phase 1: PDF/Excel → JSON
│   │   ├── extract_ets.py            # ETS 기출 PDF → Part5/6/7 문제 JSON
│   │   ├── extract_answers.py        # ETS 해설 PDF → 정답·해설 추출
│   │   ├── extract_vocab_excel.py    # 노랭이 Excel → hackers_vocab.json
│   │   ├── ocr_question_pdf.py       # 문제 PDF 텍스트 추출·캐싱
│   │   └── ocr_utils.py              # OCR 공유 유틸리티
│   │
│   ├── process/                      # Phase 2: 가공·매핑·정제
│   │   ├── find_ets_examples.py      # 단어별 기출 예문 전수 검색 (spaCy)
│   │   ├── fill_part6_blanks.py      # Part6 빈칸(-------)을 정답 볼드체로 채우기
│   │   ├── restore_ocr_sentences.py  # OCR 깨진 예문 규칙·AI 복원
│   │   ├── create_restore_batches.py # OCR 복원용 배치 파일 생성
│   │   ├── apply_restore_batches.py  # AI 복원 결과 메인 JSON에 적용
│   │   ├── categorize.py             # Part5 문제 유형 8개 카테고리 자동 분류
│   │   ├── add_pos.py                # 품사(POS) 자동 태깅
│   │   ├── fix_pos.py                # Claude API로 POS 교정
│   │   └── validate.py               # JSON 무결성 검증
│   │
│   ├── anki/                         # Phase 3: Anki 덱 생성
│   │   ├── generate_vocab_deck.py    # 단어장 덱 생성 → output/anki/toeic_vocab.apkg
│   │   ├── generate_part5_deck.py    # Part5 덱 생성 → output/anki/toeic_part5.apkg
│   │   ├── templates/                # 카드 HTML 템플릿 (앞면/뒷면 × 2종)
│   │   └── styles/card_style.css     # 카드 공통 스타일
│   │
│   ├── analyze/                      # Phase 4: 분석·리포트
│   │   ├── category_stats.py         # Part5 카테고리 출제 통계
│   │   ├── coverage_report.py        # 노랭이 단어 기출 커버리지 분석
│   │   └── word_frequency.py         # ETS 5권 빈출 단어 Top 100
│   │
│   └── utils/
│       └── nlp.py                    # Lemmatization, 단어 패밀리, 역인덱스
│
├── exam/
│   ├── generate_part5_test.py        # Part5 모의고사 HTML 생성
│   ├── generate_vocab_quiz.py        # 단어장 퀴즈 HTML 생성
│   └── result/                       # 생성된 HTML (git 미추적)
│
├── output/
│   ├── anki/                         # 생성된 .apkg (git 미추적)
│   └── reports/                      # 분석 리포트 HTML
│
├── archive/                          # 사용 종료된 스크립트 보관
│   └── scripts/
├── .request/                         # 작업지시서 (git 미추적)
├── .result/                          # 완료 보고서
├── CLAUDE.md                         # 상세 개발 가이드 (스키마, 규칙, 규약)
└── config.yaml                       # 전역 설정
```

---

## 데이터 현황

| 항목 | 수치 |
|------|------|
| 기출 문제 | 5권 × (Part5 ~300 + Part6 ~50 + Part7 ~48) |
| 단어장 | 4,206단어 (기초 / 800점 / 900점) |
| 예문 매핑 | 298,393개 예문 (OCR 복원·빈칸 채우기 완료) |
| Anki 단어 카드 | 4,209장 (기출등장 있음 3,505 / 없음 704) |
| Anki Part5 카드 | 1,500장 (5권 전체) |

---

## Quick Start

```bash
# 의존성 설치
pip install -r requirements.txt

# Anki 덱 생성 (데이터가 이미 준비된 경우)
py scripts/anki/generate_vocab_deck.py    # → output/anki/toeic_vocab.apkg
py scripts/anki/generate_part5_deck.py   # → output/anki/toeic_part5.apkg

# 모의고사 HTML 생성
py exam/generate_part5_test.py            # Part5 30문제
py exam/generate_vocab_quiz.py            # 단어장 50문제 4지선다
```

생성된 `.apkg` 파일을 Anki에서 **파일 > 가져오기**로 불러오세요.

---

## 전체 파이프라인 (처음 구축 시)

```
1. 원본 데이터 배치
   00. Reference/      ← ETS 기출 PDF (5권), 정답·해설 PDF (5권), 노랭이 Excel

2. 추출 (Phase 1)
   py scripts/extract/extract_ets.py        # 문제 JSON 생성
   py scripts/extract/extract_answers.py    # 정답·해설 반영
   py scripts/extract/extract_vocab_excel.py

3. 가공 (Phase 2)
   py scripts/process/find_ets_examples.py  # 예문 매핑 (오래 걸림)
   py scripts/process/fill_part6_blanks.py  # Part6 빈칸 채우기
   py scripts/process/categorize.py         # Part5 유형 분류

4. 덱 생성 (Phase 3)
   py scripts/anki/generate_vocab_deck.py
   py scripts/anki/generate_part5_deck.py
```

> 상세 사용법: `scripts/README.md`

---

## Anki 카드 구성

### 단어 카드 (toeic_vocab.apkg)

| 앞면 | 뒷면 |
|------|------|
| 단어 + 품사 + 빈출도(★) | 한국어 뜻 + 유의어 + 기출 예문 |

- 기출 예문에서 해당 단어는 **볼드** 처리
- 태그: `hackers::day01~30` / `frequency::high/mid/low` / `기출등장::있음/없음`

### Part5 카드 (toeic_part5.apkg)

| 앞면 | 뒷면 |
|------|------|
| 문제 문장 + 선택지 A~D | 정답(초록) + 번역(초록) + 해설(주황) + 핵심 어휘 |

- 태그: `ets::vol1~5` / `category::품사/어휘/시제...`

---

## 모의고사

```bash
# Part5 모의고사 (기본 30문제, 즉시 채점 + 해설)
py exam/generate_part5_test.py --count 30 --vol 1

# 단어 퀴즈 (기본 50문제, Day별·레벨별 선택 가능)
py exam/generate_vocab_quiz.py --count 50 --day 1 --level 기초
```

생성된 HTML을 브라우저에서 열면 바로 풀이할 수 있습니다. 상세 옵션: `exam/README.md`

---

## 저작권 안내

ETS 기출문제 및 해커스 단어장은 저작권 자료입니다.

- **개인 학습 목적으로만 사용**
- Anki 덱·모의고사 HTML의 **외부 공유·배포 금지**
- 원본 PDF/Excel은 `00. Reference/` (git 미추적)
