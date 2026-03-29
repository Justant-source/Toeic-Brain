# Toeic Brain

> ETS 기출문제 1000제 + 해커스 노랭이 단어장 → Anki 기반 토익 RC 학습 시스템

## 프로젝트 목표

1. **단어-기출 매핑**: 노랭이 단어가 기출에서 어떻게 출제되었는지 추적
2. **Anki 단어장 덱**: 노랭이 단어 + 기출 예문 결합
3. **Anki Part5 문제 덱**: Part5 기출문제 반복 풀이용

## 데이터 소스

- ETS 기출문제 1000제 (1~5권, 총 5,000문제)
- 해커스 노랭이 단어장

## 기술 스택

Python 3.11+ | PyMuPDF | pdfplumber | spaCy | genanki | pandas | pytest

## 실행 순서

```bash
pip install -r requirements.txt
# 1. 원본 PDF를 data/raw/에 배치
# 2. 데이터 추출
python scripts/extract/extract_vocab.py
python scripts/extract/extract_ets.py
# 3. 검증 → 매핑 → 분류
python scripts/process/validate.py
python scripts/process/map_words.py
python scripts/process/categorize.py
# 4. Anki 덱 생성
python scripts/anki/generate_vocab_deck.py
python scripts/anki/generate_part5_deck.py
```

## 프로젝트 구조

```
Toeic Brain/
├── data/
│   ├── raw/                  # 원본 PDF 파일
│   ├── processed/
│   │   ├── vocab/            # 추출된 단어 데이터
│   │   └── questions/        # 추출된 기출문제 데이터
│   └── mapped/               # 단어-기출 매핑 결과
├── output/
│   ├── anki/                 # 생성된 Anki 덱 (.apkg)
│   └── reports/              # 분석 리포트
├── scripts/
│   ├── extract/              # PDF 추출 스크립트
│   ├── process/              # 검증·매핑·분류 스크립트
│   ├── anki/                 # Anki 덱 생성 스크립트
│   └── analyze/              # 분석 스크립트
├── tests/
├── config.yaml
└── requirements.txt
```

## 저작권 안내

ETS 기출문제 및 해커스 단어장은 저작권이 있는 자료입니다. 개인 학습 목적으로만 사용하며 Anki 덱은 외부 공유를 금지합니다.
