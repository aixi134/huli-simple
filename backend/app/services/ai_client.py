from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import requests

from backend.app.config import settings


class AIClient:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
        api_key: str | None = None,
    ) -> None:
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.model = model or settings.llm_model
        self.timeout = timeout or settings.llm_timeout_seconds
        self.api_key = api_key or settings.llm_api_key

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        if not self.api_key:
            raise RuntimeError("未设置 QUIZ_LLM_API_KEY 或 OPENAI_API_KEY，无法调用本地多模态 LLM")

        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=self._headers(),
            json={
                "model": self.model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        return payload["choices"][0]["message"]["content"]

    def chat_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        content = self.chat(system_prompt, user_prompt)
        content = content.strip()
        if content.startswith("```"):
            lines = content.splitlines()
            content = "\n".join(line for line in lines if not line.startswith("```"))
        return json.loads(content)

    def chat_json_multimodal(self, system_prompt: str, user_prompt: str, base64_image: str) -> dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("未设置 QUIZ_LLM_API_KEY 或 OPENAI_API_KEY，无法调用本地多模态 LLM")

        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=self._headers(),
            json={
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
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        content = payload["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            lines = content.splitlines()
            content = "\n".join(line for line in lines if not line.startswith("```"))
        return json.loads(content)

    def stream_chat(self, system_prompt: str, user_prompt: str) -> Iterator[str]:
        if not self.api_key:
            raise RuntimeError("未设置 QUIZ_LLM_API_KEY 或 OPENAI_API_KEY，无法调用本地多模态 LLM")

        try:
            with requests.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json={
                    "model": self.model,
                    "temperature": 0,
                    "stream": True,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                },
                timeout=self.timeout,
                stream=True,
            ) as response:
                response.raise_for_status()
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
