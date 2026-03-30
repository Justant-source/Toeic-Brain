# Toeic Brain

> ETS 기출문제 1000제 (5권, 총 5,000문제) + 해커스 노랭이 단어장 → Anki & Obsidian 기반 토익 RC 학습 시스템

---

## 프로젝트 목표

1. **단어-기출 매핑**: 노랭이 단어가 ETS 기출에서 어떻게 출제되었는지 추적
2. **Anki 단어장 덱**: 노랭이 단어 + 기출 예문을 결합한 플래시카드
3. **Anki Part5 문제 덱**: Part5 기출문제 반복 풀이용 플래시카드
4. **Obsidian Vault**: 단어별 Atomic Note + 기출 예문 (900점 완성 단어)

---

## 기술 스택

| 영역 | 기술 |
|---|---|
| 언어 | Python 3.11+ |
| PDF 파싱 | PyMuPDF (fitz), pdfplumber |
| OCR | Tesseract + pytesseract |
| NLP | spaCy (lemmatization), nltk (WordNet) |
| Anki 덱 생성 | genanki |
| 데이터 처리 | pandas |
| 설정 관리 | PyYAML |
| 리포트 | Jinja2 + HTML |
| LLM | Claude API (품사 교정) |
| 테스트 | pytest |

---

## 데이터 소스

| 소스 | 설명 | 위치 |
|---|---|---|
| ETS 기출 1000제 (5권) | 문제 PDF + 해설 PDF | `data/raw/question/`, `data/raw/answer/` |
| 해커스 노랭이 단어장 | 단어장 PDF | `data/raw/hackers_vocab.pdf` |
| 해커스 엑셀 | 기초/800점/900점 단어 | `data/raw/voca/*.xlsx` |

---

## 프로젝트 구조

```
Toeic Brain/
├── CLAUDE.md                          # Claude Code 프로젝트 지시서
├── README.md                          # 이 파일
├── config.yaml                        # 전역 설정 (경로, 덱 ID, 카테고리 등)
├── requirements.txt                   # Python 의존성
│
├── data/
│   ├── raw/                           # 원본 파일 (git 미추적)
│   │   ├── question/                  # ETS 문제 PDF (vol1~vol5)
│   │   │   └── ocr_cache/             # 문제 PDF OCR 캐시 (vol별)
│   │   ├── answer/                    # ETS 해설 PDF
│   │   │   ├── extracted/             # 해설 추출 중간 결과
│   │   │   ├── ocr_cache/             # 해설 PDF OCR 캐시 (vol별)
│   │   │   └── rendered/              # OCR용 렌더링 이미지
│   │   ├── voca/                      # 노랭이 엑셀 (기초/800점/900점)
│   │   └── hackers_vocab.pdf          # 노랭이 단어장 원본 PDF
│   │
│   ├── processed/                     # 파싱 완료된 JSON
│   │   ├── questions/                 # 기출문제 (vol1~5 × part5~7)
│   │   │   ├── vol{N}_part5.json      # Part5: 구조화된 문제 데이터
│   │   │   ├── vol{N}_part6.json      # Part6: raw_text 지문 데이터
│   │   │   └── vol{N}_part7.json      # Part7: raw_text 지문 데이터
│   │   └── vocab/                     # 단어장 데이터
│   │       ├── day01.json ~ day30.json    # Day별 단어 JSON
│   │       ├── all_vocab.json             # 전체 단어 통합 JSON
│   │       └── chapter_map.json           # Chapter별 단어 구조 (Obsidian용)
│   │
│   └── mapped/                        # 단어-기출 매핑 결과
│       ├── word_ets_examples.json     # 단어별 기출 예문 (77만행, 핵심 매핑)
│       ├── word_question_map.json     # 단어-문제 매핑 (현재 비어있음)
│       └── ocr_examples_vol{N}.json   # 권별 OCR 기반 예문 중간 결과
│
├── scripts/
│   ├── extract/                       # Phase 1: 원본 → JSON 추출
│   ├── process/                       # Phase 2: 가공·매핑·분류
│   ├── generate/                      # Phase 3: Obsidian Vault 생성
│   ├── anki/                          # Phase 3: Anki 덱 생성
│   ├── analyze/                       # Phase 4: 분석·검증
│   └── patch_missing_explanations.py  # 일회성 패치 스크립트
│
├── output/
│   ├── anki/                          # 생성된 .apkg 파일 (git 미추적)
│   │   ├── toeic_vocab.apkg
│   │   └── toeic_part5.apkg
│   └── reports/                       # HTML 분석 리포트
│       ├── category_stats.html
│       ├── coverage_report.html
│       └── frequency_analysis.html
│
├── vault/                             # Obsidian Vault (git 미추적, 비어있음)
├── tessdata/                          # Tesseract OCR 학습 데이터
├── tests/                             # pytest 테스트
│
├── .request/                          # 작업지시서 (git 미추적)
├── .secret/                           # API 키 등 (git 미추적)
├── .claude/                           # Claude Code 설정
├── .idea/                             # PyCharm 설정 (git 미추적)
└── .obsidian/                         # Obsidian 설정 (git 미추적)
```

---

## 스크립트 상세 설명

### `scripts/extract/` — 데이터 추출 (Phase 1)

원본 PDF/Excel에서 구조화된 JSON을 추출하는 스크립트들.

| 파일 | 역할 | 입력 → 출력 | 상태 |
|---|---|---|---|
| `extract_ets.py` | ETS PDF에서 Part5/6/7 문제 추출. 섹션 경계 탐지, 빈칸 마커(-------) 파싱, 선택지 추출 | `data/raw/question/*.pdf` → `data/processed/questions/vol{N}_part{N}.json` | **활성** |
| `extract_answers.py` | ETS 해설 PDF에서 정답·해설 추출. OCR + 정답 오류 보정 (8→B, 0→D 등) | `data/raw/answer/*.pdf` → 문제 JSON에 answer/explanation 병합 | **활성** |
| `extract_vocab.py` | 노랭이 PDF에서 단어 추출 (word, POS, 뜻, 예문, Day, 유의어 등). OCR 캐싱 지원 | `data/raw/hackers_vocab.pdf` → `data/processed/vocab/day{NN}.json` | **활성** |
| `extract_vocab_excel.py` | 노랭이 엑셀에서 단어 추출 (기초/800점/900점 레벨별 처리) | `data/raw/voca/*.xlsx` → `data/processed/vocab/` | **활성** |
| `extract_chapters.py` | 노랭이 PDF에서 Chapter 구조 + 900점 단어 추출 (Obsidian Vault 전용) | `data/raw/hackers_vocab.pdf` → `data/processed/vocab/chapter_map.json` | **활성** |
| `ocr_question_pdf.py` | ETS 문제 PDF 텍스트 추출 (PyMuPDF → Tesseract 폴백). 페이지별 OCR 캐싱 | `data/raw/question/*.pdf` → `data/raw/question/ocr_cache/` | **활성** |
| `ocr_answer_pdf.py` | ETS 해설 PDF에 OCR 투명 텍스트 레이어 삽입. 검색 가능 PDF 생성 | `data/raw/answer/*.pdf` → 검색 가능 PDF | **활성** |
| `ocr_utils.py` | OCR 공통 유틸리티 (페이지 렌더링, Tesseract 호출, 의존성 체크) | — (다른 스크립트에서 import) | **활성** (공유 모듈) |
| `ocr_pipeline.py` | 범용 OCR 파이프라인 (docstring만 존재, 구현 없음) | — | **미사용** (빈 스텁) |

### `scripts/process/` — 데이터 가공 (Phase 2)

추출된 JSON을 가공·매핑·분류하는 스크립트들.

| 파일 | 역할 | 입력 → 출력 | 상태 |
|---|---|---|---|
| `validate.py` | 문제·단어 JSON 무결성 검증. 필수 필드, 데이터 타입, 이상값 체크 + 자동 수정 | `data/processed/**/*.json` → 검증 리포트 (콘솔) | **활성** |
| `map_words.py` | 노랭이 단어 → Part5 문제 매핑. 단어 패밀리 구축 (lemma + 굴절형 + 동의어), 역인덱스 검색 | `vocab/*.json` + `questions/*.json` → `data/mapped/word_question_map.json` | **활성** (but 출력 파일 현재 비어있음) |
| `categorize.py` | Part5 문제 유형 자동 분류. 선택지 패턴 분석으로 8개 카테고리 배정 (품사/시제/어휘 등) | `vol{N}_part5.json` → 같은 파일에 `category` 필드 추가 | **활성** |
| `find_ets_examples.py` | 단어별 ETS 기출 예문 전수 검색 (Part5/6/7). spaCy lemmatization + 단어 패밀리 확장 | `chapter_map.json` + `questions/*.json` → `data/mapped/word_ets_examples.json` | **활성** (핵심 매핑) |
| `find_examples_from_ocr_cache.py` | OCR 캐시 텍스트에서 직접 예문 검색 (구조화 JSON 대신 raw OCR 사용) | `data/raw/question/ocr_cache/` → `data/mapped/ocr_examples_vol{N}.json` | **활성** (보완 경로) |
| `merge_ocr_examples.py` | 권별 OCR 예문 JSON을 `word_ets_examples.json`에 병합. 중복 제거 포함 | `ocr_examples_vol{N}.json` → `word_ets_examples.json` 업데이트 | **활성** |
| `add_pos.py` | NLTK WordNet + 영어 접미사 패턴으로 단어에 POS 태그 자동 부여 | `day{NN}.json` → 같은 파일에 `pos` 필드 추가 | **활성** |
| `fix_pos.py` | Claude API를 사용한 POS 교정. 배치 처리로 오류 POS 수정 | `day{NN}.json` → POS 교정 JSON | **활성** |
| `apply_pos_corrections.py` | 여러 POS 교정 파일을 합쳐서 단어 JSON에 일괄 적용 | 교정 JSON → `day{NN}.json` 업데이트 | **활성** |
| `create_chapter_map.py` | `all_vocab.json`에서 Day/Chapter별 단어 그룹핑 → `chapter_map.json` 생성 | `all_vocab.json` → `chapter_map.json` | **활성** |

### `scripts/generate/` — Obsidian Vault 생성 (Phase 3-A)

| 파일 | 역할 | 입력 → 출력 | 상태 |
|---|---|---|---|
| `generate_obsidian_vault.py` | Chapter 구조 + 기출 예문 데이터 결합 → 단어별 Atomic MD 파일 생성. YAML frontmatter + Vol별 예문 그룹화 | `chapter_map.json` + `word_ets_examples.json` → `vault/ch NN. 주제/900점 완성/*.md` | **활성** (vault/ 현재 비어있음) |

### `scripts/anki/` — Anki 덱 생성 (Phase 3-B)

| 파일 | 역할 | 입력 → 출력 | 상태 |
|---|---|---|---|
| `generate_vocab_deck.py` | 노랭이 단어 + 기출 예문 → Anki 단어장 덱 생성. Day/빈도/POS 태그 부여 | `vocab/*.json` + `word_ets_examples.json` → `output/anki/toeic_vocab.apkg` | **활성** |
| `generate_part5_deck.py` | Part5 문제 → Anki 문제 덱 생성. 권/카테고리/난이도 태그 부여, 인터랙티브 선택지 | `vol{N}_part5.json` → `output/anki/toeic_part5.apkg` | **활성** |
| `templates/vocab_front.html` | 단어 카드 앞면 HTML 템플릿 | — | **활성** |
| `templates/vocab_back.html` | 단어 카드 뒷면 HTML 템플릿 | — | **활성** |
| `templates/part5_front.html` | Part5 카드 앞면 HTML 템플릿 | — | **활성** |
| `templates/part5_back.html` | Part5 카드 뒷면 HTML 템플릿 | — | **활성** |
| `styles/card_style.css` | Anki 카드 공통 CSS 스타일 | — | **활성** |

### `scripts/analyze/` — 분석·검증 (Phase 4)

| 파일 | 역할 | 입력 → 출력 | 상태 |
|---|---|---|---|
| `category_stats.py` | Part5 카테고리별 출제 분포 통계. 전체/권별 막대 그래프 출력 | `vol{N}_part5.json` → `output/reports/category_stats.html` | **활성** |
| `coverage_report.py` | 노랭이 단어의 기출 커버리지 분석. Day별 등장률 + 미등장 단어 목록 | `vocab/*.json` + `questions/*.json` → `output/reports/coverage_report.html` | **활성** |
| `word_frequency.py` | ETS 5권 전체 빈출 단어 Top 100 분석. 불용어 필터링, 권별 빈도 비교 | `questions/*.json` → `output/reports/frequency_analysis.html` | **활성** |
| `validate_vault.py` | Obsidian Vault MD 파일 무결성 검증. frontmatter 필드 체크, 통계 리포트 | `vault/**/*.md` → 검증 리포트 (콘솔/HTML) | **활성** |

### `scripts/` (루트) — 일회성 스크립트

| 파일 | 역할 | 상태 |
|---|---|---|
| `patch_missing_explanations.py` | OCR이 깨진 해설을 수동 패치. 특정 문제 ID 하드코딩하여 해설 PDF에서 재추출 후 JSON에 병합 | **미사용** (일회성, 이미 실행 완료) |

---

## 테스트

| 파일 | 테스트 대상 |
|---|---|
| `tests/test_extract.py` | 빈칸 정규화, 푸터 제거, 문제 파싱 로직 |
| `tests/test_mapping.py` | lemmatization 폴백, 단어 패밀리 구축, 역인덱스 생성 |
| `tests/test_anki.py` | 템플릿/CSS 존재 확인, `load_text` 헬퍼, Anki 모델 빌드 |

```bash
pytest tests/
```

---

## 데이터 파일 상세

### `data/processed/questions/vol{N}_part5.json`

Part5 구조화 문제 데이터. 각 문제에 sentence, choices, answer, category, explanation 포함.

### `data/processed/questions/vol{N}_part6.json`, `vol{N}_part7.json`

Part6/7 데이터. `raw_text` 형태의 지문 텍스트 (Part5처럼 구조화되지 않음).

### `data/processed/vocab/day{NN}.json`

Day(1~30)별 단어 목록. word, pos, meaning_kr, example_sentence, synonyms 등 포함.

### `data/processed/vocab/all_vocab.json`

전체 단어 통합 파일 (day01~day30 합본, 약 42,000행).

### `data/processed/vocab/chapter_map.json`

Chapter별 단어 구조 (Obsidian Vault 생성용). chapter, title, words[] 구조.

### `data/mapped/word_ets_examples.json`

핵심 매핑 파일 (약 77만행). 단어별로 ETS 5권 전체에서 발견된 모든 예문 + 출처(Vol/Test/Q) 수록.

### `data/mapped/ocr_examples_vol{N}.json`

OCR 캐시 기반 예문 검색 중간 결과 (권별). `merge_ocr_examples.py`로 `word_ets_examples.json`에 병합.

### `data/mapped/word_question_map.json`

`map_words.py`의 출력 대상이나, **현재 비어있음** (0 bytes). `word_ets_examples.json`이 사실상 이 역할을 대체.

---

## 미사용·검토 필요 파일

리팩토링 시 정리 또는 제거를 검토할 파일들:

| 파일 | 사유 |
|---|---|
| `scripts/extract/ocr_pipeline.py` | **빈 스텁**: docstring만 존재, 구현 코드 없음. `ocr_utils.py`와 `ocr_question_pdf.py`가 실질적인 OCR 처리 담당 |
| `scripts/patch_missing_explanations.py` | **일회성**: "One-time script"로 명시. 이미 실행 완료되어 역할 종료. 히스토리 보존만 필요 |
| `data/mapped/word_question_map.json` | **비어있음**: `map_words.py`의 출력이지만 0바이트. `word_ets_examples.json`이 대체 역할 수행 중. `map_words.py` 자체의 필요성도 검토 필요 |
| `kor.traineddata` (루트) | **중복/오배치**: `tessdata/kor.traineddata`에도 동일 파일 존재. 루트의 파일은 git staged 후 삭제된 상태 (AD) |

### 중복·유사 기능 정리 검토

| 영역 | 파일들 | 검토 포인트 |
|---|---|---|
| 단어 추출 | `extract_vocab.py` vs `extract_vocab_excel.py` vs `extract_chapters.py` | 3개 스크립트가 각각 다른 소스(PDF/Excel)와 다른 목적(Day별/Chapter별)으로 단어 추출. 공통 로직 통합 가능성 검토 |
| 예문 검색 | `find_ets_examples.py` vs `find_examples_from_ocr_cache.py` | 동일 목적(단어→예문 매핑)이지만 데이터 소스가 다름 (구조화 JSON vs raw OCR). 하나로 통합 가능한지 검토 |
| 단어-문제 매핑 | `map_words.py` vs `find_ets_examples.py` | 기능이 상당 부분 겹침. `map_words.py`의 출력(`word_question_map.json`)이 비어있고, `find_ets_examples.py`가 실질적 매핑 담당. `map_words.py`의 유틸 함수만 모듈로 분리하고 스크립트 자체는 제거 검토 |
| POS 처리 | `add_pos.py` → `fix_pos.py` → `apply_pos_corrections.py` | 3단계 POS 파이프라인. 단일 스크립트로 통합 가능성 검토 |

---

## 실행 순서

### 전체 파이프라인

```bash
# 0. 환경 설정
pip install -r requirements.txt
# 원본 PDF/Excel을 data/raw/에 배치

# ── Phase 1: 데이터 추출 ──
python scripts/extract/extract_vocab.py          # 노랭이 PDF → day01~30.json
python scripts/extract/extract_vocab_excel.py     # 노랭이 Excel → all_vocab.json
python scripts/extract/extract_chapters.py        # 노랭이 PDF → chapter_map.json
python scripts/extract/extract_ets.py             # ETS PDF → vol{N}_part{5,6,7}.json
python scripts/extract/extract_answers.py         # 해설 PDF → 정답/해설 병합

# ── Phase 2: 가공·매핑 ──
python scripts/process/validate.py                # JSON 무결성 검증
python scripts/process/add_pos.py                 # POS 자동 태깅
python scripts/process/fix_pos.py                 # Claude API로 POS 교정
python scripts/process/apply_pos_corrections.py   # POS 교정 적용
python scripts/process/categorize.py              # Part5 유형 분류
python scripts/process/create_chapter_map.py      # Chapter 구조 생성
python scripts/process/find_ets_examples.py       # 기출 예문 전수 검색
python scripts/process/find_examples_from_ocr_cache.py  # OCR 기반 보완 검색
python scripts/process/merge_ocr_examples.py      # OCR 예문 병합

# ── Phase 3: 덱·Vault 생성 ──
python scripts/anki/generate_vocab_deck.py        # Anki 단어장 덱
python scripts/anki/generate_part5_deck.py        # Anki Part5 덱
python scripts/generate/generate_obsidian_vault.py  # Obsidian Vault

# ── Phase 4: 분석 ──
python scripts/analyze/category_stats.py          # 카테고리 통계
python scripts/analyze/coverage_report.py         # 커버리지 리포트
python scripts/analyze/word_frequency.py          # 빈출 단어 분석
python scripts/analyze/validate_vault.py          # Vault 검증
```

---

## 설정 파일

### `config.yaml`

프로젝트 전역 설정. 경로, ETS 권/파트 번호, Anki 덱 이름/ID, Vault 출력 경로, Part5 카테고리 목록 정의.

### `.gitignore`

`data/raw/`, `output/anki/*.apkg`, `vault/`, `.secret/`, `.obsidian/`, `.request/` 등 미추적.

### `tessdata/`

Tesseract OCR 학습 데이터 (`eng.traineddata`, `kor.traineddata`, `osd.traineddata`) 및 설정.

---

## 저작권 안내

ETS 기출문제 및 해커스 단어장은 저작권이 있는 자료입니다.
- **개인 학습 목적으로만 사용**
- Anki 덱 및 Obsidian Vault의 **외부 공유·배포 금지**
- 원본 파일은 git에 커밋하지 않음 (`data/raw/`는 `.gitignore`에 포함)
