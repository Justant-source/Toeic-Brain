# Toeic Brain 프로젝트 구조 리팩토링 — 완료 보고서

> 작성일: 2026-03-31
> 작업지시서: `.request/toeic-brain-restructure.md`

---

## 수행 작업 요약

7개 커밋으로 프로젝트 구조를 리팩토링했다.

| # | 커밋 | 내용 |
|---|------|------|
| 1 | `20b668a` | `scripts/utils/nlp.py` 공유 모듈 추출 + import 경로 변경 |
| 2 | `cb232a0` | Obsidian 관련 스크립트·설정 제거 (generate/, validate_vault, config.yaml vault) |
| 3 | `967caf5` | 미사용 스크립트·빈 파일 archive/ 이동 + ocr_pipeline.py 삭제 |
| 4 | `2879ed3` | tessdata/ git 추적 해제 + .gitignore 업데이트 |
| 5 | `12a3142` | exam/ 모의고사 시스템 구축 (Part5 + 단어장 퀴즈 HTML 생성기) |
| 6 | `6a13f98` | scripts/README.md + exam/README.md 사용법 가이드 작성 |
| 7 | `455d58e` | README.md 간소화 + CLAUDE.md 구조 반영 + .result/ 추가 |

---

## 생성/수정/삭제된 파일

### 신규 생성

| 파일 | 용도 |
|------|------|
| `scripts/utils/__init__.py` | utils 패키지 |
| `scripts/utils/nlp.py` | NLP 공유 유틸리티 (4함수 + build_inverted_index) |
| `exam/generate_part5_test.py` | Part5 모의고사 HTML 생성기 |
| `exam/generate_vocab_quiz.py` | 단어장 퀴즈 HTML 생성기 |
| `exam/README.md` | 모의고사 사용법 가이드 |
| `scripts/README.md` | 스크립트 사용법 가이드 |
| `.result/.gitkeep` | 완료 보고서 디렉토리 |

### 이동 (→ archive/)

| 원래 위치 | 이동 위치 |
|-----------|-----------|
| `scripts/generate/generate_obsidian_vault.py` | `archive/scripts/` |
| `scripts/analyze/validate_vault.py` | `archive/scripts/` |
| `scripts/patch_missing_explanations.py` | `archive/scripts/` |
| `scripts/process/map_words.py` | `archive/scripts/` |
| `data/mapped/ocr_examples_vol{1-5}.json` | `archive/data/` |
| `data/mapped/fill_patches_vol{1-5}.json` | `archive/data/` |
| `data/mapped/word_question_map.json` | `archive/data/` |

### 삭제

| 파일 | 사유 |
|------|------|
| `scripts/extract/ocr_pipeline.py` | 빈 스텁 (docstring만) |
| `scripts/generate/__init__.py` | 폴더 삭제 시 함께 제거 |
| `tessdata/*` (git에서만) | git 추적 해제, 로컬 유지 |

### 수정

| 파일 | 변경 내용 |
|------|-----------|
| `scripts/process/find_ets_examples.py` | import 경로 변경 (map_words → utils.nlp) |
| `tests/test_mapping.py` | import 경로 변경 (map_words → utils.nlp) |
| `config.yaml` | vault 섹션 제거 |
| `.gitignore` | tessdata/, exam/result/, archive/data/ 추가 |
| `README.md` | 326줄 → 76줄 간소화, Obsidian 제거 |
| `CLAUDE.md` | 실제 데이터 스키마로 갱신, 새 구조 반영 |

---

## 데이터 통계

- **pytest**: 62/62 통과
- **Part5 문제**: 1,467문제 (5권)
- **단어장**: 4,209단어 (30 Days)
- **git 추적 해제**: tessdata/ 29MB 제거
- **archive 이동**: 스크립트 4개, 데이터 11개

---

## 검증 결과

- [x] `pytest tests/` 전체 통과
- [x] `from scripts.utils.nlp import ...` 성공
- [x] `from scripts.process.find_ets_examples import *` 성공
- [x] `from scripts.extract.extract_vocab import *` 성공
- [x] `scripts/extract/ocr_pipeline.py` 존재하지 않음
- [x] `scripts/generate/` 폴더 존재하지 않음
- [x] `scripts/analyze/validate_vault.py` 존재하지 않음
- [x] `data/mapped/`에 `word_ets_examples.json`만 존재
- [x] `archive/scripts/`에 4개 파일 존재
- [x] `archive/data/`에 11개 파일 존재
- [x] `exam/generate_part5_test.py` 실행 → HTML 생성 성공
- [x] `exam/generate_vocab_quiz.py` 실행 → HTML 생성 성공
- [x] `exam/generate_part5_test.py --help` 정상
- [x] `exam/generate_vocab_quiz.py --help` 정상
- [x] `config.yaml`에 vault 섹션 없음
- [x] `tessdata/`가 `.gitignore`에 포함
- [x] `exam/result/`가 `.gitignore`에 포함
- [x] `README.md`에 Obsidian/Vault 언급 없음
- [x] `CLAUDE.md`에 Obsidian/Vault 목표·기능 언급 없음
- [x] `.result/` 디렉토리 존재

---

## 발견된 이슈 및 후속 작업

1. **카테고리 정규화**: Part5의 `category` 필드가 OCR 원문 그대로라 300+종류. `exam/generate_part5_test.py`에서 키워드 기반으로 8개로 정규화했으나, 원본 데이터 자체를 정규화하면 Anki 태그도 깔끔해짐
2. **모의고사 브라우저 테스트**: HTML 생성은 확인했으나, 실제 브라우저에서 문제 풀이·채점·결과 화면 동작을 수동 확인 필요
