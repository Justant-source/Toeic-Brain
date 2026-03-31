"""
Validate the integrity of extracted JSON data (questions and vocabulary)
before further processing.
"""

import sys
import json
import re
import argparse
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

# Windows UTF-8 fix
sys.stdout.reconfigure(encoding="utf-8")

# ── ANSI colours ──────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def green(s: str)  -> str: return f"{GREEN}{s}{RESET}"
def yellow(s: str) -> str: return f"{YELLOW}{s}{RESET}"
def red(s: str)    -> str: return f"{RED}{s}{RESET}"
def cyan(s: str)   -> str: return f"{CYAN}{s}{RESET}"
def bold(s: str)   -> str: return f"{BOLD}{s}{RESET}"

# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class Issue:
    severity: str          # "error" | "warning"
    file: str
    item_id: str
    field: str
    description: str

    def __str__(self) -> str:
        colour = red if self.severity == "error" else yellow
        tag = colour(f"[{self.severity.upper()}]")
        return (
            f"  {tag} {self.file} | id={self.item_id} | "
            f"field={self.field} | {self.description}"
        )


@dataclass
class ValidationResult:
    target: str                        # "questions" | "vocab" | "mapping"
    total: int = 0
    valid: int = 0
    warnings: int = 0
    errors: int = 0
    issues: list[Issue] = field(default_factory=list)
    fixed: int = 0

    def add_issue(self, severity: str, file: str, item_id: str,
                  field_name: str, description: str) -> None:
        self.issues.append(Issue(severity, file, item_id, field_name, description))
        if severity == "error":
            self.errors += 1
        else:
            self.warnings += 1

    def ok(self) -> bool:
        return self.errors == 0


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_json(path: Path) -> Optional[list | dict]:
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as exc:
        print(red(f"  JSON parse error in {path}: {exc}"))
        return None


def save_json(path: Path, data: list | dict) -> None:
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


# ── Question validation ───────────────────────────────────────────────────────

QUESTION_ID_RE  = re.compile(r"^vol(\d+)_test(\d+)_part(\d+)_(\d{3})$")
VALID_PARTS     = {5, 6, 7}
VALID_ANSWERS   = {None, "A", "B", "C", "D"}
VALID_CATEGORIES = {
    None,
    "품사", "동사시제/태", "접속사/전치사", "관계대명사",
    "어휘", "대명사", "비교급/최상급", "기타문법",
}
CHOICE_KEYS     = {"A", "B", "C", "D"}
BLANK_MARKER    = "-------"


def validate_question(
    q: dict,
    fname: str,
    result: ValidationResult,
    fix: bool,
) -> dict:
    """Validate a single question dict; return (possibly fixed) dict."""
    qid = q.get("id", "<unknown>")

    def err(f: str, msg: str)  -> None: result.add_issue("error",   fname, qid, f, msg)
    def warn(f: str, msg: str) -> None: result.add_issue("warning", fname, qid, f, msg)

    required = ["id", "volume", "test", "part", "question_number", "sentence", "choices"]
    for req in required:
        if req not in q:
            err(req, f"Required field '{req}' is missing")

    # id
    if "id" in q:
        m = QUESTION_ID_RE.match(str(q["id"]))
        if not m:
            err("id", f"Does not match vol{{N}}_test{{NN}}_part{{N}}_{{NNN}}: {q['id']!r}")
        else:
            id_vol, id_test, id_part, _ = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
            if "volume" in q and q["volume"] != id_vol:
                err("id", f"volume in id ({id_vol}) != volume field ({q['volume']})")
            if "test" in q and q["test"] != id_test:
                err("id", f"test in id ({id_test}) != test field ({q['test']})")
            if "part" in q and q["part"] != id_part:
                err("id", f"part in id ({id_part}) != part field ({q['part']})")

    # volume
    if "volume" in q:
        if not isinstance(q["volume"], int) or not (1 <= q["volume"] <= 5):
            err("volume", f"Must be integer 1-5, got {q['volume']!r}")

    # test
    if "test" in q:
        if not isinstance(q["test"], int) or not (1 <= q["test"] <= 10):
            err("test", f"Must be integer 1-10, got {q['test']!r}")

    # part
    if "part" in q:
        if q["part"] not in VALID_PARTS:
            err("part", f"Must be 5, 6, or 7, got {q['part']!r}")

    # question_number
    if "question_number" in q:
        if not isinstance(q["question_number"], int) or not (101 <= q["question_number"] <= 200):
            err("question_number", f"Must be integer 101-200, got {q['question_number']!r}")

    # sentence
    if "sentence" in q:
        sentence = q["sentence"]
        if fix and isinstance(sentence, str):
            sentence = sentence.strip()
            q["sentence"] = sentence
        if not isinstance(sentence, str) or not sentence:
            err("sentence", "Must be a non-empty string")
        else:
            part = q.get("part")
            if part == 5 and BLANK_MARKER not in sentence:
                # Attempt to normalise common alternative blank markers
                if fix:
                    normalised = re.sub(r"-{5,}", BLANK_MARKER, sentence)
                    normalised = re.sub(r"_{5,}", BLANK_MARKER, normalised)
                    normalised = re.sub(r"\.{5,}", BLANK_MARKER, normalised)
                    if BLANK_MARKER in normalised:
                        q["sentence"] = normalised
                        result.fixed += 1
                    else:
                        warn("sentence", f'Part 5 sentence missing blank marker "{BLANK_MARKER}"')
                else:
                    warn("sentence", f'Part 5 sentence missing blank marker "{BLANK_MARKER}"')

    # choices
    if "choices" in q:
        choices = q["choices"]
        if not isinstance(choices, dict):
            err("choices", "Must be a dict")
        else:
            missing = CHOICE_KEYS - choices.keys()
            extra   = choices.keys() - CHOICE_KEYS
            if missing:
                err("choices", f"Missing keys: {sorted(missing)}")
            if extra:
                warn("choices", f"Unexpected keys: {sorted(extra)}")
            for k in CHOICE_KEYS & choices.keys():
                v = choices[k]
                if fix and isinstance(v, str):
                    choices[k] = v.strip()
                    v = choices[k]
                if not isinstance(v, str) or not v:
                    err("choices", f"Choice {k} must be a non-empty string, got {v!r}")

    # answer
    if "answer" in q:
        if q["answer"] not in VALID_ANSWERS:
            err("answer", f"Must be null or one of A/B/C/D, got {q['answer']!r}")

    # category
    if "category" in q:
        if q["category"] not in VALID_CATEGORIES:
            warn("category", f"Unexpected category value: {q['category']!r}")

    return q


def validate_questions(
    question_files: list[Path],
    result: ValidationResult,
    fix: bool,
    verbose: bool,
) -> dict[str, dict]:
    """Validate all question JSON files. Returns {id: question} index."""
    all_ids: dict[str, str] = {}   # id -> file where first seen
    question_index: dict[str, dict] = {}

    # Group files to check sequential question numbers per (volume, test)
    test_questions: dict[tuple[int, int, int], list[int]] = {}

    for path in sorted(question_files):
        fname = path.name
        data  = load_json(path)

        if data is None:
            result.add_issue("error", fname, "<file>", "file", "Could not load file")
            continue

        if not isinstance(data, list):
            result.add_issue("error", fname, "<file>", "file", "Top-level must be a JSON array")
            continue

        modified = False
        valid_in_file = 0

        for raw_q in data:
            result.total += 1
            if not isinstance(raw_q, dict):
                result.add_issue("error", fname, "<item>", "type", "Item is not a JSON object")
                continue

            q = validate_question(raw_q, fname, result, fix)
            if fix and q is not raw_q:
                modified = True

            qid = q.get("id", "")
            if qid:
                if qid in all_ids:
                    result.add_issue(
                        "error", fname, qid, "id",
                        f"Duplicate ID also found in {all_ids[qid]}",
                    )
                else:
                    all_ids[qid] = fname
                    question_index[qid] = q

                    vol  = q.get("volume")
                    test = q.get("test")
                    part = q.get("part")
                    qnum = q.get("question_number")
                    if all(isinstance(x, int) for x in (vol, test, part, qnum)):
                        key = (vol, test, part)
                        test_questions.setdefault(key, []).append(qnum)

            # Count as valid if no errors were added for this item
            pre_err = result.errors
            if result.errors == pre_err:
                valid_in_file += 1

        result.valid += valid_in_file

        if fix and modified:
            save_json(path, data)
            if verbose:
                print(yellow(f"  [FIX] Wrote {path}"))

    # Check sequential question numbers for Part 5 (101-130)
    for (vol, test, part), nums in test_questions.items():
        if part != 5:
            continue
        nums_sorted = sorted(set(nums))
        expected = list(range(101, 101 + len(nums_sorted)))
        if nums_sorted != expected:
            result.add_issue(
                "warning",
                f"vol{vol}",
                f"vol{vol}_test{test:02d}_part{part}",
                "question_number",
                f"Numbers not sequential: {nums_sorted[:10]}{'...' if len(nums_sorted) > 10 else ''}",
            )

    return question_index


# ── Vocabulary validation ─────────────────────────────────────────────────────

VOCAB_ID_RE = re.compile(r"^hw_(\d{4})$")
VALID_POS   = re.compile(
    r"^(n\.|v\.|adj\.|adv\.|prep\.|conj\.|phr\.|interj\.|det\.|num\.|abbr\.)"
)
VALID_FREQ  = {None, "★", "★★", "★★★"}


def validate_vocab_entry(
    entry: dict,
    fname: str,
    result: ValidationResult,
    fix: bool,
) -> dict:
    eid = entry.get("id", "<unknown>")

    def err(f: str, msg: str)  -> None: result.add_issue("error",   fname, eid, f, msg)
    def warn(f: str, msg: str) -> None: result.add_issue("warning", fname, eid, f, msg)

    required = ["id", "word", "pos", "meaning_kr", "day"]
    for req in required:
        if req not in entry:
            err(req, f"Required field '{req}' is missing")

    # id
    if "id" in entry:
        if not VOCAB_ID_RE.match(str(entry["id"])):
            err("id", f"Does not match hw_{{NNNN}}: {entry['id']!r}")

    # word
    if "word" in entry:
        word = entry["word"]
        if fix and isinstance(word, str):
            entry["word"] = word.strip()
            word = entry["word"]
        if not isinstance(word, str) or not word:
            err("word", "Must be a non-empty English string")
        elif not re.search(r"[A-Za-z]", word):
            warn("word", f"Word appears to contain no English letters: {word!r}")

    # pos
    if "pos" in entry:
        pos = entry["pos"]
        if fix and isinstance(pos, str):
            entry["pos"] = pos.strip()
            pos = entry["pos"]
        if not isinstance(pos, str) or not pos:
            err("pos", "Must be a non-empty string")
        elif not VALID_POS.match(pos):
            warn("pos", f"Unexpected POS value: {pos!r}")

    # meaning_kr
    if "meaning_kr" in entry:
        meaning = entry["meaning_kr"]
        if fix and isinstance(meaning, str):
            entry["meaning_kr"] = meaning.strip()
            meaning = entry["meaning_kr"]
        if not isinstance(meaning, str) or not meaning:
            err("meaning_kr", "Must be a non-empty Korean string")

    # day
    if "day" in entry:
        if not isinstance(entry["day"], int) or entry["day"] < 1:
            err("day", f"Must be integer >= 1, got {entry['day']!r}")

    # frequency (optional)
    if "frequency" in entry:
        if entry["frequency"] not in VALID_FREQ:
            warn("frequency", f"Unexpected frequency value: {entry['frequency']!r}")

    return entry


def validate_vocab(
    vocab_path: Path,
    result: ValidationResult,
    fix: bool,
    verbose: bool,
) -> dict[str, dict]:
    """Validate vocabulary JSON. Returns {id: entry} index."""
    fname = vocab_path.name
    data  = load_json(vocab_path)

    vocab_index: dict[str, dict] = {}

    if data is None:
        result.add_issue("error", fname, "<file>", "file",
                         f"Could not load {vocab_path}")
        return vocab_index

    if not isinstance(data, list):
        result.add_issue("error", fname, "<file>", "file",
                         "Top-level must be a JSON array")
        return vocab_index

    seen_ids:   dict[str, int] = {}    # id -> first position
    day_words:  dict[tuple[int, str], int] = {}  # (day, word) -> first position

    modified = False

    for idx, raw_entry in enumerate(data):
        result.total += 1
        if not isinstance(raw_entry, dict):
            result.add_issue("error", fname, f"<index {idx}>", "type",
                             "Item is not a JSON object")
            continue

        entry = validate_vocab_entry(raw_entry, fname, result, fix)
        if fix and entry is not raw_entry:
            modified = True

        eid = entry.get("id", "")
        if eid:
            if eid in seen_ids:
                result.add_issue("error", fname, eid, "id",
                                 f"Duplicate ID (first at index {seen_ids[eid]})")
            else:
                seen_ids[eid] = idx
                vocab_index[eid] = entry

        day  = entry.get("day")
        word = entry.get("word", "").lower().strip()
        if isinstance(day, int) and word:
            key = (day, word)
            if key in day_words:
                result.add_issue("warning", fname, eid, "word",
                                 f"Duplicate word '{word}' within day {day} "
                                 f"(first at index {day_words[key]})")
            else:
                day_words[key] = idx

        result.valid += 1

    if fix and modified:
        save_json(vocab_path, data)
        if verbose:
            print(yellow(f"  [FIX] Wrote {vocab_path}"))

    return vocab_index


# ── Mapping validation ────────────────────────────────────────────────────────

def validate_mapping(
    mapping_path: Path,
    question_index: dict[str, dict],
    vocab_index: dict[str, dict],
    result: ValidationResult,
    verbose: bool,
) -> None:
    fname = mapping_path.name
    data  = load_json(mapping_path)

    if data is None:
        result.add_issue("error", fname, "<file>", "file",
                         f"Could not load {mapping_path}")
        return

    entries = data if isinstance(data, list) else (
        list(data.values()) if isinstance(data, dict) else None
    )
    if entries is None:
        result.add_issue("error", fname, "<file>", "file",
                         "Top-level must be a JSON array or object")
        return

    for entry in entries:
        result.total += 1
        if not isinstance(entry, dict):
            result.add_issue("error", fname, "<item>", "type",
                             "Mapping entry is not a JSON object")
            continue

        eid = entry.get("vocab_id", entry.get("word", "<unknown>"))

        def err(f: str, msg: str)  -> None: result.add_issue("error",   fname, str(eid), f, msg)
        def warn(f: str, msg: str) -> None: result.add_issue("warning", fname, str(eid), f, msg)

        required = ["word", "vocab_id", "occurrences", "total_count"]
        for req in required:
            if req not in entry:
                err(req, f"Required field '{req}' is missing")

        # vocab_id must exist
        vid = entry.get("vocab_id")
        if vid and vocab_index and vid not in vocab_index:
            err("vocab_id", f"vocab_id {vid!r} not found in vocabulary")

        # total_count == len(occurrences)
        occs = entry.get("occurrences")
        tc   = entry.get("total_count")
        if isinstance(occs, list) and isinstance(tc, int):
            if tc != len(occs):
                err("total_count",
                    f"total_count={tc} but len(occurrences)={len(occs)}")
        elif occs is not None and not isinstance(occs, list):
            err("occurrences", "Must be a list")

        # each occurrence's question_id must exist
        if isinstance(occs, list):
            for i, occ in enumerate(occs):
                if not isinstance(occ, dict):
                    err("occurrences", f"Occurrence [{i}] is not a dict")
                    continue
                qid = occ.get("question_id")
                if qid and question_index and qid not in question_index:
                    warn("occurrences",
                         f"Occurrence [{i}] question_id {qid!r} not found in questions")

        result.valid += 1


# ── Summary output ────────────────────────────────────────────────────────────

def print_result(res: ValidationResult, verbose: bool) -> None:
    status = green("PASS") if res.ok() else red("FAIL")
    print(
        f"  {bold(res.target.upper()):<20s}  "
        f"total={cyan(str(res.total))}  "
        f"valid={green(str(res.valid))}  "
        f"warnings={yellow(str(res.warnings))}  "
        f"errors={red(str(res.errors))}  "
        f"[{status}]"
    )
    if res.fixed:
        print(f"    {yellow(f'Auto-fixed {res.fixed} item(s)')}")

    if verbose or res.errors > 0:
        for issue in res.issues:
            if verbose or issue.severity == "error":
                print(str(issue))


def print_summary(results: list[ValidationResult]) -> None:
    total   = sum(r.total    for r in results)
    valid   = sum(r.valid    for r in results)
    warns   = sum(r.warnings for r in results)
    errors  = sum(r.errors   for r in results)
    overall = green("ALL PASS") if errors == 0 else red("ERRORS FOUND")

    print()
    print(bold("=" * 60))
    print(bold("  VALIDATION SUMMARY"))
    print(bold("=" * 60))
    for res in results:
        print_result(res, verbose=False)
    print(bold("-" * 60))
    print(
        f"  {'TOTAL':<20s}  "
        f"total={cyan(str(total))}  "
        f"valid={green(str(valid))}  "
        f"warnings={yellow(str(warns))}  "
        f"errors={red(str(errors))}  "
        f"[{overall}]"
    )
    print(bold("=" * 60))


# ── Main entry point ──────────────────────────────────────────────────────────

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Validate Toeic Brain extracted JSON data"
    )
    p.add_argument("--questions", action="store_true",
                   help="Validate question files only")
    p.add_argument("--vocab", action="store_true",
                   help="Validate vocabulary file only")
    p.add_argument("--verbose", "-v", action="store_true",
                   help="Show all details including warnings")
    p.add_argument("--fix", action="store_true",
                   help="Auto-fix minor issues (trim whitespace, normalise blanks)")
    return p


def main() -> int:
    parser = build_arg_parser()
    args   = parser.parse_args()

    # If no target flag supplied, validate everything
    run_questions = args.questions or not args.vocab
    run_vocab     = args.vocab     or not args.questions

    # Resolve project root relative to this script
    script_dir   = Path(__file__).resolve().parent
    project_root = script_dir.parent.parent  # scripts/process/ -> project root

    # Try to load config for path overrides
    config_path = project_root / "config.yaml"
    json_dir = project_root / "data" / "json"

    questions_dir = json_dir / "questions"
    vocab_path    = json_dir / "hackers_vocab.json"

    print(bold(f"\nToeic Brain — Data Validator"))
    print(f"  Project root : {project_root}")
    print(f"  Questions    : {questions_dir}")
    print(f"  Vocab        : {vocab_path}")
    print()

    all_results: list[ValidationResult] = []
    question_index: dict[str, dict] = {}
    vocab_index:    dict[str, dict] = {}

    # ── Questions ──────────────────────────────────────────────────────────────
    if run_questions:
        qfiles = sorted(questions_dir.glob("vol*_part5.json")) if questions_dir.exists() else []
        res_q  = ValidationResult(target="questions")

        if not qfiles:
            print(yellow("  [WARN] No question files found matching vol*_part5.json"))
            res_q.add_issue("warning", str(questions_dir), "<dir>", "files",
                            "No question files found")
        else:
            if args.verbose:
                print(f"  Question files: {[f.name for f in qfiles]}")
            question_index = validate_questions(qfiles, res_q, args.fix, args.verbose)

        all_results.append(res_q)

        if args.verbose:
            print(f"\n{bold('Question issues:')}")
            for issue in res_q.issues:
                print(str(issue))

    # ── Vocabulary ─────────────────────────────────────────────────────────────
    if run_vocab:
        res_v = ValidationResult(target="vocab")

        if not vocab_path.exists():
            print(yellow(f"  [WARN] Vocab file not found: {vocab_path}"))
            res_v.add_issue("warning", vocab_path.name, "<file>", "file",
                            "Vocab file not found")
        else:
            vocab_index = validate_vocab(vocab_path, res_v, args.fix, args.verbose)

        all_results.append(res_v)

        if args.verbose:
            print(f"\n{bold('Vocab issues:')}")
            for issue in res_v.issues:
                print(str(issue))

    if not all_results:
        print(yellow("  Nothing to validate."))
        return 0

    print_summary(all_results)

    has_errors = any(not r.ok() for r in all_results)
    return 1 if has_errors else 0


if __name__ == "__main__":
    sys.exit(main())
