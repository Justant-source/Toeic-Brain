# CLAUDE.md — Toeic Brain

## 프로젝트 개요

TOEIC RC 학습 시스템. ETS 기출문제 1000제(5권, 총 5000문항)와 Hackers 노랭이 단어장을 연결하여 Anki 플래시카드 덱과 모의고사 HTML을 생성한다.

### 핵심 목표

1. **단어-기출 매핑**: 노랭이 단어장의 어휘가 기출 어디에 등장하는지 매핑
2. **Vocab Anki 덱**: 노랭이 단어장 기반 어휘 학습 덱 생성
3. **Part5 Anki 덱**: ETS 기출 Part5 문제 덱 생성
4. **모의고사**: Part5 모의고사 + 단어장 퀴즈 HTML 생성

### 기술 스택

- Python 3.11+
- PDF 파싱: PyMuPDF, pdfplumber
- OCR: Tesseract + pytesseract
- NLP: spaCy (lemmatization)
- Anki 생성: genanki
- 데이터 처리: pandas

---

## 디렉토리 구조

```
Toeic Brain/
├── CLAUDE.md                          # 이 파일
├── README.md                          # 프로젝트 소개 (간소화)
├── config.yaml                        # 전역 설정
├── requirements.txt                   # Python 의존성
│
├── data/
│   ├── raw/                           # 원본 PDF/Excel (git 미추적)
│   ├── processed/                     # 파싱 완료 JSON
│   │   ├── questions/                 # vol{N}_part{5,6,7}.json
│   │   └── vocab/                     # day{NN}.json, all_vocab.json, chapter_map.json
│   └── mapped/                        # 핵심 매핑 결과만
│       └── word_ets_examples.json     # 유일한 핵심 매핑 파일 (28MB)
│
├── scripts/
│   ├── README.md                      # 스크립트 사용법 가이드
│   ├── utils/                         # 공유 유틸리티 모듈
│   │   ├── __init__.py
│   │   └── nlp.py                     # NLP 함수 (lemma, word family, inverted index)
│   ├── extract/                       # Phase 1: 원본 → JSON 추출
│   ├── process/                       # Phase 2: 가공·매핑·분류
│   ├── anki/                          # Phase 3: Anki 덱 생성
│   │   ├── templates/                 # 카드 HTML 템플릿
│   │   └── styles/                    # 카드 CSS
│   └── analyze/                       # Phase 4: 분석·검증
│
├── exam/                              # 모의고사 HTML 생성
│   ├── README.md                      # 사용법 가이드
│   ├── generate_part5_test.py         # Part5 모의고사 생성기
│   ├── generate_vocab_quiz.py         # 단어장 퀴즈 생성기
│   └── result/                        # 생성된 HTML 출력 (git 미추적)
│
├── output/
│   ├── anki/                          # 생성된 .apkg (git 미추적)
│   └── reports/                       # HTML 리포트
│
├── archive/                           # 사용 종료된 파일 보관
│   ├── scripts/                       # map_words.py, generate_obsidian_vault.py 등
│   └── data/                          # ocr_examples_vol*.json 등 중간 산출물
│
├── .request/                          # 작업지시서
├── .result/                           # 완료 보고서
└── .claude/                           # Claude Code 설정
```

---

## 데이터 스키마

### Question JSON (기출문제)

파일 위치: `data/processed/questions/vol{N}_part{N}.json`

```json
{
  "id": "vol1_test01_part5_101",
  "volume": 1,
  "test": 1,
  "part": 5,
  "question_number": 101,
  "sentence": "Ms. Durkin asked for volunteers to help ------- with the employee fitness program.",
  "choices": { "A": "she", "B": "her", "C": "hers", "D": "herself" },
  "answer": "B",
  "category": "인칭대명사의 격_목적격",
  "explanation": "빈칸은 to help의 목적어 자리로..."
}
```

- `id` 형식: `vol{N}_test{NN}_part{N}_{NNN}`
- `choices`: `{"A": "...", "B": "...", "C": "...", "D": "..."}` 딕셔너리
- 필수 필드: id, volume, test, part, question_number, sentence, choices, answer, category

### Vocab JSON (단어장)

파일 위치: `data/processed/vocab/day{NN}.json`

```json
{
  "word": "resume",
  "meaning_kr": "이력서",
  "day": 1,
  "level": "기초",
  "id": "hw_0001",
  "pos": ["noun", "verb"]
}
```

- `id` 형식: `hw_{NNNN}`
- `pos`: 문자열 리스트 (복수 POS 가능)
- `level` 값: "기초", "800점", "900점"

### Mapping JSON (단어-기출 매핑)

파일 위치: `data/mapped/word_ets_examples.json`

```json
{
  "resume": {
    "vocab_id": "hw_0001",
    "chapter": 1,
    "total_count": 49,
    "examples": [
      {
        "sentence": "Please submit your resume...",
        "source": "Vol 1, p.42",
        "volume": 1,
        "page": 42,
        "part": 5,
        "question_number": 123
      }
    ]
  }
}
```

---

## Part5 카테고리 분류

기출 Part5 문제는 다음 8개 카테고리로 분류한다:

| 카테고리 | 설명 | 예시 |
|---------|------|------|
| 품사 | 품사 선택 문제 | success / successful / successfully |
| 동사시제/태 | 시제, 능동/수동 | reviewed / is reviewed / has been reviewing |
| 접속사/전치사 | 접속사 vs 전치사 선택 | despite / although / because of |
| 관계대명사 | 관계사 선택 | who / which / that / whose |
| 어휘 | 문맥상 적절한 어휘 | appropriate / approximate / appreciable |
| 대명사 | 대명사 선택 | themselves / their / them |
| 비교급/최상급 | 비교 표현 | more / most / better / best |
| 기타문법 | 위 외 문법 사항 | 주어-동사 수일치, 병렬구조 등 |

> **참고**: 실제 데이터의 `category` 필드는 OCR에서 추출된 원문 그대로이므로 위 8개와 정확히 일치하지 않음. `exam/generate_part5_test.py`에서 키워드 기반으로 정규화 처리.

---

## Anki 태그 체계

### Vocab 덱 태그

```
hackers::day01 ~ hackers::day30       # 노랭이 단어장 Day
frequency::high / mid / low           # 출현 빈도
pos::verb / noun / adj / adv          # 품사
기출등장::있음 / 없음                    # 기출 매핑 여부
```

### Part5 덱 태그

```
ets::vol1 ~ ets::vol5                 # 출처 권
part::5                               # 파트
category::품사 / 어휘 / 시제 ...       # 카테고리
difficulty::easy / medium / hard       # 난이도
```

---

## 작업 흐름

1. `.request/`에 작업지시서 작성 (파일명: `YYYYMMDD_작업명.md`)
2. 작업 수행
3. `.result/`에 완료 보고서 작성 (파일명: `YYYYMMDD_작업명_결과.md`)

### 보고서 포함 사항

- 수행한 작업 요약
- 생성/수정된 파일 목록
- 데이터 통계 (처리 건수, 성공/실패)
- 발견된 이슈 및 후속 작업

---

## Git 컨벤션

### 커밋 메시지

한국어 Conventional 형식:

```
[영역] 작업내용 요약
```

영역 예시:
- `[추출]` — PDF 파싱, 데이터 추출
- `[가공]` — 매핑, 분류, 검증
- `[Anki]` — 덱 생성, 템플릿, 스타일
- `[분석]` — 통계, 리포트
- `[기능]` — 모의고사 등 신규 기능
- `[리팩토링]` — 구조 정리, 모듈 분리
- `[문서]` — README, 가이드 작성
- `[테스트]` — 테스트 추가/수정
- `[설정]` — 프로젝트 설정, 환경

### .gitignore 필수 항목

```
data/raw/          # 원본 PDF (저작권)
output/anki/*.apkg # 생성된 덱
tessdata/          # OCR 학습 데이터 (29MB)
exam/result/       # 모의고사 HTML 결과물
archive/data/      # 아카이브 데이터
.env
__pycache__/
```

---

## 저작권 및 주의사항

- **개인 학습 목적만 허용**: 이 프로젝트의 모든 산출물은 개인 학습용으로만 사용
- **외부 공유 금지**: 추출된 데이터, 생성된 Anki 덱, 모의고사 HTML의 외부 배포 금지
- **원본 git 미추적**: `data/raw/` 내 PDF 파일은 반드시 `.gitignore`에 포함
- ETS 기출문제 1000제, Hackers 노랭이 단어장의 저작권은 각 출판사에 귀속

---

## 개발 규칙

### 코드 스타일

- Python 표준: PEP 8
- 타입 힌트 사용 권장
- docstring: 한국어 가능, 매개변수/반환값은 영문 타입 표기

### 데이터 처리 원칙

- 원본 PDF → JSON 변환은 `scripts/extract/`에서만 수행
- 추출 결과는 항상 `data/processed/`에 JSON으로 저장
- 매핑/분류 등 가공은 `scripts/process/`에서 수행
- Anki 덱 생성은 `scripts/anki/`에서 수행, 결과는 `output/anki/`에 저장
- 모의고사 생성은 `exam/`에서 수행, 결과는 `exam/result/`에 저장
