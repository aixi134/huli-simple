from __future__ import annotations

import json

from backend.app.services.ai_client import AIClient


def _build_prompts(analysis: dict[str, object]) -> tuple[str, str]:
    system_prompt = (
        "你是一个护理考试薄弱点分析助手。"
        "你会根据用户真实错题统计给出简洁、可执行的中文学习建议。"
        "只返回 JSON，不要输出 markdown，不要输出解释性前缀。"
    )
    user_prompt = (
        "请根据下面的错题统计生成专项学习建议。"
        "不要编造不存在的数据，只能基于提供的统计与题目样本总结。"
        "JSON 结构必须是："
        '{"summary":"...","weak_points":[{"title":"...","reason":"...","priority":"high"}],'
        '"confusion_advice":[{"pattern":"...","reason":"...","advice":"..."}],'
        '"study_plan":[{"step":1,"action":"...","goal":"..."}],"next_action":"..."}'
        "。"
        "priority 只能是 high、medium、low。"
        "study_plan 控制在 3-5 条。"
        "全部内容请使用中文。\n\n"
        f"错题统计与样本：\n{json.dumps(analysis, ensure_ascii=False, default=str)}"
    )
    return system_prompt, user_prompt


def recommend_weakness_study_plan(analysis: dict[str, object]) -> dict[str, object]:
    client = AIClient()
    system_prompt, user_prompt = _build_prompts(analysis)
    payload = client.chat_json(system_prompt, user_prompt)
    if isinstance(payload, dict):
        return payload
    raise RuntimeError("薄弱点分析返回的内容不是 JSON 对象")
