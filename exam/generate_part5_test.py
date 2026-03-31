"""
Part5 모의고사 HTML 생성기.

ETS 기출 Part5 문제(5권, 약 1,500문제)에서 랜덤 출제하여 단일 HTML 파일을 생성한다.

Usage:
    python exam/generate_part5_test.py                          # 기본 30문제
    python exam/generate_part5_test.py --count 20 --vol 1 2     # 1·2권에서 20문제
    python exam/generate_part5_test.py --category 품사 어휘      # 특정 카테고리
    python exam/generate_part5_test.py --shuffle                 # 선택지 순서 랜덤화
"""

import sys
import json
import argparse
import random
import html
import glob
from pathlib import Path
from datetime import datetime

# ── Paths ─────────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
QUESTIONS_DIR = PROJECT_ROOT / "data" / "processed" / "questions"
RESULT_DIR = SCRIPT_DIR / "result"

# ── Category normalisation ────────────────────────────────────────────────────

# Raw categories from OCR are messy.  We map them to 8 canonical groups.
_CATEGORY_KEYWORDS = {
    "품사":       ["명사 자리", "형용사 자리", "부사 자리", "명사자리", "형용사자리",
                   "부사자리", "품사"],
    "동사":       ["동사 자리", "동사 어형", "동사 어휘", "동사자리", "동사어형",
                   "동사 이행", "동사 이휘", "동사(과거분사)", "동명사", "to부정사",
                   "현재분사", "과거분사", "분사구문", "목적격보어", "명령문"],
    "접속사/전치사": ["접속사", "전치사", "접속부사", "등위접속사", "상관접속사",
                      "부사절 접속사", "명사절 접속사"],
    "관계대명사":  ["관계대명사", "복합관계대명사", "복합관계사", "관계부사"],
    "어휘":       ["명사 어휘", "형용사 어휘", "부사 어휘", "부사어휘",
                   "동사 어휘", "부사구 어휘", "구전치사 어휘", "전치사 어휘",
                   "전치사 이휘", "형용사_어휘", "명사 이휘", "동사 이휘",
                   "소유격 대명사 어휘"],
    "대명사":     ["대명사", "인칭대명사", "재귀대명사", "지시대명사", "부정대명사",
                   "소유대명사"],
    "비교급/최상급": ["비교급", "최상급"],
    "기타문법":   ["한정사", "수량 형용사", "수량형용사", "숫자"],
}


def normalise_category(raw: str) -> str:
    """Map a raw OCR category string to one of the 8 canonical categories."""
    if not raw:
        return "기타문법"
    low = raw.strip()
    for canon, keywords in _CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in low:
                return canon
    return "기타문법"


# ── HTML escape helper ────────────────────────────────────────────────────────

def esc(s: str) -> str:
    return html.escape(str(s))


# ── Question loading ──────────────────────────────────────────────────────────

def load_questions(volumes: list[int] | None = None) -> list[dict]:
    """Load Part5 questions from vol*_part5.json files."""
    files = sorted(QUESTIONS_DIR.glob("vol*_part5.json"))
    questions = []
    for f in files:
        with open(f, encoding="utf-8") as fh:
            qs = json.load(fh)
        if volumes:
            qs = [q for q in qs if q.get("volume") in volumes]
        questions.extend(qs)
    return questions


def select_questions(
    questions: list[dict],
    count: int,
    categories: list[str] | None = None,
) -> list[dict]:
    """Select questions, optionally filtered by canonical category."""
    if categories:
        cat_set = set(categories)
        questions = [q for q in questions if normalise_category(q.get("category", "")) in cat_set]

    if len(questions) <= count:
        selected = questions[:]
    else:
        # Try to distribute evenly across canonical categories
        by_cat: dict[str, list[dict]] = {}
        for q in questions:
            cat = normalise_category(q.get("category", ""))
            by_cat.setdefault(cat, []).append(q)

        selected = []
        per_cat = max(1, count // len(by_cat)) if by_cat else count
        for cat, qs in by_cat.items():
            random.shuffle(qs)
            selected.extend(qs[:per_cat])

        # Fill remaining slots randomly
        if len(selected) < count:
            remaining = [q for q in questions if q not in selected]
            random.shuffle(remaining)
            selected.extend(remaining[: count - len(selected)])

        random.shuffle(selected)
        selected = selected[:count]

    return selected


# ── HTML generation ───────────────────────────────────────────────────────────

def generate_html(questions: list[dict], shuffle_choices: bool) -> str:
    """Generate a self-contained HTML test page."""
    q_data = []
    for i, q in enumerate(questions):
        choices = q.get("choices", {})
        keys = list(choices.keys())  # A, B, C, D
        answer = q.get("answer", "")

        if shuffle_choices:
            pairs = [(k, choices[k]) for k in keys]
            random.shuffle(pairs)
            new_choices = {chr(65 + j): v for j, (_, v) in enumerate(pairs)}
            # Find new answer key
            orig_answer_text = choices.get(answer, "")
            new_answer = answer
            for nk, nv in new_choices.items():
                if nv == orig_answer_text:
                    new_answer = nk
                    break
            choices = new_choices
            answer = new_answer

        q_data.append({
            "idx": i + 1,
            "id": q.get("id", ""),
            "vol": q.get("volume", ""),
            "test": q.get("test", ""),
            "qnum": q.get("question_number", ""),
            "sentence": q.get("sentence", ""),
            "choices": choices,
            "answer": answer,
            "category": normalise_category(q.get("category", "")),
            "raw_category": q.get("category", ""),
            "explanation": q.get("explanation", ""),
        })

    q_json = json.dumps(q_data, ensure_ascii=False)
    total = len(q_data)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TOEIC Part5 모의고사 ({total}문제)</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
       background: #f5f5f5; color: #1B2A4A; min-width: 360px; }}

.header {{ position: sticky; top: 0; z-index: 100; background: #1B2A4A; color: #fff;
           padding: 12px 20px; display: flex; justify-content: space-between; align-items: center; }}
.header h1 {{ font-size: 16px; color: #C4A35A; }}
.header .info {{ font-size: 14px; display: flex; gap: 16px; align-items: center; }}
.progress-bar {{ height: 4px; background: #334; }}
.progress-fill {{ height: 100%; background: #C4A35A; transition: width 0.3s; }}

.container {{ max-width: 720px; margin: 0 auto; padding: 20px; }}

.question-card {{ background: #fff; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                  padding: 24px; margin-bottom: 16px; display: none; }}
.question-card.active {{ display: block; }}

.q-meta {{ font-size: 13px; color: #888; margin-bottom: 8px; }}
.q-meta .cat {{ background: #C4A35A22; color: #8B7332; padding: 2px 8px; border-radius: 4px;
               font-size: 12px; font-weight: 600; }}
.q-sentence {{ font-size: 17px; line-height: 1.7; margin: 16px 0; word-break: keep-all; }}
.q-sentence .blank {{ color: #C4A35A; font-weight: 700; }}

.choices {{ display: flex; flex-direction: column; gap: 10px; margin-top: 16px; }}
.choice-btn {{ display: flex; align-items: center; gap: 12px; padding: 14px 16px; border: 2px solid #e0e0e0;
               border-radius: 8px; background: #fff; cursor: pointer; font-size: 15px; transition: all 0.2s; }}
.choice-btn:hover:not(.disabled) {{ border-color: #C4A35A; background: #FFFDF5; }}
.choice-btn .key {{ font-weight: 700; color: #1B2A4A; min-width: 28px; }}
.choice-btn.correct {{ border-color: #2E7D32; background: #E8F5E9; }}
.choice-btn.wrong {{ border-color: #C62828; background: #FFEBEE; }}
.choice-btn.show-answer {{ border-color: #2E7D32; background: #E8F5E9; }}
.choice-btn .icon {{ margin-left: auto; font-size: 18px; }}
.choice-btn.disabled {{ cursor: default; opacity: 0.85; }}

.explanation {{ margin-top: 16px; }}
.explanation summary {{ cursor: pointer; color: #C4A35A; font-weight: 600; font-size: 14px; padding: 8px 0; }}
.explanation .text {{ background: #f9f9f9; border-radius: 8px; padding: 14px; font-size: 14px;
                     line-height: 1.8; color: #444; white-space: pre-wrap; word-break: keep-all; }}

.nav-btn {{ display: inline-block; margin-top: 16px; padding: 12px 32px; background: #1B2A4A;
            color: #C4A35A; border: none; border-radius: 8px; font-size: 15px; font-weight: 600;
            cursor: pointer; float: right; }}
.nav-btn:hover {{ background: #243656; }}
.nav-btn:disabled {{ opacity: 0.4; cursor: default; }}

/* Result screen */
.result {{ display: none; background: #fff; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);
           padding: 32px; text-align: center; }}
.result.active {{ display: block; }}
.result h2 {{ font-size: 24px; color: #1B2A4A; margin-bottom: 8px; }}
.result .score {{ font-size: 48px; font-weight: 800; color: #C4A35A; margin: 16px 0; }}
.result .sub {{ color: #888; font-size: 15px; margin-bottom: 24px; }}
.cat-stats {{ text-align: left; margin: 24px 0; }}
.cat-row {{ display: flex; align-items: center; gap: 12px; margin-bottom: 10px; font-size: 14px; }}
.cat-row .label {{ min-width: 100px; font-weight: 600; }}
.cat-row .bar-bg {{ flex: 1; height: 20px; background: #eee; border-radius: 4px; overflow: hidden; }}
.cat-row .bar-fill {{ height: 100%; background: #C4A35A; border-radius: 4px; transition: width 0.5s; }}
.cat-row .pct {{ min-width: 48px; text-align: right; font-weight: 600; }}
.wrong-list {{ text-align: left; margin-top: 24px; }}
.wrong-list h3 {{ font-size: 16px; margin-bottom: 12px; color: #C62828; }}
.wrong-item {{ font-size: 13px; color: #555; padding: 4px 0; border-bottom: 1px solid #f0f0f0; }}
.result-actions {{ margin-top: 24px; display: flex; gap: 12px; justify-content: center; }}
.result-actions button {{ padding: 12px 24px; border: 2px solid #1B2A4A; border-radius: 8px;
                          font-size: 14px; font-weight: 600; cursor: pointer; background: #fff; color: #1B2A4A; }}
.result-actions button.primary {{ background: #1B2A4A; color: #C4A35A; }}
</style>
</head>
<body>

<div class="header">
  <h1>TOEIC Part5 모의고사</h1>
  <div class="info">
    <span id="counter">1/{total}</span>
    <span id="timer">⏱ 00:00</span>
  </div>
</div>
<div class="progress-bar"><div class="progress-fill" id="progress" style="width:0%"></div></div>

<div class="container" id="quiz-area"></div>

<script>
const Q = {q_json};
const TOTAL = Q.length;
let current = 0;
let score = 0;
let answered = new Array(TOTAL).fill(null);
let startTime = Date.now();

// Timer
setInterval(() => {{
  const s = Math.floor((Date.now() - startTime) / 1000);
  const m = String(Math.floor(s / 60)).padStart(2, '0');
  const sec = String(s % 60).padStart(2, '0');
  document.getElementById('timer').textContent = '⏱ ' + m + ':' + sec;
}}, 1000);

function esc(s) {{ const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }}

function renderSentence(s) {{
  return s.replace(/-------/g, '<span class="blank">_______</span>');
}}

function render() {{
  const area = document.getElementById('quiz-area');
  area.innerHTML = '';

  if (current >= TOTAL) {{
    showResult();
    return;
  }}

  const q = Q[current];
  document.getElementById('counter').textContent = (current + 1) + '/' + TOTAL;
  document.getElementById('progress').style.width = ((current + 1) / TOTAL * 100) + '%';

  const card = document.createElement('div');
  card.className = 'question-card active';

  let choicesHtml = '';
  for (const [key, val] of Object.entries(q.choices)) {{
    choicesHtml += '<button class="choice-btn" data-key="' + key + '">'
      + '<span class="key">(' + key + ')</span> '
      + '<span>' + esc(val) + '</span>'
      + '<span class="icon"></span></button>';
  }}

  card.innerHTML = '<div class="q-meta">Q' + q.idx + '. <span class="cat">' + esc(q.category) + '</span>'
    + ' Vol.' + q.vol + '</div>'
    + '<div class="q-sentence">' + renderSentence(esc(q.sentence)) + '</div>'
    + '<div class="choices">' + choicesHtml + '</div>'
    + (q.explanation ? '<details class="explanation"><summary>▶ 해설 보기</summary>'
      + '<div class="text">' + esc(q.explanation) + '</div></details>' : '')
    + '<button class="nav-btn" id="next-btn" disabled onclick="nextQ()">다음 문제 →</button>';

  area.appendChild(card);

  // Re-apply state if already answered
  if (answered[current] !== null) {{
    applyAnswer(answered[current], false);
  }} else {{
    card.querySelectorAll('.choice-btn').forEach(btn => {{
      btn.addEventListener('click', () => answerClick(btn));
    }});
  }}
}}

function answerClick(btn) {{
  const key = btn.dataset.key;
  answered[current] = key;
  applyAnswer(key, true);
}}

function applyAnswer(key, isNew) {{
  const q = Q[current];
  const card = document.querySelector('.question-card');
  const btns = card.querySelectorAll('.choice-btn');

  btns.forEach(b => {{
    b.classList.add('disabled');
    b.removeEventListener('click', answerClick);
    const bKey = b.dataset.key;
    if (bKey === q.answer) {{
      b.classList.add(bKey === key ? 'correct' : 'show-answer');
      b.querySelector('.icon').textContent = '✅';
    }} else if (bKey === key) {{
      b.classList.add('wrong');
      b.querySelector('.icon').textContent = '❌';
    }}
  }});

  if (isNew && key === q.answer) score++;
  document.getElementById('next-btn').disabled = false;
}}

function nextQ() {{
  current++;
  render();
  window.scrollTo(0, 0);
}}

function showResult() {{
  const elapsed = Math.floor((Date.now() - startTime) / 1000);
  const m = String(Math.floor(elapsed / 60)).padStart(2, '0');
  const sec = String(elapsed % 60).padStart(2, '0');
  const pct = Math.round(score / TOTAL * 100);

  // Category stats
  const catCorrect = {{}};
  const catTotal = {{}};
  const wrongItems = [];
  Q.forEach((q, i) => {{
    const cat = q.category;
    catTotal[cat] = (catTotal[cat] || 0) + 1;
    if (answered[i] === q.answer) {{
      catCorrect[cat] = (catCorrect[cat] || 0) + 1;
    }} else {{
      wrongItems.push(q);
    }}
  }});

  let catHtml = '';
  for (const cat of Object.keys(catTotal).sort()) {{
    const c = catCorrect[cat] || 0;
    const t = catTotal[cat];
    const p = Math.round(c / t * 100);
    catHtml += '<div class="cat-row"><span class="label">' + esc(cat) + '</span>'
      + '<div class="bar-bg"><div class="bar-fill" style="width:' + p + '%"></div></div>'
      + '<span class="pct">' + c + '/' + t + '</span></div>';
  }}

  let wrongHtml = '';
  if (wrongItems.length) {{
    wrongHtml = '<div class="wrong-list"><h3>틀린 문제 (' + wrongItems.length + ')</h3>';
    wrongItems.forEach(q => {{
      wrongHtml += '<div class="wrong-item">Q' + q.idx + ' (' + esc(q.category)
        + ') Vol.' + q.vol + ' #' + q.qnum + '</div>';
    }});
    wrongHtml += '</div>';
  }}

  const area = document.getElementById('quiz-area');
  area.innerHTML = '<div class="result active">'
    + '<h2>시험 결과</h2>'
    + '<div class="score">' + score + ' / ' + TOTAL + '</div>'
    + '<div class="sub">' + pct + '%  ⏱ ' + m + ':' + sec + '</div>'
    + '<div class="cat-stats">' + catHtml + '</div>'
    + wrongHtml
    + '<div class="result-actions">'
    + '<button onclick="location.reload()">처음부터 다시</button>'
    + '</div></div>';

  document.getElementById('counter').textContent = '완료';
  document.getElementById('progress').style.width = '100%';
}}

render();
</script>
</body>
</html>"""


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Part5 모의고사 HTML 생성기")
    parser.add_argument("--count", type=int, default=30, help="출제 문제 수 (기본 30)")
    parser.add_argument("--vol", type=int, nargs="+", help="출제할 권 번호 (예: 1 2 3)")
    parser.add_argument("--category", nargs="+", help="출제할 카테고리 (예: 품사 어휘)")
    parser.add_argument("--shuffle", action="store_true", help="선택지 순서 랜덤화")
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")

    questions = load_questions(args.vol)
    if not questions:
        print("오류: Part5 문제를 찾을 수 없습니다.", file=sys.stderr)
        sys.exit(1)

    selected = select_questions(questions, args.count, args.category)
    print(f"총 {len(questions)}문제 중 {len(selected)}문제 선택")

    html_content = generate_html(selected, args.shuffle)

    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    output_path = RESULT_DIR / f"part5_test_{timestamp}.html"
    output_path.write_text(html_content, encoding="utf-8")
    print(f"생성 완료: {output_path}")


if __name__ == "__main__":
    main()
