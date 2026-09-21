import pandas as pd

from engine.stats import (
    crosstab_counts,
    format_count_pct,
    format_pct,
    multi_choice_stats,
    numeric_stats,
    single_choice_stats,
)


def test_format_count_pct_uses_one_decimal_place():
    assert format_count_pct(63, 201) == "63人（31.3%）"
    assert format_pct(1, 0) == "0.0%"


def test_single_choice_stats_default_descending_and_stable_ties():
    series = pd.Series(["B", "A", "B", "C", "A", "B"])

    result = single_choice_stats(series)

    assert [row["option"] for row in result] == ["B", "A", "C"]
    assert [row["n"] for row in result] == [3, 2, 1]
    assert result[0] == {
        "option": "B",
        "n": 3,
        "pct": 50.0,
        "count_pct_label": "3人（50.0%）",
    }


def test_single_choice_stats_respects_explicit_order_over_counts():
    series = pd.Series(["low", "high", "high", "high", "medium", "high"])

    result = single_choice_stats(series, order=["low", "medium", "high"])

    assert [row["option"] for row in result] == ["low", "medium", "high"]
    assert [row["n"] for row in result] == [1, 1, 4]


def test_multi_choice_stats_uses_sample_base_so_percentages_can_exceed_100():
    series = pd.Series(
        [["A", "B"], ["A", "C"], ["A", "B"]], dtype=object
    )

    result = multi_choice_stats(series)

    assert [row["n"] for row in result] == [3, 2, 1]
    assert [row["pct"] for row in result] == [100.0, 66.7, 33.3]
    assert sum(row["pct"] for row in result) == 200.0


def test_numeric_stats_discards_nan_and_rounds_mean_median():
    result = numeric_stats(pd.Series([1, 2, 4, None, "bad"]))

    assert result == {"n": 3, "mean": 2.3, "median": 2.0, "min": 1.0, "max": 4.0}


def test_crosstab_counts_uses_group_denominators_and_three_group_total():
    df = pd.DataFrame(
        {
            "group": ["B", "A", "A", "B", "C"],
            "answer": ["No", "Yes", "Yes", "Yes", "No"],
        }
    )

    result = crosstab_counts(df, "group", "answer")

    assert result.columns.tolist() == ["B", "A", "C", "三组合计"]
    assert result.index.tolist() == ["Yes", "No"]
    assert result.loc["Yes", "A"] == "2人（100.0%）"
    assert result.loc["Yes", "B"] == "1人（50.0%）"
    assert result.loc["Yes", "三组合计"] == "3人（60.0%）"


def test_crosstab_counts_respects_explicit_row_and_column_order():
    df = pd.DataFrame({"group": ["A", "B"], "answer": ["Yes", "No"]})

    result = crosstab_counts(
        df,
        "group",
        "answer",
        group_order=["B", "A"],
        answer_order=["No", "Yes"],
    )

    assert result.columns.tolist() == ["B", "A", "合计"]
    assert result.index.tolist() == ["No", "Yes"]


def test_crosstab_counts_keeps_explicitly_requested_group_even_with_zero_members():
    # 所有人都落在"圈选组"，"其余"一个人都没有——但既然调用方明确要看这两组的对比，
    # "其余"这一列必须出现（全 0），不能因为没人就悄悄从结果里消失，
    # 消失了看起来会像是"圈选组"和"合计"永远一样、分析坏掉了。
    df = pd.DataFrame({"group": ["圈选组", "圈选组", "圈选组"], "answer": ["A", "A", "B"]})

    result = crosstab_counts(df, "group", "answer", group_order=["圈选组", "其余"])

    assert result.columns.tolist() == ["圈选组", "其余", "合计"]
    assert result.loc["A", "其余"] == "0人（0.0%）"
    assert result.loc["A", "圈选组"] == "2人（66.7%）"
    assert result.loc["A", "合计"] == "2人（66.7%）"


def test_crosstab_counts_denominator_includes_group_member_with_missing_answer():
    df = pd.DataFrame(
        {"group": ["A", "A", "B"], "answer": ["Yes", None, "Yes"]}
    )

    result = crosstab_counts(df, "group", "answer")

    assert result.loc["Yes", "A"] == "1人（50.0%）"
    assert result.loc["Yes", "B"] == "1人（100.0%）"
    assert result.loc["Yes", "合计"] == "2人（66.7%）"


def test_crosstab_counts_group_totals_override_supports_exploded_multi_select():
    # 交叉分析"对比到哪道题"是多选题的场景：调用方会把"人 × 选中的选项"展开成
    # 一行一个再传进来——组 A 只有 2 个人，但 A 组里 1 号选了 2 个选项、2 号选了
    # 1 个选项，展开后 A 组出现 3 行。如果 crosstab_counts 还按展开后的行数
    # （df[group_col].eq("A").sum() == 3）当分母，会错误地把 A 组算成 3 个人；
    # 显式传 group_totals={"A": 2, "B": 1} 之后，分母必须用这份真实人数，不能被
    # 展开动作污染。
    exploded = pd.DataFrame(
        {
            "group": ["A", "A", "A", "B"],
            "answer": ["苹果", "香蕉", "苹果", "苹果"],
        }
    )

    result = crosstab_counts(
        exploded,
        "group",
        "answer",
        group_order=["A", "B"],
        group_totals={"A": 2, "B": 1},
    )

    # A 组真实只有 2 人，但 2 人一共选了 3 次"苹果"里的 2 次——分母是 2（人数），
    # 不是 3（展开后的行数）。
    assert result.loc["苹果", "A"] == "2人（100.0%）"
    assert result.loc["香蕉", "A"] == "1人（50.0%）"
    assert result.loc["苹果", "B"] == "1人（100.0%）"
    # 合计的分母也要用 group_totals 相加（2+1=3），不是展开后的行数（3+1=4）。
    assert result.loc["苹果", "合计"] == "3人（100.0%）"


def test_crosstab_counts_without_group_totals_keeps_old_default_behavior():
    # 不传 group_totals 的调用方（单选题那条路）行为要跟改动前完全一样。
    df = pd.DataFrame({"group": ["A", "A", "B"], "answer": ["Yes", "No", "Yes"]})

    result = crosstab_counts(df, "group", "answer")

    assert result.loc["Yes", "A"] == "1人（50.0%）"
    assert result.loc["Yes", "B"] == "1人（100.0%）"
