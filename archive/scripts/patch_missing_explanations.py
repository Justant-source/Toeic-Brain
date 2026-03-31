"""
patch_missing_explanations.py

One-time script to extract and patch missing Part5 explanations
from ETS answer PDFs where OCR garbled question numbers/layout.

Usage:
    py -3.14 scripts/patch_missing_explanations.py
"""

import sys
import io
import re
import json
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

try:
    import fitz
except ImportError:
    print("ERROR: PyMuPDF (fitz) not installed. Run: pip install pymupdf")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

BASE = Path("C:/Data/Toeic Brain")
RAW_DIR = BASE / "data" / "raw" / "answer"
JSON_DIR = BASE / "data" / "processed" / "questions"

# Missing items: {vol: [(test_number, question_number), ...]}
MISSING = {
    1: [(3, 113), (5, 120), (5, 123), (7, 111), (7, 112), (7, 114),
        (8, 103), (8, 104), (8, 105)],
    2: [(1, 115), (5, 108), (7, 117), (7, 119), (9, 109), (9, 114)],
    3: [(1, 107), (1, 125), (2, 107), (4, 107), (6, 116), (7, 101),
        (7, 103), (7, 108), (7, 126), (8, 116), (8, 125), (9, 125),
        (10, 114), (10, 130)],
}

# Answer key page indices (0-based) for each volume
# Each index is the first page of a test (answer sheet page)
ANSWER_KEY_PAGES = {
    1: [1, 20, 40, 61, 82, 104, 124, 145, 166, 187, 210],
    2: [1, 22, 43, 64, 84, 105, 127, 148, 170, 191, 212],
    3: [1, 22, 43, 64, 85, 106, 127, 149, 171, 193, 214],
}


# ─────────────────────────────────────────────────────────────────────────────
# PDF extraction helpers
# ─────────────────────────────────────────────────────────────────────────────

def classify_right_block(text, x0, x1):
    """Classify a right-half block.

    Returns (kind, normalized_text):
      kind='label': section marker (해설/번역/어휘 or OCR variant)
      kind='header': question number line (e.g., '113 전치사어휘')
      kind='separator': dots/dashes separator
      kind='content': actual explanation text
    """
    clean = text.strip()
    first_line = clean.split('\n')[0].strip()
    width = x1 - x0

    # Exact label matches (standalone)
    if first_line in ('해설', '번역', '어휘') and width < 50:
        return 'label', first_line

    # OCR-garbled '번역' label (appears as decorative chars in narrow block)
    if re.match(r'^[여버「」\s\n]+$', clean) and width < 20:
        return 'label', '번역'

    # Question number header (e.g., '113 전치사어휘', '112 형용사 자리 _ 명사 수식')
    # Also handles OCR variant where '11' is misread as '끄': '끄4 인칭대명사...'
    if re.match(r'^\d{3}\s+\S', first_line) or re.match(r'^끄\d\s+\S', first_line):
        return 'header', clean

    # Separator lines (dots, dashes)
    stripped = clean.replace(' ', '').replace('\n', '')
    if len(stripped) >= 3 and re.match(r'^[\.·\-·]+$', stripped):
        return 'separator', clean

    # Label fused with content (e.g., '어휘 word1 어휘1\nword2 어휘2')
    # These have the label word as the first token followed by a space
    for lbl in ('해설', '번역', '어휘'):
        if first_line == lbl or first_line.startswith(lbl + ' ') or first_line.startswith(lbl + '\n'):
            if first_line != lbl:
                return 'label_with_content', lbl
            elif '\n' in clean:
                # label on first line, content on subsequent lines
                rest = '\n'.join(clean.split('\n')[1:]).strip()
                return 'label_then_content', (lbl, rest)

    return 'content', clean


def extract_test_text(pdf_path, test_idx, answer_key_pages):
    """Extract merged text for a test's pages.

    Handles the 2-column layout: left half of page processed first,
    then right half. Within the right half, label blocks and question
    number headers are emitted as normalized markers.
    """
    start_page = answer_key_pages[test_idx]
    end_page = answer_key_pages[test_idx + 1]

    pdf = fitz.open(str(pdf_path))
    all_lines = []

    for pi in range(start_page, end_page):
        page = pdf[pi]
        raw_blocks = page.get_text('blocks')

        left_blocks = []
        right_blocks = []

        for b in raw_blocks:
            x0, y0, x1, y1, text, block_no, block_type = b
            if block_type != 0:
                continue
            text = text.strip()
            if not text:
                continue
            if x0 < 280:
                left_blocks.append((y0, text))
            else:
                right_blocks.append((y0, x0, x1, text))

        # Emit left column sorted by y
        for y, text in sorted(left_blocks, key=lambda b: b[0]):
            all_lines.append(text)

        # Process right column sorted by y (then x for same-y blocks)
        for y, x0, x1, text in sorted(right_blocks, key=lambda b: (b[0], b[1])):
            kind, value = classify_right_block(text, x0, x1)

            if kind == 'label':
                all_lines.append(value)
            elif kind == 'header':
                all_lines.append(value)
            elif kind == 'separator':
                pass  # skip
            elif kind == 'label_with_content':
                # value is the label name; the full text has label + content
                all_lines.append(value)
                rest = text.strip()[len(value):].strip()
                if rest:
                    all_lines.append(rest)
            elif kind == 'label_then_content':
                lbl, rest = value
                all_lines.append(lbl)
                if rest:
                    all_lines.append(rest)
            else:
                all_lines.append(text)

    pdf.close()
    return '\n'.join(all_lines)


def find_part5_section(full_text):
    """Extract Part5 explanations section from test text."""
    p5_match = re.search(r'PART\s*[S5]', full_text)
    p6_match = re.search(r'PART\s*6', full_text)
    if not p5_match:
        return ''
    end = p6_match.start() if p6_match else len(full_text)
    return full_text[p5_match.start():end]


def _make_q_pattern(q_num):
    """Generate regex pattern for a question number, handling OCR variants.

    OCR sometimes reads '11' as '끄' (HANGUL SYLLABLE GGEU, looks like ㄲ).
    So '114' → '끄4', '116' → '끄6', '113' → '끄3', etc.
    We generate alternatives for 11X numbers.
    """
    s = str(q_num)
    if len(s) == 3 and s[:2] == '11':
        # 11X can appear as '끄X' due to OCR
        return rf'(?:{s}|끄{s[2]})'
    return s


def find_question_section(part5_text, q_num):
    """Find the raw text section for question q_num.

    Handles OCR-garbled question numbers (e.g., '끄4' for '114').
    """
    q_pat = _make_q_pattern(q_num)
    pattern = rf'(?:^|\n){q_pat}\s+\S'
    m = re.search(pattern, part5_text)
    if not m:
        return None

    start = m.start()
    if part5_text[start] == '\n':
        start += 1

    # Determine the actual matched length (may differ from len(str(q_num)))
    matched_num_end = m.end() - 1  # exclude the \S character
    matched_len = matched_num_end - start

    # Find the next question to determine section end
    end = len(part5_text)
    for nq in range(q_num + 1, q_num + 20):
        np_pat = _make_q_pattern(nq)
        np = rf'(?:^|\n){np_pat}\s+\S'
        nm = re.search(np, part5_text[start + matched_len:])
        if nm:
            e = start + matched_len + nm.start()
            if part5_text[e] == '\n':
                e += 1
            end = e
            break

    return part5_text[start:end]


# ─────────────────────────────────────────────────────────────────────────────
# Explanation text parsing
# ─────────────────────────────────────────────────────────────────────────────

def clean_text_block(t):
    """Remove OCR artifacts and normalize whitespace."""
    # Remove lone decorative OCR characters
    t = re.sub(r'\n[여버「」]\n', '\n', t)
    t = re.sub(r'\n[여버「」]$', '', t)
    t = re.sub(r'^[여버「」]\n', '', t)
    # Remove separator lines
    t = re.sub(r'(?m)^[\.·\-]{3,}$', '', t)
    # Remove standalone page numbers
    t = re.sub(r'(?m)^\d{1,2}\s*$', '', t)
    # Collapse multiple blank lines
    t = re.sub(r'\n{3,}', '\n\n', t)
    return t.strip()


def parse_section_to_explanation(section):
    """Parse a raw question section into the explanation JSON format.

    Output format:
        {해설 text}
        [번역] {번역 text}
        [어휘] {어휘 text}
    """
    lines = section.strip().split('\n')
    lines = [l.strip() for l in lines if l.strip()]

    # Skip question number line (e.g., '113 전치사어휘', or OCR-garbled '끄4 인칭대명사...')
    if lines and (re.match(r'^\d{3}\s+', lines[0]) or re.match(r'^끄\d\s+', lines[0])):
        lines = lines[1:]

    # Skip separator lines
    lines = [l for l in lines if not re.match(r'^[\.·\-]{3,}$', l)]

    # Parse into sections using labels as separators
    sections = {'해설': [], '번역': [], '어휘': []}
    current = '해설'

    for line in lines:
        if line == '해설':
            current = '해설'
        elif line == '번역':
            current = '번역'
        elif line == '어휘':
            current = '어휘'
        else:
            sections[current].append(line)

    haesul = clean_text_block('\n'.join(sections['해설']))
    bun = clean_text_block('\n'.join(sections['번역']))
    eohwi = clean_text_block('\n'.join(sections['어휘']))

    result = haesul
    if bun:
        result += '\n[번역] ' + bun
    if eohwi:
        result += '\n[어휘] ' + eohwi

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Main extraction and patching
# ─────────────────────────────────────────────────────────────────────────────

def extract_explanation(vol, test_num, q_num, answer_key_pages):
    """Extract explanation text for a specific question."""
    pdf_path = RAW_DIR / f"ets_answer_vol{vol}.pdf"

    test_idx = test_num - 1
    if test_idx >= len(answer_key_pages) - 1:
        print(f"  ERROR: test {test_num} out of range for vol{vol}")
        return None

    full_text = extract_test_text(pdf_path, test_idx, answer_key_pages)
    part5_text = find_part5_section(full_text)

    if not part5_text:
        print(f"  WARNING: Could not find Part5 section in vol{vol} test{test_num}")
        return None

    section = find_question_section(part5_text, q_num)
    if not section:
        print(f"  WARNING: Could not find Q{q_num} in vol{vol} test{test_num} Part5")
        # Debug: show nearby content
        idx = part5_text.find(str(q_num))
        if idx >= 0:
            print(f"    (partial match at pos {idx}): {repr(part5_text[max(0,idx-20):idx+100])}")
        return None

    explanation = parse_section_to_explanation(section)
    return explanation


def patch_json(vol, test_num, q_num, explanation):
    """Patch a specific question's explanation in the JSON file."""
    json_path = JSON_DIR / f"vol{vol}_part5.json"

    with open(json_path, encoding='utf-8') as f:
        data = json.load(f)

    target_id = f"vol{vol}_test{test_num:02d}_part5_{q_num}"
    found = False
    for q in data:
        if q['id'] == target_id:
            if q.get('explanation') and q['explanation'].strip():
                print(f"  SKIP: {target_id} already has explanation")
                return False
            q['explanation'] = explanation
            found = True
            break

    if not found:
        print(f"  ERROR: {target_id} not found in {json_path.name}")
        return False

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return True


def main():
    print("=" * 60)
    print("Patching missing Part5 explanations")
    print("=" * 60)

    success_count = 0
    fail_count = 0
    skip_count = 0

    for vol, missing_list in sorted(MISSING.items()):
        print(f"\n[Vol {vol}]")
        ak_pages = ANSWER_KEY_PAGES[vol]

        for test_num, q_num in missing_list:
            print(f"  Processing: test={test_num}, q={q_num} ...", end='', flush=True)

            explanation = extract_explanation(vol, test_num, q_num, ak_pages)

            if explanation is None:
                print(" FAILED (extraction)")
                fail_count += 1
                continue

            if not explanation.strip():
                print(" FAILED (empty explanation)")
                # Debug: show raw section
                pdf_path = RAW_DIR / f"ets_answer_vol{vol}.pdf"
                full_text = extract_test_text(pdf_path, test_num - 1, ak_pages)
                part5_text = find_part5_section(full_text)
                section = find_question_section(part5_text, q_num)
                if section:
                    print(f"    Raw section: {repr(section[:300])}")
                fail_count += 1
                continue

            result = patch_json(vol, test_num, q_num, explanation)

            if result:
                print(f" OK")
                print(f"    Preview: {explanation[:100].replace(chr(10), ' ')}")
                success_count += 1
            else:
                skip_count += 1

    print(f"\n{'=' * 60}")
    print(f"Done. Success: {success_count}, Skipped: {skip_count}, Failed: {fail_count}")

    # Verification
    print("\nVerification: checking for remaining empty explanations...")
    for vol in [1, 2, 3]:
        json_path = JSON_DIR / f"vol{vol}_part5.json"
        if not json_path.exists():
            continue
        with open(json_path, encoding='utf-8') as f:
            data = json.load(f)
        empty = [(q['id'], q['test'], q['question_number'])
                 for q in data
                 if not q.get('explanation') or not q['explanation'].strip()]
        if empty:
            print(f"  Vol{vol} still missing {len(empty)} explanations:")
            for qid, t, qn in empty:
                print(f"    {qid}")
        else:
            print(f"  Vol{vol}: all explanations present OK")


if __name__ == '__main__':
    main()
