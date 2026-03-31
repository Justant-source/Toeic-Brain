"""
단어장 퀴즈 HTML 생성기.

노랭이 단어장(Day 1~30, 약 4,000단어)에서 4지선다 퀴즈를 생성한다.

Usage:
    python exam/generate_vocab_quiz.py                             # 기본 50문제
    python exam/generate_vocab_quiz.py --count 30 --day 1 2 3      # Day 1~3에서 30문제
    python exam/generate_vocab_quiz.py --mode kr2en --level 900점  # 한→영, 900점만
    python exam/generate_vocab_quiz.py --with-examples             # 기출 예문 포함
"""

import sys
import json
import argparse
import random
import html
from pathlib import Path
from datetime import datetime

# ── Paths ─────────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
JSON_DIR = PROJECT_ROOT / "data" / "json"
EXAMPLES_PATH = JSON_DIR / "word_ets_examples.json"
RESULT_DIR = SCRIPT_DIR / "result"

# ── HTML escape helper ────────────────────────────────────────────────────────

def esc(s: str) -> str:
    return html.escape(str(s))


# ── Data loading ──────────────────────────────────────────────────────────────

def load_vocab(days: list[int] | None = None, levels: list[str] | None = None) -> list[dict]:
    """Load vocabulary from hackers_vocab.json, filtering by day and level."""
    vocab_path = JSON_DIR / "hackers_vocab.json"
    if not vocab_path.exists():
        return []
    with open(vocab_path, encoding="utf-8") as fh:
        all_entries = json.load(fh)
    vocab = []
    for e in all_entries:
        if days and e.get("day") not in days:
            continue
        if levels and e.get("level") not in levels:
            continue
        if e.get("word") and e.get("meaning_kr"):
            vocab.append(e)
    return vocab


def load_examples() -> dict:
    """Load word → examples mapping."""
    if not EXAMPLES_PATH.exists():
        return {}
    with open(EXAMPLES_PATH, encoding="utf-8") as f:
        return json.load(f)


def pick_distractors(correct: dict, pool: list[dict], mode: str, count: int = 3) -> list[str]:
    """Pick distractor options that differ from the correct answer."""
    correct_pos = set(correct.get("pos", []))
    correct_val = correct["meaning_kr"] if mode == "en2kr" else correct["word"]

    # Prefer same POS for more natural distractors
    same_pos = [e for e in pool
                if e["id"] != correct["id"]
                and (set(e.get("pos", [])) & correct_pos)
                and (e["meaning_kr"] if mode == "en2kr" else e["word"]) != correct_val]
    diff_pos = [e for e in pool
                if e["id"] != correct["id"]
                and not (set(e.get("pos", [])) & correct_pos)
                and (e["meaning_kr"] if mode == "en2kr" else e["word"]) != correct_val]

    random.shuffle(same_pos)
    random.shuffle(diff_pos)
    candidates = same_pos + diff_pos

    distractors = []
    seen = {correct_val}
    for c in candidates:
        val = c["meaning_kr"] if mode == "en2kr" else c["word"]
        if val not in seen:
            distractors.append(val)
            seen.add(val)
        if len(distractors) >= count:
            break
    return distractors


def select_questions(vocab: list[dict], count: int) -> list[dict]:
    """Select up to count vocab entries, distributed across days."""
    by_day: dict[int, list[dict]] = {}
    for v in vocab:
        by_day.setdefault(v.get("day", 0), []).append(v)

    selected = []
    per_day = max(1, count // len(by_day)) if by_day else count
    for day, entries in by_day.items():
        random.shuffle(entries)
        selected.extend(entries[:per_day])

    if len(selected) < count:
        remaining = [v for v in vocab if v not in selected]
        random.shuffle(remaining)
        selected.extend(remaining[: count - len(selected)])

    random.shuffle(selected)
    return selected[:count]


# ── HTML generation ───────────────────────────────────────────────────────────

def generate_html(
    vocab: list[dict],
    pool: list[dict],
    mode: str,
    with_examples: bool,
    examples_data: dict,
) -> str:
    """Generate a self-contained HTML quiz page."""
    q_data = []
    for i, entry in enumerate(vocab):
        word = entry["word"]
        meaning = entry["meaning_kr"]
        pos_list = entry.get("pos", [])
        pos_str = ", ".join(pos_list) if pos_list else ""

        if mode == "en2kr":
            prompt = word
            prompt_sub = f"({pos_str})" if pos_str else ""
            correct_answer = meaning
        else:
            prompt = meaning
            prompt_sub = ""
            correct_answer = word

        distractors = pick_distractors(entry, pool, mode)
        options = [correct_answer] + distractors
        random.shuffle(options)
        answer_idx = options.index(correct_answer)

        example = None
        if with_examples and word.lower() in examples_data:
            exs = examples_data[word.lower()].get("examples", [])
            # Pick one with a source
            for ex in exs:
                if ex.get("sentence") and ex.get("source"):
                    example = {"sentence": ex["sentence"][:200], "source": ex["source"]}
                    break

        q_data.append({
            "idx": i + 1,
            "word": word,
            "meaning": meaning,
            "day": entry.get("day", ""),
            "level": entry.get("level", ""),
            "pos": pos_str,
            "prompt": prompt,
            "prompt_sub": prompt_sub,
            "options": options,
            "answer_idx": answer_idx,
            "example": example,
        })

    q_json = json.dumps(q_data, ensure_ascii=False)
    total = len(q_data)
    mode_label = "영→한" if mode == "en2kr" else "한→영"
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>단어장 퀴즈 ({mode_label}, {total}문제)</title>
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
.q-meta .tag {{ background: #C4A35A22; color: #8B7332; padding: 2px 8px; border-radius: 4px;
               font-size: 12px; font-weight: 600; }}

.prompt {{ text-align: center; margin: 24px 0; }}
.prompt .word {{ font-size: 28px; font-weight: 700; color: #1B2A4A; }}
.prompt .sub {{ font-size: 15px; color: #888; margin-top: 4px; }}

.choices {{ display: flex; flex-direction: column; gap: 10px; margin-top: 16px; }}
.choice-btn {{ display: flex; align-items: center; gap: 12px; padding: 14px 16px; border: 2px solid #e0e0e0;
               border-radius: 8px; background: #fff; cursor: pointer; font-size: 15px; transition: all 0.2s; }}
.choice-btn:hover:not(.disabled) {{ border-color: #C4A35A; background: #FFFDF5; }}
.choice-btn .num {{ font-weight: 700; color: #1B2A4A; min-width: 24px; }}
.choice-btn.correct {{ border-color: #2E7D32; background: #E8F5E9; }}
.choice-btn.wrong {{ border-color: #C62828; background: #FFEBEE; }}
.choice-btn.show-answer {{ border-color: #2E7D32; background: #E8F5E9; }}
.choice-btn .icon {{ margin-left: auto; font-size: 18px; }}
.choice-btn.disabled {{ cursor: default; opacity: 0.85; }}

.example-box {{ margin-top: 16px; padding: 12px 16px; background: #f9f9f9; border-radius: 8px;
                border-left: 3px solid #C4A35A; display: none; }}
.example-box.visible {{ display: block; }}
.example-box .label {{ font-size: 12px; color: #C4A35A; font-weight: 600; margin-bottom: 4px; }}
.example-box .sent {{ font-size: 14px; line-height: 1.6; color: #444; }}
.example-box .src {{ font-size: 12px; color: #999; margin-top: 4px; }}

.nav-btn {{ display: inline-block; margin-top: 16px; padding: 12px 32px; background: #1B2A4A;
            color: #C4A35A; border: none; border-radius: 8px; font-size: 15px; font-weight: 600;
            cursor: pointer; float: right; }}
.nav-btn:hover {{ background: #243656; }}
.nav-btn:disabled {{ opacity: 0.4; cursor: default; }}

.result {{ display: none; background: #fff; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);
           padding: 32px; text-align: center; }}
.result.active {{ display: block; }}
.result h2 {{ font-size: 24px; color: #1B2A4A; margin-bottom: 8px; }}
.result .score {{ font-size: 48px; font-weight: 800; color: #C4A35A; margin: 16px 0; }}
.result .sub {{ color: #888; font-size: 15px; margin-bottom: 24px; }}
.day-stats {{ text-align: left; margin: 24px 0; }}
.day-row {{ display: flex; align-items: center; gap: 12px; margin-bottom: 10px; font-size: 14px; }}
.day-row .label {{ min-width: 80px; font-weight: 600; }}
.day-row .bar-bg {{ flex: 1; height: 20px; background: #eee; border-radius: 4px; overflow: hidden; }}
.day-row .bar-fill {{ height: 100%; background: #C4A35A; border-radius: 4px; transition: width 0.5s; }}
.day-row .pct {{ min-width: 48px; text-align: right; font-weight: 600; }}
.wrong-list {{ text-align: left; margin-top: 24px; }}
.wrong-list h3 {{ font-size: 16px; margin-bottom: 12px; color: #C62828; }}
.wrong-item {{ font-size: 13px; color: #555; padding: 6px 0; border-bottom: 1px solid #f0f0f0; }}
.wrong-item .w {{ font-weight: 600; color: #1B2A4A; }}
.result-actions {{ margin-top: 24px; display: flex; gap: 12px; justify-content: center; }}
.result-actions button {{ padding: 12px 24px; border: 2px solid #1B2A4A; border-radius: 8px;
                          font-size: 14px; font-weight: 600; cursor: pointer; background: #fff; color: #1B2A4A; }}
.result-actions button.primary {{ background: #1B2A4A; color: #C4A35A; }}
</style>
</head>
<body>

<div class="header">
  <h1>단어장 퀴즈 ({esc(mode_label)})</h1>
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
const NUMS = ['①', '②', '③', '④'];

setInterval(() => {{
  const s = Math.floor((Date.now() - startTime) / 1000);
  const m = String(Math.floor(s / 60)).padStart(2, '0');
  const sec = String(s % 60).padStart(2, '0');
  document.getElementById('timer').textContent = '⏱ ' + m + ':' + sec;
}}, 1000);

function esc(s) {{ const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }}

function render() {{
  const area = document.getElementById('quiz-area');
  area.innerHTML = '';

  if (current >= TOTAL) {{ showResult(); return; }}

  const q = Q[current];
  document.getElementById('counter').textContent = (current + 1) + '/' + TOTAL;
  document.getElementById('progress').style.width = ((current + 1) / TOTAL * 100) + '%';

  const card = document.createElement('div');
  card.className = 'question-card active';

  let choicesHtml = '';
  q.options.forEach((opt, i) => {{
    choicesHtml += '<button class="choice-btn" data-idx="' + i + '">'
      + '<span class="num">' + NUMS[i] + '</span> '
      + '<span>' + esc(opt) + '</span>'
      + '<span class="icon"></span></button>';
  }});

  let exampleHtml = '';
  if (q.example) {{
    exampleHtml = '<div class="example-box" id="example-box">'
      + '<div class="label">기출 예문</div>'
      + '<div class="sent">' + esc(q.example.sentence) + '</div>'
      + '<div class="src">— ' + esc(q.example.source) + '</div></div>';
  }}

  card.innerHTML = '<div class="q-meta">Q' + q.idx + '. '
    + '<span class="tag">Day ' + q.day + '</span> '
    + '<span class="tag">' + esc(q.level) + '</span></div>'
    + '<div class="prompt"><div class="word">' + esc(q.prompt) + '</div>'
    + (q.prompt_sub ? '<div class="sub">' + esc(q.prompt_sub) + '</div>' : '') + '</div>'
    + '<div class="choices">' + choicesHtml + '</div>'
    + exampleHtml
    + '<button class="nav-btn" id="next-btn" disabled onclick="nextQ()">다음 문제 →</button>';

  area.appendChild(card);

  if (answered[current] !== null) {{
    applyAnswer(answered[current], false);
  }} else {{
    card.querySelectorAll('.choice-btn').forEach(btn => {{
      btn.addEventListener('click', () => answerClick(btn));
    }});
  }}
}}

function answerClick(btn) {{
  const idx = parseInt(btn.dataset.idx);
  answered[current] = idx;
  applyAnswer(idx, true);
}}

function applyAnswer(idx, isNew) {{
  const q = Q[current];
  const card = document.querySelector('.question-card');
  const btns = card.querySelectorAll('.choice-btn');

  btns.forEach(b => {{
    b.classList.add('disabled');
    const bIdx = parseInt(b.dataset.idx);
    if (bIdx === q.answer_idx) {{
      b.classList.add(bIdx === idx ? 'correct' : 'show-answer');
      b.querySelector('.icon').textContent = '✅';
    }} else if (bIdx === idx) {{
      b.classList.add('wrong');
      b.querySelector('.icon').textContent = '❌';
    }}
  }});

  if (isNew && idx === q.answer_idx) score++;

  const exBox = document.getElementById('example-box');
  if (exBox) exBox.classList.add('visible');

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

  const dayCorrect = {{}};
  const dayTotal = {{}};
  const wrongItems = [];
  Q.forEach((q, i) => {{
    const d = 'Day ' + q.day;
    dayTotal[d] = (dayTotal[d] || 0) + 1;
    if (answered[i] === q.answer_idx) {{
      dayCorrect[d] = (dayCorrect[d] || 0) + 1;
    }} else {{
      wrongItems.push(q);
    }}
  }});

  let dayHtml = '';
  for (const d of Object.keys(dayTotal).sort((a, b) => parseInt(a.split(' ')[1]) - parseInt(b.split(' ')[1]))) {{
    const c = dayCorrect[d] || 0;
    const t = dayTotal[d];
    const p = Math.round(c / t * 100);
    dayHtml += '<div class="day-row"><span class="label">' + esc(d) + '</span>'
      + '<div class="bar-bg"><div class="bar-fill" style="width:' + p + '%"></div></div>'
      + '<span class="pct">' + c + '/' + t + '</span></div>';
  }}

  let wrongHtml = '';
  if (wrongItems.length) {{
    wrongHtml = '<div class="wrong-list"><h3>틀린 단어 (' + wrongItems.length + ')</h3>';
    wrongItems.forEach(q => {{
      wrongHtml += '<div class="wrong-item"><span class="w">' + esc(q.word) + '</span> — '
        + esc(q.meaning) + '</div>';
    }});
    wrongHtml += '</div>';
  }}

  const area = document.getElementById('quiz-area');
  area.innerHTML = '<div class="result active">'
    + '<h2>퀴즈 결과</h2>'
    + '<div class="score">' + score + ' / ' + TOTAL + '</div>'
    + '<div class="sub">' + pct + '%  ⏱ ' + m + ':' + sec + '</div>'
    + '<div class="day-stats">' + dayHtml + '</div>'
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
    parser = argparse.ArgumentParser(description="단어장 퀴즈 HTML 생성기")
    parser.add_argument("--count", type=int, default=50, help="출제 문제 수 (기본 50)")
    parser.add_argument("--day", type=int, nargs="+", help="출제할 Day (예: 1 5 10)")
    parser.add_argument("--level", nargs="+", help="출제할 레벨 (예: 기초 800점 900점)")
    parser.add_argument("--mode", choices=["en2kr", "kr2en"], default="en2kr",
                        help="퀴즈 모드 (기본: en2kr)")
    parser.add_argument("--with-examples", action="store_true", help="기출 예문 포함")
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")

    vocab = load_vocab(args.day, args.level)
    if not vocab:
        print("오류: 단어를 찾을 수 없습니다.", file=sys.stderr)
        sys.exit(1)

    selected = select_questions(vocab, args.count)
    print(f"총 {len(vocab)}단어 중 {len(selected)}문제 선택")

    examples_data = load_examples() if args.with_examples else {}
    html_content = generate_html(selected, vocab, args.mode, args.with_examples, examples_data)

    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    output_path = RESULT_DIR / f"vocab_quiz_{timestamp}.html"
    output_path.write_text(html_content, encoding="utf-8")
    print(f"생성 완료: {output_path}")


if __name__ == "__main__":
    main()
