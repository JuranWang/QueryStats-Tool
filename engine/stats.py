"""Survey statistics and client-facing number formatting."""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

import pandas as pd


def format_pct(count: int, total: int) -> str:
    """Format a count as a percentage with exactly one decimal place."""

    percentage = 0.0 if total == 0 else round(count / total * 100, 1)
    return f"{percentage:.1f}%"


def format_count_pct(count: int, total: int) -> str:
    """Format evidence as a concrete respondent count and percentage."""

    return f"{count}人（{format_pct(count, total)}）"


def _ordered_observed_values(values: Iterable[Any], order: list[str] | None) -> list[Any]:
    observed = list(dict.fromkeys(values))
    if order is None:
        return observed
    ordered = [value for requested in order for value in observed if value == requested]
    ordered.extend(value for value in observed if value not in ordered)
    return ordered


def _stats_rows(counts: Counter, options: list[Any], total: int) -> list[dict]:
    return [
        {
            "option": str(option),
            "n": int(counts[option]),
            "pct": 0.0 if total == 0 else round(counts[option] / total * 100, 1),
            "count_pct_label": format_count_pct(int(counts[option]), total),
        }
        for option in options
    ]


def single_choice_stats(
    series: pd.Series, order: list[str] | None = None
) -> list[dict]:
    """Calculate stable single-choice counts and percentages."""

    values = series.dropna().tolist()
    counts = Counter(values)
    first_seen = _ordered_observed_values(values, order)
    if order is None:
        first_seen.sort(key=lambda value: -counts[value])
    return _stats_rows(counts, first_seen, len(values))


def multi_choice_stats(
    list_series: pd.Series, order: list[str] | None = None
) -> list[dict]:
    """Calculate multi-choice rates using respondent count as denominator."""

    flattened: list[Any] = []
    for choices in list_series:
        if isinstance(choices, (list, tuple)):
            flattened.extend(choices)
    counts = Counter(flattened)
    options = _ordered_observed_values(flattened, order)
    if order is None:
        options.sort(key=lambda value: -counts[value])
    return _stats_rows(counts, options, len(list_series))


def numeric_stats(series: pd.Series) -> dict:
    """Return descriptive statistics after coercing invalid values to NaN."""

    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return {"n": 0, "mean": float("nan"), "median": float("nan"), "min": float("nan"), "max": float("nan")}
    return {
        "n": int(numeric.count()),
        "mean": round(float(numeric.mean()), 1),
        "median": round(float(numeric.median()), 1),
        "min": float(numeric.min()),
        "max": float(numeric.max()),
    }


def crosstab_counts(
    df: pd.DataFrame,
    group_col: str,
    answer_col: str,
    group_order: list[str] | None = None,
    answer_order: list[str] | None = None,
    group_totals: dict[str, int] | None = None,
) -> pd.DataFrame:
    """Build a formatted answer-by-group table with group-based denominators.

    group_totals：可选，显式指定每个分组的分母（人数）。交叉分析"对比到哪道题"
    支持多选题之后才需要这个参数——多选题一个人可能同时选中好几个选项，构造
    交叉表之前调用方（app.py）要把"人 × 选中的选项"展开成一行一个（explode），
    展开之后同一个分组会出现好几行（一个人选了几个选项就出现几行）。这时候如果
    还用默认算法 `df[group_col].eq(group).sum()` 当分母，算出来的是"选项被选中的
    次数"而不是"人数"，选得越多分母被撑得越大，百分比会算错。传这个参数就能绕开
    默认算法，直接用调用方在展开之前、按真实受访者算好的人数——单选题的调用方
    不传这个参数，行为跟以前完全一样。
    """

    # 真实测试跑真实数据才挖出来的坑：多选题那条路传进来的 df 是 explode() 展开过的
    # ——explode 会保留原来的行号，一个人选了 3 个选项，展开后这一行的原始索引会
    # 重复出现 3 次，索引里就有重复值了。pd.crosstab 内部有一步要按索引对齐/reindex，
    # 索引有重复会直接抛 "cannot reindex on an axis with duplicate labels"。这里
    # 统一 reset_index，不管调用方传进来的索引长什么样都先归零成 0,1,2,...，跟
    # 单选题那条路（索引本来就不重复）也没有副作用，属于让这个函数本身更皮实的
    # 防御性修复，不是只给多选题这一种情况打补丁。
    working = df[[group_col, answer_col]].dropna().reset_index(drop=True)
    observed_groups = list(dict.fromkeys(df[group_col].dropna().tolist()))
    observed_answers = list(dict.fromkeys(df[answer_col].dropna().tolist()))

    # 显式传了 order 时，原样保留整份名单——哪怕某个组一个人都没有，也要出现在结果里
    # （比如交叉分析"圈选组 vs 其余"，用户明确要看这两组的对比，"其余"是 0 人本身就是一个
    # 值得看到的结果，不该因为没人就把这一列悄悄删掉，看起来像是漏了一组）。
    # 没传 order 才退回"只列数据里实际出现过的值"这个默认行为。
    groups = list(group_order) if group_order is not None else observed_groups
    answers = list(answer_order) if answer_order is not None else observed_answers
    raw = pd.crosstab(working[answer_col], working[group_col]).reindex(
        index=answers, columns=groups, fill_value=0
    )
    totals = raw.sum(axis=1)
    if answer_order is None:
        raw = raw.loc[sorted(answers, key=lambda value: -totals[value])]

    def _group_total(group: str) -> int:
        if group_totals is not None:
            return int(group_totals.get(group, 0))
        return int(df[group_col].eq(group).sum())

    formatted = pd.DataFrame(index=raw.index)
    for group in groups:
        group_total = _group_total(group)
        formatted[group] = [
            format_count_pct(int(count), group_total) for count in raw[group]
        ]

    total_name = "三组合计" if len(groups) == 3 else "合计"
    overall_total = sum(_group_total(group) for group in groups)
    formatted[total_name] = [
        format_count_pct(int(count), overall_total) for count in raw.sum(axis=1)
    ]
    formatted.index.name = answer_col
    return formatted
