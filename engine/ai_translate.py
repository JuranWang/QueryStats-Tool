"""Faithful survey-verbatim translation with deterministic validation."""

from __future__ import annotations

import json
import re
import sqlite3

from . import db


PROMPT_VERSION = "v1"


def _has_translatable_text(text: str, protected_terms: list[str]) -> bool:
    remainder = re.sub(r"\d+", "", text)
    for term in protected_terms:
        remainder = re.sub(re.escape(term), "", remainder, flags=re.IGNORECASE)
    return any(character.isalpha() for character in remainder)


def _validate_translation(
    text_en: str, translation: str, protected_terms: list[str]
) -> list[str]:
    issues: list[str] = []
    for number in re.findall(r"\d+", text_en):
        if number not in translation:
            issues.append(f"missing_number:{number}")

    for term in protected_terms:
        matches = re.findall(re.escape(term), text_en, flags=re.IGNORECASE)
        if matches and any(
            source_spelling not in translation for source_spelling in matches
        ):
            issues.append(f"missing_term:{term}")

    if not translation.strip():
        issues.append("empty_translation")
    if (
        translation.strip() == text_en.strip()
        and _has_translatable_text(text_en, protected_terms)
    ):
        issues.append("untranslated")
    return issues


def translate_verbatims(
    provider,
    items: list[dict],
    protected_terms: list[str],
    batch_size: int = 40,
    conn: sqlite3.Connection | None = None,
    question_id: int | None = None,
) -> list[dict]:
    """Translate verbatims in batches and report validation issues unchanged."""

    if batch_size <= 0:
        raise ValueError("batch_size must be greater than zero")

    translations_by_id: dict[int, str] = {}
    for start in range(0, len(items), batch_size):
        batch = items[start : start + batch_size]
        system = "你负责忠实翻译问卷开放题原话。"
        user = (
            "逐句直译，不概括、不总结主题；阿拉伯数字原样保留；"
            "下面这些专有名词原样保留不翻译："
            f"{json.dumps(protected_terms, ensure_ascii=False)}。\n"
            "每条 response_id 必须出现且只出现一次。请只返回 JSON 对象，格式为："
            '{"translations": [{"response_id": 1, "translation": "译文"}]}。\n'
            f"待翻译回答：{json.dumps(batch, ensure_ascii=False)}"
        )
        output = provider.complete_json(system, user)
        if conn is not None and question_id is not None:
            db.log_ai_run(
                conn,
                question_id,
                "translate",
                PROMPT_VERSION,
                json.dumps(output, ensure_ascii=False),
            )

        batch_ids = {item["response_id"] for item in batch}
        returned = output.get("translations", [])
        if not isinstance(returned, list):
            returned = []
        for item in returned:
            if not isinstance(item, dict):
                continue
            response_id = item.get("response_id")
            translation = item.get("translation")
            if (
                response_id in batch_ids
                and response_id not in translations_by_id
                and isinstance(translation, str)
            ):
                translations_by_id[response_id] = translation

        for item in batch:
            translations_by_id.setdefault(item["response_id"], "")

    results: list[dict] = []
    for item in items:
        response_id = item["response_id"]
        translation = translations_by_id[response_id]
        issues = _validate_translation(item["text_en"], translation, protected_terms)
        results.append(
            {
                "response_id": response_id,
                "translation": translation,
                "valid": not issues,
                "issues": issues,
            }
        )
    return results
