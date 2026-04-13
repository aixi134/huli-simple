from __future__ import annotations

import json
import time
from collections import deque
from collections.abc import Iterator
from threading import Lock
from typing import Any

import requests

from backend.app.config import settings


_REQUEST_TIMESTAMPS: deque[float] = deque()
_REQUEST_LOCK = Lock()


class AIClient:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
        api_key: str | None = None,
        rate_limit_per_minute: int | None = None,
        retry_attempts: int = 0,
    ) -> None:
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.model = model or settings.llm_model
        self.timeout = timeout or settings.llm_timeout_seconds
        self.api_key = api_key or settings.llm_api_key
        self.rate_limit_per_minute = rate_limit_per_minute
        self.retry_attempts = max(retry_attempts, 0)

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

    def _post_chat_completion(self, payload: dict[str, Any], *, stream: bool = False) -> requests.Response:
        if not self.api_key:
            raise RuntimeError("未设置 QUIZ_LLM_API_KEY 或 OPENAI_API_KEY，无法调用本地多模态 LLM")

        last_error: Exception | None = None
        for attempt_index in range(self.retry_attempts + 1):
            response: requests.Response | None = None
            try:
                self._wait_for_rate_limit_slot()
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                    timeout=self.timeout,
                    stream=stream,
                )
                response.raise_for_status()
                return response
            except requests.HTTPError as exc:
                last_error = exc
                should_retry = response is not None and self._should_retry_response(response)
                if response is not None:
                    response.close()
                if not should_retry or attempt_index >= self.retry_attempts:
                    raise
                time.sleep(self._retry_delay(attempt_index, response))
            except requests.RequestException as exc:
                last_error = exc
                if response is not None:
                    response.close()
                if attempt_index >= self.retry_attempts:
                    raise
                time.sleep(self._retry_delay(attempt_index))

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

    def chat_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        content = self.chat(system_prompt, user_prompt)
        content = content.strip()
        if content.startswith("```"):
            lines = content.splitlines()
            content = "\n".join(line for line in lines if not line.startswith("```"))
        return json.loads(content)

    def chat_json_multimodal(self, system_prompt: str, user_prompt: str, base64_image: str) -> dict[str, Any]:
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
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}},
                        ],
                    },
                ],
            }
        )
        try:
            payload = response.json()
        finally:
            response.close()
        content = payload["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            lines = content.splitlines()
            content = "\n".join(line for line in lines if not line.startswith("```"))
        return json.loads(content)

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
