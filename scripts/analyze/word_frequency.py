"""
5권 전체 기준 가장 많이 출제된 단어 분석. Top 100 빈출 단어, 권별 출제 경향 변화.
"""

import sys
import json
import re
from pathlib import Path
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

# ── paths ─────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "processed" / "questions"
OUTPUT_DIR = ROOT / "output" / "reports"

# ── stop words ────────────────────────────────────────────────────────────────

STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall",
    "should", "can", "could", "may", "might", "must", "to", "of", "in",
    "for", "on", "with", "at", "by", "from", "as", "into", "through",
    "during", "before", "after", "above", "below", "between", "out",
    "off", "over", "under", "again", "then", "once", "that", "this",
    "these", "those", "it", "its", "and", "or", "but", "nor", "so",
    "yet", "both", "either", "neither", "not", "no", "all", "any",
    "each", "every", "few", "more", "most", "other", "such", "same",
    "than", "too", "very", "just", "there", "their", "they", "them",
    "which", "who", "whom", "whose", "what", "when", "where", "how",
    "i", "me", "my", "we", "our", "you", "your", "he", "his", "she",
    "her", "if", "up", "about", "also", "s", "---", "-------",
}

BLANK_PATTERN = re.compile(r"-{2,}")
TOKEN_PATTERN = re.compile(r"[a-zA-Z']+")


def tokenize(text: str) -> list[str]:
    text = BLANK_PATTERN.sub(" ", text)
    return [t.lower() for t in TOKEN_PATTERN.findall(text)
            if t.lower() not in STOP_WORDS and len(t) > 1]


# ── data loading ──────────────────────────────────────────────────────────────

def load_part5_files() -> dict[int, list[dict]]:
    """Return {volume: [questions]}"""
    result: dict[int, list[dict]] = {}
    for path in sorted(DATA_DIR.glob("vol*_part5.json")):
        try:
            with open(path, encoding="utf-8") as f:
                questions = json.load(f)
            vol = questions[0]["volume"] if questions else int(path.stem[3])
            result[vol] = questions
        except (OSError, json.JSONDecodeError, KeyError) as e:
            print(f"[WARN] Skipping {path.name}: {e}")
    return result


def count_words_in_question(q: dict) -> list[str]:
    words = tokenize(q.get("sentence", ""))
    for choice in q.get("choices", {}).values():
        words.extend(tokenize(choice))
    return words


# ── analysis ──────────────────────────────────────────────────────────────────

def analyse(volumes: dict[int, list[dict]]) -> tuple[Counter, dict[int, Counter]]:
    global_counter: Counter = Counter()
    per_vol: dict[int, Counter] = {}

    for vol, questions in sorted(volumes.items()):
        vc: Counter = Counter()
        for q in questions:
            words = count_words_in_question(q)
            vc.update(words)
            global_counter.update(words)
        per_vol[vol] = vc
        print(f"  Vol {vol}: {len(questions)} questions, {sum(vc.values())} tokens, "
              f"{len(vc)} unique words")

    return global_counter, per_vol


# ── console output ────────────────────────────────────────────────────────────

def print_top(counter: Counter, n: int = 100):
    print(f"\n{'─'*55}")
    print(f"  TOP {n} MOST FREQUENT WORDS (all volumes)")
    print(f"{'─'*55}")
    print(f"  {'Rank':<5} {'Word':<20} {'Count':>6}")
    print(f"  {'─'*5} {'─'*20} {'─'*6}")
    for rank, (word, count) in enumerate(counter.most_common(n), 1):
        print(f"  {rank:<5} {word:<20} {count:>6}")


def print_per_vol_top(per_vol: dict[int, Counter], n: int = 10):
    print(f"\n{'─'*55}")
    print("  TOP 10 PER VOLUME")
    print(f"{'─'*55}")
    for vol, counter in sorted(per_vol.items()):
        top = counter.most_common(n)
        words = ", ".join(f"{w}({c})" for w, c in top)
        print(f"  Vol {vol}: {words}")


# ── HTML output ───────────────────────────────────────────────────────────────

def build_html(global_counter: Counter, per_vol: dict[int, Counter]) -> str:
    top100 = global_counter.most_common(100)
    total_tokens = sum(global_counter.values())

    # per-volume top-10 table columns
    vol_list = sorted(per_vol.keys())
    vol_headers = "".join(f"<th>Vol {v} Top 10</th>" for v in vol_list)

    vol_rows = ""
    max_rows = 10
    per_vol_top = {v: per_vol[v].most_common(max_rows) for v in vol_list}
    for i in range(max_rows):
        cells = ""
        for v in vol_list:
            tops = per_vol_top[v]
            if i < len(tops):
                w, c = tops[i]
                cells += f"<td>{w} <span class='cnt'>({c})</span></td>"
            else:
                cells += "<td></td>"
        vol_rows += f"<tr><td class='rank'>{i+1}</td>{cells}</tr>\n"

    global_rows = ""
    for rank, (word, count) in enumerate(top100, 1):
        pct = count / total_tokens * 100
        bar_w = int(pct * 40)
        global_rows += (
            f"<tr>"
            f"<td class='rank'>{rank}</td>"
            f"<td class='word'>{word}</td>"
            f"<td class='cnt'>{count}</td>"
            f"<td class='pct'>{pct:.2f}%</td>"
            f"<td class='bar'><div style='width:{bar_w}px'></div></td>"
            f"</tr>\n"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Word Frequency Analysis — TOEIC Brain</title>
<style>
  body {{ font-family: 'Segoe UI', Arial, sans-serif; background:#f8f9fa; color:#212529; margin:0; padding:24px; }}
  h1 {{ color:#0d6efd; border-bottom:2px solid #0d6efd; padding-bottom:8px; }}
  h2 {{ color:#495057; margin-top:36px; }}
  table {{ border-collapse:collapse; width:100%; max-width:900px; background:#fff;
           box-shadow:0 1px 4px rgba(0,0,0,.12); border-radius:6px; overflow:hidden; margin-bottom:32px; }}
  th {{ background:#0d6efd; color:#fff; padding:10px 14px; text-align:left; font-size:.9rem; }}
  td {{ padding:7px 14px; border-bottom:1px solid #dee2e6; font-size:.875rem; }}
  tr:last-child td {{ border-bottom:none; }}
  tr:hover td {{ background:#e9f2ff; }}
  .rank {{ color:#6c757d; width:50px; text-align:center; }}
  .word {{ font-weight:600; }}
  .cnt  {{ color:#0d6efd; text-align:right; }}
  .pct  {{ color:#6c757d; text-align:right; }}
  .bar div {{ background:#0d6efd55; height:14px; border-radius:3px; min-width:2px; }}
  .summary {{ background:#fff; border-left:4px solid #0d6efd; padding:12px 18px;
              margin-bottom:28px; border-radius:0 6px 6px 0; max-width:600px;
              box-shadow:0 1px 3px rgba(0,0,0,.08); }}
</style>
</head>
<body>
<h1>Word Frequency Analysis — TOEIC Brain ETS Part 5</h1>
<div class="summary">
  <strong>Total tokens analysed:</strong> {total_tokens:,}<br>
  <strong>Unique words (after stop-word filter):</strong> {len(global_counter):,}<br>
  <strong>Volumes:</strong> {', '.join(f'Vol {v}' for v in vol_list)}
</div>

<h2>Top 100 Most Frequent Words (All Volumes)</h2>
<table>
<thead><tr>
  <th>Rank</th><th>Word</th><th>Count</th><th>% of tokens</th><th>Bar</th>
</tr></thead>
<tbody>
{global_rows}
</tbody>
</table>

<h2>Top 10 Per Volume</h2>
<table>
<thead><tr>
  <th>Rank</th>{vol_headers}
</tr></thead>
<tbody>
{vol_rows}
</tbody>
</table>

</body>
</html>
"""


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    if not DATA_DIR.exists():
        print(f"[ERROR] Data directory not found: {DATA_DIR}")
        sys.exit(1)

    print("Loading Part5 files...")
    volumes = load_part5_files()
    if not volumes:
        print("[ERROR] No Part5 files found.")
        sys.exit(1)

    print("\nAnalysing word frequency...")
    global_counter, per_vol = analyse(volumes)

    print_top(global_counter, n=100)
    print_per_vol_top(per_vol, n=10)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "frequency_analysis.html"
    html = build_html(global_counter, per_vol)
    out_path.write_text(html, encoding="utf-8")
    print(f"\n[OK] HTML report saved: {out_path}")


if __name__ == "__main__":
    main()
