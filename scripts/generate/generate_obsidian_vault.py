"""
Obsidian Atomic Vocab MD 파일을 생성한다.
chapter_map.json + word_ets_examples.json → vault/ 디렉토리
"""

import sys
import json
import re
import argparse
import logging
from pathlib import Path
from collections import defaultdict

# Windows UTF-8 fix
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Paths
DEFAULT_CHAPTER_MAP = PROJECT_ROOT / "data" / "processed" / "vocab" / "chapter_map.json"
DEFAULT_EXAMPLES = PROJECT_ROOT / "data" / "mapped" / "word_ets_examples.json"
DEFAULT_VAULT_DIR = PROJECT_ROOT / "vault"

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# POS abbreviation map for tags
# ---------------------------------------------------------------------------
POS_TAG_MAP = {
    "noun": "noun",
    "verb": "verb",
    "adjective": "adj",
    "adverb": "adv",
    "preposition": "prep",
    "conjunction": "conj",
}


def sanitize_filename(word: str) -> str:
    """Windows에서 사용 불가능한 문자를 제거/치환하여 파일명을 생성한다."""
    # Remove characters invalid in Windows filenames: < > : " / \ | ? *
    sanitized = re.sub(r'[<>:"/\\|?*]', "_", word.strip())
    # Also strip leading/trailing dots and spaces (Windows restriction)
    sanitized = sanitized.strip(". ")
    return sanitized.lower()


def _pos_tag(pos: str) -> str:
    """품사 문자열을 태그용 약어로 변환한다."""
    return POS_TAG_MAP.get(pos.lower(), pos.lower()) if pos else "unknown"


def generate_frontmatter(
    word_entry: dict,
    chapter: dict,
    ets_count: int,
    parts_appeared: list[int],
) -> str:
    """YAML frontmatter 블록을 문자열로 생성한다."""
    word = word_entry["word"]
    pos = word_entry.get("pos", "")
    meaning = word_entry.get("meaning_kr", "")
    ch_num = chapter["chapter"]
    ch_title = chapter["title"]
    pos_short = _pos_tag(pos)

    parts = parts_appeared if parts_appeared else [5, 6, 7]

    tags = [
        "toeic/vocab",
        f"toeic/ch{ch_num:02d}",
        f"toeic/{pos_short}",
        "toeic/900",
    ]

    lines = [
        "---",
        f"word: {word}",
        f"pos: {pos}",
        f"meaning: {meaning}",
        f"chapter: {ch_num}",
        f"chapter_title: {ch_title}",
        "level: 900점 완성",
        f"part: {json.dumps(sorted(set(parts)))}",
        f"ets_count: {ets_count}",
        "tags:",
    ]
    for tag in tags:
        lines.append(f"  - {tag}")
    lines.append("---")
    return "\n".join(lines)


def generate_heading(word_entry: dict) -> str:
    """단어 제목 + 뜻 블록을 생성한다."""
    word = word_entry["word"]
    pos = word_entry.get("pos", "")
    meaning = word_entry.get("meaning_kr", "")
    return f"# {word}\n\n> **{meaning}** ({pos})"


def generate_ets_section(examples: list[dict]) -> str:
    """기출 예문 섹션을 볼륨별로 그룹화하여 생성한다."""
    if not examples:
        return ""

    # Group by volume
    by_volume: dict[int, list[dict]] = defaultdict(list)
    for ex in examples:
        vol = ex.get("volume", 0)
        by_volume[vol].append(ex)

    parts = []
    parts.append("## 기출 예문")

    for vol in sorted(by_volume.keys()):
        parts.append("")
        parts.append(f"### Vol {vol}")

        vol_examples = by_volume[vol]
        for i, ex in enumerate(vol_examples):
            sentence = ex.get("sentence", "")
            source = ex.get("source", "")
            parts.append("")
            parts.append(f"> {sentence}")
            parts.append(f"> — *{source}*")

    return "\n".join(parts)


def generate_related_section(word_entry: dict) -> str:
    """관련어 섹션을 생성한다."""
    related = word_entry.get("related_words", [])
    if not related:
        return ""

    lines = ["## 관련어", ""]
    for rw in related:
        # related_words is a list of strings; we don't have POS/meaning info
        lines.append(f"- **{rw}**")
    return "\n".join(lines)


def generate_book_example_section(word_entry: dict) -> str:
    """노랭이 예문 섹션을 생성한다."""
    sentence = word_entry.get("example_sentence", "")
    translation = word_entry.get("example_translation", "")
    if not sentence:
        return ""

    lines = ["## 노랭이 예문", ""]
    lines.append(f"> {sentence}")
    if translation:
        lines.append(f"> {translation}")
    return "\n".join(lines)


def generate_word_md(
    word_entry: dict,
    chapter: dict,
    examples: dict | None,
) -> str:
    """단어 하나에 대한 전체 마크다운 문서를 생성한다."""
    # ETS info
    ets_examples = []
    ets_count = 0
    parts_appeared = [5, 6, 7]

    if examples:
        ets_examples = examples.get("examples", [])
        ets_count = examples.get("total_count", len(ets_examples))
        if examples.get("parts_appeared"):
            parts_appeared = examples["parts_appeared"]

    sections = []

    # Frontmatter
    sections.append(
        generate_frontmatter(word_entry, chapter, ets_count, parts_appeared)
    )

    # Heading
    sections.append(generate_heading(word_entry))

    # ETS examples
    ets_sec = generate_ets_section(ets_examples)
    if ets_sec:
        sections.append(ets_sec)

    # Related words
    related_sec = generate_related_section(word_entry)
    if related_sec:
        sections.append(related_sec)

    # Book example
    book_sec = generate_book_example_section(word_entry)
    if book_sec:
        sections.append(book_sec)

    return "\n\n".join(sections) + "\n"


def generate_vault(
    chapter_map: list[dict],
    word_examples: dict,
    vault_dir: Path,
) -> dict:
    """vault/ 디렉토리에 Obsidian MD 파일을 생성하고 통계를 반환한다."""
    stats = {
        "total_files": 0,
        "per_chapter": {},
        "skipped": 0,
        "chapters": 0,
    }

    for chapter in chapter_map:
        ch_num = chapter["chapter"]
        ch_title = chapter.get("title") or ""
        dir_name = f"ch {ch_num:02d}. {ch_title}" if ch_title else f"ch {ch_num:02d}"
        level_dir = vault_dir / dir_name / "900점 완성"
        level_dir.mkdir(parents=True, exist_ok=True)

        ch_count = 0
        seen_filenames: dict[str, int] = {}

        for word_entry in chapter.get("words", []):
            word = word_entry.get("word", "")
            if not word:
                stats["skipped"] += 1
                continue

            # Look up ETS examples
            examples = word_examples.get(word.lower())

            # Generate filename (handle duplicates within same chapter)
            base_name = sanitize_filename(word)
            if base_name in seen_filenames:
                seen_filenames[base_name] += 1
                filename = f"{base_name}_{seen_filenames[base_name]}.md"
            else:
                seen_filenames[base_name] = 1
                filename = f"{base_name}.md"

            # Generate content
            content = generate_word_md(word_entry, chapter, examples)

            # Write file
            filepath = level_dir / filename
            filepath.write_text(content, encoding="utf-8", newline="\n")
            ch_count += 1
            logger.debug("생성: %s", filepath)

        stats["per_chapter"][ch_num] = ch_count
        stats["total_files"] += ch_count
        stats["chapters"] += 1
        logger.info("ch %02d. %s — %d 파일 생성", ch_num, ch_title, ch_count)

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Obsidian Atomic Vocab MD 파일을 생성한다."
    )
    parser.add_argument(
        "--chapter-map",
        type=Path,
        default=DEFAULT_CHAPTER_MAP,
        help="chapter_map.json 경로",
    )
    parser.add_argument(
        "--examples",
        type=Path,
        default=DEFAULT_EXAMPLES,
        help="word_ets_examples.json 경로",
    )
    parser.add_argument(
        "--vault-dir",
        type=Path,
        default=DEFAULT_VAULT_DIR,
        help="출력 vault 디렉토리 경로",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="상세 로그 출력",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    # Load chapter map
    logger.info("chapter_map 로드: %s", args.chapter_map)
    if not args.chapter_map.exists():
        logger.error("chapter_map.json을 찾을 수 없습니다: %s", args.chapter_map)
        sys.exit(1)
    with open(args.chapter_map, encoding="utf-8") as f:
        chapter_map = json.load(f)

    # Load ETS examples
    logger.info("word_ets_examples 로드: %s", args.examples)
    if not args.examples.exists():
        logger.error("word_ets_examples.json을 찾을 수 없습니다: %s", args.examples)
        sys.exit(1)
    with open(args.examples, encoding="utf-8") as f:
        word_examples = json.load(f)

    # Generate vault
    logger.info("vault 생성 시작: %s", args.vault_dir)
    stats = generate_vault(chapter_map, word_examples, args.vault_dir)

    # Summary
    print()
    print("=" * 50)
    print("Obsidian Vault 생성 완료")
    print("=" * 50)
    print(f"총 챕터 수: {stats['chapters']}")
    print(f"총 파일 수: {stats['total_files']}")
    if stats["skipped"]:
        print(f"스킵된 항목: {stats['skipped']}")
    print()
    print("챕터별 파일 수:")
    for ch_num in sorted(stats["per_chapter"]):
        count = stats["per_chapter"][ch_num]
        print(f"  ch {ch_num:02d}: {count} 파일")


if __name__ == "__main__":
    main()
