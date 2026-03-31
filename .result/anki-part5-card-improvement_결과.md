# Part5 Anki 카드 개선 완료 보고서

## 수행 작업 요약

Part5 Anki 카드 뒷면(정답면) 레이아웃을 작업지시서(`anki-part5-card-improvement.md`) 기준으로 개선했다.

---

## 수정된 파일

### 1. `scripts/anki/generate_part5_deck.py`

- **`FilledSentence` 필드 추가**: 13번째 모델 필드로 등록
- **`make_filled_sentence()` 함수 추가**:
  ```python
  def make_filled_sentence(sentence: str, answer_text: str) -> str:
      escaped = html.escape(sentence)
      bolded  = f"<b>{html.escape(answer_text)}</b>"
      return escaped.replace("-------", bolded, 1)
  ```
- **해설 전처리**: `explanation_raw.replace("\n[번역]", "\n\n[번역]")` — `[번역]` 앞에 빈 줄 삽입
- **노트 필드 목록에 `FilledSentence` 추가** (마지막 필드)

### 2. `scripts/anki/templates/part5_back.html`

- **제거**: `<ul class="choices">` 블록 (정답 `(A)(B)(C)(D)` 버튼 + `정답 ({{Answer}}) {{AnswerText}}`)
- **추가**: 앞면과 동일한 태그 헤더 (`Part5`, `Vol.N`, `Q.N`) + 유형 태그
- **추가**: `{{FilledSentence}}` — 빈칸에 정답이 볼드체로 삽입된 문장 표시

---

## 생성 결과

```
Deck written to: C:\Data\Toeic Brain\output\anki\toeic_part5.apkg
Total cards: 1,467
  Vol.1: 297 cards
  Vol.2: 276 cards
  Vol.3: 297 cards
  Vol.4: 298 cards
  Vol.5: 299 cards
```

---

## 카드 뒷면 변경 전/후

**변경 전**:
```
정답 (D) between
[해설 본문][번역] 번역 텍스트
```

**변경 후**:
```
Part5  Vol.1  Q.113
유형: 전치사 어휘

One of Grommer Consulting's goals is to enhance the relationship
<b>between</b> salespeople and their customers.

─────────────────────
해설
해설 본문...

[번역] 번역 텍스트
```

---

## 이슈 없음

- 모든 5개 볼륨 정상 로드
- `-------` 치환 정상 동작
- `[번역]` 앞 줄바꿈 삽입 정상
- `.apkg` 생성 완료
