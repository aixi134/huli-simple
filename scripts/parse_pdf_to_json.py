from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.config import settings
import fitz

from backend.app.services.parser_fallback import extract_with_gemma, extract_with_gemma_from_image
from backend.app.services.parser_rules import (
    ParseError,
    build_structured_output,
    extract_answer_section_text,
    extract_pages,
    extract_question_section,
    merge_questions_answers,
    parse_answers,
    parse_question,
    save_json,
    split_questions,
    validate_questions,
)


def parse_pdf_with_ocr(pdf_path: Path) -> dict[str, object]:
    doc = fitz.open(pdf_path)
    all_questions: list[dict[str, object]] = []
    for index, page in enumerate(doc, start=1):
        image_path = settings.failed_dir / f"{pdf_path.stem}.page-{index}.png"
        page.get_pixmap(matrix=fitz.Matrix(1.8, 1.8), alpha=False).save(image_path)
        parsed = extract_with_gemma_from_image(image_path)
        for item in parsed.get("questions", []):
            item["parse_method"] = "llm_fallback"
            item["source_file"] = str(pdf_path)
            item["source_page_start"] = index
            item["source_page_end"] = index
            if "number" in item:
                try:
                    item["number"] = int(item["number"])
                except (TypeError, ValueError):
                    continue
            all_questions.append(item)

    payload = build_structured_output(pdf_path, all_questions)
    output_path = settings.parsed_questions_dir / f"{pdf_path.stem}.json"
    save_json(output_path, payload)
    return payload


def parse_pdf(pdf_path: Path, use_fallback: bool = True) -> dict[str, object]:
    settings.ensure_dirs()
    pages = extract_pages(pdf_path)
    raw_output_path = settings.raw_pages_dir / f"{pdf_path.stem}.pages.json"
    save_json(raw_output_path, pages)

    if not any(str(page["text"]).strip() for page in pages):
        if not use_fallback:
            raise ParseError("PDF 为扫描版，未提取到文本")
        return parse_pdf_with_ocr(pdf_path)

    question_text = extract_question_section(pages)
    answer_text = extract_answer_section_text(pages)
    split_items = split_questions(question_text)
    parsed_questions: list[dict[str, object]] = []
    question_errors: list[str] = []
    fallback_question_numbers: set[int] = set()

    for item in split_items:
        number = int(item["number"])
        raw_text = str(item["raw_text"])
        try:
            parsed_questions.append(parse_question(raw_text, shared_options=item.get("shared_options")))
        except ParseError as exc:
            if not use_fallback:
                question_errors.append(str(exc))
                continue
            try:
                fallback_item = extract_with_gemma(raw_text)
                fallback_item["number"] = int(fallback_item.get("number") or number)
                fallback_item["parse_method"] = "llm_fallback"
                fallback_item["source_file"] = str(pdf_path)
                fallback_item.setdefault("source_page_start", None)
                fallback_item.setdefault("source_page_end", None)
                parsed_questions.append(fallback_item)
                fallback_question_numbers.add(number)
            except Exception as fallback_exc:  # noqa: BLE001
                question_errors.append(f"第 {number} 题解析失败：{exc}；AI 兜底失败：{fallback_exc}")

    answers = parse_answers(answer_text)
    merged = merge_questions_answers(parsed_questions, answers, source_file=str(pdf_path))
    validation = validate_questions(merged)

    if not validation.ok and use_fallback:
        repaired_questions: list[dict[str, object]] = []
        for item in merged:
            if item["answer"] and len(item["options"]) >= 4:
                repaired_questions.append(item)
                continue
            raw_text = next(question["raw_text"] for question in split_items if question["number"] == item["number"])
            try:
                fallback_item = extract_with_gemma(raw_text)
                fallback_item["parse_method"] = "llm_fallback"
                fallback_item["source_file"] = str(pdf_path)
                fallback_item.setdefault("source_page_start", None)
                fallback_item.setdefault("source_page_end", None)
                repaired_questions.append(fallback_item)
                fallback_question_numbers.add(int(item["number"]))
            except Exception as fallback_exc:  # noqa: BLE001
                question_errors.append(f"第 {item['number']} 题校验失败且 AI 兜底失败：{fallback_exc}")
        merged = repaired_questions

    payload = build_structured_output(pdf_path, merged)
    payload.setdefault("parse_stats", {})
    payload["parse_stats"]["fallback_questions"] = len(fallback_question_numbers)
    payload["parse_stats"]["failed_questions"] = len(question_errors)
    payload["parse_stats"]["question_errors"] = question_errors
    output_path = settings.parsed_questions_dir / f"{pdf_path.stem}.json"
    save_json(output_path, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="PDF 转结构化 JSON 题库")
    parser.add_argument("pdf_path", type=Path, help="PDF 文件路径")
    parser.add_argument("--no-fallback", action="store_true", help="关闭本地模型兜底")
    args = parser.parse_args()

    try:
        payload = parse_pdf(args.pdf_path, use_fallback=not args.no_fallback)
    except ParseError as exc:
        raise SystemExit(f"解析失败: {exc}") from exc

    print(f"输出文件: {settings.parsed_questions_dir / f'{args.pdf_path.stem}.json'}")
    print(f"题目数量: {len(payload['questions'])}")
    for item in payload["questions"][:2]:
        print(f"- 第{item['number']}题: {item['stem'][:60]}")


if __name__ == "__main__":
    main()
