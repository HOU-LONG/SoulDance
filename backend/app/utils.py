from __future__ import annotations

import json
import re
from typing import Any


def extract_json(raw: str) -> dict[str, Any]:
    """从 LLM 原始输出中提取 JSON 对象。

    处理常见格式：裸 JSON、```json ... ``` 代码块、内嵌在文本中的 JSON。
    当解析失败或结果不是 dict 时抛出 ValueError。
    """
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?", "", raw).strip()
        raw = re.sub(r"```$", "", raw).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, flags=re.S)
        if not match:
            raise
        data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError(f"extract_json: expected dict, got {type(data).__name__}")
    return data


