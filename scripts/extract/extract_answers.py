"""
ETS 정답 및 해설 PDF에서 정답과 해설을 추출하여 기존 JSON에 반영하는 스크립트.
Google Vision API를 사용하여 OCR을 수행한다.

Usage:
    py -3 scripts/extract/extract_answers.py --vol 4
    py -3 scripts/extract/extract_answers.py --vol 1 2 3 4 5
"""

import json
import re
import sys
import io
import os
import argparse
import logging
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

import pymupdf

BASE_DIR = Path(__file__).resolve().parent.parent.parent
RAW_DIR = BASE_DIR / "data" / "raw" / "answer"
QUESTIONS_DIR = BASE_DIR / "data" / "processed" / "questions"
CACHE_DIR = BASE_DIR / "data" / "raw" / "answer" / "ocr_cache"

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(
    BASE_DIR / ".secret" / "key.json"
)

# OCR 오류 보정: (8) -> B, (0) -> D 등
OCR_ANSWER_MAP = {
    "8": "B",
    "0": "D",
    "}": "",
    "{": "",
    "|": "",
    "l": "",
}


def fix_ocr_answer(raw: str) -> str:
    """OCR 인식 오류를 보정하여 A/B/C/D 중 하나로 변환."""
    raw = raw.strip()
    for bad, good in OCR_ANSWER_MAP.items():
        raw = raw.replace(bad, good)
    raw = raw.strip()
    if raw in ("A", "B", "C", "D"):
        return raw
    return raw


def extract_answer_key(page_text: str) -> dict[int, str]:
    """정답표 페이지에서 {문항번호: 정답} 딕셔너리를 추출 (garbled text OK)."""
    answers = {}
    page_text = re.sub(r"(\d{2})\s(\d)\s*\(", r"\1\2 (", page_text)
    for match in re.finditer(r"(\d{3})\s*\(([A-D08}{|l]+)\)?", page_text):
        q_num = int(match.group(1))
        raw_answer = match.group(2)
        answer = fix_ocr_answer(raw_answer)
        answers[q_num] = answer
    return answers


def _get_page_text(doc: pymupdf.Document, page_idx: int, vol_cache: Path) -> str:
    """PDF 페이지의 텍스트를 가져옴. OCR 캐시가 있으면 캐시 우선 사용."""
    cache_file = vol_cache / f"page_{page_idx + 1:04d}.txt"
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8")
    return doc[page_idx].get_text()


def find_test_structure(
    doc: pymupdf.Document, vol_cache: Path
) -> list[dict]:
    """PDF의 각 테스트 구조를 파악: 정답표 페이지, Part5/6/7 해설 범위."""
    tests = []
    for page_idx in range(len(doc)):
        text = doc[page_idx].get_text()
        answers = extract_answer_key(text)
        if len(answers) >= 50:
            tests.append({
                "answer_page": page_idx,
                "answers": answers,
                "part5_pages": [],
                "part6_pages": [],
                "part7_pages": [],
            })

    # 각 테스트의 Part5/6/7 해설 페이지 범위 결정
    for i, test in enumerate(tests):
        start = test["answer_page"]
        end = tests[i + 1]["answer_page"] if i + 1 < len(tests) else len(doc)

        part5_start = None
        part6_start = None
        part7_start = None

        for page_idx in range(start, end):
            # garbled text layer와 OCR 캐시 모두 확인
            text = _get_page_text(doc, page_idx, vol_cache)
            if re.search(r"PART\s*[5S]\b|PARTS\b|Part\s*5\b", text) and part5_start is None:
                part5_start = page_idx
            if re.search(r"PART\s*6\b|Part\s*6\b", text) and part6_start is None:
                part6_start = page_idx
            if re.search(r"PART\s*7\b|Part\s*7\b", text) and part7_start is None:
                part7_start = page_idx

        # Part5 pages: from part5_start to part6_start INCLUSIVE
        # (Part5 마지막 문제들이 Part6 시작 페이지에 포함될 수 있음)
        if part5_start is not None:
            if part6_start is not None:
                p5_end = part6_start + 1  # Part6 시작 페이지 포함
            elif part7_start is not None:
                p5_end = part7_start + 1
            else:
                p5_end = end
            test["part5_pages"] = list(range(part5_start, p5_end))

        if part6_start is not None:
            p6_end = (part7_start + 1) if part7_start else end
            test["part6_pages"] = list(range(part6_start, p6_end))

        if part7_start is not None:
            test["part7_pages"] = list(range(part7_start, end))

    return tests


def _get_vision_client():
    """Google Vision API 클라이언트 싱글톤."""
    if not hasattr(_get_vision_client, "_client"):
        from google.cloud import vision
        _get_vision_client._client = vision.ImageAnnotatorClient()
    return _get_vision_client._client


def ocr_page_vision(page: pymupdf.Page, cache_path: Path | None = None) -> str:
    """Google Vision API로 PDF 페이지를 OCR. 2단 레이아웃을 좌우 분할하여 처리."""
    if cache_path and cache_path.exists():
        return cache_path.read_text(encoding="utf-8")

    from google.cloud import vision
    from PIL import Image as PILImage

    client = _get_vision_client()

    matrix = pymupdf.Matrix(2.0, 2.0)  # 144 DPI
    pixmap = page.get_pixmap(matrix=matrix, alpha=False)
    img = PILImage.open(io.BytesIO(pixmap.tobytes("png")))

    w, h = img.size
    mid = w // 2

    texts = []
    for crop_box in [(0, 0, mid, h), (mid, 0, w, h)]:
        half = img.crop(crop_box)
        buf = io.BytesIO()
        half.save(buf, format="PNG")
        image = vision.Image(content=buf.getvalue())
        response = client.text_detection(image=image)
        t = response.full_text_annotation.text if response.full_text_annotation else ""
        texts.append(t)

    text = texts[0] + "\n" + texts[1]

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(text, encoding="utf-8")

    return text


def parse_part5_explanations(full_text: str) -> dict[int, dict]:
    """Part5 해설 텍스트를 파싱하여 {문항번호: {category, explanation}} 반환."""
    explanations = {}

    # 문항 패턴: "101 대명사 자리" or "101 대명사" 등
    # Split by question numbers
    q_pattern = re.compile(r"(?:^|\n)(\d{3})\s+(.+?)(?=\n\d{3}\s|\Z)", re.DOTALL)
    matches = list(q_pattern.finditer(full_text))

    if not matches:
        # Try alternative pattern
        q_pattern2 = re.compile(r"(\d{3})\s+(.*?)(?=\d{3}\s+[가-힣]|\Z)", re.DOTALL)
        matches = list(q_pattern2.finditer(full_text))

    for match in matches:
        q_num = int(match.group(1))
        if q_num < 101 or q_num > 130:
            continue

        raw_text = match.group(2).strip()
        parsed = _parse_single_explanation(raw_text)
        if parsed:
            explanations[q_num] = parsed

    return explanations


def _parse_single_explanation(raw: str) -> dict | None:
    """단일 문항 해설 텍스트를 파싱."""
    lines = raw.split("\n")

    category = ""
    explanation = ""
    translation = ""
    vocabulary = ""

    current = "category"

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Skip noise
        if re.match(r"^TEST\s*\d", line):
            continue
        if re.match(r"^동영상\s*강의", line):
            continue

        if current == "category":
            category = line
            current = "waiting"
            continue

        if line.startswith("해설"):
            current = "explanation"
            rest = line[2:].strip()
            if rest:
                explanation += rest + " "
            continue
        elif line.startswith("번역"):
            current = "translation"
            rest = line[2:].strip()
            if rest:
                translation += rest + " "
            continue
        elif line.startswith("어휘"):
            current = "vocabulary"
            rest = line[2:].strip()
            if rest:
                vocabulary += rest + " "
            continue

        if current == "explanation":
            explanation += line + " "
        elif current == "translation":
            translation += line + " "
        elif current == "vocabulary":
            vocabulary += line + " "
        elif current == "waiting":
            if line.startswith("해설"):
                current = "explanation"
                rest = line[2:].strip()
                if rest:
                    explanation += rest + " "
            else:
                category += " " + line

    # Clean up
    category = re.sub(r"\s{2,}", " ", category).strip()
    explanation = re.sub(r"\s{2,}", " ", explanation).strip()
    translation = re.sub(r"\s{2,}", " ", translation).strip()
    vocabulary = re.sub(r"\s{2,}", " ", vocabulary).strip()

    if not any([explanation, translation, vocabulary]):
        return None

    return {
        "category": category,
        "explanation": explanation,
        "translation": translation,
        "vocabulary": vocabulary,
    }


def parse_part67_explanations(full_text: str, part: int) -> dict[int, dict]:
    """Part6/7 해설 텍스트를 파싱."""
    explanations = {}

    # Part 6/7 questions: 131-146 (Part6) or 147-200 (Part7)
    q_pattern = re.compile(r"(?:^|\n)(\d{3})\s+(.+?)(?=\n\d{3}\s|\Z)", re.DOTALL)
    matches = list(q_pattern.finditer(full_text))

    for match in matches:
        q_num = int(match.group(1))
        raw_text = match.group(2).strip()

        if part == 6 and not (131 <= q_num <= 146):
            continue
        if part == 7 and not (147 <= q_num <= 200):
            continue

        parsed = _parse_single_explanation(raw_text)
        if parsed:
            explanations[q_num] = parsed

    return explanations


def process_volume(vol: int):
    """하나의 볼륨 처리."""
    pdf_path = RAW_DIR / f"ets_answer_vol{vol}.pdf"
    if not pdf_path.exists():
        logger.error(f"PDF 없음: {pdf_path}")
        return

    doc = pymupdf.open(str(pdf_path))
    logger.info(f"=== Vol {vol} ({len(doc)} pages) ===")

    vol_cache = CACHE_DIR / f"vol{vol}"
    vol_cache.mkdir(parents=True, exist_ok=True)

    # 1. PDF 구조 파악
    tests = find_test_structure(doc, vol_cache)
    logger.info(f"  {len(tests)}개 테스트 발견")

    all_answers: dict[tuple[int, int], str] = {}
    all_explanations: dict[tuple[int, int], dict] = {}

    for test_idx, test in enumerate(tests):
        test_num = test_idx + 1
        answers = test["answers"]

        for q_num, answer in answers.items():
            all_answers[(test_num, q_num)] = answer

        logger.info(
            f"  Test {test_num}: 정답 {len(answers)}개, "
            f"Part5 pages={test['part5_pages']}, "
            f"Part6 pages={test['part6_pages']}, "
            f"Part7 pages={test['part7_pages']}"
        )

        # 2. Part5 해설 OCR
        if test["part5_pages"]:
            part5_text = ""
            for page_idx in test["part5_pages"]:
                cache_file = vol_cache / f"page_{page_idx + 1:04d}.txt"
                page_text = ocr_page_vision(doc[page_idx], cache_file)
                part5_text += page_text + "\n"

            explanations = parse_part5_explanations(part5_text)
            for q_num, expl in explanations.items():
                all_explanations[(test_num, q_num)] = expl
            logger.info(f"    Part5 해설: {len(explanations)}개 추출")

        # 3. Part6 해설 OCR
        if test["part6_pages"]:
            part6_text = ""
            for page_idx in test["part6_pages"]:
                cache_file = vol_cache / f"page_{page_idx + 1:04d}.txt"
                page_text = ocr_page_vision(doc[page_idx], cache_file)
                part6_text += page_text + "\n"

            explanations = parse_part67_explanations(part6_text, part=6)
            for q_num, expl in explanations.items():
                all_explanations[(test_num, q_num)] = expl
            logger.info(f"    Part6 해설: {len(explanations)}개 추출")

        # 4. Part7 해설 OCR
        if test["part7_pages"]:
            part7_text = ""
            for page_idx in test["part7_pages"]:
                cache_file = vol_cache / f"page_{page_idx + 1:04d}.txt"
                page_text = ocr_page_vision(doc[page_idx], cache_file)
                part7_text += page_text + "\n"

            explanations = parse_part67_explanations(part7_text, part=7)
            for q_num, expl in explanations.items():
                all_explanations[(test_num, q_num)] = expl
            logger.info(f"    Part7 해설: {len(explanations)}개 추출")

    doc.close()

    # 5. JSON 파일 업데이트
    for part in [5, 6, 7]:
        json_path = QUESTIONS_DIR / f"vol{vol}_part{part}.json"
        if not json_path.exists():
            continue

        with open(json_path, "r", encoding="utf-8") as f:
            questions = json.load(f)

        updated_answer = 0
        updated_expl = 0
        updated_cat = 0

        for q in questions:
            test = q["test"]
            q_num = q.get("question_number")

            if q_num is None:
                # Part 6/7: raw_text 형태 → 정답을 딕셔너리로 저장
                if q.get("answer") is None:
                    test_answers = {
                        str(k): v for (t, k), v in all_answers.items() if t == test
                    }
                    if test_answers:
                        q["answer"] = test_answers
                        updated_answer += 1

                # Part 6/7: 해설도 딕셔너리로 저장
                test_explanations = {}
                for (t, qn), expl in all_explanations.items():
                    if t == test:
                        q_range = range(131, 147) if part == 6 else range(147, 201)
                        if qn in q_range:
                            test_explanations[str(qn)] = expl["explanation"]
                if test_explanations:
                    existing = q.get("explanation") or {}
                    if isinstance(existing, str):
                        existing = {}
                    existing.update(test_explanations)
                    q["explanation"] = existing
                    updated_expl += 1
                continue

            key = (test, q_num)

            # 정답 업데이트
            if key in all_answers:
                old = q.get("answer")
                new = all_answers[key]
                if old is None or old != new:
                    q["answer"] = new
                    updated_answer += 1

            # 해설 업데이트 (항상 최신 OCR 결과로 덮어씀)
            if key in all_explanations:
                expl_data = all_explanations[key]
                if expl_data.get("explanation"):
                    q["explanation"] = expl_data["explanation"]
                if expl_data.get("translation"):
                    q["translation"] = expl_data["translation"]
                if expl_data.get("vocabulary"):
                    q["vocabulary"] = expl_data["vocabulary"]
                if any(expl_data.get(k) for k in ("explanation", "translation", "vocabulary")):
                    updated_expl += 1
                if expl_data.get("category"):
                    q["category"] = expl_data["category"]
                    updated_cat += 1

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(questions, f, ensure_ascii=False, indent=2)

        logger.info(
            f"  vol{vol}_part{part}.json: "
            f"정답 {updated_answer}개, 해설 {updated_expl}개, "
            f"카테고리 {updated_cat}개 업데이트"
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--vol", type=int, nargs="+", default=[4, 5],
        help="처리할 볼륨 번호 (기본: 4 5)"
    )
    args = parser.parse_args()

    logger.info("ETS 정답 및 해설 추출 시작")
    logger.info(f"PDF 경로: {RAW_DIR}")
    logger.info(f"JSON 경로: {QUESTIONS_DIR}")
    logger.info(f"처리 대상: vol {args.vol}")

    for vol in args.vol:
        process_volume(vol)

    logger.info("완료!")


if __name__ == "__main__":
    main()
