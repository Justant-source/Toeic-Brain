"""
Part5 문제 유형별 출제 통계. 품사/어휘/문법 등 카테고리별 출제 비율 분석.
"""

import sys
import json
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "json" / "questions"
OUTPUT_DIR = ROOT / "output" / "reports"

CATEGORIES = [
    "품사", "동사시제/태", "접속사/전치사", "관계대명사",
    "어휘", "대명사", "비교급/최상급", "기타문법",
]
UNCATEGORIZED_LABEL = "(미분류)"


# ── data loading ──────────────────────────────────────────────────────────────

def load_volumes() -> dict[int, list[dict]]:
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


# ── stats computation ─────────────────────────────────────────────────────────

def compute_stats(
    volumes: dict[int, list[dict]]
) -> tuple[dict[str, int], dict[int, dict[str, int]]]:
    """Return (global_counts, per_vol_counts)."""
    global_counts: dict[str, int] = {}
    per_vol: dict[int, dict[str, int]] = {}

    for vol, questions in sorted(volumes.items()):
        vc: dict[str, int] = {}
        for q in questions:
            cat = q.get("category") or UNCATEGORIZED_LABEL
            vc[cat] = vc.get(cat, 0) + 1
            global_counts[cat] = global_counts.get(cat, 0) + 1
        per_vol[vol] = vc

    return global_counts, per_vol


def ordered_cats(counts: dict[str, int]) -> list[str]:
    """Return CATEGORIES that appear in counts, then any extras, then uncategorized."""
    seen = [c for c in CATEGORIES if c in counts]
    extras = [c for c in counts if c not in CATEGORIES and c != UNCATEGORIZED_LABEL]
    tail = [UNCATEGORIZED_LABEL] if UNCATEGORIZED_LABEL in counts else []
    return seen + extras + tail


# ── console output ────────────────────────────────────────────────────────────

def print_global(global_counts: dict[str, int]):
    total = sum(global_counts.values()) or 1
    print(f"\n{'═'*52}")
    print(f"  CATEGORY DISTRIBUTION  (all volumes, {total} questions)")
    print(f"{'═'*52}")
    print(f"  {'Category':<18} {'Count':>5}  {'%':>6}  Bar")
    print(f"  {'─'*18} {'─'*5}  {'─'*6}  {'─'*20}")
    for cat in ordered_cats(global_counts):
        n = global_counts.get(cat, 0)
        pct = n / total * 100
        bar = "█" * int(pct / 2.5)
        print(f"  {cat:<18} {n:>5}  {pct:>5.1f}%  {bar}")
    print(f"{'═'*52}")


def print_per_vol(per_vol: dict[int, dict[str, int]], all_cats: list[str]):
    print(f"\n{'─'*52}")
    print("  PER-VOLUME BREAKDOWN")
    print(f"{'─'*52}")

    # header
    header = f"  {'Category':<18}"
    for vol in sorted(per_vol.keys()):
        header += f"  V{vol:>2}"
    print(header)
    print(f"  {'─'*18}" + "  ────" * len(per_vol))

    for cat in all_cats:
        row = f"  {cat:<18}"
        for vol in sorted(per_vol.keys()):
            n = per_vol[vol].get(cat, 0)
            row += f"  {n:>4}"
        print(row)

    # totals row
    row = f"  {'TOTAL':<18}"
    for vol in sorted(per_vol.keys()):
        row += f"  {sum(per_vol[vol].values()):>4}"
    print(f"  {'─'*18}" + "  ────" * len(per_vol))
    print(row)


# ── HTML output ───────────────────────────────────────────────────────────────

PALETTE = [
    "#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f",
    "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac",
]


def build_html(
    global_counts: dict[str, int],
    per_vol: dict[int, dict[str, int]],
) -> str:
    total = sum(global_counts.values()) or 1
    cats = ordered_cats(global_counts)
    vol_list = sorted(per_vol.keys())

    # ── global summary rows ──
    global_rows = ""
    for i, cat in enumerate(cats):
        n = global_counts.get(cat, 0)
        pct = n / total * 100
        color = PALETTE[i % len(PALETTE)]
        bar_w = int(pct * 3.5)
        global_rows += (
            f"<tr>"
            f"<td><span class='dot' style='background:{color}'></span>{cat}</td>"
            f"<td class='num'>{n}</td>"
            f"<td class='pct'>{pct:.1f}%</td>"
            f"<td class='bar'><div style='width:{bar_w}px;background:{color}'></div></td>"
            f"</tr>\n"
        )

    # ── per-vol table header ──
    vol_th = "".join(f"<th>Vol {v}</th>" for v in vol_list)

    # ── per-vol table rows ──
    per_vol_rows = ""
    for i, cat in enumerate(cats):
        color = PALETTE[i % len(PALETTE)]
        cells = "".join(
            f"<td class='num'>{per_vol[v].get(cat, 0)}</td>" for v in vol_list
        )
        per_vol_rows += (
            f"<tr>"
            f"<td><span class='dot' style='background:{color}'></span>{cat}</td>"
            f"{cells}"
            f"</tr>\n"
        )

    # totals row
    total_cells = "".join(
        f"<td class='num'><strong>{sum(per_vol[v].values())}</strong></td>"
        for v in vol_list
    )
    per_vol_rows += f"<tr class='total'><td><strong>TOTAL</strong></td>{total_cells}</tr>\n"

    # ── per-vol percentage table rows ──
    pct_rows = ""
    for i, cat in enumerate(cats):
        color = PALETTE[i % len(PALETTE)]
        cells = ""
        for v in vol_list:
            vt = sum(per_vol[v].values()) or 1
            p = per_vol[v].get(cat, 0) / vt * 100
            cells += f"<td class='num'>{p:.1f}%</td>"
        pct_rows += (
            f"<tr>"
            f"<td><span class='dot' style='background:{color}'></span>{cat}</td>"
            f"{cells}"
            f"</tr>\n"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Category Stats — TOEIC Brain</title>
<style>
  body {{ font-family:'Segoe UI',Arial,sans-serif; background:#f8f9fa; color:#212529; margin:0; padding:24px; }}
  h1   {{ color:#0d6efd; border-bottom:2px solid #0d6efd; padding-bottom:8px; }}
  h2   {{ color:#495057; margin-top:36px; }}
  table {{ border-collapse:collapse; width:100%; max-width:860px; background:#fff;
           box-shadow:0 1px 4px rgba(0,0,0,.12); border-radius:6px; overflow:hidden; margin-bottom:32px; }}
  th   {{ background:#0d6efd; color:#fff; padding:10px 14px; text-align:left; font-size:.88rem; }}
  td   {{ padding:7px 14px; border-bottom:1px solid #dee2e6; font-size:.875rem; }}
  tr:last-child td {{ border-bottom:none; }}
  tr:hover td {{ background:#e9f2ff; }}
  tr.total td  {{ background:#f1f3f5; font-weight:600; border-top:2px solid #adb5bd; }}
  .dot {{ display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:7px; vertical-align:middle; }}
  .num {{ text-align:right; }}
  .pct {{ text-align:right; color:#6c757d; }}
  .bar div {{ height:14px; border-radius:3px; min-width:2px; }}
  .summary {{ background:#fff; border-left:4px solid #0d6efd; padding:12px 18px;
              margin-bottom:28px; border-radius:0 6px 6px 0; max-width:560px;
              box-shadow:0 1px 3px rgba(0,0,0,.08); }}
</style>
</head>
<body>
<h1>Category Stats — TOEIC Brain ETS Part 5</h1>
<div class="summary">
  <strong>Total questions:</strong> {total:,}<br>
  <strong>Volumes analysed:</strong> {', '.join(f'Vol {v}' for v in vol_list)}<br>
  <strong>Categories detected:</strong> {len(cats)}
</div>

<h2>Overall Category Distribution</h2>
<table>
<thead><tr><th>Category</th><th>Count</th><th>%</th><th>Bar</th></tr></thead>
<tbody>
{global_rows}
</tbody>
</table>

<h2>Per-Volume Count</h2>
<table>
<thead><tr><th>Category</th>{vol_th}</tr></thead>
<tbody>
{per_vol_rows}
</tbody>
</table>

<h2>Per-Volume Percentage</h2>
<table>
<thead><tr><th>Category</th>{vol_th}</tr></thead>
<tbody>
{pct_rows}
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
    volumes = load_volumes()
    if not volumes:
        print("[ERROR] No Part5 files found.")
        sys.exit(1)

    print(f"Loaded {sum(len(v) for v in volumes.values())} questions "
          f"across {len(volumes)} volume(s).\n")

    global_counts, per_vol = compute_stats(volumes)
    all_cats = ordered_cats(global_counts)

    uncategorized = global_counts.get(UNCATEGORIZED_LABEL, 0)
    total = sum(global_counts.values())
    if uncategorized > 0:
        print(f"[NOTE] {uncategorized}/{total} questions have no category yet. "
              f"Run scripts/process/categorize.py first.")

    print_global(global_counts)
    print_per_vol(per_vol, all_cats)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "category_stats.html"
    html = build_html(global_counts, per_vol)
    out_path.write_text(html, encoding="utf-8")
    print(f"\n[OK] HTML report saved: {out_path}")


if __name__ == "__main__":
    main()
