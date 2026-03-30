"""
word_ets_examples.json 의 ------- 빈칸을 정답으로 채운다.

- OCR cache (p.N) 예문: Part5/6 문제 DB와 매칭 → 정답 단어/문장 삽입
- Part 6 passage 예문: raw_text 파싱 → 정답 choice 삽입
- Part 7 잡음 빈칸: 제거

Output: data/mapped/fill_patches_vol{N}.json
  { word: [ { "idx": N, "new_sentence": "..." }, ... ] }

Usage:
  py -3 scripts/process/fill_blanks.py --vol 1
  py -3 scripts/process/fill_blanks.py --vol 1 2 3
"""

import re
import json
import sys
import argparse
import logging
from pathlib import Path
from collections import defaultdict

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

PROJECT_ROOT   = Path(__file__).resolve().parent.parent.parent
QUESTIONS_DIR  = PROJECT_ROOT / "data" / "processed" / "questions"
ETS_EXAMPLES   = PROJECT_ROOT / "data" / "mapped" / "word_ets_examples.json"
PATCHES_DIR    = PROJECT_ROOT / "data" / "mapped"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

BLANK = "-------"
_BLANK_RE = re.compile(r"-{3,}")
_CHOICE_LINE_RE = re.compile(r"^\s*\d{2,3}\.\s*\([A-D]\)")
_CHOICE_CONT_RE = re.compile(r"^\s*\([A-D]\)\s")
_QNUM_RE = re.compile(r"^\s*(\d{2,3})\.\s*$")


# ── Normalisation ─────────────────────────────────────────────────────────────

def _norm(text: str) -> str:
    """Normalise for fuzzy matching: lowercase, compress spaces, unify blank marker."""
    t = text.lower()
    t = _BLANK_RE.sub("@@BLANK@@", t)
    t = re.sub(r"\*\*", "", t)              # strip bold markers
    t = re.sub(r"[^\w\s@]", " ", t)        # keep word chars + @BLANK marker
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _partial_key(norm: str, n: int = 60) -> str:
    """Short key: first n + last n chars of normalised text (fast bucket lookup)."""
    return norm[:n] + "|" + norm[-n:]


# ── Part 5 lookup ─────────────────────────────────────────────────────────────

def build_part5_lookup(vol: int) -> dict[str, dict]:
    """
    Returns {norm_sentence: {"answer_text": str, "filled": str}}
    Also returns {partial_key: norm_sentence} for fallback lookup.
    """
    exact: dict[str, dict] = {}
    for fp in sorted(QUESTIONS_DIR.glob(f"vol{vol}_part5.json")):
        qs = json.loads(fp.read_text(encoding="utf-8"))
        for q in qs:
            sentence = (q.get("sentence") or "").strip()
            choices  = q.get("choices") or {}
            answer   = q.get("answer") or ""
            if not sentence or not answer or answer not in choices:
                continue
            answer_text = str(choices[answer]).strip()
            filled = _BLANK_RE.sub(answer_text, sentence, count=1)
            key = _norm(sentence)
            exact[key] = {
                "answer_text": answer_text,
                "filled": filled,
            }
    return exact


# ── Part 6 lookup ─────────────────────────────────────────────────────────────

def _parse_choices_from_block(block: str, q_num: int) -> dict[str, str]:
    """Extract (A)/(B)/(C)/(D) choices for question q_num from a raw passage block."""
    # Find lines like "131. (A) ..." or "131.\n(A) ..."
    pattern = re.compile(
        r"(?:^|\n)\s*" + str(q_num) + r"\.\s*(?:\([A-D]\)[^\n]*)(?:\n\s*\([A-D]\)[^\n]*)*",
        re.MULTILINE,
    )
    m = pattern.search(block)
    if not m:
        return {}
    chunk = m.group(0)
    choices: dict[str, str] = {}
    for cm in re.finditer(r"\(([A-D])\)\s*(.+?)(?=\s*\([A-D]\)|\s*\d{2,3}\.|\Z)", chunk, re.DOTALL):
        letter = cm.group(1)
        text = re.sub(r"\s+", " ", cm.group(2)).strip()
        if text:
            choices[letter] = text
    return choices


def build_part6_lookup(vol: int) -> dict[str, dict]:
    """
    Parse Part 6 raw_text passages to build:
    {norm_blanked_sentence: {"answer_text": str, "filled": str}}
    """
    lookup: dict[str, dict] = {}

    for fp in sorted(QUESTIONS_DIR.glob(f"vol{vol}_part6.json")):
        entries = json.loads(fp.read_text(encoding="utf-8"))
        for entry in entries:
            raw = (entry.get("raw_text") or "").strip()
            answers: dict[str, str] = {
                str(k): str(v) for k, v in (entry.get("answer") or {}).items()
            }
            if not raw or not answers:
                continue

            # Find each passage block
            header_re = re.compile(
                r"Questions\s+(\d{2,3})\s*[-–—]\s*(\d{2,3})\s+refer\s+to\s+the\s+following\s+",
                re.IGNORECASE,
            )
            headers = list(header_re.finditer(raw))
            if not headers:
                headers_fake = [None]  # treat whole thing as one block
                blocks = [(raw, 131, 134)]   # dummy range
            else:
                blocks = []
                for i, hdr in enumerate(headers):
                    q_start = int(hdr.group(1))
                    q_end   = int(hdr.group(2))
                    blk_start = hdr.end()
                    blk_end   = headers[i + 1].start() if i + 1 < len(headers) else len(raw)
                    blocks.append((raw[blk_start:blk_end], q_start, q_end))

            for block_text, q_start, q_end in blocks:
                # Extract passage lines (remove choice lines and header noise)
                passage_lines = []
                for line in block_text.split("\n"):
                    stripped = line.strip()
                    if not stripped:
                        continue
                    if _CHOICE_LINE_RE.match(stripped):
                        continue
                    if _CHOICE_CONT_RE.match(stripped):
                        continue
                    if re.match(r"^\d{2,3}\.\s*$", stripped):
                        continue
                    passage_lines.append(stripped)
                passage_text = " ".join(passage_lines)

                # Split passage into sentences
                sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z\"(])", passage_text)

                # For each sentence with a blank, find its question number
                blank_idx = 0  # which blank are we on (0-indexed among all blanks in passage)
                for sent in sentences:
                    if BLANK not in sent and "@@BLANK@@" not in sent:
                        continue
                    q_num = q_start + blank_idx
                    blank_idx += 1
                    if q_num > q_end:
                        break

                    ans_letter = answers.get(str(q_num), "")
                    if not ans_letter:
                        continue

                    # Get choice text for this question
                    choices = _parse_choices_from_block(block_text, q_num)
                    ans_text = choices.get(ans_letter, "").strip()
                    if not ans_text:
                        continue

                    # For sentence-insertion blanks, the ans_text IS the sentence
                    # For word blanks, ans_text is the word/phrase
                    sent_stripped = re.sub(r"\*\*", "", sent)  # remove existing bold
                    # Check if this is a sentence blank (answer is a full sentence)
                    is_sentence_blank = len(ans_text.split()) >= 5

                    if is_sentence_blank:
                        # Replace the blank marker with the answer sentence
                        filled = re.sub(r"-{3,}\s*[.,]?", ans_text, sent_stripped, count=1).strip()
                    else:
                        filled = _BLANK_RE.sub(ans_text, sent_stripped, count=1)

                    key = _norm(sent)
                    lookup[key] = {
                        "answer_text": ans_text,
                        "filled": filled,
                    }

    return lookup


# ── Apply fill to a single sentence ─────────────────────────────────────────

def fill_sentence(
    sentence: str,
    part5_lookup: dict[str, dict],
    part6_lookup: dict[str, dict],
) -> str | None:
    """
    Try to fill blanks in sentence. Returns filled sentence or None if not found.
    """
    if BLANK not in sentence:
        return None  # nothing to do

    norm = _norm(sentence)

    # Try Part 5 (exact)
    if norm in part5_lookup:
        info = part5_lookup[norm]
        ans = info["answer_text"]
        # Re-build filled with bold on answer
        raw = re.sub(r"\*\*", "", sentence)  # strip old bold
        filled = _BLANK_RE.sub(f"**{ans}**", raw, count=1)
        return filled

    # Try Part 6 (exact)
    if norm in part6_lookup:
        info = part6_lookup[norm]
        ans = info["answer_text"]
        raw = re.sub(r"\*\*", "", sentence)
        filled = _BLANK_RE.sub(f"**{ans}**", raw, count=1)
        return filled

    # Fuzzy: check if any Part 5 key is substring of norm (or vice versa)
    # (handles OCR that includes extra words before/after)
    for p5key, info in part5_lookup.items():
        # Both must contain @@BLANK@@
        if "@@blank@@" not in p5key:
            continue
        # Check if the core matches (strip surrounding noise)
        p5_stripped = p5key.replace("@@blank@@", "@@BLANK@@")
        if p5_stripped in norm or norm in p5key:
            ans = info["answer_text"]
            raw = re.sub(r"\*\*", "", sentence)
            filled = _BLANK_RE.sub(f"**{ans}**", raw, count=1)
            return filled

    return None  # no match


# ── Main processing per volume ───────────────────────────────────────────────

def process_volume(
    vol: int,
    ets_data: dict[str, dict],
) -> dict[str, list[dict]]:
    """
    Returns patches: {word: [{"idx": int, "new_sentence": str}]}
    """
    logger.info("Vol %d: building lookups ...", vol)
    part5 = build_part5_lookup(vol)
    part6 = build_part6_lookup(vol)
    logger.info("Vol %d: Part5=%d, Part6=%d lookup entries", vol, len(part5), len(part6))

    patches: dict[str, list[dict]] = defaultdict(list)
    total_blanks = 0
    total_filled = 0
    unfilled = 0

    for word, entry in ets_data.items():
        examples = entry.get("examples") or []
        for idx, ex in enumerate(examples):
            sentence = ex.get("sentence") or ""
            if BLANK not in sentence:
                continue
            if ex.get("volume") != vol:
                continue

            total_blanks += 1
            filled = fill_sentence(sentence, part5, part6)

            if filled is not None:
                patches[word].append({"idx": idx, "new_sentence": filled})
                total_filled += 1
            else:
                unfilled += 1

    logger.info(
        "Vol %d: %d blanks found, %d filled, %d unfilled",
        vol, total_blanks, total_filled, unfilled,
    )
    return dict(patches)


# ── CLI ──────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Fill ------- blanks with correct answers")
    p.add_argument("--vol", type=int, nargs="+", default=[1, 2, 3, 4, 5], metavar="N")
    return p.parse_args()


def main():
    args = parse_args()

    ets_data: dict = json.loads(ETS_EXAMPLES.read_text(encoding="utf-8"))
    print(f"  Loaded {len(ets_data):,} words from word_ets_examples.json")

    for vol in sorted(args.vol):
        print(f"\n  Processing Vol {vol} ...")
        patches = process_volume(vol, ets_data)

        words_patched = len(patches)
        total_patches = sum(len(v) for v in patches.values())

        out_path = PATCHES_DIR / f"fill_patches_vol{vol}.json"
        out_path.write_text(
            json.dumps(patches, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  Vol {vol}: {total_patches:,} patches across {words_patched:,} words → {out_path.name}")


if __name__ == "__main__":
    main()
