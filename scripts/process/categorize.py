"""
Part5 문제를 유형별로 자동 분류한다.
카테고리: 품사, 동사시제/태, 접속사/전치사, 관계대명사, 어휘, 대명사, 비교급/최상급, 기타문법
"""

import sys
import json
import argparse
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

# ── word sets ──────────────────────────────────────────────────────────────────

PRONOUNS = {
    "i", "me", "my", "mine", "myself",
    "you", "your", "yours", "yourself", "yourselves",
    "he", "him", "his", "himself",
    "she", "her", "hers", "herself",
    "it", "its", "itself",
    "we", "us", "our", "ours", "ourselves",
    "they", "them", "their", "theirs", "themselves",
}

RELATIVE_PRONOUNS = {"who", "whom", "whose", "which", "that", "whoever",
                     "whomever", "whichever", "whatever"}

PREPOSITIONS = {
    "about", "above", "across", "after", "against", "along", "amid", "among",
    "around", "as", "at", "before", "behind", "below", "beneath", "beside",
    "besides", "between", "beyond", "by", "concerning", "despite", "down",
    "during", "except", "for", "from", "in", "inside", "into", "like",
    "near", "of", "off", "on", "onto", "out", "outside", "over", "past",
    "regarding", "since", "through", "throughout", "till", "to", "toward",
    "towards", "under", "underneath", "until", "up", "upon", "via",
    "with", "within", "without",
}

CONJUNCTIONS = {
    "although", "because", "since", "unless", "until", "whereas", "while",
    "though", "even", "if", "when", "whenever", "where", "wherever",
    "after", "before", "once", "so", "yet", "but", "and", "or", "nor",
    "however", "therefore", "furthermore", "moreover", "nevertheless",
    "nonetheless", "consequently", "accordingly", "thus", "hence",
    "provided", "given", "assuming", "whether", "both", "either", "neither",
}

TENSE_AUXILIARIES = {
    "was", "were", "is", "are", "am",
    "has", "have", "had",
    "will", "would", "shall", "should",
    "can", "could", "may", "might", "must",
    "be", "been", "being",
}

COMPARATIVE_MARKERS = {"more", "most", "less", "least", "better", "best",
                       "worse", "worst", "further", "furthest", "farther",
                       "farthest", "higher", "lower", "greater", "lesser"}

COMPARATIVE_SUFFIXES = ("er", "est")


# ── helpers ───────────────────────────────────────────────────────────────────

def normalize(word: str) -> str:
    return word.strip().lower().rstrip(".,;:")


def choices_list(choices: dict) -> list[str]:
    return [normalize(v) for v in choices.values()]


def longest_common_prefix(words: list[str]) -> str:
    if not words:
        return ""
    prefix = words[0]
    for w in words[1:]:
        while not w.startswith(prefix):
            prefix = prefix[:-1]
            if not prefix:
                return ""
    return prefix


def count_prefix_sharers(words: list[str], min_len: int = 4) -> int:
    """Return how many words share a common prefix of at least min_len chars with any other word."""
    sharers = set()
    for i, a in enumerate(words):
        for j, b in enumerate(words):
            if i != j:
                lcp = longest_common_prefix([a, b])
                if len(lcp) >= min_len:
                    sharers.add(i)
                    sharers.add(j)
    return len(sharers)


def has_tense_pattern(words: list[str]) -> bool:
    """Detect tense/voice: at least 2 choices contain an auxiliary or a past-tense marker."""
    hits = 0
    for w in words:
        tokens = w.split()
        if any(t in TENSE_AUXILIARIES for t in tokens) or (
            len(tokens) == 1 and (w.endswith("ed") or w.endswith("ing"))
        ):
            hits += 1
    return hits >= 2


def all_in_set(words: list[str], word_set: set) -> bool:
    return all(w in word_set for w in words)


def majority_in_set(words: list[str], word_set: set, threshold: float = 0.75) -> bool:
    return sum(1 for w in words if w in word_set) / len(words) >= threshold


def has_comparative(words: list[str]) -> bool:
    for w in words:
        tokens = w.split()
        if any(t in COMPARATIVE_MARKERS for t in tokens):
            return True
        # single word ending in -er / -est (len > 4 to avoid 'her', 'her', 'set' etc.)
        if len(w) > 4 and (w.endswith("er") or w.endswith("est")):
            return True
    return False


# ── main classifier ───────────────────────────────────────────────────────────

def classify(question: dict) -> str:
    choices = choices_list(question.get("choices", {}))
    if len(choices) < 2:
        return "기타문법"

    # 1. 대명사
    if majority_in_set(choices, PRONOUNS, 0.75):
        return "대명사"

    # 2. 관계대명사
    if majority_in_set(choices, RELATIVE_PRONOUNS, 0.5) and len(choices) >= 3:
        if sum(1 for c in choices if c in RELATIVE_PRONOUNS) >= 2:
            return "관계대명사"

    # 3. 접속사/전치사
    prep_conj = PREPOSITIONS | CONJUNCTIONS
    if majority_in_set(choices, prep_conj, 0.75):
        return "접속사/전치사"

    # 4. 비교급/최상급
    if has_comparative(choices):
        return "비교급/최상급"

    # 5. 품사 — 3+ choices share a common root prefix of >= 4 chars
    sharers = count_prefix_sharers(choices, min_len=4)
    if sharers >= 3:
        return "품사"

    # 6. 동사시제/태
    if has_tense_pattern(choices):
        return "동사시제/태"

    # 7. 어휘 — no obvious grammar pattern, different roots
    return "어휘"


# ── I/O helpers ───────────────────────────────────────────────────────────────

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "json" / "questions"

CATEGORIES = [
    "품사", "동사시제/태", "접속사/전치사", "관계대명사",
    "어휘", "대명사", "비교급/최상급", "기타문법",
]


def process_file(path: Path, dry_run: bool) -> dict:
    """Classify all questions in one file. Returns {category: count}."""
    try:
        with open(path, encoding="utf-8") as f:
            questions = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"  [WARN] Cannot read {path.name}: {e}")
        return {}

    counts: dict[str, int] = {}
    for q in questions:
        if q.get("part") != 5:
            continue
        cat = classify(q)
        q["category"] = cat
        counts[cat] = counts.get(cat, 0) + 1

    if not dry_run:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(questions, f, ensure_ascii=False, indent=2)
        print(f"  Updated {path.name}  ({sum(counts.values())} questions)")
    else:
        print(f"  [dry-run] {path.name}  ({sum(counts.values())} questions)")

    return counts


def merge_counts(a: dict, b: dict) -> dict:
    merged = dict(a)
    for k, v in b.items():
        merged[k] = merged.get(k, 0) + v
    return merged


def print_distribution(totals: dict, label: str = "TOTAL"):
    grand = sum(totals.values()) or 1
    print(f"\n{'─'*40}")
    print(f"  {label}  ({grand} questions)")
    print(f"{'─'*40}")
    for cat in CATEGORIES:
        n = totals.get(cat, 0)
        bar = "█" * (n * 30 // grand)
        print(f"  {cat:<14} {n:>4}  {n/grand*100:5.1f}%  {bar}")
    print(f"{'─'*40}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Auto-classify Part5 questions by category")
    parser.add_argument("--volume", type=int, help="Process a specific volume (1-5)")
    parser.add_argument("--dry-run", action="store_true", help="Show categories without modifying files")
    args = parser.parse_args()

    if not DATA_DIR.exists():
        print(f"[ERROR] Data directory not found: {DATA_DIR}")
        sys.exit(1)

    if args.volume:
        pattern = f"vol{args.volume}_part5.json"
        files = sorted(DATA_DIR.glob(pattern))
        if not files:
            print(f"[ERROR] No file matching {pattern} in {DATA_DIR}")
            sys.exit(1)
    else:
        files = sorted(DATA_DIR.glob("vol*_part5.json"))

    if not files:
        print("[ERROR] No Part5 JSON files found.")
        sys.exit(1)

    print(f"{'[DRY-RUN] ' if args.dry_run else ''}Processing {len(files)} file(s)...\n")

    totals: dict[str, int] = {}
    for path in files:
        counts = process_file(path, dry_run=args.dry_run)
        totals = merge_counts(totals, counts)

    print_distribution(totals)


if __name__ == "__main__":
    main()
