"""Obsidian Vault 검증 및 통계 리포트 생성."""

import sys
import json
import re
import argparse
import logging
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime

# Windows UTF-8
sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_VAULT_DIR = PROJECT_ROOT / "vault"
DEFAULT_CHAPTER_MAP = PROJECT_ROOT / "data" / "processed" / "vocab" / "chapter_map.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "output" / "reports" / "vault_stats.html"

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

REQUIRED_FRONTMATTER = [
    "word", "pos", "meaning", "chapter", "chapter_title", "level", "ets_count", "tags",
]


# ── data classes ─────────────────────────────────────────────────────────────


@dataclass
class FileInfo:
    path: Path
    word: str
    chapter: int
    frontmatter: dict
    ets_count_declared: int
    ets_count_actual: int
    issues: list[str] = field(default_factory=list)


# ── parsing helpers ──────────────────────────────────────────────────────────


def parse_frontmatter(md_text: str) -> dict:
    """Parse YAML frontmatter between --- markers. Returns dict of key-value pairs."""
    m = re.match(r"^---\s*\n(.*?)\n---", md_text, re.DOTALL)
    if not m:
        return {}
    fm: dict = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # handle key: value (simple YAML, no nested)
        colon_idx = line.find(":")
        if colon_idx == -1:
            continue
        key = line[:colon_idx].strip()
        val = line[colon_idx + 1:].strip()
        # strip surrounding quotes
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
            val = val[1:-1]
        # try to parse lists like [tag1, tag2]
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1]
            items = [x.strip().strip('"').strip("'") for x in inner.split(",") if x.strip()]
            fm[key] = items
        else:
            # try int
            try:
                fm[key] = int(val)
            except ValueError:
                fm[key] = val
    return fm


def count_ets_examples(md_text: str) -> int:
    """Count ETS example blockquote patterns in the MD file.

    Matches lines starting with '>' which represent ETS example sentences.
    Groups consecutive blockquote lines as a single example.
    """
    count = 0
    in_block = False
    for line in md_text.splitlines():
        stripped = line.strip()
        if stripped.startswith(">"):
            if not in_block:
                count += 1
                in_block = True
        else:
            if stripped == "":
                in_block = False
            else:
                in_block = False
    return count


# ── scanning ─────────────────────────────────────────────────────────────────


def scan_vault(vault_dir: Path) -> list[FileInfo]:
    """Scan all .md files in the vault directory and parse their contents."""
    files: list[FileInfo] = []
    if not vault_dir.exists():
        log.error("Vault directory does not exist: %s", vault_dir)
        return files

    for md_path in sorted(vault_dir.rglob("*.md")):
        issues: list[str] = []
        try:
            text = md_path.read_text(encoding="utf-8")
        except OSError as e:
            issues.append(f"Cannot read file: {e}")
            files.append(FileInfo(
                path=md_path, word=md_path.stem, chapter=0,
                frontmatter={}, ets_count_declared=0, ets_count_actual=0,
                issues=issues,
            ))
            continue

        fm = parse_frontmatter(text)

        # Check required frontmatter fields
        for req in REQUIRED_FRONTMATTER:
            if req not in fm:
                issues.append(f"Missing frontmatter field: {req}")

        word = str(fm.get("word", md_path.stem))
        chapter = fm.get("chapter", 0)
        if not isinstance(chapter, int):
            try:
                chapter = int(chapter)
            except (ValueError, TypeError):
                issues.append(f"Invalid chapter value: {chapter}")
                chapter = 0

        ets_declared = fm.get("ets_count", 0)
        if not isinstance(ets_declared, int):
            try:
                ets_declared = int(ets_declared)
            except (ValueError, TypeError):
                issues.append(f"Invalid ets_count value: {ets_declared}")
                ets_declared = 0

        ets_actual = count_ets_examples(text)

        if ets_declared != ets_actual:
            issues.append(
                f"ets_count mismatch: frontmatter says {ets_declared}, "
                f"but found {ets_actual} blockquote(s)"
            )

        files.append(FileInfo(
            path=md_path,
            word=word,
            chapter=chapter,
            frontmatter=fm,
            ets_count_declared=ets_declared,
            ets_count_actual=ets_actual,
            issues=issues,
        ))

    return files


# ── chapter map ──────────────────────────────────────────────────────────────


def load_chapter_map(path: Path) -> list[dict]:
    """Load chapter_map.json. Returns list of chapter entries."""
    if not path.exists():
        log.warning("chapter_map.json not found: %s", path)
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        log.error("Cannot read chapter_map.json: %s", e)
        return []

    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # support dict keyed by chapter number
        result = []
        for key, val in data.items():
            if isinstance(val, dict):
                entry = {**val}
                if "chapter" not in entry:
                    entry["chapter"] = key
                result.append(entry)
            elif isinstance(val, list):
                result.append({"chapter": key, "words": val})
        return result
    return []


# ── validation ───────────────────────────────────────────────────────────────


def validate_files(files: list[FileInfo], chapter_map: list[dict]) -> list[str]:
    """Cross-reference vault files against chapter_map. Returns list of issues."""
    issues: list[str] = []

    # Build expected word set from chapter_map
    expected_words: set[str] = set()
    for entry in chapter_map:
        words = entry.get("words", [])
        if isinstance(words, list):
            for w in words:
                if isinstance(w, str):
                    expected_words.add(w.lower())
                elif isinstance(w, dict):
                    expected_words.add(str(w.get("word", "")).lower())

    # Build actual word set from vault files
    actual_words: set[str] = {f.word.lower() for f in files}

    missing = expected_words - actual_words
    extra = actual_words - expected_words

    for w in sorted(missing):
        issues.append(f"Missing file: word '{w}' in chapter_map but no MD file")
    for w in sorted(extra):
        issues.append(f"Extra file: word '{w}' has MD file but not in chapter_map")

    return issues


# ── statistics ───────────────────────────────────────────────────────────────


def compute_stats(files: list[FileInfo], chapter_map: list[dict]) -> dict:
    """Compute all statistics for the HTML report."""
    # Expected words from chapter_map
    expected_words: set[str] = set()
    chapter_info: dict[int, dict] = {}  # chapter_num -> {title, words}
    for entry in chapter_map:
        ch = entry.get("chapter", 0)
        if not isinstance(ch, int):
            try:
                ch = int(ch)
            except (ValueError, TypeError):
                ch = 0
        title = entry.get("title", entry.get("chapter_title", f"Chapter {ch}"))
        words = entry.get("words", [])
        word_list: list[str] = []
        if isinstance(words, list):
            for w in words:
                if isinstance(w, str):
                    word_list.append(w.lower())
                elif isinstance(w, dict):
                    word_list.append(str(w.get("word", "")).lower())
        expected_words.update(word_list)
        chapter_info[ch] = {"title": title, "words": word_list}

    actual_words = {f.word.lower() for f in files}
    files_by_word = {f.word.lower(): f for f in files}

    missing = sorted(expected_words - actual_words)
    extra = sorted(actual_words - expected_words)

    with_examples = [f for f in files if f.ets_count_actual > 0]
    without_examples = [f for f in files if f.ets_count_actual == 0]

    # Per-chapter breakdown
    chapter_stats: list[dict] = []
    for ch_num in sorted(chapter_info.keys()):
        info = chapter_info[ch_num]
        ch_words = info["words"]
        ch_files = [files_by_word[w] for w in ch_words if w in files_by_word]
        ch_with_ex = [f for f in ch_files if f.ets_count_actual > 0]
        coverage_pct = len(ch_with_ex) / len(ch_words) * 100 if ch_words else 0.0
        chapter_stats.append({
            "chapter": ch_num,
            "title": info["title"],
            "word_count": len(ch_words),
            "files_found": len(ch_files),
            "with_examples": len(ch_with_ex),
            "coverage_pct": coverage_pct,
        })

    # Top 10 words by ets_count
    top_ets = sorted(files, key=lambda f: f.ets_count_actual, reverse=True)[:10]

    # Per-volume example distribution
    vol_dist: dict[str, int] = {}
    for f in files:
        tags = f.frontmatter.get("tags", [])
        if isinstance(tags, list):
            for tag in tags:
                tag_str = str(tag)
                if tag_str.startswith("ets/vol") or tag_str.startswith("ets::vol"):
                    vol_dist[tag_str] = vol_dist.get(tag_str, 0) + 1

    # If no volume tags found from tags, try to count from file content
    if not vol_dist:
        vol_pattern = re.compile(r"vol(\d+)", re.IGNORECASE)
        for f in files:
            try:
                text = f.path.read_text(encoding="utf-8")
            except OSError:
                continue
            for m in vol_pattern.finditer(text):
                key = f"vol{m.group(1)}"
                vol_dist[key] = vol_dist.get(key, 0) + 1

    # Files with issues
    files_with_issues = [f for f in files if f.issues]

    return {
        "total_files": len(files),
        "total_expected": len(expected_words),
        "missing": missing,
        "extra": extra,
        "with_examples": len(with_examples),
        "without_examples": len(without_examples),
        "chapter_stats": chapter_stats,
        "top_ets": top_ets,
        "vol_dist": vol_dist,
        "files_with_issues": files_with_issues,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ── HTML report ──────────────────────────────────────────────────────────────


def build_html_report(stats: dict) -> str:
    """Build self-contained HTML report string."""

    # KPI values
    total_files = stats["total_files"]
    total_expected = stats["total_expected"]
    with_ex = stats["with_examples"]
    without_ex = stats["without_examples"]
    missing_count = len(stats["missing"])
    extra_count = len(stats["extra"])
    issue_count = len(stats["files_with_issues"])

    # ── chapter rows ──
    chapter_rows = ""
    for ch in stats["chapter_stats"]:
        pct = ch["coverage_pct"]
        bar_w = int(pct * 1.8)
        color = "#28a745" if pct >= 50 else ("#ffc107" if pct >= 25 else "#dc3545")
        chapter_rows += (
            f"<tr>"
            f"<td class='num'>{ch['chapter']}</td>"
            f"<td>{ch['title']}</td>"
            f"<td class='num'>{ch['word_count']}</td>"
            f"<td class='num'>{ch['files_found']}</td>"
            f"<td class='num'>{ch['with_examples']}</td>"
            f"<td class='pct'>{pct:.1f}%</td>"
            f"<td class='bar'><div style='width:{bar_w}px;background:{color}'></div></td>"
            f"</tr>\n"
        )

    # ── top 10 ets rows ──
    top_rows = ""
    for i, f in enumerate(stats["top_ets"], 1):
        top_rows += (
            f"<tr>"
            f"<td class='num'>{i}</td>"
            f"<td class='word'>{f.word}</td>"
            f"<td class='num'>{f.chapter}</td>"
            f"<td class='num'>{f.ets_count_actual}</td>"
            f"</tr>\n"
        )

    # ── volume distribution rows ──
    vol_rows = ""
    for vol_key in sorted(stats["vol_dist"].keys()):
        vol_rows += (
            f"<tr>"
            f"<td class='word'>{vol_key}</td>"
            f"<td class='num'>{stats['vol_dist'][vol_key]}</td>"
            f"</tr>\n"
        )
    if not vol_rows:
        vol_rows = "<tr><td colspan='2' style='color:#6c757d;'>No volume data found</td></tr>\n"

    # ── missing files rows ──
    missing_rows = ""
    for i, w in enumerate(stats["missing"][:50], 1):
        missing_rows += f"<tr><td class='num'>{i}</td><td class='word'>{w}</td></tr>\n"
    if not missing_rows:
        missing_rows = "<tr><td colspan='2' style='color:#28a745;'>None - all words have files</td></tr>\n"

    # ── extra files rows ──
    extra_rows = ""
    for i, w in enumerate(stats["extra"][:50], 1):
        extra_rows += f"<tr><td class='num'>{i}</td><td class='word'>{w}</td></tr>\n"
    if not extra_rows:
        extra_rows = "<tr><td colspan='2' style='color:#28a745;'>None - no extra files</td></tr>\n"

    # ── issue rows ──
    issue_rows = ""
    for f in stats["files_with_issues"][:100]:
        issues_html = "<br>".join(f.issues)
        issue_rows += (
            f"<tr>"
            f"<td class='word'>{f.word}</td>"
            f"<td class='num'>{f.chapter}</td>"
            f"<td class='sample'>{issues_html}</td>"
            f"</tr>\n"
        )
    if not issue_rows:
        issue_rows = "<tr><td colspan='3' style='color:#28a745;'>No issues found</td></tr>\n"

    generated_at = stats["generated_at"]

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Vault Validation Report — TOEIC Brain</title>
<style>
  body  {{ font-family:'Segoe UI',Arial,sans-serif; background:#f8f9fa; color:#212529; margin:0; padding:24px; }}
  h1    {{ color:#0d6efd; border-bottom:2px solid #0d6efd; padding-bottom:8px; }}
  h2    {{ color:#495057; margin-top:36px; }}
  .ts   {{ color:#6c757d; font-size:.8rem; margin-top:-8px; margin-bottom:24px; }}
  table {{ border-collapse:collapse; width:100%; max-width:960px; background:#fff;
           box-shadow:0 1px 4px rgba(0,0,0,.12); border-radius:6px; overflow:hidden; margin-bottom:32px; }}
  th    {{ background:#0d6efd; color:#fff; padding:10px 14px; text-align:left; font-size:.88rem; }}
  td    {{ padding:7px 14px; border-bottom:1px solid #dee2e6; font-size:.85rem; vertical-align:middle; }}
  tr:last-child td {{ border-bottom:none; }}
  tr:hover td {{ background:#e9f2ff; }}
  .word {{ font-weight:600; }}
  .num  {{ text-align:right; }}
  .pct  {{ text-align:right; font-weight:600; }}
  .bar div {{ height:14px; border-radius:3px; min-width:2px; }}
  .sample {{ font-size:.78rem; color:#495057; }}
  .kpi  {{ display:inline-block; background:#fff; border-radius:8px; padding:16px 24px;
           margin:0 12px 16px 0; box-shadow:0 1px 4px rgba(0,0,0,.12); min-width:140px; text-align:center; }}
  .kpi .val {{ font-size:2rem; font-weight:700; color:#0d6efd; }}
  .kpi .lbl {{ font-size:.8rem; color:#6c757d; margin-top:4px; }}
  .kpi.warn .val {{ color:#ffc107; }}
  .kpi.err  .val {{ color:#dc3545; }}
  .kpi.ok   .val {{ color:#28a745; }}
</style>
</head>
<body>
<h1>Vault Validation Report — TOEIC Brain</h1>
<p class="ts">Generated: {generated_at}</p>

<div>
  <div class="kpi"><div class="val">{total_files:,}</div><div class="lbl">Total MD Files</div></div>
  <div class="kpi"><div class="val">{total_expected:,}</div><div class="lbl">Expected Words</div></div>
  <div class="kpi{'  err' if missing_count > 0 else '  ok'}"><div class="val">{missing_count:,}</div><div class="lbl">Missing Files</div></div>
  <div class="kpi{'  warn' if extra_count > 0 else '  ok'}"><div class="val">{extra_count:,}</div><div class="lbl">Extra Files</div></div>
  <div class="kpi ok"><div class="val">{with_ex:,}</div><div class="lbl">With ETS Examples</div></div>
  <div class="kpi"><div class="val">{without_ex:,}</div><div class="lbl">Without ETS Examples</div></div>
  <div class="kpi{'  err' if issue_count > 0 else '  ok'}"><div class="val">{issue_count:,}</div><div class="lbl">Files with Issues</div></div>
</div>

<h2>Per-Chapter Breakdown</h2>
<table>
<thead><tr>
  <th>Ch#</th><th>Title</th><th>Words</th><th>Files</th><th>With ETS</th><th>Coverage</th><th>Bar</th>
</tr></thead>
<tbody>
{chapter_rows}
</tbody>
</table>

<h2>Top 10 Words by ETS Example Count</h2>
<table>
<thead><tr><th>#</th><th>Word</th><th>Chapter</th><th>ETS Examples</th></tr></thead>
<tbody>
{top_rows}
</tbody>
</table>

<h2>Per-Volume Example Distribution</h2>
<table>
<thead><tr><th>Volume</th><th>Example Count</th></tr></thead>
<tbody>
{vol_rows}
</tbody>
</table>

<h2>Missing Files (in chapter_map, no MD file)</h2>
<p style="color:#6c757d;font-size:.85rem;">
  Showing up to 50 entries. Total missing: {missing_count}
</p>
<table>
<thead><tr><th>#</th><th>Word</th></tr></thead>
<tbody>
{missing_rows}
</tbody>
</table>

<h2>Extra Files (MD file, not in chapter_map)</h2>
<p style="color:#6c757d;font-size:.85rem;">
  Showing up to 50 entries. Total extra: {extra_count}
</p>
<table>
<thead><tr><th>#</th><th>Word</th></tr></thead>
<tbody>
{extra_rows}
</tbody>
</table>

<h2>Files with Validation Issues</h2>
<p style="color:#6c757d;font-size:.85rem;">
  Showing up to 100 entries. Total with issues: {issue_count}
</p>
<table>
<thead><tr><th>Word</th><th>Chapter</th><th>Issues</th></tr></thead>
<tbody>
{issue_rows}
</tbody>
</table>

</body>
</html>
"""


# ── main ─────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Obsidian Vault 검증 및 통계 리포트 생성")
    parser.add_argument(
        "--vault", type=Path, default=DEFAULT_VAULT_DIR,
        help=f"Vault directory (default: {DEFAULT_VAULT_DIR})",
    )
    parser.add_argument(
        "--chapter-map", type=Path, default=DEFAULT_CHAPTER_MAP,
        help=f"chapter_map.json path (default: {DEFAULT_CHAPTER_MAP})",
    )
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT,
        help=f"Output HTML path (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()

    log.info("Scanning vault: %s", args.vault)
    files = scan_vault(args.vault)
    log.info("Found %d MD files", len(files))

    log.info("Loading chapter map: %s", args.chapter_map)
    chapter_map = load_chapter_map(args.chapter_map)
    log.info("Chapter map entries: %d", len(chapter_map))

    log.info("Validating files against chapter map...")
    cross_issues = validate_files(files, chapter_map)
    for issue in cross_issues:
        log.warning(issue)

    log.info("Computing statistics...")
    stats = compute_stats(files, chapter_map)

    # Console summary
    print(f"\n{'='*58}")
    print(f"  VAULT VALIDATION SUMMARY")
    print(f"{'='*58}")
    print(f"  Total MD files     : {stats['total_files']:,}")
    print(f"  Expected words     : {stats['total_expected']:,}")
    print(f"  Missing files      : {len(stats['missing']):,}")
    print(f"  Extra files        : {len(stats['extra']):,}")
    print(f"  With ETS examples  : {stats['with_examples']:,}")
    print(f"  Without ETS examp. : {stats['without_examples']:,}")
    print(f"  Files with issues  : {len(stats['files_with_issues']):,}")
    print(f"{'='*58}")

    if stats["chapter_stats"]:
        print(f"\n{'─'*58}")
        print(f"  PER-CHAPTER BREAKDOWN")
        print(f"{'─'*58}")
        print(f"  {'Ch#':<5} {'Title':<25} {'Words':>6} {'ETS':>5} {'%':>7}")
        print(f"  {'─'*5} {'─'*25} {'─'*6} {'─'*5} {'─'*7}")
        for ch in stats["chapter_stats"]:
            print(
                f"  {ch['chapter']:<5} {ch['title'][:25]:<25} "
                f"{ch['word_count']:>6} {ch['with_examples']:>5} "
                f"{ch['coverage_pct']:>6.1f}%"
            )

    if stats["top_ets"]:
        print(f"\n{'─'*58}")
        print(f"  TOP 10 WORDS BY ETS EXAMPLE COUNT")
        print(f"{'─'*58}")
        for i, f in enumerate(stats["top_ets"], 1):
            print(f"  {i:>2}. {f.word:<22} {f.ets_count_actual:>4} examples")

    # Write HTML
    args.output.parent.mkdir(parents=True, exist_ok=True)
    html = build_html_report(stats)
    args.output.write_text(html, encoding="utf-8")
    log.info("HTML report saved: %s", args.output)


if __name__ == "__main__":
    main()
