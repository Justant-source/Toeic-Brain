# Scripts 사용 가이드

## 디렉토리 구조

```
scripts/
├── utils/       # 공유 유틸리티 (직접 실행 X, import용)
├── extract/     # Phase 1: 원본 PDF/Excel → JSON 추출
├── process/     # Phase 2: JSON 가공·매핑·분류
├── anki/        # Phase 3: Anki 덱 생성
└── analyze/     # Phase 4: 분석·검증 리포트
```

## 실행 순서

### Phase 1: 데이터 추출 (초기 1회)

```bash
python scripts/extract/extract_vocab.py          # 노랭이 PDF → hackers_vocab.json
python scripts/extract/extract_vocab_excel.py     # 노랭이 Excel → hackers_vocab.json
python scripts/extract/extract_chapters.py        # 노랭이 PDF → chapter_map.json
python scripts/extract/extract_ets.py             # ETS PDF → vol{N}_part{5,6,7}.json
python scripts/extract/extract_answers.py         # 해설 PDF → 정답/해설 병합
```

### Phase 2: 데이터 가공 (초기 1회 + 데이터 변경 시)

```bash
python scripts/process/validate.py                # JSON 무결성 검증
python scripts/process/add_pos.py                 # POS 자동 태깅
python scripts/process/fix_pos.py                 # Claude API로 POS 교정
python scripts/process/apply_pos_corrections.py   # POS 교정 적용
python scripts/process/categorize.py              # Part5 유형 분류
python scripts/process/create_chapter_map.py      # Chapter 구조 생성
python scripts/process/find_ets_examples.py       # 기출 예문 전수 검색
python scripts/process/find_examples_from_ocr_cache.py  # OCR 기반 보완 검색
python scripts/process/merge_ocr_examples.py      # OCR 예문 병합
python scripts/process/fill_blanks.py             # 예문 빈칸을 정답으로 채움
python scripts/process/apply_fill_patches.py      # 패치 적용 + Anki 덱 재생성
```

### Phase 3: Anki 덱 생성 (가공 후 실행)

```bash
python scripts/anki/generate_vocab_deck.py        # Anki 단어장 덱
python scripts/anki/generate_part5_deck.py        # Anki Part5 덱
```

### Phase 4: 분석 (필요 시)

```bash
python scripts/analyze/category_stats.py          # 카테고리 통계
python scripts/analyze/coverage_report.py         # 커버리지 리포트
python scripts/analyze/word_frequency.py          # 빈출 단어 분석
```

---

## 개별 스크립트 상세

### utils/nlp.py
- **역할**: NLP 공유 유틸리티 (lemmatisation, 단어 패밀리 확장, 역인덱스)
- **직접 실행 안 함** — 다른 스크립트에서 import
- **주요 함수**: `get_lemma()`, `get_sentence_lemmas()`, `_build_word_family()`, `build_inverted_index()`
- **의존성**: spaCy (필수, en_core_web_sm 모델)

### extract/extract_ets.py
- **역할**: ETS 문제 PDF에서 Part5/6/7 문제 추출
- **입력**: `00. Reference/*.pdf (ETS 기출)`
- **출력**: `data/json/questions/vol{N}_part{N}.json`
- **의존성**: PyMuPDF, PyYAML

### extract/extract_answers.py
- **역할**: ETS 해설 PDF에서 정답·해설 추출 후 문제 JSON에 병합
- **입력**: `00. Reference/*.pdf (ETS 해설)`
- **출력**: `data/json/questions/vol{N}_*.json` (answer/explanation 필드 추가)
- **의존성**: PyMuPDF, pytesseract

### extract/extract_vocab.py
- **역할**: 노랭이 PDF에서 단어 추출 (word, POS, 뜻, 예문, Day, 유의어)
- **입력**: `00. Reference/hackers_vocab.pdf`
- **출력**: `data/json/hackers_vocab.json`
- **의존성**: PyMuPDF, pytesseract, PIL

### extract/extract_vocab_excel.py
- **역할**: 노랭이 Excel에서 단어 추출 (기초/800점/900점 레벨별)
- **입력**: `00. Reference/*.xlsx`
- **출력**: `data/json/hackers_vocab.json`
- **의존성**: openpyxl

### extract/extract_chapters.py
- **역할**: 노랭이 PDF에서 Chapter 구조 + 900점 단어 추출
- **입력**: `00. Reference/hackers_vocab.pdf`
- **출력**: `data/json/chapter_map.json`
- **의존성**: PyMuPDF

### extract/ocr_question_pdf.py
- **역할**: ETS 문제 PDF 텍스트 추출 (PyMuPDF → Tesseract 폴백), 페이지별 캐싱
- **입력**: `00. Reference/*.pdf (ETS 기출)`
- **출력**: `00. Reference/ocr_cache/`
- **의존성**: PyMuPDF, pytesseract

### extract/ocr_answer_pdf.py
- **역할**: ETS 해설 PDF에 OCR 투명 텍스트 레이어 삽입
- **입력**: `00. Reference/*.pdf (ETS 해설)`
- **출력**: 검색 가능 PDF
- **의존성**: pytesseract, PIL, PyMuPDF

### extract/ocr_utils.py
- **역할**: OCR 공통 유틸리티 (페이지 렌더링, Tesseract 호출, 캐시 관리)
- **직접 실행 안 함** — 다른 스크립트에서 import
- **의존성**: PyMuPDF, pytesseract, PIL

### process/validate.py
- **역할**: 문제·단어 JSON 무결성 검증 (필수 필드, 데이터 타입, 이상값)
- **입력**: `data/json/**/*.json`
- **출력**: 검증 리포트 (콘솔)

### process/categorize.py
- **역할**: Part5 문제 유형 자동 분류 (선택지 패턴 → 8개 카테고리)
- **입력**: `vol{N}_part5.json`
- **출력**: 같은 파일에 `category` 필드 추가

### process/add_pos.py
- **역할**: NLTK WordNet + 접미사 패턴으로 POS 자동 태깅
- **입력**: `hackers_vocab.json`
- **출력**: 같은 파일에 `pos` 필드 추가
- **의존성**: nltk

### process/fix_pos.py
- **역할**: Claude API로 POS 교정 (배치 처리)
- **입력**: `hackers_vocab.json`
- **출력**: POS 교정 JSON
- **의존성**: anthropic

### process/apply_pos_corrections.py
- **역할**: POS 교정 파일을 단어 JSON에 일괄 적용
- **입력**: 교정 JSON + `hackers_vocab.json`
- **출력**: 업데이트된 `hackers_vocab.json`

### process/create_chapter_map.py
- **역할**: `hackers_vocab.json`에서 Day/Chapter별 단어 그룹핑
- **입력**: `data/json/hackers_vocab.json`
- **출력**: `data/json/chapter_map.json`

### process/find_ets_examples.py
- **역할**: 단어별 ETS 기출 예문 전수 검색 (Part5/6/7, spaCy lemmatization)
- **입력**: `hackers_vocab.json` + `questions/*.json`
- **출력**: `data/json/word_ets_examples.json`
- **의존성**: scripts.utils.nlp

### process/find_examples_from_ocr_cache.py
- **역할**: OCR 캐시 텍스트에서 직접 예문 검색 (구조화 JSON 대신 raw OCR)
- **입력**: `00. Reference/ocr_cache/`
- **출력**: `data/json/ocr_examples_vol{N}.json`

### process/merge_ocr_examples.py
- **역할**: 권별 OCR 예문을 `word_ets_examples.json`에 병합 (중복 제거)
- **입력**: `ocr_examples_vol{N}.json` + `word_ets_examples.json`
- **출력**: 업데이트된 `word_ets_examples.json`

### process/fill_blanks.py
- **역할**: 예문 내 `-------` 빈칸을 정답으로 채움
- **입력**: `questions/*.json` + `word_ets_examples.json`
- **출력**: `data/json/fill_patches_vol{N}.json`

### process/apply_fill_patches.py
- **역할**: fill_patches를 `word_ets_examples.json`에 적용 + Anki 덱 재생성
- **입력**: `fill_patches_vol{N}.json`
- **출력**: 업데이트된 `word_ets_examples.json`

### anki/generate_vocab_deck.py
- **역할**: 노랭이 단어 + 기출 예문 → Anki 단어장 덱
- **입력**: `hackers_vocab.json` + `word_ets_examples.json`
- **출력**: `output/anki/toeic_vocab.apkg`
- **의존성**: genanki

### anki/generate_part5_deck.py
- **역할**: Part5 문제 → Anki 문제 덱 (인터랙티브 선택지)
- **입력**: `vol{N}_part5.json`
- **출력**: `output/anki/toeic_part5.apkg`
- **의존성**: genanki

### analyze/category_stats.py
- **역할**: Part5 카테고리별 출제 분포 통계
- **입력**: `vol{N}_part5.json`
- **출력**: `output/reports/category_stats.html`

### analyze/coverage_report.py
- **역할**: 노랭이 단어의 기출 커버리지 분석 (Day별 등장률)
- **입력**: `hackers_vocab.json` + `word_ets_examples.json`
- **출력**: `output/reports/coverage_report.html`

### analyze/word_frequency.py
- **역할**: ETS 5권 전체 빈출 단어 Top 100 분석
- **입력**: `questions/*.json`
- **출력**: `output/reports/frequency_analysis.html`
