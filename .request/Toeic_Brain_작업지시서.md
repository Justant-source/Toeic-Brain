# Toeic Brain 프로젝트 작업지시서

> Flight Brain 프로젝트 패턴을 기반으로 한 토익 RC 학습 시스템

---

## 1. 프로젝트 개요

### 목적
ETS 기출문제 1000제(1~5권, 총 5,000문제)와 해커스 노랭이 단어장을 체계적으로 연결하여, Anki 플래시카드 기반의 토익 RC 학습 시스템을 구축한다.

### 핵심 목표
1. **단어-기출 매핑**: 노랭이 단어장의 각 단어가 기출문제에서 어떤 문맥으로 출제되었는지 추적
2. **Anki 단어장 덱**: 노랭이 단어 + 기출 예문을 결합한 Anki 덱 생성
3. **Anki Part5 문제 덱**: Part5 기출문제를 Anki 카드로 변환하여 반복 풀이

---

## 2. 데이터 소스

### 2-1. ETS 기출문제 1000제 (5권)

| 권 | 파일명 규칙 (예시) | 문제 수 |
|---|---|---|
| 1권 | `ets_1000_vol1.*` | 1,000 |
| 2권 | `ets_1000_vol2.*` | 1,000 |
| 3권 | `ets_1000_vol3.*` | 1,000 |
| 4권 | `ets_1000_vol4.*` | 1,000 |
| 5권 | `ets_1000_vol5.*` | 1,000 |

**파일 형식 확인 필요**: PDF / 스캔 이미지 / 텍스트 기반 등
- 스캔 이미지인 경우 → OCR 파이프라인 필요
- 텍스트 기반인 경우 → 파싱 스크립트로 직접 추출

**추출할 데이터 구조 (문제당)**:
```json
{
  "id": "vol1_part5_001",
  "volume": 1,
  "part": 5,
  "question_number": 1,
  "sentence": "The company will ------- its new policy next month.",
  "choices": {
    "A": "implement",
    "B": "implementation",
    "C": "implementing",
    "D": "implemented"
  },
  "answer": "A",
  "category": "품사",
  "explanation": "동사 자리에 동사 원형이 와야 한다 (will + 동사원형)"
}
```

### 2-2. 해커스 노랭이 단어장

**추출할 데이터 구조 (단어당)**:
```json
{
  "id": "hw_0001",
  "word": "implement",
  "pos": "v.",
  "meaning_kr": "시행하다, 실행하다",
  "meaning_en": "to put into effect",
  "example_sentence": "The new policy was implemented last quarter.",
  "example_translation": "새로운 정책이 지난 분기에 시행되었다.",
  "day": 1,
  "synonyms": ["execute", "carry out", "enforce"],
  "frequency": "★★★"
}
```

---

## 3. 프로젝트 구조

```
toeic-brain/
├── README.md
├── requirements.txt
├── config.yaml                    # 전역 설정
│
├── data/
│   ├── raw/                       # 원본 파일 (git 미추적)
│   │   ├── ets_vol1/
│   │   ├── ets_vol2/
│   │   ├── ets_vol3/
│   │   ├── ets_vol4/
│   │   ├── ets_vol5/
│   │   └── hackers_vocab/
│   │
│   ├── processed/                 # 파싱 완료된 JSON
│   │   ├── questions/
│   │   │   ├── vol1_part5.json
│   │   │   ├── vol1_part6.json
│   │   │   ├── vol1_part7.json
│   │   │   └── ...
│   │   └── vocab/
│   │       └── hackers_vocab.json
│   │
│   └── mapped/                    # 단어-기출 매핑 결과
│       └── word_question_map.json
│
├── scripts/
│   ├── extract/                   # 데이터 추출
│   │   ├── extract_ets.py         # ETS 기출문제 파싱
│   │   ├── extract_vocab.py       # 노랭이 단어장 파싱
│   │   └── ocr_pipeline.py        # OCR 필요 시
│   │
│   ├── process/                   # 데이터 가공
│   │   ├── map_words.py           # 단어-기출 매핑
│   │   ├── categorize.py          # 문제 유형 분류 (품사/어휘/문법)
│   │   └── validate.py            # 데이터 무결성 검증
│   │
│   ├── anki/                      # Anki 덱 생성
│   │   ├── generate_vocab_deck.py # 단어장 Anki 덱
│   │   ├── generate_part5_deck.py # Part5 문제 Anki 덱
│   │   ├── templates/             # Anki 카드 HTML/CSS 템플릿
│   │   │   ├── vocab_front.html
│   │   │   ├── vocab_back.html
│   │   │   ├── part5_front.html
│   │   │   └── part5_back.html
│   │   └── styles/
│   │       └── card_style.css
│   │
│   └── analyze/                   # 분석 도구
│       ├── word_frequency.py      # 기출 빈출 단어 분석
│       ├── category_stats.py      # 유형별 출제 통계
│       └── coverage_report.py     # 노랭이 단어의 기출 커버리지
│
├── output/                        # 최종 산출물
│   ├── anki/
│   │   ├── toeic_vocab.apkg       # 단어장 Anki 덱
│   │   └── toeic_part5.apkg       # Part5 문제 Anki 덱
│   └── reports/
│       ├── coverage_report.html   # 커버리지 리포트
│       └── frequency_analysis.html
│
└── tests/
    ├── test_extract.py
    ├── test_mapping.py
    └── test_anki.py
```

---

## 4. 작업 단계 (Phase)

### Phase 1: 데이터 추출 (Extract)

#### 1-1. ETS 기출문제 추출
- 원본 파일 형식 확인 (PDF/이미지/텍스트)
- Part별 문제 파싱 (Part5 / Part6 / Part7)
- JSON 구조로 정규화
- 정답 및 해설 매핑

**스크립트**: `scripts/extract/extract_ets.py`

**입력**: `data/raw/ets_vol{1-5}/`
**출력**: `data/processed/questions/vol{1-5}_part{5,6,7}.json`

#### 1-2. 노랭이 단어장 추출
- 단어, 품사, 뜻, 예문 파싱
- Day별 그룹핑 보존
- 동의어/유의어 추출

**스크립트**: `scripts/extract/extract_vocab.py`

**입력**: `data/raw/hackers_vocab/`
**출력**: `data/processed/vocab/hackers_vocab.json`

---

### Phase 2: 데이터 가공 (Process)

#### 2-1. 단어-기출 매핑
노랭이 단어장의 각 단어에 대해 기출문제에서의 출현을 추적한다.

**매핑 로직**:
1. 단어의 원형(lemma) 기준 매칭
2. 파생어/변형 포함 (implement → implementation, implementing 등)
3. 동의어 그룹 확장 매칭

**매핑 결과 구조**:
```json
{
  "word": "implement",
  "vocab_id": "hw_0001",
  "occurrences": [
    {
      "question_id": "vol1_part5_001",
      "context": "The company will ------- its new policy",
      "as_answer": true,
      "as_choice": "A",
      "form_used": "implement"
    },
    {
      "question_id": "vol2_part5_087",
      "context": "The ------- of the new system took three months",
      "as_answer": true,
      "as_choice": "B",
      "form_used": "implementation"
    }
  ],
  "total_count": 2,
  "parts_appeared": ["Part5"],
  "forms_seen": ["implement", "implementation"]
}
```

**스크립트**: `scripts/process/map_words.py`

#### 2-2. 문제 유형 분류
Part5 문제를 유형별로 태깅한다.

**분류 카테고리**:
- 품사 (Parts of Speech)
- 동사 시제/태 (Tense/Voice)
- 접속사/전치사 (Conjunction/Preposition)
- 관계대명사 (Relative Pronoun)
- 어휘 (Vocabulary)
- 대명사 (Pronoun)
- 비교급/최상급 (Comparison)
- 기타 문법 (Other Grammar)

**스크립트**: `scripts/process/categorize.py`

---

### Phase 3: Anki 덱 생성 (Generate)

#### 3-1. 단어장 Anki 덱

**카드 구성 (앞면)**:
```
┌─────────────────────────────────┐
│          implement              │
│            (v.)                 │
│                                 │
│  ★★★  기출 2회                  │
└─────────────────────────────────┘
```

**카드 구성 (뒷면)**:
```
┌─────────────────────────────────┐
│  implement (v.)                 │
│  시행하다, 실행하다                │
│                                 │
│  ─── 기출 예문 ───               │
│  ❶ The company will ______      │
│     its new policy next month.  │
│     → implement (동사원형)       │
│                                 │
│  ❷ The ______ of the new system │
│     took three months.          │
│     → implementation (명사형)    │
│                                 │
│  ─── 노랭이 예문 ───             │
│  The new policy was implemented │
│  last quarter.                  │
│                                 │
│  유의어: execute, carry out      │
│  Day 1 | Hackers #0001          │
└─────────────────────────────────┘
```

**Anki 태그 체계**:
- `hackers::day01`, `hackers::day02`, ...
- `frequency::high`, `frequency::mid`, `frequency::low`
- `pos::verb`, `pos::noun`, `pos::adj`, ...
- `기출등장::있음`, `기출등장::없음`

**스크립트**: `scripts/anki/generate_vocab_deck.py`
**출력**: `output/anki/toeic_vocab.apkg`

#### 3-2. Part5 문제 Anki 덱

**카드 구성 (앞면)**:
```
┌─────────────────────────────────┐
│  [Part5] Vol.1 - Q.001          │
│  유형: 품사                      │
│                                 │
│  The company will ------- its   │
│  new policy next month.         │
│                                 │
│  (A) implement                  │
│  (B) implementation             │
│  (C) implementing               │
│  (D) implemented                │
│                                 │
│  [A] [B] [C] [D]  ← 탭 선택     │
└─────────────────────────────────┘
```

**카드 구성 (뒷면)**:
```
┌─────────────────────────────────┐
│  정답: (A) implement            │
│                                 │
│  ─── 해설 ───                   │
│  will + 동사원형 구조.            │
│  빈칸은 조동사 will 뒤이므로      │
│  동사 원형 implement가 정답.      │
│                                 │
│  ─── 어휘 ───                   │
│  implement: 시행하다             │
│  policy: 정책                   │
│                                 │
│  Vol.1 | Part5 | #001 | 품사    │
└─────────────────────────────────┘
```

**Anki 태그 체계**:
- `ets::vol1`, `ets::vol2`, ...
- `part::5`
- `category::품사`, `category::어휘`, `category::시제`, ...
- `difficulty::easy`, `difficulty::medium`, `difficulty::hard`

**스크립트**: `scripts/anki/generate_part5_deck.py`
**출력**: `output/anki/toeic_part5.apkg`

---

### Phase 4: 분석 & 리포트 (Analyze)

#### 4-1. 커버리지 리포트
- 노랭이 단어 중 기출에 등장한 비율
- Day별 기출 커버리지
- 기출에는 나왔지만 노랭이에 없는 단어 목록 (보충 학습용)

#### 4-2. 빈출 분석
- 5권 전체 기준 가장 많이 출제된 단어 Top 100
- 유형별 출제 비율 (품사 몇%, 어휘 몇% 등)
- 권별 출제 경향 변화

---

## 5. 기술 스택

| 영역 | 기술 |
|---|---|
| 언어 | Python 3.11+ |
| PDF 파싱 | PyMuPDF (fitz) / pdfplumber |
| OCR | Tesseract + pytesseract (필요 시) |
| NLP | spaCy (lemmatization), nltk |
| Anki 덱 생성 | genanki |
| 데이터 처리 | pandas |
| 설정 관리 | PyYAML |
| 테스트 | pytest |
| 리포트 | Jinja2 + HTML |

---

## 6. Anki 카드 디자인 가이드

### 공통 스타일
```css
/* Flight Brain 패턴 차용 - 깔끔한 학습 카드 */
.card {
  font-family: 'Pretendard', 'Apple SD Gothic Neo', sans-serif;
  max-width: 600px;
  margin: 0 auto;
  padding: 20px;
  background: #FAFAFA;
  border-radius: 12px;
}

.word-main {
  font-size: 28px;
  font-weight: 700;
  color: #1A1A1A;
  text-align: center;
}

.meaning-kr {
  font-size: 20px;
  color: #333;
  margin-top: 8px;
}

.example-sentence {
  background: #F0F4F8;
  padding: 12px 16px;
  border-left: 4px solid #3B82F6;
  border-radius: 4px;
  margin: 12px 0;
  font-size: 15px;
  line-height: 1.6;
}

.tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  margin: 2px;
}

.tag-correct { background: #D1FAE5; color: #065F46; }
.tag-category { background: #DBEAFE; color: #1E40AF; }
.tag-volume { background: #F3E8FF; color: #6B21A8; }
```

### Part5 인터랙티브 요소
- JavaScript로 선택지 클릭 시 정답/오답 피드백
- 오답 시 해당 선택지가 왜 틀린지 표시
- 정답률 추적 (Anki 자체 기능 활용)

---

## 7. 실행 순서 (Quick Start)

```bash
# 1. 환경 설정
pip install -r requirements.txt

# 2. 원본 데이터를 data/raw/에 배치

# 3. 데이터 추출
python scripts/extract/extract_vocab.py
python scripts/extract/extract_ets.py

# 4. 데이터 검증
python scripts/process/validate.py

# 5. 단어-기출 매핑
python scripts/process/map_words.py

# 6. 문제 유형 분류
python scripts/process/categorize.py

# 7. Anki 덱 생성
python scripts/anki/generate_vocab_deck.py
python scripts/anki/generate_part5_deck.py

# 8. 분석 리포트
python scripts/analyze/coverage_report.py
python scripts/analyze/word_frequency.py
```

---

## 8. 우선순위 및 마일스톤

| 순서 | 작업 | 중요도 | 예상 소요 |
|---|---|---|---|
| M1 | 노랭이 단어장 추출 & JSON 변환 | ★★★ | 1~2일 |
| M2 | ETS Part5 문제 추출 (1권부터) | ★★★ | 2~3일 |
| M3 | 단어장 Anki 덱 생성 (기본) | ★★★ | 1일 |
| M4 | Part5 Anki 덱 생성 (기본) | ★★★ | 1일 |
| M5 | 단어-기출 매핑 | ★★☆ | 2~3일 |
| M6 | 단어장 Anki 덱 고도화 (기출 예문 포함) | ★★☆ | 1~2일 |
| M7 | ETS 2~5권 추출 확장 | ★★☆ | 3~5일 |
| M8 | 문제 유형 자동 분류 | ★☆☆ | 2~3일 |
| M9 | 커버리지/빈출 분석 리포트 | ★☆☆ | 1~2일 |

---

## 9. 주의사항

### 저작권
- ETS 기출문제 및 해커스 단어장은 저작권이 있는 자료
- 개인 학습 목적으로만 사용하며 Anki 덱은 외부 공유 금지
- 원본 파일은 git에 커밋하지 않음 (`.gitignore`에 `data/raw/` 추가)

### 데이터 품질
- OCR 추출 시 오탈자 검수 필수 (특히 특수문자, 빈칸 표시)
- 정답 매핑 오류 검증 스크립트 포함
- 추출 후 샘플링 검수 (권당 최소 50문제 수동 확인)

### Anki 호환성
- `.apkg` 형식으로 생성 (Anki 2.1+ 호환)
- 미디어 파일 포함 시 상대 경로 사용
- 카드 템플릿은 AnkiDroid/AnkiMobile에서도 정상 렌더링 확인

---

## 10. Flight Brain 패턴 차용 포인트

> 아래는 Flight Brain에서 검증된 패턴을 Toeic Brain에 적용하는 방식입니다.
> Flight Brain 프로젝트 파일을 공유해주시면 더 정확하게 맞출 수 있습니다.

| Flight Brain 패턴 | Toeic Brain 적용 |
|---|---|
| 원본 데이터 → JSON 정규화 | ETS PDF → 문제 JSON / 단어장 → 단어 JSON |
| 데이터 간 크로스레퍼런스 | 단어 ↔ 기출문제 매핑 |
| Anki 덱 자동 생성 | 단어장 덱 + Part5 문제 덱 |
| 카드 템플릿 커스터마이징 | 앞면/뒷면 HTML+CSS 템플릿 |
| 태그 기반 필터링 | Day별 / 유형별 / 권별 태그 |
| 분석 리포트 | 커버리지 / 빈출 / 유형별 통계 |

---

*작성일: 2026-03-29*
*프로젝트: Toeic Brain v1.0*
