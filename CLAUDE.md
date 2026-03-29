# CLAUDE.md — Toeic Brain

## 프로젝트 개요

TOEIC RC 학습 시스템. ETS 기출문제 1000제(5권, 총 5000문항)와 Hackers 노랭이 단어장을 연결하여 Anki 플래시카드 덱을 생성한다.

### 핵심 목표

1. **단어-기출 매핑**: 노랭이 단어장의 어휘가 기출 어디에 등장하는지 매핑
2. **Vocab Anki 덱**: 노랭이 단어장 기반 어휘 학습 덱 생성
3. **Part5 Anki 덱**: ETS 기출 Part5 문제 덱 생성

### 기술 스택

- Python 3.11+
- PDF 파싱: PyMuPDF, pdfplumber
- Anki 생성: genanki
- 데이터 처리: pandas
- NLP: spaCy
- 테스트: pytest

---

## 디렉토리 구조

```
toeic-brain/
├── CLAUDE.md              # 이 파일
├── data/
│   ├── raw/               # 원본 PDF (git 미추적)
│   │   ├── ets_vol1.pdf ~ ets_vol5.pdf
│   │   └── hackers_vocab.pdf
│   ├── processed/         # 파싱 완료 JSON
│   │   ├── questions/     # 기출문제 JSON (권별)
│   │   └── vocab/         # 단어장 JSON (day별)
│   └── mapped/            # 단어-기출 매핑 결과 JSON
├── scripts/
│   ├── extract/           # 데이터 추출
│   │   ├── extract_ets.py
│   │   ├── extract_vocab.py
│   │   └── ocr_pipeline.py
│   ├── process/           # 데이터 가공
│   │   ├── map_words.py
│   │   ├── categorize.py
│   │   └── validate.py
│   ├── anki/              # Anki 덱 생성
│   │   ├── generate_vocab_deck.py
│   │   ├── generate_part5_deck.py
│   │   ├── templates/     # 카드 HTML 템플릿
│   │   └── styles/        # 카드 CSS
│   └── analyze/           # 분석 스크립트
│       ├── word_frequency.py
│       ├── category_stats.py
│       └── coverage_report.py
├── output/
│   ├── anki/              # 생성된 .apkg 파일
│   └── reports/           # HTML 분석 리포트
├── tests/                 # pytest 테스트
├── .request/              # 작업지시서
└── .result/               # 완료 보고서
```

---

## 데이터 스키마

### Question JSON (기출문제)

파일 위치: `data/processed/questions/vol{N}_part{N}.json`

```json
{
  "id": "vol1_part5_001",
  "volume": 1,
  "part": 5,
  "question_number": 1,
  "sentence": "The manager ------- the report before the meeting.",
  "choices": ["(A) review", "(B) reviews", "(C) reviewed", "(D) reviewing"],
  "answer": "C",
  "category": "동사시제/태",
  "explanation": "과거 시제 문맥 (before the meeting)"
}
```

- `id` 형식: `vol{N}_part{N}_{NNN}` (예: `vol3_part6_042`)
- 필수 필드: id, volume, part, question_number, sentence, choices, answer, category

### Vocab JSON (단어장)

파일 위치: `data/processed/vocab/day{NN}.json`

```json
{
  "id": "hw_0001",
  "word": "revenue",
  "pos": "noun",
  "meaning_kr": "수익, 매출",
  "meaning_en": "income from business activities",
  "example_sentence": "The company's revenue increased by 20%.",
  "example_translation": "회사의 매출이 20% 증가했다.",
  "day": 1,
  "synonyms": ["income", "earnings", "proceeds"],
  "frequency": "high"
}
```

- `id` 형식: `hw_{NNNN}` (예: `hw_0523`)
- `pos` 값: noun, verb, adjective, adverb, preposition, conjunction 등
- `frequency` 값: high, mid, low

### Mapping JSON (단어-기출 매핑)

파일 위치: `data/mapped/word_mapping.json`

```json
{
  "word": "revenue",
  "vocab_id": "hw_0001",
  "occurrences": [
    {"question_id": "vol1_part5_023", "form": "revenue"},
    {"question_id": "vol2_part6_105", "form": "revenues"}
  ],
  "total_count": 2,
  "parts_appeared": [5, 6],
  "forms_seen": ["revenue", "revenues"]
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
- `[테스트]` — 테스트 추가/수정
- `[설정]` — 프로젝트 설정, 환경

### .gitignore 필수 항목

```
data/raw/          # 원본 PDF (저작권)
output/anki/*.apkg # 생성된 덱
.env
__pycache__/
```

---

## 저작권 및 주의사항

- **개인 학습 목적만 허용**: 이 프로젝트의 모든 산출물은 개인 학습용으로만 사용
- **외부 공유 금지**: 추출된 데이터, 생성된 Anki 덱의 외부 배포 금지
- **원본 git 미추적**: `data/raw/` 내 PDF 파일은 반드시 `.gitignore`에 포함
- ETS 기출문제 1000제, Hackers 노랭이 단어장의 저작권은 각 출판사에 귀속

---

## 개발 규칙

### 코드 스타일

- Python 표준: PEP 8
- 타입 힌트 사용 권장
- docstring: 한국어 가능, 매개변수/반환값은 영문 타입 표기

### 테스트

- `pytest` 사용
- 테스트 파일명: `test_*.py`
- 최소 커버리지: 추출/가공 모듈은 반드시 테스트 포함

### 데이터 처리 원칙

- 원본 PDF → JSON 변환은 `scripts/extract/`에서만 수행
- 추출 결과는 항상 `data/processed/`에 JSON으로 저장
- 매핑/분류 등 가공은 `scripts/process/`에서 수행
- Anki 덱 생성은 `scripts/anki/`에서 수행, 결과는 `output/anki/`에 저장
