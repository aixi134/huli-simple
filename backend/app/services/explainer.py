from __future__ import annotations

from collections.abc import Iterator

from backend.app.services.ai_client import AIClient


def _build_prompts(question: str, options: dict[str, str], answer: str, explanation: str) -> tuple[str, str]:
    option_lines = "\n".join(f"{label}. {content}" for label, content in sorted(options.items()))
    system_prompt = (
        "你是一个护理考试讲题助手。"
        "请输出简洁、易读的中文 markdown。"
        "使用小标题和项目符号，不要输出代码块。"
    )
    user_prompt = (
        "请用通俗方式讲解这道护理题，并使用 markdown 输出。\n"
        "必须包含：\n"
        "1. 一个简短结论\n"
        "2. 为什么正确答案正确\n"
        "3. 每个错误选项为什么错\n\n"
        f"题干：{question}\n"
        f"选项：\n{option_lines}\n"
        f"正确答案：{answer}\n"
        f"参考解析：{explanation or '暂无'}"
    )
    return system_prompt, user_prompt


def explain_with_gemma(question: str, options: dict[str, str], answer: str, explanation: str) -> str:
    client = AIClient()
    system_prompt, user_prompt = _build_prompts(question, options, answer, explanation)
    return client.chat(system_prompt, user_prompt).strip()


def stream_explanation_with_gemma(question: str, options: dict[str, str], answer: str, explanation: str) -> Iterator[str]:
    client = AIClient()
    system_prompt, user_prompt = _build_prompts(question, options, answer, explanation)
    yield from client.stream_chat(system_prompt, user_prompt)
