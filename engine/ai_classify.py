"""LLM-assisted classification for open-ended survey responses."""

from __future__ import annotations

import json
import sqlite3

from . import db


PROMPT_VERSION = "v1"


def _log_output(
    conn: sqlite3.Connection | None,
    question_id: int | None,
    mode: str,
    output: dict,
) -> None:
    if conn is not None and question_id is not None:
        db.log_ai_run(
            conn,
            question_id,
            mode,
            PROMPT_VERSION,
            json.dumps(output, ensure_ascii=False),
        )


def _classify_closed(
    provider,
    responses: list[dict],
    categories: list[str],
    batch_size: int,
    conn: sqlite3.Connection | None,
    question_id: int | None,
    audit_mode: str,
) -> list[dict]:
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than zero")

    assignments_by_id: dict[int, str] = {}
    for start in range(0, len(responses), batch_size):
        batch = responses[start : start + batch_size]
        system = "你负责将开放题回答分配到一组已经确定的封闭类目。"
        user = (
            "只能从给定类目里选择，不许自造新类目。每条 response_id 必须出现且只出现一次。\n"
            "请只返回 JSON 对象，格式为："
            '{"assignments": [{"response_id": 1, "category": "类目"}]}。\n'
            f"给定类目：{json.dumps(categories, ensure_ascii=False)}\n"
            f"待分类回答：{json.dumps(batch, ensure_ascii=False)}"
        )
        output = provider.complete_json(system, user)
        _log_output(conn, question_id, audit_mode, output)

        batch_ids = {item["response_id"] for item in batch}
        returned = output.get("assignments", [])
        if not isinstance(returned, list):
            returned = []
        for item in returned:
            if not isinstance(item, dict):
                continue
            response_id = item.get("response_id")
            if response_id not in batch_ids or response_id in assignments_by_id:
                continue
            category = item.get("category")
            assignments_by_id[response_id] = (
                category if category in categories else "__unclassified__"
            )

        for item in batch:
            assignments_by_id.setdefault(item["response_id"], "__unclassified__")

    return [
        {
            "response_id": item["response_id"],
            "category": assignments_by_id[item["response_id"]],
        }
        for item in responses
    ]


def classify_closed(
    provider,
    responses: list[dict],
    categories: list[str],
    batch_size: int = 60,
    conn: sqlite3.Connection | None = None,
    question_id: int | None = None,
) -> list[dict]:
    """Assign every response to one of the caller-provided categories."""

    return _classify_closed(
        provider,
        responses,
        categories,
        batch_size,
        conn,
        question_id,
        "classify_closed",
    )


def classify_open(
    provider,
    responses: list[dict],
    sample_size: int = 60,
    batch_size: int = 60,
    conn: sqlite3.Connection | None = None,
    question_id: int | None = None,
) -> dict:
    """Extract categories from a stable sample, then classify all responses."""

    if sample_size < 0:
        raise ValueError("sample_size must not be negative")
    sample = responses[: min(sample_size, len(responses))]
    system = "你负责从当前开放题的实际回答中提炼封闭分类标签。"
    user = (
        "阅读这些开放题回答，总结出 5-8 个能覆盖这些回答的分类标签，"
        "使用中文短语。请只返回 JSON 对象，格式为："
        '{"categories": ["类目一", "类目二"]}。\n'
        f"回答样本：{json.dumps(sample, ensure_ascii=False)}"
    )
    output = provider.complete_json(system, user)
    _log_output(conn, question_id, "classify_open_extract", output)

    raw_categories = output.get("categories", [])
    categories = (
        [category for category in raw_categories if isinstance(category, str)]
        if isinstance(raw_categories, list)
        else []
    )
    assignments = _classify_closed(
        provider,
        responses,
        categories,
        batch_size,
        conn,
        question_id,
        "classify_open_assign",
    )
    return {"categories": categories, "assignments": assignments}


def classify_custom(
    provider,
    responses: list[dict],
    instruction: str,
    sample_size: int = 60,
    batch_size: int = 60,
    conn: sqlite3.Connection | None = None,
    question_id: int | None = None,
) -> dict:
    """按用户自己写的分析指令提炼类目、再分配——跟 classify_open 是同一套"先提炼、
    再分配"流程，唯一区别是提炼类目这一步的指令是用户自己写的（比如"判断每条回答有没有
    提到价格敏感"），不是固定写死的"总结开放题回答"。

    分配这一步复用 _classify_closed，保证结果只会是提炼出来的类目之一——所以不管指令
    多自由，最终结果始终是"每条回答对应一个类目"这种表格/柱状图/饼图能直接展示的形状，
    不会退化成一段不能画图的自由文本。这是这个功能存在的意义：用户想用自己的 prompt
    做点额外分析，但结果还是要能像封闭分类/开放聚类一样出图，不是聊天式的自由问答。
    """

    if not instruction.strip():
        raise ValueError("instruction must not be empty")
    if sample_size < 0:
        raise ValueError("sample_size must not be negative")

    sample = responses[: min(sample_size, len(responses))]
    system = "你负责按用户给定的分析要求，从开放题回答中提炼分类标签。"
    user = (
        f"分析要求：{instruction.strip()}\n"
        "阅读这些开放题回答，根据上面的分析要求总结出 2-8 个能覆盖这些回答的分类标签，"
        "使用中文短语。请只返回 JSON 对象，格式为："
        '{"categories": ["类目一", "类目二"]}。\n'
        f"回答样本：{json.dumps(sample, ensure_ascii=False)}"
    )
    output = provider.complete_json(system, user)
    _log_output(conn, question_id, "classify_custom_extract", output)

    raw_categories = output.get("categories", [])
    categories = (
        [category for category in raw_categories if isinstance(category, str)]
        if isinstance(raw_categories, list)
        else []
    )
    assignments = _classify_closed(
        provider,
        responses,
        categories,
        batch_size,
        conn,
        question_id,
        "classify_custom_assign",
    )
    return {"categories": categories, "assignments": assignments}
