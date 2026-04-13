from __future__ import annotations

import json
import logging
import time
from collections import deque
from collections.abc import Iterator
from threading import Lock
from typing import Any

import requests

from backend.app.config import settings


if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
_REQUEST_TIMESTAMPS: deque[float] = deque()
_REQUEST_LOCK = Lock()
_SUPPORTED_MULTIMODAL_PROVIDER_MODES = {"openai_compatible_data_url"}


class OCRProviderConfigurationError(RuntimeError):
    def __init__(self, message: str, *, code: str, details: list[str] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or []


class AIClient:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
        api_key: str | None = None,
        rate_limit_per_minute: int | None = None,
        retry_attempts: int = 0,
        provider_mode: str | None = None,
        use_case: str = "text",
    ) -> None:
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.model = model or settings.llm_model
        self.timeout = timeout or settings.llm_timeout_seconds
        self.api_key = api_key or settings.llm_api_key
        self.rate_limit_per_minute = rate_limit_per_minute
        self.retry_attempts = max(retry_attempts, 0)
        self.provider_mode = (provider_mode or "").strip()
        self.use_case = use_case

    @classmethod
    def get_ocr_config_summary(cls) -> dict[str, Any]:
        return {
            "enabled": settings.ocr_llm_enabled,
            "provider": settings.ocr_llm_provider or "",
            "base_url": settings.ocr_llm_base_url or settings.llm_base_url,
            "model": settings.ocr_llm_model or settings.llm_model,
            "api_key_configured": bool(settings.ocr_llm_api_key or settings.llm_api_key),
        }

    @classmethod
    def for_ocr(cls, *, rate_limit_per_minute: int | None = None, retry_attempts: int = 0) -> "AIClient":
        summary = cls.get_ocr_config_summary()
        if not settings.ocr_llm_enabled:
            raise OCRProviderConfigurationError(
                "该 PDF 为扫描版，当前未启用 OCR 图片识别。请配置 QUIZ_OCR_LLM_ENABLED=true，并指定支持多模态图片输入的 OCR provider。",
                code="ocr_not_enabled",
                details=[
                    "扫描版 PDF OCR 不会默认复用 QUIZ_LLM_* 配置。",
                    f"当前文本 LLM base_url: {settings.llm_base_url}",
                    f"当前文本 LLM model: {settings.llm_model}",
                    "请至少设置 QUIZ_OCR_LLM_ENABLED=true 与 QUIZ_OCR_LLM_PROVIDER。",
                ],
            )

        provider_mode = str(summary["provider"] or "").strip()
        if not provider_mode:
            raise OCRProviderConfigurationError(
                "未配置 QUIZ_OCR_LLM_PROVIDER，无法确定扫描版 PDF OCR 的图片输入格式。",
                code="ocr_provider_missing",
                details=[
                    f"当前 OCR base_url: {summary['base_url']}",
                    f"当前 OCR model: {summary['model']}",
                    f"支持的 OCR provider 模式: {', '.join(sorted(_SUPPORTED_MULTIMODAL_PROVIDER_MODES))}",
                ],
            )

        if not summary["api_key_configured"]:
            raise OCRProviderConfigurationError(
                "未配置 OCR API Key，无法执行扫描版 PDF OCR。",
                code="ocr_api_key_missing",
                details=[
                    f"当前 OCR base_url: {summary['base_url']}",
                    f"当前 OCR model: {summary['model']}",
                    "请配置 QUIZ_OCR_LLM_API_KEY，或在启用 OCR 后复用通用 QUIZ_LLM_API_KEY/OPENAI_API_KEY。",
                ],
            )

        return cls(
            base_url=str(summary["base_url"]),
            model=str(summary["model"]),
            timeout=settings.ocr_llm_timeout_seconds,
            api_key=settings.ocr_llm_api_key or settings.llm_api_key,
            rate_limit_per_minute=rate_limit_per_minute,
            retry_attempts=retry_attempts,
            provider_mode=provider_mode,
            use_case="ocr",
        )

    def ensure_multimodal_image_supported(self) -> None:
        if self.provider_mode in _SUPPORTED_MULTIMODAL_PROVIDER_MODES:
            return

        details = [
            f"当前 OCR provider: {self.provider_mode or '未配置'}",
            f"当前 OCR base_url: {self.base_url}",
            f"当前 OCR model: {self.model}",
            "当前请求格式: OpenAI chat/completions + image_url(data URL)",
            f"支持的 OCR provider 模式: {', '.join(sorted(_SUPPORTED_MULTIMODAL_PROVIDER_MODES))}",
        ]
        logger.error(
            "OCR capability gate blocked provider_mode=%s base_url=%s model=%s use_case=%s",
            self.provider_mode or "unset",
            self.base_url,
            self.model,
            self.use_case,
        )
        raise OCRProviderConfigurationError(
            "当前配置的 OCR 提供商或模型不支持图片识别，请切换到支持多模态图片输入的 OCR provider。",
            code="ocr_provider_incompatible",
            details=details,
        )

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _wait_for_rate_limit_slot(self) -> None:
        if not self.rate_limit_per_minute or self.rate_limit_per_minute <= 0:
            return

        window_seconds = 60.0
        while True:
            now = time.monotonic()
            with _REQUEST_LOCK:
                cutoff = now - window_seconds
                while _REQUEST_TIMESTAMPS and _REQUEST_TIMESTAMPS[0] <= cutoff:
                    _REQUEST_TIMESTAMPS.popleft()
                if len(_REQUEST_TIMESTAMPS) < self.rate_limit_per_minute:
                    _REQUEST_TIMESTAMPS.append(now)
                    return
                sleep_seconds = max(_REQUEST_TIMESTAMPS[0] + window_seconds - now, 0.01)
            time.sleep(sleep_seconds)

    @staticmethod
    def _should_retry_response(response: requests.Response) -> bool:
        return response.status_code == 429 or response.status_code >= 500

    @staticmethod
    def _retry_delay(attempt_index: int, response: requests.Response | None = None) -> float:
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    return max(float(retry_after), 0.0)
                except ValueError:
                    pass
        return min(2**attempt_index, 8)

    @staticmethod
    def _summarize_payload(payload: dict[str, Any]) -> dict[str, Any]:
        messages = payload.get("messages") or []
        text_chars = 0
        image_count = 0
        for message in messages:
            content = message.get("content")
            if isinstance(content, str):
                text_chars += len(content)
                continue
            if isinstance(content, list):
                for part in content:
                    if not isinstance(part, dict):
                        continue
                    if part.get("type") == "text":
                        text_chars += len(str(part.get("text") or ""))
                    elif part.get("type") == "image_url":
                        image_count += 1
        return {
            "model": payload.get("model"),
            "stream": bool(payload.get("stream")),
            "message_count": len(messages),
            "text_chars": text_chars,
            "image_count": image_count,
        }

    @staticmethod
    def _strip_code_fences(content: str) -> str:
        stripped = content.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            stripped = "\n".join(line for line in lines if not line.startswith("```"))
        return stripped.strip()

    @classmethod
    def _parse_json_content(cls, content: str, *, error_context: str) -> Any:
        stripped = cls._strip_code_fences(content)
        try:
            return json.loads(stripped)
        except json.JSONDecodeError as exc:
            snippet = stripped[:240] or "<empty>"
            logger.error("%s returned non-JSON content: %s", error_context, snippet)
            raise RuntimeError(f"{error_context}返回的内容不是 JSON：{snippet}") from exc

    def _post_chat_completion(self, payload: dict[str, Any], *, stream: bool = False) -> requests.Response:
        if not self.api_key:
            raise RuntimeError("未设置 QUIZ_LLM_API_KEY 或 OPENAI_API_KEY，无法调用本地多模态 LLM")

        request_url = f"{self.base_url}/chat/completions"
        request_meta = self._summarize_payload(payload)
        last_error: Exception | None = None
        for attempt_index in range(self.retry_attempts + 1):
            response: requests.Response | None = None
            started_at = time.perf_counter()
            try:
                self._wait_for_rate_limit_slot()
                logger.info(
                    "LLM request start use_case=%s provider_mode=%s url=%s model=%s stream=%s messages=%s text_chars=%s images=%s attempt=%s/%s",
                    self.use_case,
                    self.provider_mode or "default",
                    request_url,
                    request_meta["model"],
                    request_meta["stream"],
                    request_meta["message_count"],
                    request_meta["text_chars"],
                    request_meta["image_count"],
                    attempt_index + 1,
                    self.retry_attempts + 1,
                )
                response = requests.post(
                    request_url,
                    headers=self._headers(),
                    json=payload,
                    timeout=self.timeout,
                    stream=stream,
                )
                response.raise_for_status()
                logger.info(
                    "LLM request success use_case=%s provider_mode=%s status=%s elapsed=%.2fs model=%s stream=%s attempt=%s/%s",
                    self.use_case,
                    self.provider_mode or "default",
                    response.status_code,
                    time.perf_counter() - started_at,
                    request_meta["model"],
                    request_meta["stream"],
                    attempt_index + 1,
                    self.retry_attempts + 1,
                )
                return response
            except requests.HTTPError as exc:
                last_error = exc
                should_retry = response is not None and self._should_retry_response(response)
                status_code = response.status_code if response is not None else "unknown"
                response_body = ""
                if response is not None:
                    response_body = response.text[:500]
                    response.close()
                if not should_retry or attempt_index >= self.retry_attempts:
                    logger.exception(
                        "LLM request failed use_case=%s provider_mode=%s status=%s: %s",
                        self.use_case,
                        self.provider_mode or "default",
                        status_code,
                        response_body or exc,
                    )
                    raise
                delay_seconds = self._retry_delay(attempt_index, response)
                logger.warning(
                    "LLM request hit retryable HTTP error use_case=%s provider_mode=%s status=%s, retrying in %.1fs (%s/%s)",
                    self.use_case,
                    self.provider_mode or "default",
                    status_code,
                    delay_seconds,
                    attempt_index + 1,
                    self.retry_attempts,
                )
                time.sleep(delay_seconds)
            except requests.RequestException as exc:
                last_error = exc
                if response is not None:
                    response.close()
                if attempt_index >= self.retry_attempts:
                    logger.exception(
                        "LLM request failed after retries use_case=%s provider_mode=%s: %s",
                        self.use_case,
                        self.provider_mode or "default",
                        exc,
                    )
                    raise
                delay_seconds = self._retry_delay(attempt_index)
                logger.warning(
                    "LLM request raised %s use_case=%s provider_mode=%s, retrying in %.1fs (%s/%s)",
                    exc.__class__.__name__,
                    self.use_case,
                    self.provider_mode or "default",
                    delay_seconds,
                    attempt_index + 1,
                    self.retry_attempts,
                )
                time.sleep(delay_seconds)

        if last_error is not None:
            raise last_error
        raise RuntimeError("LLM 请求失败")

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        response = self._post_chat_completion(
            {
                "model": self.model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            }
        )
        try:
            payload = response.json()
        finally:
            response.close()
        return payload["choices"][0]["message"]["content"]

    def chat_json(self, system_prompt: str, user_prompt: str) -> Any:
        content = self.chat(system_prompt, user_prompt)
        return self._parse_json_content(content, error_context="LLM 文本解析")

    def chat_json_multimodal(
        self,
        system_prompt: str,
        user_prompt: str,
        base64_image: str,
        *,
        mime_type: str = "image/png",
    ) -> Any:
        self.ensure_multimodal_image_supported()
        response = self._post_chat_completion(
            {
                "model": self.model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_prompt},
                            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}},
                        ],
                    },
                ],
            }
        )
        try:
            payload = response.json()
        finally:
            response.close()
        content = payload["choices"][0]["message"]["content"]
        return self._parse_json_content(content, error_context="OCR 图片识别")

    def stream_chat(self, system_prompt: str, user_prompt: str) -> Iterator[str]:
        try:
            with self._post_chat_completion(
                {
                    "model": self.model,
                    "temperature": 0,
                    "stream": True,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                },
                stream=True,
            ) as response:
                yielded = False
                for line in response.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    if line.startswith("data: "):
                        line = line[6:]
                    if line == "[DONE]":
                        return
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    choice = (payload.get("choices") or [{}])[0]
                    delta = choice.get("delta") or {}
                    content = delta.get("content")
                    if isinstance(content, str) and content:
                        yielded = True
                        yield content
                if yielded:
                    return
        except Exception:
            pass

        full_text = self.chat(system_prompt, user_prompt)
        chunk_size = 80
        for index in range(0, len(full_text), chunk_size):
            yield full_text[index : index + chunk_size]
