"""
품사(POS) 교정 스크립트
LLM을 사용해 각 단어의 올바른 품사를 판단하고 JSON 파일을 업데이트한다.
하나의 단어가 여러 품사를 가질 수 있으므로 pos를 리스트로 변환한다.
"""

import json
import glob
import os
import asyncio
import re
from pathlib import Path
import anthropic

BASE_DIR = Path(__file__).resolve().parent.parent.parent
VOCAB_DIR = BASE_DIR / "data" / "json"
BATCH_SIZE = 50
MAX_CONCURRENT = 8

client = anthropic.Anthropic()


def load_all_vocab() -> tuple[dict[str, list], list[dict]]:
    """hackers_vocab.json에서 전체 단어 목록 로드."""
    vocab_path = VOCAB_DIR / "hackers_vocab.json"
    file_map: dict[str, list] = {}
    all_words: list[dict] = []
    if vocab_path.exists():
        with open(vocab_path, encoding="utf-8") as f:
            all_words = json.load(f)
        file_map[str(vocab_path)] = all_words
    return file_map, all_words


def build_batches(all_words: list[dict], batch_size: int) -> list[list[dict]]:
    return [all_words[i:i+batch_size] for i in range(0, len(all_words), batch_size)]


SYSTEM_PROMPT = """You are an English vocabulary expert for TOEIC learners.
Given a list of English words with their Korean meanings, determine the correct part(s) of speech for each word.

Rules:
- A word can have MULTIPLE parts of speech (e.g., "demand" → ["noun", "verb"])
- Use ONLY these pos values: noun, verb, adjective, adverb, preposition, conjunction
- Base your judgment on the WORD itself AND the Korean meaning provided
- For words that are commonly used as multiple parts of speech in TOEIC, list all applicable ones
- Return ONLY a JSON array, no explanation

Examples:
Input word "demand", meaning "수요, 요구하다" → ["noun", "verb"]
Input word "resume", meaning "이력서, 재개하다" → ["noun", "verb"]
Input word "conduct", meaning "행동, 수행하다" → ["noun", "verb"]
Input word "quickly", meaning "빠르게" → ["adverb"]
Input word "require", meaning "요구하다" → ["verb"]
"""


def build_prompt(batch: list[dict]) -> str:
    lines = []
    for w in batch:
        lines.append(f'- id: {w["id"]}, word: "{w["word"]}", meaning: "{w["meaning_kr"]}"')
    return (
        "Determine the correct part(s) of speech for each word below.\n"
        "Return a JSON object mapping each id to a list of pos values.\n"
        "Example response format: {\"hw_0001\": [\"noun\", \"verb\"], \"hw_0002\": [\"noun\"]}\n\n"
        + "\n".join(lines)
    )


async def process_batch(semaphore: asyncio.Semaphore, batch: list[dict], batch_idx: int) -> dict[str, list[str]]:
    """단일 배치를 LLM으로 처리하고 id→pos_list 매핑 반환."""
    async with semaphore:
        loop = asyncio.get_event_loop()
        prompt = build_prompt(batch)

        def call_api():
            return client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

        response = await loop.run_in_executor(None, call_api)
        text = response.content[0].text.strip()

        # JSON 파싱 — 코드블록 제거
        text = re.sub(r"```(?:json)?\s*", "", text).strip("`").strip()
        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            # JSON 블록만 추출 시도
            m = re.search(r"\{[^{}]+\}", text, re.DOTALL)
            if m:
                result = json.loads(m.group())
            else:
                print(f"  [배치 {batch_idx}] JSON 파싱 실패:\n{text[:300]}")
                result = {}

        print(f"  [배치 {batch_idx}] {len(batch)}개 처리 완료 → {len(result)}개 응답")
        return result


async def run_all_batches(batches: list[list[dict]]) -> dict[str, list[str]]:
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    tasks = [
        process_batch(semaphore, batch, i + 1)
        for i, batch in enumerate(batches)
    ]
    results = await asyncio.gather(*tasks)
    merged: dict[str, list[str]] = {}
    for r in results:
        merged.update(r)
    return merged


def normalize_pos(pos_value) -> list[str]:
    """현재 pos 값을 리스트로 정규화."""
    valid = {"noun", "verb", "adjective", "adverb", "preposition", "conjunction"}
    if isinstance(pos_value, list):
        return [p for p in pos_value if p in valid]
    if isinstance(pos_value, str):
        parts = [p.strip() for p in re.split(r"[/,]", pos_value)]
        return [p for p in parts if p in valid]
    return []


def apply_corrections(file_map: dict[str, list], corrections: dict[str, list[str]]) -> dict[str, int]:
    """교정 결과를 file_map에 반영하고 변경 건수 반환."""
    stats = {"updated": 0, "unchanged": 0, "not_found": 0}
    for path, words in file_map.items():
        for word in words:
            wid = word["id"]
            if wid not in corrections:
                stats["not_found"] += 1
                continue
            new_pos = corrections[wid]
            old_pos = normalize_pos(word.get("pos", ""))
            if set(new_pos) != set(old_pos):
                word["pos"] = new_pos
                stats["updated"] += 1
            else:
                # 기존 단일 문자열을 리스트로 통일
                word["pos"] = new_pos
                stats["unchanged"] += 1
    return stats


def save_files(file_map: dict[str, list]) -> None:
    for path, words in file_map.items():
        with open(path, "w", encoding="utf-8") as f:
            json.dump(words, f, ensure_ascii=False, indent=2)
    print(f"  {len(file_map)}개 파일 저장 완료")


async def main():
    print("=== POS 교정 시작 ===")
    print(f"배치 크기: {BATCH_SIZE}, 최대 동시 요청: {MAX_CONCURRENT}")

    file_map, all_words = load_all_vocab()
    print(f"총 단어: {len(all_words)}개, 파일: {len(file_map)}개")

    batches = build_batches(all_words, BATCH_SIZE)
    print(f"배치 수: {len(batches)}")

    print("\n[LLM 처리 중...]")
    corrections = await run_all_batches(batches)
    print(f"\n총 {len(corrections)}개 단어 응답 수신")

    stats = apply_corrections(file_map, corrections)
    print(f"\n[결과] 변경: {stats['updated']}개, 유지: {stats['unchanged']}개, 미응답: {stats['not_found']}개")

    save_files(file_map)
    print("\n=== 완료 ===")


if __name__ == "__main__":
    asyncio.run(main())
