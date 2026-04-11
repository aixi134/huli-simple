from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

try:
    import fitz
except ModuleNotFoundError:  # pragma: no cover - handled at runtime
    fitz = None


QUESTION_SECTION_START_RE = re.compile(
    r"(?:[一1]\s*[、.]\s*(?:A1(?:/A2)?|A2|A1A2|A1、A2|A1/A2型选择题|A1型选择题|A2型选择题|选择题)|^\s*1\s*[、.])",
    re.IGNORECASE | re.MULTILINE,
)
ANSWER_SECTION_START_RE = re.compile(r"参考答案(?:及解析)?|答案与解析|参考解析")
NEXT_SECTION_RE = re.compile(r"(?m)^\s*[一二三四五六七八九十]+\s*[、.]\s*[A-Z0-9]+\s*型选择题")
GROUP_STEM_RE = re.compile(r"(?ms)^\s*【\d+\s*[~～-]\s*\d+】\s*(.*?)\s*(?=(?:^\s*\d+\s*[\.、])|\Z)")
QUESTION_SPLIT_RE = re.compile(r"(?m)^\s*(\d+)\s*[\.、]")
OPTION_MARK_RE = re.compile(r"(?<![A-Z])([A-E])\s*[\.、．]\s*")
INLINE_ANSWER_RE = re.compile(r"答案\s*[:：]\s*([A-E])")
ANSWER_ENTRY_RE = re.compile(
    r"(?ms)(\d+)\s*[\.、]\s*([A-E])\s*(?:解析[:：]\s*|[\r\n]+)(.*?)(?=(?:\n\s*\d+\s*[\.、]\s*[A-E]\s*(?:解析[:：]|\n))|\Z)"
)
YEAR_RE = re.compile(r"(20\d{2})")
SUBJECT_KEYWORDS = ["基础知识", "相关专业知识", "专业知识", "专业实践能力"]
QUESTION_TYPE_RE = re.compile(r"(A1/A2|A1|A2|B1)", re.IGNORECASE)


@dataclass
class ParseValidationResult:
    ok: bool
    reasons: list[str]


class ParseError(ValueError):
    pass


def extract_pages(pdf_path: str | Path) -> list[dict[str, object]]:
    if fitz is None:
        raise RuntimeError("PyMuPDF 未安装，请先执行 pip install -r backend/requirements.txt")

    pdf_path = Path(pdf_path)
    pages: list[dict[str, object]] = []
    with fitz.open(pdf_path) as doc:
        for index, page in enumerate(doc, start=1):
            text = page.get_text("text")
            pages.append({"page": index, "text": normalize_text(text)})
    return pages


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u3000", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_question_section(pages: list[dict[str, object]]) -> str:
    combined = "\n\n".join(str(page["text"]) for page in pages)
    if not combined:
        raise ParseError("PDF 文本为空")

    start_match = QUESTION_SECTION_START_RE.search(combined)
    if not start_match:
        raise ParseError("未找到题目起始区块")

    section = combined[start_match.start() :]
    end_match = ANSWER_SECTION_START_RE.search(section)
    if end_match:
        section = section[: end_match.start()]
    return section.strip()


def extract_answer_section_text(pages: list[dict[str, object]]) -> str:
    combined = "\n\n".join(str(page["text"]) for page in pages)
    end_match = ANSWER_SECTION_START_RE.search(combined)
    if end_match:
        return combined[end_match.start() :].strip()
    return combined


def split_questions(text: str) -> list[dict[str, object]]:
    matches = list(QUESTION_SPLIT_RE.finditer(text))
    if not matches:
        raise ParseError("未识别到题号")

    group_options_by_question = extract_group_options(text)
    questions: list[dict[str, object]] = []
    numbers: list[int] = []
    for index, match in enumerate(matches):
        number = int(match.group(1))
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        raw_text = text[start:end].strip()
        if raw_text:
            questions.append(
                {
                    "number": number,
                    "raw_text": raw_text,
                    "shared_options": group_options_by_question.get(number),
                }
            )
            numbers.append(number)

    if not numbers:
        raise ParseError("题目切分后为空")
    return questions


def parse_question(raw_text: str, shared_options: dict[str, str] | None = None) -> dict[str, object]:
    number_match = re.match(r"^\s*(\d+)\s*[\.、]\s*", raw_text)
    if not number_match:
        raise ParseError("题目缺少题号")
    number = int(number_match.group(1))
    body = raw_text[number_match.end() :].strip()

    inline_answer_match = INLINE_ANSWER_RE.search(body)
    answer = inline_answer_match.group(1).strip().upper() if inline_answer_match else ""
    if inline_answer_match:
        body = body[: inline_answer_match.start()].rstrip()

    option_matches = list(OPTION_MARK_RE.finditer(body))
    options: dict[str, str] = {}
    if len(option_matches) >= 2:
        stem = body[: option_matches[0].start()].strip()
        for index, match in enumerate(option_matches):
            label = match.group(1)
            start = match.end()
            end = option_matches[index + 1].start() if index + 1 < len(option_matches) else len(body)
            content = body[start:end].strip()
            content = re.sub(r"\s*\n\s*", " ", content)
            options[label] = content
    elif shared_options:
        stem = body.strip()
        options = dict(shared_options)
    else:
        raise ParseError(f"第 {number} 题选项数量不足")

    if not stem:
        raise ParseError(f"第 {number} 题题干为空")
    return {
        "number": number,
        "stem": re.sub(r"\s*\n\s*", " ", stem),
        "options": options,
        "answer": answer,
    }


def extract_group_options(text: str) -> dict[int, dict[str, str]]:
    group_options_by_question: dict[int, dict[str, str]] = {}
    for match in GROUP_STEM_RE.finditer(text):
        range_text = match.group(0).split("】", 1)[0].strip("【")
        stem_body = match.group(1).strip()
        range_numbers = [int(item) for item in re.findall(r"\d+", range_text)]
        if len(range_numbers) < 2:
            continue
        options = parse_options_only(stem_body)
        if len(options) < 2:
            continue
        start, end = range_numbers[0], range_numbers[-1]
        for number in range(start, end + 1):
            group_options_by_question[number] = options
    return group_options_by_question


def parse_options_only(text: str) -> dict[str, str]:
    option_matches = list(OPTION_MARK_RE.finditer(text))
    if len(option_matches) < 2:
        return {}
    options: dict[str, str] = {}
    for index, match in enumerate(option_matches):
        label = match.group(1)
        start = match.end()
        end = option_matches[index + 1].start() if index + 1 < len(option_matches) else len(text)
        content = text[start:end].strip()
        content = re.sub(r"\s*\n\s*", " ", content)
        options[label] = content
    return options


def parse_answers(text: str) -> dict[str, dict[str, str]]:
    answers: dict[str, dict[str, str]] = {}
    for match in ANSWER_ENTRY_RE.finditer(text):
        number = match.group(1)
        answer = match.group(2).strip().upper()
        explanation = normalize_text(match.group(3))
        answers[number] = {
            "answer": answer,
            "explanation": explanation,
        }
    if not answers:
        compact_re = re.compile(r"(?m)^(\d+)\s*[\.、]\s*([A-E])\s*$")
        for match in compact_re.finditer(text):
            number = match.group(1)
            answers[number] = {"answer": match.group(2).strip().upper(), "explanation": ""}
    return answers


def merge_questions_answers(
    questions: list[dict[str, object]],
    answers: dict[str, dict[str, str]],
    *,
    source_file: str | None = None,
    parse_method: str = "rule",
    metadata: dict[str, object] | None = None,
) -> list[dict[str, object]]:
    merged: list[dict[str, object]] = []
    metadata = metadata or {}
    for question in questions:
        number = int(question["number"])
        answer_data = answers.get(str(number), {"answer": "", "explanation": ""})
        resolved_answer = answer_data.get("answer") or str(question.get("answer", "")).strip().upper()
        merged.append(
            {
                "number": number,
                "stem": question["stem"],
                "options": question["options"],
                "answer": resolved_answer,
                "explanation": answer_data.get("explanation", "") or str(question.get("explanation", "")).strip(),
                "source_file": source_file or str(question.get("source_file", "")),
                "source_page_start": question.get("source_page_start", metadata.get("source_page_start")),
                "source_page_end": question.get("source_page_end", metadata.get("source_page_end")),
                "parse_method": str(question.get("parse_method", parse_method)),
            }
        )
    return merged


def build_structured_output(pdf_path: str | Path, merged_questions: list[dict[str, object]]) -> dict[str, object]:
    path = Path(pdf_path)
    metadata = extract_source_metadata(path)
    return {
        "source_file": str(path),
        "subject": metadata["subject"],
        "year": metadata["year"],
        "question_type": metadata["question_type"],
        "parse_stats": {
            "total_questions": len(merged_questions),
            "fallback_questions": sum(1 for item in merged_questions if item.get("parse_method") == "llm_fallback"),
        },
        "questions": merged_questions,
    }


def extract_source_metadata(pdf_path: str | Path) -> dict[str, object]:
    path = Path(pdf_path)
    joined = f"{path.parent.name} {path.name}"
    year_match = YEAR_RE.search(joined)
    year = int(year_match.group(1)) if year_match else None
    subject = next((item for item in SUBJECT_KEYWORDS if item in joined), None)
    question_type_match = QUESTION_TYPE_RE.search(joined)
    question_type = question_type_match.group(1).upper() if question_type_match else "single_choice"
    return {
        "year": year,
        "subject": subject,
        "question_type": question_type,
    }


def validate_questions(questions: list[dict[str, object]]) -> ParseValidationResult:
    reasons: list[str] = []
    if not questions:
        reasons.append("没有题目")
        return ParseValidationResult(ok=False, reasons=reasons)

    numbers = [int(item["number"]) for item in questions]
    if len(numbers) != len(set(numbers)):
        reasons.append("题号重复")

    for item in questions:
        options = item.get("options", {})
        if len(options) < 4:
            reasons.append(f"第 {item['number']} 题选项不足")
        if not item.get("answer"):
            reasons.append(f"第 {item['number']} 题缺少答案")
    return ParseValidationResult(ok=not reasons, reasons=reasons)


def save_json(path: str | Path, payload: object) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
