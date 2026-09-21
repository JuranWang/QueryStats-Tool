"""LLM-assisted phenomenon-level insights, grounded in Python-computed numbers.

Discipline (same as ai_classify.py / ai_translate.py): Python computes every number in
advance; the model is only allowed to pick out which numbers are worth saying and phrase
them into a sentence. It is never trusted to do its own arithmetic. Every number the model's
text contains is checked against the numbers it was actually given — an insight citing a
number that isn't verifiable in the input data is dropped entirely, not "corrected".
"""

from __future__ import annotations

import json
import re
import sqlite3

from . import db

PROMPT_VERSION = "v1"

_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def generate_insights(
    provider,
    stats_bundle: dict,
    conn: sqlite3.Connection | None = None,
    question_id: int | None = None,
) -> list[dict]:
    """Ask the model for 2-4 phenomenon-level insights grounded in ``stats_bundle``.

    ``stats_bundle`` is a JSON-serializable dict of stats Python has already computed
    (e.g. ``{"Q1": single_choice_stats(...), "crosstab_Q1_Q3": crosstab_counts(...)}``
    turned into plain dicts/lists first). The model only sees this data; it is told not to
    compute or invent new numbers and not to make business judgments (只做现象判断).

    Returns ``[{"text": str}, ...]`` — insights whose numbers cannot all be found verbatim
    in the serialized ``stats_bundle`` are silently dropped, not shown, not "fixed".

    ``conn``/``question_id`` are optional audit hooks (same pattern as ai_classify/ai_translate),
    logged via ``db.log_ai_run``. AI 洞察 is a whole-project thing, not tied to one question,
    but the current `ai_runs` schema requires a `question_id` — pass `None` to skip logging
    until that schema gap is addressed (see 设计文档 changelog).
    """

    serialized = json.dumps(stats_bundle, ensure_ascii=False, sort_keys=True)

    system = "你是问卷数据分析助手。只做现象判断，不做商业判断。"
    user = (
        "下面是已经算好的问卷统计数据（JSON）。请从中挑 2 到 4 条值得说的现象级洞察，"
        "每条一两句话，必须带具体数字，数字必须和下面数据完全一致——不能自己计算、"
        "四舍五入、合并或编造新数字。不要给出商业建议（不要说"
        "「应该主打什么」「该定什么价」这类话，只描述现象）。\n"
        '请只返回一个 JSON 对象，格式为：{"insights": ["第一条……", "第二条……"]}。\n'
        f"统计数据：{serialized}"
    )

    output = provider.complete_json(system, user)

    if conn is not None and question_id is not None:
        db.log_ai_run(conn, question_id, "insight", PROMPT_VERSION, json.dumps(output, ensure_ascii=False))

    raw_insights = output.get("insights", [])
    if not isinstance(raw_insights, list):
        raw_insights = []

    # 用集合做精确 token 匹配，不能用子串包含——"5" 不能因为 "45" 里含 "5" 就被判定为可验证。
    available_numbers = set(_NUMBER_RE.findall(serialized))

    verified: list[dict] = []
    for text in raw_insights:
        if not isinstance(text, str) or not text.strip():
            continue
        numbers = _NUMBER_RE.findall(text)
        if all(number in available_numbers for number in numbers):
            verified.append({"text": text})

    return verified
