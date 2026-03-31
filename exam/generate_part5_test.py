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
    """Generate a self-contained HTML test page (all questions at once, report at end)."""
    q_data = []
    for i, q in enumerate(questions):
        choices = q.get("choices", {})
        keys = list(choices.keys())
        answer = q.get("answer", "")

        if shuffle_choices:
            pairs = [(k, choices[k]) for k in keys]
            random.shuffle(pairs)
            new_choices = {chr(65 + j): v for j, (_, v) in enumerate(pairs)}
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
            "explanation": q.get("explanation", ""),
            "translation": q.get("translation", ""),
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
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans KR", sans-serif;
       background: #f0f2f5; color: #1B2A4A; min-width: 360px; }}

/* ── Header ── */
.header {{ position: sticky; top: 0; z-index: 100; background: #1B2A4A; color: #fff;
           padding: 12px 20px; display: flex; justify-content: space-between; align-items: center; }}
.header h1 {{ font-size: 16px; color: #C4A35A; font-weight: 700; }}
.header .info {{ font-size: 14px; display: flex; gap: 16px; align-items: center; }}
#answered-count {{ color: #C4A35A; font-weight: 700; }}
.progress-bar {{ height: 4px; background: #2d3e5a; }}
.progress-fill {{ height: 100%; background: #C4A35A; transition: width 0.3s; width: 0%; }}

/* ── Layout ── */
.container {{ max-width: 760px; margin: 0 auto; padding: 20px 16px 120px; }}

/* ── Question card ── */
.question-card {{ background: #fff; border-radius: 12px;
                  box-shadow: 0 2px 8px rgba(0,0,0,0.07);
                  padding: 24px; margin-bottom: 16px;
                  border-left: 4px solid #e0e0e0; transition: border-color 0.2s; }}
.question-card.answered {{ border-left-color: #C4A35A; }}

.q-meta {{ display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
           font-size: 12px; color: #999; margin-bottom: 10px; }}
.q-num  {{ font-weight: 800; font-size: 15px; color: #1B2A4A; }}
.q-cat  {{ background: #C4A35A22; color: #7a6020; padding: 2px 8px; border-radius: 4px;
           font-size: 12px; font-weight: 600; }}
.q-src  {{ margin-left: auto; color: #bbb; }}

.q-sentence {{ font-size: 16px; line-height: 1.8; margin: 12px 0 18px;
               word-break: keep-all; color: #1a1a2e; }}
.blank {{ display: inline-block; min-width: 80px; border-bottom: 2px solid #C4A35A;
          color: #C4A35A; font-weight: 700; text-align: center; padding: 0 4px; }}

.choices {{ display: flex; flex-direction: column; gap: 8px; }}
.choice-btn {{ display: flex; align-items: flex-start; gap: 10px; padding: 12px 14px;
               border: 2px solid #e8e8e8; border-radius: 8px; background: #fafafa;
               cursor: pointer; font-size: 14px; text-align: left; transition: all 0.15s;
               width: 100%; }}
.choice-btn:hover:not([disabled]) {{ border-color: #C4A35A; background: #fffcf0; }}
.choice-btn[disabled] {{ cursor: default; }}
.choice-btn .ck {{ font-weight: 700; color: #888; min-width: 24px; flex-shrink: 0; }}
.choice-btn .ct {{ flex: 1; line-height: 1.5; }}
.choice-btn .ci {{ margin-left: 6px; font-size: 16px; flex-shrink: 0; }}

.choice-btn.selected  {{ border-color: #1B2A4A; background: #f0f4ff; }}
.choice-btn.selected .ck {{ color: #1B2A4A; }}

/* ── Submit bar ── */
.submit-bar {{ position: fixed; bottom: 0; left: 0; right: 0; background: #fff;
               border-top: 1px solid #e0e0e0; padding: 14px 20px;
               display: flex; justify-content: center; align-items: center; gap: 16px;
               box-shadow: 0 -4px 12px rgba(0,0,0,0.08); z-index: 99; }}
.submit-btn {{ padding: 14px 40px; background: #1B2A4A; color: #C4A35A;
               border: none; border-radius: 8px; font-size: 16px; font-weight: 700;
               cursor: pointer; transition: background 0.2s; }}
.submit-btn:hover:not(:disabled) {{ background: #243656; }}
.submit-btn:disabled {{ background: #aaa; color: #fff; cursor: not-allowed; }}
.submit-note {{ font-size: 13px; color: #999; }}

/* ════════════════════════════════
   RESULT PAGE
════════════════════════════════ */
#result-page {{ display: none; }}
#result-page.show {{ display: block; }}

.result-hero {{ background: #1B2A4A; color: #fff; padding: 40px 20px; text-align: center; }}
.result-hero h2 {{ font-size: 22px; color: #C4A35A; margin-bottom: 16px; }}
.score-big {{ font-size: 64px; font-weight: 900; color: #C4A35A; line-height: 1; }}
.score-denom {{ font-size: 28px; color: #8a9bbf; }}
.result-sub {{ margin-top: 12px; font-size: 15px; color: #8a9bbf; display: flex;
               justify-content: center; gap: 24px; flex-wrap: wrap; }}

.result-body {{ max-width: 760px; margin: 0 auto; padding: 24px 16px 60px; }}

/* category accuracy */
.section-title {{ font-size: 16px; font-weight: 700; color: #1B2A4A; margin: 28px 0 14px;
                  padding-bottom: 6px; border-bottom: 2px solid #e8e8e8; }}
.cat-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 10px; }}
.cat-card {{ background: #fff; border-radius: 10px; padding: 14px 16px;
             box-shadow: 0 1px 4px rgba(0,0,0,0.07); }}
.cat-card .cat-name {{ font-weight: 600; font-size: 14px; margin-bottom: 8px; }}
.cat-card .bar-wrap {{ display: flex; align-items: center; gap: 8px; }}
.cat-card .bar-bg {{ flex: 1; height: 10px; background: #eee; border-radius: 5px; overflow: hidden; }}
.cat-card .bar-fill {{ height: 100%; border-radius: 5px; transition: width 0.6s ease; }}
.bar-fill.good {{ background: #43a047; }}
.bar-fill.mid  {{ background: #fb8c00; }}
.bar-fill.bad  {{ background: #e53935; }}
.cat-card .bar-pct {{ font-size: 13px; font-weight: 700; min-width: 44px; text-align: right; }}

/* wrong list */
.wrong-card {{ background: #fff; border-radius: 12px; padding: 20px;
               box-shadow: 0 1px 6px rgba(0,0,0,0.08); margin-bottom: 14px;
               border-left: 4px solid #e53935; }}
.wrong-card .wc-meta {{ font-size: 12px; color: #999; margin-bottom: 6px; display: flex; gap: 8px; }}
.wrong-card .wc-cat {{ color: #e53935; font-weight: 600; }}
.wrong-card .wc-sentence {{ font-size: 14px; line-height: 1.7; color: #222; margin: 8px 0 12px; }}
.answer-row {{ display: flex; gap: 10px; font-size: 14px; margin-bottom: 6px;
               padding: 8px 12px; border-radius: 6px; align-items: flex-start; }}
.answer-row.correct-row {{ background: #e8f5e9; }}
.answer-row.wrong-row   {{ background: #ffebee; }}
.answer-row .ar-label {{ font-weight: 700; min-width: 60px; flex-shrink: 0; }}
.answer-row .ar-key {{ font-weight: 700; min-width: 28px; flex-shrink: 0; }}
.answer-row .ar-text {{ flex: 1; }}
.answer-row .ar-icon {{ font-size: 16px; flex-shrink: 0; }}

.expl-toggle {{ margin-top: 10px; }}
.expl-toggle summary {{ cursor: pointer; font-size: 13px; color: #888; padding: 4px 0;
                        user-select: none; }}
.expl-toggle summary:hover {{ color: #C4A35A; }}
.expl-body {{ background: #fafafa; border-radius: 6px; padding: 12px 14px; margin-top: 8px;
              font-size: 13px; line-height: 1.8; color: #444; white-space: pre-wrap; }}
.expl-body .translation {{ color: #2E7D32; margin-bottom: 8px; font-style: italic; }}

/* claude prompt box */
.claude-box {{ background: #f5f0ff; border: 1px solid #c5b3f0; border-radius: 12px;
               padding: 20px; margin-top: 28px; }}
.claude-box h3 {{ font-size: 15px; color: #5b21b6; margin-bottom: 10px; }}
.claude-prompt {{ background: #fff; border: 1px solid #ddd; border-radius: 8px; padding: 14px;
                  font-size: 13px; line-height: 1.7; color: #333; white-space: pre-wrap;
                  max-height: 260px; overflow-y: auto; font-family: monospace; }}
.copy-btn {{ margin-top: 10px; padding: 10px 20px; background: #5b21b6; color: #fff;
             border: none; border-radius: 6px; font-size: 14px; cursor: pointer; }}
.copy-btn:hover {{ background: #4c1d95; }}

/* result actions */
.result-actions {{ display: flex; gap: 12px; flex-wrap: wrap; margin-top: 28px; }}
.result-actions button {{ padding: 12px 24px; border: 2px solid #1B2A4A; border-radius: 8px;
                          font-size: 14px; font-weight: 600; cursor: pointer; background: #fff;
                          color: #1B2A4A; }}
.result-actions button.primary {{ background: #1B2A4A; color: #C4A35A; border-color: #1B2A4A; }}
</style>
</head>
<body>

<!-- ── QUIZ PAGE ── -->
<div id="quiz-page">
  <div class="header">
    <h1>TOEIC Part5 모의고사</h1>
    <div class="info">
      <span><span id="answered-count">0</span>/{total} 답변</span>
      <span id="timer">⏱ 00:00</span>
    </div>
  </div>
  <div class="progress-bar"><div class="progress-fill" id="progress"></div></div>

  <div class="container" id="quiz-area"></div>

  <div class="submit-bar">
    <span class="submit-note" id="submit-note">{total}문제를 모두 답한 후 채점하세요</span>
    <button class="submit-btn" id="submit-btn" disabled onclick="submitExam()">채점하기</button>
  </div>
</div>

<!-- ── RESULT PAGE ── -->
<div id="result-page"></div>

<script>
const Q = {q_json};
const TOTAL = Q.length;
const answered = new Array(TOTAL).fill(null);
let startTime = Date.now();
let timerInterval;

/* ── Timer ── */
timerInterval = setInterval(() => {{
  const s = Math.floor((Date.now() - startTime) / 1000);
  document.getElementById('timer').textContent =
    '⏱ ' + String(Math.floor(s/60)).padStart(2,'0') + ':' + String(s%60).padStart(2,'0');
}}, 1000);

/* ── Helpers ── */
function esc(s) {{ const d = document.createElement('div'); d.textContent = String(s||''); return d.innerHTML; }}
function renderSentence(s) {{
  return esc(s).replace(/-------/g, '<span class="blank">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</span>');
}}

/* ── Build quiz ── */
function buildQuiz() {{
  const area = document.getElementById('quiz-area');
  Q.forEach((q, i) => {{
    const card = document.createElement('div');
    card.className = 'question-card';
    card.id = 'card-' + i;

    let choicesHtml = '';
    for (const [key, val] of Object.entries(q.choices)) {{
      choicesHtml += `<button class="choice-btn" data-qi="${{i}}" data-key="${{key}}" onclick="choose(this)">
        <span class="ck">(${{key}})</span>
        <span class="ct">${{esc(val)}}</span>
        <span class="ci"></span>
      </button>`;
    }}

    card.innerHTML =
      `<div class="q-meta">
        <span class="q-num">Q${{q.idx}}</span>
        <span class="q-cat">${{esc(q.category)}}</span>
        <span class="q-src">Vol.${{q.vol}} TEST${{q.test}}</span>
      </div>
      <div class="q-sentence">${{renderSentence(q.sentence)}}</div>
      <div class="choices">${{choicesHtml}}</div>`;

    area.appendChild(card);
  }});
}}

function choose(btn) {{
  const qi = parseInt(btn.dataset.qi);
  const key = btn.dataset.key;
  const card = document.getElementById('card-' + qi);

  // Deselect previous
  card.querySelectorAll('.choice-btn').forEach(b => b.classList.remove('selected'));
  btn.classList.add('selected');

  const wasAnswered = answered[qi] !== null;
  answered[qi] = key;

  if (!wasAnswered) {{
    card.classList.add('answered');
    const cnt = answered.filter(a => a !== null).length;
    document.getElementById('answered-count').textContent = cnt;
    document.getElementById('progress').style.width = (cnt / TOTAL * 100) + '%';
    document.getElementById('submit-note').textContent =
      cnt < TOTAL ? `${{TOTAL - cnt}}문제 남았습니다` : '모두 답했습니다 — 채점 가능!';
    document.getElementById('submit-btn').disabled = cnt < TOTAL;
  }}
}}

/* ── Submit & Show Result ── */
function submitExam() {{
  clearInterval(timerInterval);
  const elapsed = Math.floor((Date.now() - startTime) / 1000);

  let score = 0;
  const catCorrect = {{}}, catTotal = {{}};
  const wrongItems = [], correctItems = [];

  Q.forEach((q, i) => {{
    const userAns = answered[i];
    const isCorrect = userAns === q.answer;
    if (isCorrect) score++;

    catTotal[q.category] = (catTotal[q.category] || 0) + 1;
    if (isCorrect) catCorrect[q.category] = (catCorrect[q.category] || 0) + 1;
    else wrongItems.push({{ ...q, userAnswer: userAns }});
    correctItems.push({{ ...q, userAnswer: userAns, isCorrect }});
  }});

  const pct = Math.round(score / TOTAL * 100);
  const mm = String(Math.floor(elapsed/60)).padStart(2,'0');
  const ss = String(elapsed%60).padStart(2,'0');

  /* ─ Category cards ─ */
  let catHtml = '<div class="cat-grid">';
  const catOrder = ['품사','동사','접속사/전치사','관계대명사','어휘','대명사','비교급/최상급','기타문법'];
  const cats = catOrder.filter(c => catTotal[c]);
  cats.forEach(cat => {{
    const c = catCorrect[cat] || 0, t = catTotal[cat];
    const p = Math.round(c/t*100);
    const cls = p>=80 ? 'good' : p>=50 ? 'mid' : 'bad';
    catHtml += `<div class="cat-card">
      <div class="cat-name">${{esc(cat)}}</div>
      <div class="bar-wrap">
        <div class="bar-bg"><div class="bar-fill ${{cls}}" style="width:${{p}}%"></div></div>
        <div class="bar-pct">${{c}}/${{t}}</div>
      </div>
    </div>`;
  }});
  catHtml += '</div>';

  /* ─ Wrong cards ─ */
  let wrongHtml = '';
  wrongItems.forEach(q => {{
    const userTxt = q.choices[q.userAnswer] || '(미답변)';
    const corrTxt = q.choices[q.answer] || '';
    const explBody = (q.translation ? '<div class="translation">📘 ' + esc(q.translation) + '</div>' : '')
      + (q.explanation ? esc(q.explanation) : '');
    wrongHtml += `<div class="wrong-card">
      <div class="wc-meta">
        <span>Q${{q.idx}}</span>
        <span class="wc-cat">${{esc(q.category)}}</span>
        <span>Vol.${{q.vol}} TEST${{q.test}} #${{q.qnum}}</span>
      </div>
      <div class="wc-sentence">${{renderSentence(q.sentence)}}</div>
      <div class="answer-row correct-row">
        <span class="ar-label">✅ 정답</span>
        <span class="ar-key">(${{q.answer}})</span>
        <span class="ar-text">${{esc(corrTxt)}}</span>
      </div>
      <div class="answer-row wrong-row">
        <span class="ar-label">❌ 내 답</span>
        <span class="ar-key">(${{q.userAnswer}})</span>
        <span class="ar-text">${{esc(userTxt)}}</span>
      </div>
      ${{(q.explanation || q.translation) ? `<details class="expl-toggle">
        <summary>▶ 번역 · 해설 보기</summary>
        <div class="expl-body">${{explBody}}</div>
      </details>` : ''}}
    </div>`;
  }});

  /* ─ Claude prompt ─ */
  let promptLines = [
    `TOEIC Part5 모의고사 결과를 분석해주세요.`,
    ``,
    `[시험 정보]`,
    `- 총 문제: ${{TOTAL}}문제`,
    `- 정답: ${{score}}문제 (${{pct}}%)`,
    `- 소요 시간: ${{mm}}:${{ss}}`,
    ``,
    `[유형별 정답률]`,
  ];
  cats.forEach(cat => {{
    const c = catCorrect[cat]||0, t = catTotal[cat], p = Math.round(c/t*100);
    promptLines.push(`- ${{cat}}: ${{c}}/${{t}} (${{p}}%)`);
  }});
  promptLines.push('', '[오답 목록]');
  wrongItems.forEach(q => {{
    promptLines.push(`Q${{q.idx}} [${{q.category}}] Vol.${{q.vol}}`);
    promptLines.push(`  문제: ${{q.sentence}}`);
    promptLines.push(`  정답: (${{q.answer}}) ${{q.choices[q.answer]||''}}`);
    promptLines.push(`  내가 선택: (${{q.userAnswer}}) ${{q.choices[q.userAnswer]||''}}`);
    promptLines.push('');
  }});
  promptLines.push('위 결과를 바탕으로:');
  promptLines.push('1. 취약한 문법 유형과 그 이유를 분석해주세요.');
  promptLines.push('2. 오답 문제마다 왜 틀렸는지 간략히 설명해주세요.');
  promptLines.push('3. 집중적으로 학습해야 할 포인트를 우선순위로 알려주세요.');
  const claudePrompt = promptLines.join('\\n');

  /* ─ Render result page ─ */
  const rp = document.getElementById('result-page');
  rp.innerHTML = `
    <div class="result-hero">
      <h2>시험 결과 — ${{now}}</h2>
      <div><span class="score-big">${{score}}</span><span class="score-denom"> / ${{TOTAL}}</span></div>
      <div class="result-sub">
        <span>정답률 ${{pct}}%</span>
        <span>소요시간 ${{mm}}:${{ss}}</span>
        <span>오답 ${{wrongItems.length}}문제</span>
      </div>
    </div>

    <div class="result-body">
      <div class="section-title">📊 유형별 정답률</div>
      ${{catHtml}}

      ${{wrongItems.length > 0 ? `
      <div class="section-title">❌ 오답 분석 (${{wrongItems.length}}문제)</div>
      ${{wrongHtml}}
      ` : '<div class="section-title" style="color:#43a047">🎉 전부 정답!</div>'}}

      <div class="claude-box">
        <h3>💬 Claude에게 분석 요청하기</h3>
        <p style="font-size:13px;color:#666;margin-bottom:10px;">아래 텍스트를 복사해서 Claude에게 붙여넣으세요.</p>
        <div class="claude-prompt" id="claude-prompt">${{esc(claudePrompt)}}</div>
        <button class="copy-btn" onclick="copyPrompt()">📋 클립보드에 복사</button>
        <span id="copy-toast" style="margin-left:10px;font-size:13px;color:#43a047;display:none">복사됨!</span>
      </div>

      <div class="result-actions">
        <button class="primary" onclick="location.reload()">🔄 다시 풀기</button>
        <button onclick="window.print()">🖨 인쇄</button>
      </div>
    </div>`;

  document.getElementById('quiz-page').style.display = 'none';
  rp.classList.add('show');
  window.scrollTo(0, 0);
}}

function copyPrompt() {{
  const text = document.getElementById('claude-prompt').innerText;
  navigator.clipboard.writeText(text).then(() => {{
    const t = document.getElementById('copy-toast');
    t.style.display = 'inline';
    setTimeout(() => t.style.display = 'none', 2000);
  }});
}}

const now = "{now}";
buildQuiz();
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
