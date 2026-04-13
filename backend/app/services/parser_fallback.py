from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from backend.app.services.ai_client import AIClient, OCRProviderConfigurationError


PARSER_LLM_REQUESTS_PER_MINUTE = 30
PARSER_LLM_RETRY_ATTEMPTS = 3


def build_parser_ai_client() -> AIClient:
    return AIClient(rate_limit_per_minute=PARSER_LLM_REQUESTS_PER_MINUTE, retry_attempts=PARSER_LLM_RETRY_ATTEMPTS)


def build_parser_ocr_ai_client() -> AIClient:
    return AIClient.for_ocr(rate_limit_per_minute=PARSER_LLM_REQUESTS_PER_MINUTE, retry_attempts=PARSER_LLM_RETRY_ATTEMPTS)


def get_ocr_runtime_summary() -> dict[str, Any]:
    return AIClient.get_ocr_config_summary()


def extract_with_gemma(page_text: str) -> dict[str, object]:
    client = build_parser_ai_client()
    system_prompt = (
        "你是一个严格的题目抽取器。"
        "只返回 JSON，不要输出 markdown，不要输出解释。"
        "JSON 结构必须是: "
        '{"number":1,"stem":"...","options":{"A":"...","B":"...","C":"...","D":"...","E":"..."},"answer":"A","explanation":"..."}'
    )
    user_prompt = (
        "请从下面文本中抽取一道护理选择题。"
        "如果没有 E 选项，可以省略 E。"
        "必须保证 answer 是 A-E 之一。\n\n"
        f"文本:\n{page_text}"
    )
    payload = client.chat_json(system_prompt, user_prompt)
    if isinstance(payload, dict):
        return payload
    raise RuntimeError("文本兜底返回的内容不是 JSON 对象")


def extract_with_gemma_from_image(image_path: str | Path) -> dict[str, object]:
    path = Path(image_path)
    image_bytes = path.read_bytes()
    content = base64.b64encode(image_bytes).decode("utf-8")
    client = build_parser_ocr_ai_client()
    mime_type = "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
    system_prompt = (
        "你是一个严格的 OCR 题目抽取器。"
        "你会从试卷图片中抽取单选题，并且只返回 JSON。"
        "不要输出 markdown，不要输出解释。"
    )
    user_prompt = (
        "请识别图片里的护理选择题，输出 JSON 数组。"
        "每个元素格式必须是："
        '{"number":1,"stem":"...","options":{"A":"...","B":"...","C":"...","D":"...","E":"..."},"answer":"A","explanation":""}'
        "。如果图片中没有某题解析，explanation 置空字符串。"
    )
    payload = client.chat_json_multimodal(system_prompt, user_prompt, content, mime_type=mime_type)
    if isinstance(payload, dict):
        if "questions" in payload and isinstance(payload["questions"], list):
            return payload
        return {"questions": [payload]}
    if isinstance(payload, list):
        return {"questions": payload}
    raise RuntimeError("OCR 图片识别返回的内容不是 JSON 对象或数组")


__all__ = [
    "OCRProviderConfigurationError",
    "extract_with_gemma",
    "extract_with_gemma_from_image",
    "get_ocr_runtime_summary",
]
