"""
노랭이 단어장의 기출 커버리지 리포트. Day별 기출 커버리지, 기출에는 나왔지만 노랭이에 없는 단어 목록.
"""

import sys
import json
import re
from pathlib import Path
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
VOCAB_PATH = ROOT / "data" / "json" / "hackers_vocab.json"
ETS_EXAMPLES_PATH = ROOT / "data" / "json" / "word_ets_examples.json"
OUTPUT_DIR = ROOT / "output" / "reports"

# ── loading helpers ───────────────────────────────────────────────────────────

def load_json(path: Path, label: str) -> dict | list | None:
    if not path.exists():
        print(f"[WARN] {label} not found: {path}")
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"[WARN] Cannot read {label}: {e}")
        return None


# ── vocab helpers ─────────────────────────────────────────────────────────────

def vocab_by_day(vocab_data: list | dict) -> dict[str, list[str]]:
    """
    Accept either a list of {word, day} dicts or a dict {day: [words]}.
    Returns {day_label: [word, ...]}
    """
    days: dict[str, list[str]] = defaultdict(list)

    if isinstance(vocab_data, list):
        for item in vocab_data:
            if isinstance(item, dict):
                word = str(item.get("word", item.get("headword", ""))).strip().lower()
                day = str(item.get("day", item.get("Day", "unknown")))
                if word:
                    days[day].append(word)
    elif isinstance(vocab_data, dict):
        for key, val in vocab_data.items():
            if isinstance(val, list):
                for entry in val:
                    if isinstance(entry, str):
                        days[key].append(entry.strip().lower())
                    elif isinstance(entry, dict):
                        word = str(entry.get("word", entry.get("headword", ""))).strip().lower()
                        if word:
                            days[key].append(word)
            else:
                days[key].append(str(val).strip().lower())

    return dict(days)


def flat_vocab_set(days: dict[str, list[str]]) -> set[str]:
    return {w for words in days.values() for w in words}


# ── map helpers ───────────────────────────────────────────────────────────────

def parse_word_question_map(map_data: dict | list) -> dict[str, list[str]]:
    """
    Accept:
      - dict {word: [question_ids]}   <- primary expected format
      - list [{word, questions}]
    Returns {word: [question_ids]}
    """
    if isinstance(map_data, dict):
        result = {}
        for word, val in map_data.items():
            w = word.strip().lower()
            if isinstance(val, list):
                result[w] = val
            elif isinstance(val, dict):
                result[w] = val.get("questions", val.get("question_ids", []))
            else:
                result[w] = []
        return result
    if isinstance(map_data, list):
        result = {}
        for item in map_data:
            w = str(item.get("word", "")).strip().lower()
            qs = item.get("questions", item.get("question_ids", []))
            if w:
                result[w] = qs if isinstance(qs, list) else []
        return result
    return {}


# ── analysis ──────────────────────────────────────────────────────────────────

def compute_coverage(
    days: dict[str, list[str]],
    vocab_set: set[str],
    wq_map: dict[str, list[str]],
) -> tuple[dict, list, list]:
    """
    Returns:
      day_stats   : {day: {total, matched, coverage_pct, words:[{word,count}]}}
      not_in_vocab: [{word, count, questions}]   words in questions but not in vocab
      top_by_count: [{word, count}] all matched words sorted by count desc
    """
    # words that appear in ETS questions (from map)
    ets_words: set[str] = set(wq_map.keys())

    # ── per-day coverage ──────────────────────────────────
    day_stats: dict = {}
    for day, words in sorted(days.items(), key=lambda x: _day_sort_key(x[0])):
        matched = []
        for w in words:
            if w in wq_map:
                cnt = len(wq_map[w])
                matched.append({"word": w, "count": cnt})
        matched.sort(key=lambda x: -x["count"])
        day_stats[day] = {
            "total": len(words),
            "matched": len(matched),
            "coverage_pct": len(matched) / len(words) * 100 if words else 0.0,
            "words": matched,
        }

    # ── words in ETS but not in vocab ────────────────────
    not_in_vocab = []
    for w in sorted(ets_words):
        if w not in vocab_set:
            cnt = len(wq_map[w])
            not_in_vocab.append({"word": w, "count": cnt, "questions": wq_map[w][:5]})
    not_in_vocab.sort(key=lambda x: -x["count"])

    # ── top words by occurrence count ────────────────────
    top_by_count = []
    for w in vocab_set:
        if w in wq_map:
            top_by_count.append({"word": w, "count": len(wq_map[w])})
    top_by_count.sort(key=lambda x: -x["count"])

    return day_stats, not_in_vocab, top_by_count


def _day_sort_key(day: str) -> tuple:
    m = re.search(r"(\d+)", day)
    return (0, int(m.group(1))) if m else (1, day)


# ── console output ────────────────────────────────────────────────────────────

def print_summary(day_stats: dict, not_in_vocab: list, top_by_count: list):
    total_words = sum(d["total"] for d in day_stats.values())
    total_matched = sum(d["matched"] for d in day_stats.values())
    overall_pct = total_matched / total_words * 100 if total_words else 0.0

    print(f"\n{'═'*58}")
    print(f"  VOCAB COVERAGE SUMMARY")
    print(f"{'═'*58}")
    print(f"  Total vocab words  : {total_words:,}")
    print(f"  Words with ETS hits: {total_matched:,}")
    print(f"  Overall coverage   : {overall_pct:.1f}%")
    print(f"  Supp. study words  : {len(not_in_vocab):,}")
    print(f"{'═'*58}")

    print(f"\n{'─'*58}")
    print(f"  PER-DAY COVERAGE")
    print(f"{'─'*58}")
    print(f"  {'Day':<10} {'Total':>6} {'Hits':>5} {'%':>7}  Bar")
    print(f"  {'─'*10} {'─'*6} {'─'*5} {'─'*7}  {'─'*20}")
    for day, s in day_stats.items():
        bar = "█" * int(s["coverage_pct"] / 5)
        print(f"  {day:<10} {s['total']:>6} {s['matched']:>5} {s['coverage_pct']:>6.1f}%  {bar}")

    print(f"\n{'─'*58}")
    print("  TOP 20 VOCAB WORDS BY ETS OCCURRENCE")
    print(f"{'─'*58}")
    for i, item in enumerate(top_by_count[:20], 1):
        print(f"  {i:>2}. {item['word']:<22} {item['count']:>4} questions")

    print(f"\n{'─'*58}")
    print("  TOP 30 ETS WORDS NOT IN VOCAB (supplementary study)")
    print(f"{'─'*58}")
    for i, item in enumerate(not_in_vocab[:30], 1):
        print(f"  {i:>2}. {item['word']:<22} {item['count']:>4} questions")


# ── HTML output ───────────────────────────────────────────────────────────────

def build_html(
    day_stats: dict,
    not_in_vocab: list,
    top_by_count: list,
    vocab_total: int,
) -> str:
    total_words   = sum(d["total"] for d in day_stats.values())
    total_matched = sum(d["matched"] for d in day_stats.values())
    overall_pct   = total_matched / total_words * 100 if total_words else 0.0

    # ── day coverage rows ──
    day_rows = ""
    for day, s in day_stats.items():
        pct = s["coverage_pct"]
        bar_w = int(pct * 1.8)
        color = "#28a745" if pct >= 50 else ("#ffc107" if pct >= 25 else "#dc3545")
        # top matched words for this day (up to 5)
        sample = ", ".join(
            f"<span class='badge'>{w['word']}({w['count']})</span>"
            for w in s["words"][:5]
        )
        day_rows += (
            f"<tr>"
            f"<td class='day'>{day}</td>"
            f"<td class='num'>{s['total']}</td>"
            f"<td class='num'>{s['matched']}</td>"
            f"<td class='pct'>{pct:.1f}%</td>"
            f"<td class='bar'><div style='width:{bar_w}px;background:{color}'></div></td>"
            f"<td class='sample'>{sample}</td>"
            f"</tr>\n"
        )

    # ── top-by-count rows (top 50) ──
    top_rows = ""
    for i, item in enumerate(top_by_count[:50], 1):
        top_rows += (
            f"<tr>"
            f"<td class='num'>{i}</td>"
            f"<td class='word'>{item['word']}</td>"
            f"<td class='num'>{item['count']}</td>"
            f"</tr>\n"
        )

    # ── not-in-vocab rows (top 100) ──
    supp_rows = ""
    for i, item in enumerate(not_in_vocab[:100], 1):
        qs = ", ".join(str(q) for q in item["questions"][:3])
        if len(item["questions"]) > 3:
            qs += f" … +{len(item['questions'])-3}"
        supp_rows += (
            f"<tr>"
            f"<td class='num'>{i}</td>"
            f"<td class='word'>{item['word']}</td>"
            f"<td class='num'>{item['count']}</td>"
            f"<td class='sample'>{qs}</td>"
            f"</tr>\n"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Coverage Report — TOEIC Brain</title>
<style>
  body  {{ font-family:'Segoe UI',Arial,sans-serif; background:#f8f9fa; color:#212529; margin:0; padding:24px; }}
  h1    {{ color:#0d6efd; border-bottom:2px solid #0d6efd; padding-bottom:8px; }}
  h2    {{ color:#495057; margin-top:36px; }}
  table {{ border-collapse:collapse; width:100%; max-width:960px; background:#fff;
           box-shadow:0 1px 4px rgba(0,0,0,.12); border-radius:6px; overflow:hidden; margin-bottom:32px; }}
  th    {{ background:#0d6efd; color:#fff; padding:10px 14px; text-align:left; font-size:.88rem; }}
  td    {{ padding:7px 14px; border-bottom:1px solid #dee2e6; font-size:.85rem; vertical-align:middle; }}
  tr:last-child td {{ border-bottom:none; }}
  tr:hover td {{ background:#e9f2ff; }}
  .day  {{ font-weight:600; white-space:nowrap; }}
  .word {{ font-weight:600; }}
  .num  {{ text-align:right; }}
  .pct  {{ text-align:right; font-weight:600; }}
  .bar div {{ height:14px; border-radius:3px; min-width:2px; }}
  .sample {{ font-size:.78rem; color:#495057; }}
  .badge {{ display:inline-block; background:#e9ecef; border-radius:4px; padding:1px 5px; margin:1px; }}
  .kpi  {{ display:inline-block; background:#fff; border-radius:8px; padding:16px 24px;
           margin:0 12px 16px 0; box-shadow:0 1px 4px rgba(0,0,0,.12); min-width:140px; text-align:center; }}
  .kpi .val {{ font-size:2rem; font-weight:700; color:#0d6efd; }}
  .kpi .lbl {{ font-size:.8rem; color:#6c757d; margin-top:4px; }}
</style>
</head>
<body>
<h1>Vocab Coverage Report — TOEIC Brain</h1>

<div>
  <div class="kpi"><div class="val">{total_words:,}</div><div class="lbl">Total vocab words</div></div>
  <div class="kpi"><div class="val">{total_matched:,}</div><div class="lbl">Words with ETS hits</div></div>
  <div class="kpi"><div class="val">{overall_pct:.1f}%</div><div class="lbl">Overall coverage</div></div>
  <div class="kpi"><div class="val">{len(not_in_vocab):,}</div><div class="lbl">Supp. study words</div></div>
</div>

<h2>Per-Day Coverage</h2>
<table>
<thead><tr>
  <th>Day</th><th>Total</th><th>Hits</th><th>Coverage</th><th>Bar</th><th>Top Matched Words</th>
</tr></thead>
<tbody>
{day_rows}
</tbody>
</table>

<h2>Top 50 Vocab Words by ETS Occurrence</h2>
<table>
<thead><tr><th>#</th><th>Word</th><th>Question Count</th></tr></thead>
<tbody>
{top_rows}
</tbody>
</table>

<h2>Supplementary Study List — Top 100 ETS Words Not in Vocab</h2>
<p style="color:#6c757d;font-size:.85rem;">
  These words appear frequently in ETS questions but are not in the Hackers vocab book.
  Study these alongside the main vocabulary.
</p>
<table>
<thead><tr><th>#</th><th>Word</th><th>Count</th><th>Sample Question IDs</th></tr></thead>
<tbody>
{supp_rows}
</tbody>
</table>

</body>
</html>
"""


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print("Loading vocab file...")
    vocab_data = load_json(VOCAB_PATH, "hackers_vocab.json")

    print("Loading word-ETS examples...")
    map_data = load_json(ETS_EXAMPLES_PATH, "word_ets_examples.json")

    if vocab_data is None and map_data is None:
        print("[ERROR] Both input files are missing. Nothing to report.")
        sys.exit(1)

    # ── build vocab structures ──
    if vocab_data is not None:
        days = vocab_by_day(vocab_data)
        vocab_set = flat_vocab_set(days)
        print(f"  Vocab: {len(vocab_set):,} unique words across {len(days)} day(s)")
    else:
        print("[WARN] No vocab data — day coverage section will be empty.")
        days = {}
        vocab_set = set()

    # ── build map structure ──
    if map_data is not None:
        # word_ets_examples.json is dict keyed by word with examples[]
        if isinstance(map_data, dict):
            wq_map = {}
            for word, entry in map_data.items():
                w = word.strip().lower()
                examples = entry.get("examples", [])
                wq_map[w] = [ex.get("source", "") for ex in examples]
            print(f"  Map  : {len(wq_map):,} words with ETS examples")
        else:
            wq_map = parse_word_question_map(map_data)
            print(f"  Map  : {len(wq_map):,} words with question links")
    else:
        print("[WARN] No word-ETS examples — coverage stats will be zero.")
        wq_map = {}

    print("\nComputing coverage...")
    day_stats, not_in_vocab, top_by_count = compute_coverage(days, vocab_set, wq_map)

    print_summary(day_stats, not_in_vocab, top_by_count)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "coverage_report.html"
    html = build_html(day_stats, not_in_vocab, top_by_count, len(vocab_set))
    out_path.write_text(html, encoding="utf-8")
    print(f"\n[OK] HTML report saved: {out_path}")


if __name__ == "__main__":
    main()
