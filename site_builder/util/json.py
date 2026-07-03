"""Tolerant JSON helpers used for SQLite JSON columns."""

import json
from typing import Any


def loads_json(text: Any, default: Any):
    if text is None:
        return default
    if isinstance(text, (dict, list)):
        return text
    try:
        return json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return default


def loads_json_dict(text: Any) -> dict:
    value = loads_json(text, {})
    return value if isinstance(value, dict) else {}


def loads_json_list(text: Any) -> list:
    value = loads_json(text, [])
    return value if isinstance(value, list) else []


def dumps_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
