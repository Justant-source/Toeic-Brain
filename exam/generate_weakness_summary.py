"""
Part5 취약점 핵심요약집 생성기.

결과 JSON을 읽어 취약 카테고리별 vault 핵심 내용을 추출하고
자기완결형 HTML 요약집을 생성한다.

Usage:
    python exam/generate_weakness_summary.py exam/result/result_20260401_1030.json
    python exam/generate_weakness_summary.py result.json --threshold 60
    python exam/generate_weakness_summary.py result.json --output exam/result/
"""

import sys
import json
import re
import argparse
import html as html_lib
from pathlib import Path
from datetime import datetime

import yaml

# ── 경로 상수 ──────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VAULT_ROOT = PROJECT_ROOT / "vault"
RESULT_DIR = Path(__file__).resolve().parent / "result"

# ── 카테고리 → Vault 디렉토리 매핑 ────────────────────────────────────────────

CATEGORY_VAULT_MAP: dict[str, list[str]] = {
    "품사": [
        "Grammar/S4_품사/CH10_명사",
        "Grammar/S4_품사/CH12_형용사",
        "Grammar/S4_품사/CH13_부사",
    ],
    "동사": [
        "Grammar/S2_동사구/CH03_동사의형태와종류",
        "Grammar/S2_동사구/CH05_능동태수동태",
        "Grammar/S2_동사구/CH06_시제와가정법",
        "Grammar/S3_준동사구/CH07_to부정사",
        "Grammar/S3_준동사구/CH08_동명사",
        "Grammar/S3_준동사구/CH09_분사",
    ],
    "접속사/전치사": [
        "Grammar/S4_품사/CH14_전치사",
        "Grammar/S5_접속사와절/CH15_등위접속사_상관접속사",
        "Grammar/S5_접속사와절/CH17_부사절",
        "Grammar/S5_접속사와절/CH18_명사절",
    ],
    "관계대명사": [
        "Grammar/S5_접속사와절/CH16_관계절",
    ],
    "어휘": [
        "Vocabulary/S1_어휘/CH01_동사",
        "Vocabulary/S1_어휘/CH02_명사",
        "Vocabulary/S1_어휘/CH03_형용사",
        "Vocabulary/S1_어휘/CH04_부사",
        "Vocabulary/S2_어구/CH05_형용사관련어구",
        "Vocabulary/S2_어구/CH06_동사관련어구1",
        "Vocabulary/S2_어구/CH07_동사관련어구2",
        "Vocabulary/S2_어구/CH08_명사관련어구",
        "Vocabulary/S2_어구/CH09_짝을이루는표현",
        "Vocabulary/S3_유사의미어/CH10_유사의미동사",
        "Vocabulary/S3_유사의미어/CH11_유사의미명사",
        "Vocabulary/S3_유사의미어/CH12_유사의미형용사부사",
    ],
    "대명사": [
        "Grammar/S4_품사/CH11_대명사",
    ],
    "비교급/최상급": [
        "Grammar/S6_특수구문/CH19_비교구문",
    ],
    "기타문법": [
        "Grammar/S1_문장패턴/CH01_주어동사",
        "Grammar/S1_문장패턴/CH02_목적어보어수식어",
        "Grammar/S2_동사구/CH04_주어와의수일치",
        "Grammar/S6_특수구문/CH20_병치도치구문",
    ],
}

# 포함할 ## 섹션 헤딩 (집합)
INCLUDE_SECTIONS = {
    "핵심 개념",
    "핵심 공식/패턴",
    "출제 포인트",
    "출제 유형 및 전략",
    "단어/어구 목록",
    "단어 목록",
}

# ── Vault 파싱 ─────────────────────────────────────────────────────────────────

def parse_vault_file(path: Path) -> dict | None:
    """vault 마크다운 파일을 frontmatter + 필터된 섹션으로 파싱한다."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    # frontmatter 분리
    fm_match = re.match(r"^---\n(.*?\n)---\n", text, re.DOTALL)
    if fm_match:
        try:
            frontmatter = yaml.safe_load(fm_match.group(1)) or {}
        except yaml.YAMLError:
            frontmatter = {}
        body = text[fm_match.end():]
    else:
        frontmatter = {}
        body = text

    # ## 헤딩으로 섹션 분리 (### 이하는 섹션 내부 콘텐츠로 포함됨)
    parts = re.split(r"^## (.+)$", body, flags=re.MULTILINE)
    # parts = [preamble, heading1, content1, heading2, content2, ...]
    sections = []
    it = iter(parts[1:])
    for heading in it:
        content = next(it, "")
        heading = heading.strip()
        if heading in INCLUDE_SECTIONS:
            stripped = content.strip()
            if stripped:
                sections.append({"heading": heading, "body": stripped})

    return {
        "id": frontmatter.get("id", path.stem),
        "title": frontmatter.get("title", path.stem),
        "chapter": frontmatter.get("chapter", ""),
        "page": frontmatter.get("page", ""),
        "sections": sections,
    }


# ── Markdown → HTML 변환 ───────────────────────────────────────────────────────

def _inline(text: str) -> str:
    """인라인 마크다운(볼드, 이탤릭, 코드, 링크)을 HTML로 변환한다."""
    text = html_lib.escape(text)
    # Bold
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    # Italic
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    # Inline code
    text = re.sub(r"`(.+?)`", r"<code class='ic'>\1</code>", text)
    # Obsidian 내부 링크 [[...]] → 텍스트만
    text = re.sub(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", r"<span class='vref'>\1</span>", text)
    return text


def md_to_html(text: str) -> str:
    """vault 마크다운 서브셋을 HTML로 변환한다."""
    lines = text.split("\n")
    out: list[str] = []
    in_code = False
    in_table = False
    in_ul = False
    in_ol = False

    def close_list():
        nonlocal in_ul, in_ol
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False

    def close_table():
        nonlocal in_table
        if in_table:
            out.append("</tbody></table>")
            in_table = False

    for line in lines:
        # 코드 블록
        if line.strip().startswith("```"):
            if not in_code:
                close_list()
                close_table()
                lang = line.strip()[3:].strip()
                out.append(f'<pre class="vcode"><code class="lang-{lang}">')
                in_code = True
            else:
                out.append("</code></pre>")
                in_code = False
            continue

        if in_code:
            out.append(html_lib.escape(line))
            continue

        # Obsidian callout 블록 (> [!...]) 건너뜀
        if re.match(r"^>\s*\[!", line):
            continue
        if line.startswith("> "):
            close_list()
            close_table()
            out.append(f'<blockquote>{_inline(line[2:])}</blockquote>')
            continue

        # 테이블
        if "|" in line and line.strip().startswith("|"):
            close_list()
            if not in_table:
                out.append('<table class="vtable"><tbody>')
                in_table = True
            # 구분선 행 건너뜀 (|---|---|)
            if re.match(r"^\|[\s\-|:]+\|$", line.strip()):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            out.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in cells) + "</tr>")
            continue
        else:
            close_table()

        # 헤딩 (### 이하만 — ## 는 섹션 분리 시 제거됨)
        if m := re.match(r"^(#{3,5})\s+(.+)$", line):
            close_list()
            level = min(len(m.group(1)) + 1, 6)
            out.append(f"<h{level} class='vsub'>{_inline(m.group(2))}</h{level}>")
            continue

        # 번호 없는 목록
        if re.match(r"^\s*[-*]\s+", line):
            close_table()
            if not in_ul:
                if in_ol:
                    out.append("</ol>")
                    in_ol = False
                out.append("<ul class='vlist'>")
                in_ul = True
            content = re.sub(r"^\s*[-*]\s+", "", line)
            out.append(f"<li>{_inline(content)}</li>")
            continue

        # 번호 있는 목록
        if re.match(r"^\s*\d+\.\s+", line):
            close_table()
            if not in_ol:
                if in_ul:
                    out.append("</ul>")
                    in_ul = False
                out.append("<ol class='vlist'>")
                in_ol = True
            content = re.sub(r"^\s*\d+\.\s+", "", line)
            out.append(f"<li>{_inline(content)}</li>")
            continue

        # 빈 줄
        if not line.strip():
            close_list()
            continue

        # 일반 단락
        close_list()
        out.append(f"<p>{_inline(line)}</p>")

    close_list()
    close_table()
    if in_code:
        out.append("</code></pre>")

    return "\n".join(out)


# ── 데이터 로딩 ────────────────────────────────────────────────────────────────

def load_result(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def find_weak_categories(result: dict, threshold: float) -> list[tuple[str, dict]]:
    """정답률 < threshold인 카테고리를 정답률 오름차순으로 반환한다."""
    weak = []
    for cat, stats in result.get("category_stats", {}).items():
        if stats.get("rate", 100) < threshold:
            weak.append((cat, stats))
    weak.sort(key=lambda x: x[1].get("rate", 0))
    return weak


def load_vault_content(category: str) -> list[dict]:
    """카테고리에 해당하는 vault 마크다운 파일들을 파싱해 반환한다."""
    dirs = CATEGORY_VAULT_MAP.get(category, [])
    parsed = []
    for rel_dir in dirs:
        dir_path = VAULT_ROOT / rel_dir
        if not dir_path.exists():
            continue
        for md_file in sorted(dir_path.glob("*.md")):
            doc = parse_vault_file(md_file)
            if doc and doc["sections"]:
                parsed.append(doc)
    return parsed


def get_wrong_questions(result: dict, category: str) -> list[dict]:
    """특정 카테고리의 오답 문제들을 반환한다."""
    return [
        q for q in result.get("questions", [])
        if q.get("category") == category and not q.get("is_correct", True)
    ]


# ── HTML 빌더 헬퍼 ─────────────────────────────────────────────────────────────

def _rate_color(rate: float) -> str:
    if rate >= 80:
        return "#43a047"
    if rate >= 50:
        return "#fb8c00"
    return "#e53935"


def _build_overview(weak_cats: list[tuple[str, dict]]) -> str:
    if not weak_cats:
        return ""
    rows = []
    for cat, stats in weak_cats:
        rate = stats.get("rate", 0)
        color = _rate_color(rate)
        c, t = stats.get("correct", 0), stats.get("total", 1)
        rows.append(f"""
      <div class="ov-row">
        <div class="ov-name">{html_lib.escape(cat)}</div>
        <div class="ov-bar-wrap">
          <div class="ov-bar" style="width:{rate}%;background:{color}"></div>
        </div>
        <div class="ov-pct" style="color:{color}">{c}/{t} ({rate}%)</div>
      </div>""")
    return f"""
    <section class="overview-section">
      <h2 class="sec-title">취약 카테고리 개요</h2>
      <div class="ov-grid">{''.join(rows)}
      </div>
    </section>"""


def _build_vault_card(doc: dict) -> str:
    page_info = f" <span class='vpage'>p.{doc['page']}</span>" if doc.get("page") else ""
    sections_html = ""
    for sec in doc["sections"]:
        body_html = md_to_html(sec["body"])
        sections_html += f"""
        <div class="vsec">
          <div class="vsec-title">{html_lib.escape(sec['heading'])}</div>
          <div class="vsec-body">{body_html}</div>
        </div>"""
    return f"""
      <div class="vcard">
        <div class="vcard-header">
          <span class="vid">{html_lib.escape(doc['id'])}</span>
          <span class="vtitle">{html_lib.escape(doc['title'])}</span>{page_info}
        </div>{sections_html}
      </div>"""


def _highlight_blank(sentence: str) -> str:
    """------- 빈칸을 강조 표시로 변환한다."""
    escaped = html_lib.escape(sentence)
    return re.sub(r"-{5,}", '<span class="blank">▢</span>', escaped)


def _build_wrong_list(wrong_qs: list[dict]) -> str:
    if not wrong_qs:
        return ""
    items = []
    for q in wrong_qs:
        choices = q.get("choices", {})
        correct_key = q.get("correct_answer", "")
        user_key = q.get("user_answer", "")
        correct_text = choices.get(correct_key, "")
        user_text = choices.get(user_key, "")
        sentence_html = _highlight_blank(q.get("sentence", ""))
        vol = q.get("volume", "")
        test = q.get("test", "")
        qnum = q.get("question_number", "")
        items.append(f"""
        <div class="wq-card">
          <div class="wq-meta">Q{q.get('index', 0)+1} &nbsp;|&nbsp; Vol.{vol} TEST{test} #{qnum}</div>
          <div class="wq-sentence">{sentence_html}</div>
          <div class="wq-choices">
            <span class="wq-correct">✓ 정답: ({html_lib.escape(str(correct_key))}) {html_lib.escape(str(correct_text))}</span>
            <span class="wq-wrong">✗ 내 답: ({html_lib.escape(str(user_key))}) {html_lib.escape(str(user_text))}</span>
          </div>
        </div>""")
    return f"""
      <details class="wrong-details">
        <summary>❌ 오답 {len(wrong_qs)}문제 보기</summary>
        <div class="wrong-list">{''.join(items)}
        </div>
      </details>"""


def _build_cat_section(cat: str, stats: dict, vault_docs: list[dict], wrong_qs: list[dict]) -> str:
    rate = stats.get("rate", 0)
    c, t = stats.get("correct", 0), stats.get("total", 1)
    color = _rate_color(rate)
    slug = re.sub(r"[^a-z0-9]", "_", cat.lower())

    if vault_docs:
        cards_html = "".join(_build_vault_card(doc) for doc in vault_docs)
    else:
        cards_html = '<div class="vmissing">⚠ 이 카테고리의 학습 자료를 찾을 수 없습니다.</div>'

    wrong_html = _build_wrong_list(wrong_qs)

    return f"""
    <section class="cat-section" id="cat-{slug}">
      <div class="cat-header">
        <span class="cat-name">{html_lib.escape(cat)}</span>
        <span class="cat-badge" style="background:{color}">{c}/{t} &nbsp; {rate}%</span>
      </div>
      <div class="vcards">{cards_html}
      </div>{wrong_html}
    </section>"""


def _build_checklist(weak_cats: list[tuple[str, dict]]) -> str:
    if not weak_cats:
        return ""
    items = []
    for cat, _ in weak_cats:
        items.append(f'<li><label><input type="checkbox"> {html_lib.escape(cat)} 핵심 공식 암기</label></li>')
        items.append(f'<li><label><input type="checkbox"> {html_lib.escape(cat)} 출제 포인트 확인</label></li>')
        items.append(f'<li><label><input type="checkbox"> {html_lib.escape(cat)} 오답 문제 재풀기</label></li>')
    return f"""
    <section class="checklist-section">
      <h2 class="sec-title">학습 체크리스트</h2>
      <ul class="checklist">{''.join(items)}
      </ul>
    </section>"""


# ── HTML 최종 조립 ─────────────────────────────────────────────────────────────

def generate_summary_html(result: dict, weak_cats: list[tuple[str, dict]], threshold: float) -> str:
    submitted_at = result.get("submitted_at", "")
    date_str = submitted_at[:10] if submitted_at else "—"
    score = result.get("score", 0)
    total = result.get("total", 0)
    elapsed = result.get("elapsed_seconds", 0)
    mm = elapsed // 60
    ss = elapsed % 60
    n_weak = len(weak_cats)
    test_file = html_lib.escape(result.get("test_file", ""))

    overview_html = _build_overview(weak_cats)

    if weak_cats:
        cat_sections_html = ""
        for cat, stats in weak_cats:
            vault_docs = load_vault_content(cat)
            wrong_qs = get_wrong_questions(result, cat)
            cat_sections_html += _build_cat_section(cat, stats, vault_docs, wrong_qs)
    else:
        cat_sections_html = f"""
    <div class="all-good">
      🎉 모든 카테고리가 {threshold}% 이상입니다! 훌륭합니다.
    </div>"""

    checklist_html = _build_checklist(weak_cats)

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>핵심요약집 — {date_str}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans KR", sans-serif;
       background: #f0f2f5; color: #1B2A4A; min-width: 360px; line-height: 1.6; }}

/* ── Hero ── */
.hero {{ background: #1B2A4A; color: #fff; padding: 40px 24px 32px; text-align: center; }}
.hero h1 {{ font-size: 26px; font-weight: 700; color: #C4A35A; margin-bottom: 8px; }}
.hero-sub {{ font-size: 14px; color: #a0aec0; margin-bottom: 16px; }}
.hero-stats {{ display: flex; justify-content: center; gap: 32px; flex-wrap: wrap; }}
.hstat {{ text-align: center; }}
.hstat-val {{ font-size: 28px; font-weight: 700; color: #C4A35A; }}
.hstat-lbl {{ font-size: 12px; color: #a0aec0; margin-top: 2px; }}
.weak-badge {{ display: inline-block; background: #e53935; color: #fff;
               padding: 4px 12px; border-radius: 20px; font-size: 13px; font-weight: 600;
               margin-top: 14px; }}

/* ── Layout ── */
.container {{ max-width: 900px; margin: 0 auto; padding: 24px 16px 48px; }}

/* ── Section titles ── */
.sec-title {{ font-size: 18px; font-weight: 700; color: #1B2A4A;
              border-left: 4px solid #C4A35A; padding-left: 12px; margin-bottom: 16px; }}

/* ── Overview ── */
.overview-section {{ background: #fff; border-radius: 12px; padding: 24px; margin-bottom: 24px;
                     box-shadow: 0 2px 8px rgba(0,0,0,.06); }}
.ov-row {{ display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }}
.ov-name {{ width: 110px; font-size: 14px; font-weight: 600; flex-shrink: 0; }}
.ov-bar-wrap {{ flex: 1; background: #e2e8f0; border-radius: 4px; height: 14px; overflow: hidden; }}
.ov-bar {{ height: 100%; border-radius: 4px; transition: width .4s; }}
.ov-pct {{ width: 100px; font-size: 13px; font-weight: 600; text-align: right; flex-shrink: 0; }}

/* ── Category section ── */
.cat-section {{ background: #fff; border-radius: 12px; padding: 24px; margin-bottom: 24px;
                box-shadow: 0 2px 8px rgba(0,0,0,.06); }}
.cat-header {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; }}
.cat-name {{ font-size: 20px; font-weight: 700; }}
.cat-badge {{ color: #fff; padding: 4px 14px; border-radius: 20px; font-size: 13px; font-weight: 600; }}

/* ── Vault cards ── */
.vcards {{ display: flex; flex-direction: column; gap: 16px; margin-bottom: 16px; }}
.vcard {{ border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden; }}
.vcard-header {{ background: #f7f9fc; padding: 10px 14px; display: flex; align-items: baseline; gap: 10px;
                 border-bottom: 1px solid #e2e8f0; }}
.vid {{ font-size: 11px; color: #718096; font-family: monospace; }}
.vtitle {{ font-size: 14px; font-weight: 700; flex: 1; }}
.vpage {{ font-size: 12px; color: #718096; }}
.vsec {{ padding: 14px 16px; border-bottom: 1px solid #f0f0f0; }}
.vsec:last-child {{ border-bottom: none; }}
.vsec-title {{ font-size: 12px; font-weight: 700; color: #718096; text-transform: uppercase;
               letter-spacing: .04em; margin-bottom: 8px; }}
.vsec-body {{ font-size: 14px; }}
.vmissing {{ background: #fff8e1; border: 1px solid #ffe082; border-radius: 8px;
             padding: 14px; font-size: 14px; color: #856404; }}

/* ── Vault body 스타일 ── */
.vsec-body p {{ margin-bottom: 6px; }}
.vsec-body ul.vlist, .vsec-body ol.vlist {{ padding-left: 20px; margin-bottom: 8px; }}
.vsec-body li {{ margin-bottom: 4px; }}
.vsec-body table.vtable {{ border-collapse: collapse; width: 100%; font-size: 13px; margin-bottom: 8px; }}
.vsec-body table.vtable td {{ border: 1px solid #e2e8f0; padding: 5px 8px; vertical-align: top; }}
.vsec-body table.vtable tr:nth-child(even) td {{ background: #f7f9fc; }}
.vsec-body pre.vcode {{ background: #1e293b; color: #e2e8f0; border-radius: 6px;
                        padding: 12px 14px; font-size: 13px; overflow-x: auto; margin-bottom: 8px; }}
.vsec-body blockquote {{ border-left: 3px solid #C4A35A; padding-left: 12px; color: #555;
                         font-style: italic; margin-bottom: 6px; }}
.vsec-body h4.vsub, .vsec-body h5.vsub {{ font-size: 13px; font-weight: 700; color: #2d3748;
                                          margin: 10px 0 6px; }}
.vsec-body code.ic {{ background: #edf2f7; padding: 1px 5px; border-radius: 3px;
                      font-family: monospace; font-size: 12px; }}
.vsec-body .vref {{ color: #3b82f6; text-decoration: underline; cursor: default; }}

/* ── Wrong answers ── */
.wrong-details {{ margin-top: 4px; }}
.wrong-details summary {{ cursor: pointer; font-size: 14px; font-weight: 600;
                           color: #c53030; padding: 10px 0; user-select: none; }}
.wrong-details summary:hover {{ color: #e53935; }}
.wrong-list {{ display: flex; flex-direction: column; gap: 10px; margin-top: 10px; }}
.wq-card {{ background: #fff5f5; border: 1px solid #fed7d7; border-radius: 8px; padding: 14px 16px; }}
.wq-meta {{ font-size: 12px; color: #718096; margin-bottom: 6px; }}
.wq-sentence {{ font-size: 15px; line-height: 1.7; margin-bottom: 8px; }}
.wq-sentence .blank {{ background: #fed7d7; padding: 1px 6px; border-radius: 4px; font-weight: 700; }}
.wq-choices {{ display: flex; gap: 16px; flex-wrap: wrap; font-size: 13px; }}
.wq-correct {{ color: #276749; font-weight: 700; }}
.wq-wrong {{ color: #c53030; font-weight: 700; }}

/* ── Checklist ── */
.checklist-section {{ background: #fff; border-radius: 12px; padding: 24px;
                      box-shadow: 0 2px 8px rgba(0,0,0,.06); }}
.checklist {{ list-style: none; display: flex; flex-direction: column; gap: 8px; }}
.checklist li label {{ display: flex; align-items: center; gap: 10px; cursor: pointer;
                        font-size: 14px; }}
.checklist input[type="checkbox"] {{ width: 16px; height: 16px; cursor: pointer; }}

/* ── All good ── */
.all-good {{ background: #f0fff4; border: 1px solid #9ae6b4; border-radius: 12px;
             padding: 32px; text-align: center; font-size: 18px; color: #276749;
             font-weight: 600; margin-bottom: 24px; }}

/* ── Footer ── */
.footer {{ text-align: center; font-size: 12px; color: #a0aec0; padding: 24px 0; }}

@media print {{
  .wrong-details {{ display: block; }}
  .wrong-details summary {{ display: none; }}
  .wrong-list {{ display: flex !important; }}
}}
</style>
</head>
<body>

<div class="hero">
  <h1>Part5 핵심요약집</h1>
  <div class="hero-sub">시험 파일: {test_file} &nbsp;|&nbsp; 시험일: {date_str}</div>
  <div class="hero-stats">
    <div class="hstat">
      <div class="hstat-val">{score} / {total}</div>
      <div class="hstat-lbl">점수</div>
    </div>
    <div class="hstat">
      <div class="hstat-val">{mm:02d}:{ss:02d}</div>
      <div class="hstat-lbl">소요 시간</div>
    </div>
    <div class="hstat">
      <div class="hstat-val">{n_weak}개</div>
      <div class="hstat-lbl">취약 카테고리</div>
    </div>
  </div>
  {'<div class="weak-badge">⚠ 취약 카테고리 있음 — 아래 핵심 내용을 복습하세요</div>' if n_weak > 0 else ''}
</div>

<div class="container">
{overview_html}
{cat_sections_html}
{checklist_html}
</div>

<div class="footer">
  생성: {generated_at} &nbsp;|&nbsp; 출처: 해커스 토익 RC 기본서 2023
</div>

</body>
</html>"""


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Part5 취약점 핵심요약집 생성기")
    parser.add_argument("result_json", help="결과 JSON 파일 경로")
    parser.add_argument(
        "--threshold", type=float, default=70.0,
        help="취약 기준 정답률 %% (기본 70)",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="출력 디렉토리 (기본: 입력 파일과 같은 디렉토리)",
    )
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")

    result_path = Path(args.result_json)
    if not result_path.exists():
        print(f"오류: 파일을 찾을 수 없습니다: {result_path}", file=sys.stderr)
        sys.exit(1)

    result = load_result(result_path)
    weak_cats = find_weak_categories(result, args.threshold)

    total_cats = len(result.get("category_stats", {}))
    print(f"총 {total_cats}개 카테고리 중 {len(weak_cats)}개 취약 (기준: {args.threshold}%)")
    for cat, stats in weak_cats:
        print(f"  ⚠ {cat}: {stats['correct']}/{stats['total']} ({stats['rate']}%)")

    output_dir = Path(args.output) if args.output else result_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    output_path = output_dir / f"summary_{timestamp}.html"

    html_content = generate_summary_html(result, weak_cats, args.threshold)
    output_path.write_text(html_content, encoding="utf-8")
    print(f"생성 완료: {output_path}")


if __name__ == "__main__":
    main()
