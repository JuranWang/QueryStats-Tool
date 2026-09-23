"""Deterministic respondent-level survey cleanup."""

from __future__ import annotations

import os
import re
from typing import Any

import pandas as pd


def filter_valid_samples(df_all: pd.DataFrame, screen_fail_values: dict) -> pd.DataFrame:
    """Exclude respondents matching any configured screen-out value."""

    valid_mask = pd.Series(True, index=df_all.index)
    for col, fail_values in screen_fail_values.items():
        if fail_values:
            valid_mask &= ~df_all[col].isin(fail_values)
    return df_all[valid_mask]


_CODE_LIKE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,19}$")
# 见数/Credamo 有些导出（尤其是带分流/多轮重复题的问卷，比如"图片联想测试"这种一套
# 子问题在 Q1/Q2/Q3 三轮里重复出现的）字段代码不是干净的"Q5_1"，而是"Q1_1_"这种代码
# 前缀直接拼上原始题干本身，比如"Q1_1_这个人给你的第一印象是？[image]"——这种值整体
# 不满足 _CODE_LIKE_RE（含中文、超长），但前缀部分仍然是一望而知的内部字段代码，
# 真实的开放题回答不会凑巧以"字母+数字+下划线"开头。
_CODE_PREFIX_RE = re.compile(r"^[A-Za-z]{1,4}\d+(?:_\d+)*_")

# 多选题布尔列的"选中"取值——不同平台导出的字面量不一样：Tally/Prolific 这类是原生
# True/False，见数/Credamo 有的是"是"/"否"，有的（比如这次这份文件）是字符串"1"/"0"
# 而不是数字 1/0。以前 _is_truthy 的字符串分支只认"是"/"yes"，字符串"1"落不到下面数字
# 分支（isinstance(value, str) 已经提前 return 了），会被当成"未选中"——这个真实数据里
# 一整道多选题 150 人全部判定成"没选任何选项"，图表直接是空的，就是这么来的。
_TRUE_TOKENS = {"true", "1", "1.0", "是", "yes"}
_FALSE_TOKENS = {"false", "0", "0.0", "否", "no"}
_BOOLEAN_LIKE_TOKENS = _TRUE_TOKENS | _FALSE_TOKENS


def looks_like_metadata_row(row: pd.Series) -> bool:
    """判断某一行是不是"看起来像表头/字段代码"而不是真实回答。

    常见于国内问卷平台（见数等）导出的两行表头格式：第一行是完整题目文本（pandas 已经
    当列名用了），第二行是内部字段代码（比如"作答ID""Q1""Q5_1"）——如果不剔除，会被当成
    第一个受访者的真实答案，污染统计（比如某道单选题的分布里冒出一个 n=1 的诡异选项，
    值正好是字段代码，用户看到的现象就是"系统把问题也当成一个回答统计进去了"）。

    判断依据：这一行里，"值等于列名本身"、"值本身长得像一个字段代码"（字母开头、只有
    字母数字下划线、不超过 20 个字符——真实的开放题回答、地址、职业描述基本不会长这样）、
    或者"值以一个字段代码前缀开头"（比如"Q1_1_"，后面跟的是原始题干本身——分流/多轮
    重复题的字段代码常是这种"代码+原题干"拼接形式，不是干净的纯代码）的比例达到 70%
    以上，就判定为表头/代码行，不是真实数据。

    有一个例外必须排除：真实的布尔值（True/False/是/否/yes/no/0/1，多选题拆分列常见的
    取值）本身也满足"字母开头、只有字母数字"这个"像代码"的粗筛条件——一份多选题很多的
    问卷，一个真实受访者的一整行答案可能有大半都是这类布尔值（每道多选题拆出来的每个
    选项各占一列），比例很容易冲到 70% 以上，会把一个完全正常的真实respondent 误判成
    表头行、整行被剔除（这是拿真实数据复现过的 bug，不是假设）。所以布尔值不计入"像
    代码"的匹配次数，即使字面上符合 _CODE_LIKE_RE。
    """

    if row.empty:
        return False
    matches = 0
    for column, value in row.items():
        text = "" if pd.isna(value) else str(value)
        if text.strip().lower() in _BOOLEAN_LIKE_TOKENS:
            continue
        if (
            text == str(column)
            or _CODE_LIKE_RE.match(text)
            or _CODE_PREFIX_RE.match(text)
        ):
            matches += 1
    return matches / len(row) >= 0.7


def drop_leading_metadata_row(df: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    """如果第一行看起来是表头/字段代码而不是真实数据，剔除它。

    返回 (处理后的 df, 是否剔除了)——调用方应该把第二个值展示给用户看，不能悄悄丢一行
    数据不说一声（跟这个项目"不许猜、留证据"的一贯做法一致）。
    """

    if df.empty or not looks_like_metadata_row(df.iloc[0]):
        return df, False
    return df.iloc[1:].reset_index(drop=True), True


# 开放题题干是不是"追问上一题为什么这么选/为什么这么想"这种类型——命中就默认把紧邻
# 的上一题每个受访者自己的答案，当成上下文一起展示在这道开放题旁边；不命中默认不展示
# （比如"某人在产生某类需求时会搜索什么"这种开放题，跟上一题没什么关系，不需要）。
# 这只是一个默认值，页面上随时可以手动加/去掉要关联的题目，不是写死的规则。
_REASON_FOLLOWUP_KEYWORDS = ("为什么", "为何", "原因", "理由", "why", "reason")


def looks_like_reason_followup_question(title: str) -> bool:
    lowered = title.lower()
    return any(keyword in lowered for keyword in _REASON_FOLLOWUP_KEYWORDS)


def dedupe(df: pd.DataFrame, id_col: str) -> pd.DataFrame:
    """Keep the first row for each respondent identifier."""

    return df.drop_duplicates(subset=id_col, keep="first").copy()


def apply_screen_out(
    df: pd.DataFrame, screen_col: str, screen_out_values: list
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split rows into valid respondents and screened-out respondents."""

    screened_mask = df[screen_col].isin(screen_out_values)
    return df.loc[~screened_mask].copy(), df.loc[screened_mask].copy()


def _is_truthy(value: Any) -> bool:
    """Return whether a B-wave submission marker / multi-select cell counts as "selected"."""

    if isinstance(value, str):
        return value.strip().lower() in _TRUE_TOKENS
    try:
        if pd.isna(value):
            return False
        return bool(value == 1)
    except (TypeError, ValueError):
        return False


def merge_ab(
    df_a: pd.DataFrame, df_b: pd.DataFrame, key_col: str, b_submitted_col: str
) -> pd.DataFrame:
    """Join A and B respondents, retaining only submitted B records."""

    submitted_b = df_b.loc[df_b[b_submitted_col].map(_is_truthy)]
    return df_a.merge(
        submitted_b,
        on=key_col,
        how="inner",
        suffixes=("", "_b"),
        sort=False,
    )


def summarize_dropouts(
    df_before: pd.DataFrame, df_after: pd.DataFrame, id_col: str
) -> dict:
    """Report row loss and lost respondent IDs without interpreting it."""

    after_ids = set(df_after[id_col].tolist())
    dropped_ids = [value for value in df_before[id_col].tolist() if value not in after_ids]
    return {
        "before": len(df_before),
        "after": len(df_after),
        "dropped": len(df_before) - len(df_after),
        "dropped_ids": dropped_ids,
    }


def _is_boolean_like_series(series: pd.Series) -> bool:
    values = series.dropna()
    if values.empty:
        return False
    tokens = {str(v).strip().lower() for v in values.unique()}
    return tokens.issubset(_BOOLEAN_LIKE_TOKENS)


def _find_matching_open_paren(stripped: str) -> int | None:
    """假设 stripped 以 ')' 结尾，从后往前按括号深度找配对的 '(' 下标。"""

    depth = 0
    for i in range(len(stripped) - 1, -1, -1):
        char = stripped[i]
        if char == ")":
            depth += 1
        elif char == "(":
            depth -= 1
            if depth == 0:
                return i
    return None


def _multi_group_prefix(column: str) -> str | None:
    """如果这一列名字符合"题干 (选项)"（Tally 那种）或"题干-选项"（见数那种）这种
    多选题拆分列的常见命名规律，返回它的题干前缀；不符合返回 None。

    这只是"名字长得像"的初筛，真正判定要不要分组还得看 detect_multi_select_groups 里
    的取值检查——不然价格区间"0-100"这种正常单选题也会被误判。
    """

    stripped = column.rstrip()
    if stripped.endswith(")"):
        # 找跟最后这个 ")" 配对的"(" ——不能用 rindex(" (") 直接找最后一个左括号：
        # 选项文字自己带括号说明的时候（比如"Warm air blown through vents/ducts
        # (forced air)"这种，选项本身就是"(forced air)"，外层还包着 Tally 加的
        # "(选项)"括号），rindex 会找到内层那个左括号，切出来的"题干"会带着半截
        # 选项文字，导致这一列的前缀跟其他兄弟列对不上，从组里掉出去、退化成单选题
        # ——这是真实数据里复现过的 bug，不是假设。按括号深度从后往前找配对的左括号，
        # 才能正确处理这种嵌套括号。
        open_index = _find_matching_open_paren(stripped)
        if open_index is not None and open_index > 0 and stripped[open_index - 1] == " ":
            return stripped[:open_index].rstrip()
    if "-" in stripped:
        prefix, _, suffix = stripped.rpartition("-")
        # 短横线后面那段太长、或者带明显的整句标点（问号/句号），更像是题干本身
        # 凑巧带了个短横线，不是"题干-选项"这种拆分格式，不当分组前缀处理。
        if prefix and suffix and len(suffix) <= 30 and not any(p in suffix for p in "?？.。"):
            return prefix
    return None


def option_labels_for_group(cols: list[str]) -> dict[str, str]:
    """多选题一列一个选项时，原始列名常常是"题干-选项名"共享前缀，把前缀切掉更好读。

    两种常见格式都要处理，跟 `_multi_group_prefix` 用的是同一套括号识别规则：
    - Tally 那种"题干 (选项)"——每一列自己就带着选项文字，直接按括号拆，不需要跟别的列比对。
    - 见数那种"题干-选项"共享前缀——找公共前缀里最后一个分隔符，切掉前缀部分。
    如果不认括号这种格式，会退化成"整列原始题干当选项名"，图表和翻译都会拿一整句题干
    当选项显示，又长又不会被正确翻译（之前真出过这个 bug）。
    """

    if len(cols) < 2:
        return {c: c for c in cols}

    if all(c.rstrip().endswith(")") and " (" in c.rstrip() for c in cols):
        result = {}
        for c in cols:
            stripped = c.rstrip()
            # 跟 _multi_group_prefix 一样的坑，也用真实 Tally 数据复现过：选项文字
            # 本身带括号说明时，按括号深度从后往前找配对的左括号才能完整保留选项文字。
            open_index = _find_matching_open_paren(stripped)
            if open_index is not None and open_index > 0 and stripped[open_index - 1] == " ":
                option = stripped[open_index + 1 : -1].strip()
            else:
                option = stripped
            result[c] = option or c
        return result

    common = os.path.commonprefix(cols)
    cut = ""
    for sep in ("-", "_", "：", ":", "－"):
        idx = common.rfind(sep)
        if idx != -1 and idx + 1 > len(cut):
            cut = common[: idx + 1]
    if not cut:
        return {c: c for c in cols}
    return {c: (c[len(cut):].strip() or c) for c in cols}


def detect_multi_select_groups(df: pd.DataFrame) -> tuple[dict[str, list[str]], set[str]]:
    """自动识别"同一道多选题拆出来的选项列"——不管是见数的"题干-选项"还是 Tally 的
    "题干 (选项)"，只要列名符合这个规律、且这些列的取值以布尔值为主（True/False/1/0/
    是/否/yes/no），就判定成一组多选题选项列，不需要用户在映射表里手动一个个改。

    返回 (分组: {题干前缀: [原始列名,...]}, 多余的汇总列集合)。

    "多余的汇总列"专指 Tally 这类平台会额外导出的一列——列名正好等于题干前缀本身（没有
    选项后缀），内容是"选中的选项用逗号拼起来"的整句话，跟分组里几个布尔列携带的信息
    完全重复。这一列如果不排除，会被当成一道独立的开放题分析，回答内容全是逗号拼接的
    选项组合文本，等于同一份数据被数了两次，且这道"假开放题"毫无分析价值。
    """

    prefix_to_columns: dict[str, list[str]] = {}
    for column in df.columns:
        prefix = _multi_group_prefix(column)
        if prefix:
            prefix_to_columns.setdefault(prefix, []).append(column)

    groups: dict[str, list[str]] = {}
    summary_columns: set[str] = set()
    for prefix, option_columns in prefix_to_columns.items():
        if len(option_columns) < 2:
            continue
        if not all(_is_boolean_like_series(df[col]) for col in option_columns):
            continue
        groups[prefix] = option_columns
        if prefix in df.columns:
            summary_columns.add(prefix)

    return groups, summary_columns


def _looks_like_ranking_group(df: pd.DataFrame, option_columns: list[str]) -> bool:
    """Require integer ranks and complete permutations in at least 90% of answered rows."""

    max_rank = len(option_columns)
    if max_rank < 2:
        return False
    numeric = pd.DataFrame(index=df.index)
    for column in option_columns:
        values = df[column].dropna()
        ranks = pd.to_numeric(values, errors="coerce")
        if ranks.isna().any() or not (
            ranks.between(1, max_rank) & ranks.mod(1).eq(0)
        ).all():
            return False
        numeric[column] = pd.to_numeric(df[column], errors="coerce")

    answered = numeric.loc[numeric.notna().any(axis=1)]
    if answered.empty:
        return False
    expected = set(range(1, max_rank + 1))
    complete = answered.apply(lambda row: set(row.dropna()) == expected, axis=1)
    return bool(complete.mean() >= 0.9)


def detect_ranking_groups(df: pd.DataFrame) -> dict[str, list[str]]:
    """Group sibling option columns whose values form respondent-level rankings."""

    prefix_to_columns: dict[str, list[str]] = {}
    for column in df.columns:
        prefix = _multi_group_prefix(column)
        if prefix:
            prefix_to_columns.setdefault(prefix, []).append(column)

    return {
        prefix: option_columns
        for prefix, option_columns in prefix_to_columns.items()
        if _looks_like_ranking_group(df, option_columns)
    }


def merge_multi_select_columns(
    df: pd.DataFrame,
    option_cols: list[str],
    option_labels: dict[str, str] | None = None,
) -> pd.Series:
    """Combine boolean/0-1 option columns into ordered label lists."""

    labels = option_labels or {}
    return df[option_cols].apply(
        lambda row: [
            labels.get(column, column)
            for column in option_cols
            if _is_truthy(row[column])
        ],
        axis=1,
    )
