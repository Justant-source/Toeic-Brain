# Toeic Brain

> ETS 기출문제 1000제 (5권, 총 5,000문제) + 해커스 노랭이 단어장 → Anki 기반 토익 RC 학습 시스템

## 프로젝트 목표

1. **단어-기출 매핑**: 노랭이 단어가 ETS 기출에서 어떻게 출제되었는지 추적
2. **Anki 단어장 덱**: 노랭이 단어 + 기출 예문을 결합한 플래시카드
3. **Anki Part5 문제 덱**: Part5 기출문제 반복 풀이용 플래시카드
4. **모의고사**: Part5 모의고사 + 단어장 퀴즈 HTML 생성

## 디렉토리 구조

```
Toeic Brain/
├── data/
│   ├── raw/                  # 원본 PDF/Excel (git 미추적)
│   ├── processed/            # 파싱 완료 JSON (questions/, vocab/)
│   └── mapped/               # 단어-기출 매핑 (word_ets_examples.json)
├── scripts/                  # 데이터 파이프라인 (README.md 참조)
│   ├── utils/                # 공유 NLP 유틸리티
│   ├── extract/              # Phase 1: PDF/Excel → JSON
│   ├── process/              # Phase 2: 가공·매핑·분류
│   ├── anki/                 # Phase 3: Anki 덱 생성
│   └── analyze/              # Phase 4: 분석·리포트
├── exam/                     # 모의고사 HTML 생성기 (README.md 참조)
├── output/                   # Anki .apkg + HTML 리포트
├── archive/                  # 사용 종료된 스크립트·데이터 보관
├── tests/                    # pytest 테스트
├── .request/                 # 작업지시서
└── .result/                  # 완료 보고서
```

## Quick Start

```bash
# 환경 설정
pip install -r requirements.txt
# 원본 PDF/Excel을 data/raw/에 배치

# 핵심 파이프라인 (상세: scripts/README.md)
python scripts/extract/extract_ets.py             # ETS PDF → 문제 JSON
python scripts/process/find_ets_examples.py       # 단어별 기출 예문 검색
python scripts/anki/generate_vocab_deck.py        # Anki 단어장 덱 생성
python scripts/anki/generate_part5_deck.py        # Anki Part5 덱 생성
```

## 모의고사

```bash
# Part5 모의고사 (30문제, 즉시 채점 + 해설)
python exam/generate_part5_test.py

# 단어장 퀴즈 (50문제, 4지선다)
python exam/generate_vocab_quiz.py

# 옵션 상세: exam/README.md
```

생성된 HTML을 브라우저에서 열어 풀이합니다.

## OCR 설정 (선택)

OCR 기능 사용 시 `tessdata/` 폴더에 학습 데이터를 배치하세요:
- `eng.traineddata`, `kor.traineddata`, `osd.traineddata`
- 다운로드: https://github.com/tesseract-ocr/tessdata

## 테스트

```bash
pytest tests/
```

## 저작권 안내

ETS 기출문제 및 해커스 단어장은 저작권이 있는 자료입니다.
- **개인 학습 목적으로만 사용**
- Anki 덱 및 모의고사 HTML의 **외부 공유·배포 금지**
- 원본 파일은 git에 커밋하지 않음 (`data/raw/`는 `.gitignore`에 포함)
