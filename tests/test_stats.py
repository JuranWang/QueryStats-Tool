import pandas as pd

from engine.stats import (
    crosstab_counts,
    format_count_pct,
    format_pct,
    multi_choice_stats,
    numeric_stats,
    ranking_option_stats,
    ranking_table,
    single_choice_stats,
)


def test_ranking_stats_and_table_use_each_options_non_null_base():
    df = pd.DataFrame({
        "__TEST__A": ["1", "1", "2", None],
        "__TEST__B": [2, None, 1, None],
    })
    result = ranking_option_stats(df, "__TEST__A", 3)
    assert result == [
        {"option": "1", "n": 2, "pct": 66.7, "count_pct_label": format_count_pct(2, 3)},
        {"option": "2", "n": 1, "pct": 33.3, "count_pct_label": format_count_pct(1, 3)},
        {"option": "3", "n": 0, "pct": 0.0, "count_pct_label": format_count_pct(0, 3)},
    ]
    table = ranking_table(df, list(df.columns), {"__TEST__A": "硅基", "__TEST__B": "铂金硅"}, 3)
    assert table.index.tolist() == ["第1名", "第2名", "第3名"]
    assert table.columns.tolist() == ["硅基", "铂金硅"]
    assert table["硅基"].tolist() == [row["count_pct_label"] for row in result]
    assert table["铂金硅"].tolist() == [format_count_pct(1, 2), format_count_pct(1, 2), format_count_pct(0, 2)]


def test_ranking_empty_option_and_english_rank_labels():
    from engine.i18n import set_lang

    df = pd.DataFrame({"__TEST__A": [None, None]})
    result = ranking_option_stats(df, "__TEST__A", 2)
    assert [row["n"] for row in result] == [0, 0]
    assert [row["pct"] for row in result] == [0.0, 0.0]
    set_lang("en")
    table = ranking_table(df, list(df.columns), {"__TEST__A": "Silicon"}, 2)
    assert table.index.tolist() == ["Rank 1", "Rank 2"]
    assert table.iloc[:, 0].tolist() == [format_count_pct(0, 0)] * 2


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


def test_compare_choice_union_missing_options_and_preserved_labels():
    from engine.stats import compare_choice_stats

    a = single_choice_stats(pd.Series(['A', 'A', 'B']))
    b = single_choice_stats(pd.Series(['B', 'C', 'C', 'C']))
    table = compare_choice_stats(a, b, '版本一', '版本二')
    assert table.columns.tolist() == ['版本一', '版本二', '差值']
    assert table.index.tolist() == ['A', 'B', 'C']
    assert table.values.tolist() == [
        [format_count_pct(2, 3), format_count_pct(0, 0), '-66.7pp'],
        [format_count_pct(1, 3), format_count_pct(1, 4), '-8.3pp'],
        [format_count_pct(0, 0), format_count_pct(3, 4), '+75.0pp'],
    ]


def test_compare_choice_multi_uses_respondents_not_sum_of_counts():
    from engine.stats import compare_choice_stats

    a = multi_choice_stats(pd.Series([['A', 'B'], ['A']]))
    b = multi_choice_stats(pd.Series([['A', 'B'], ['A', 'B'], []]))
    table = compare_choice_stats(a, b, 'a', 'b')
    assert table.loc['A'].tolist() == [format_count_pct(2, 2), format_count_pct(2, 3), '-33.3pp']
    assert table.loc['B'].tolist() == [format_count_pct(1, 2), format_count_pct(2, 3), '+16.7pp']


def test_compare_choice_rounding_zero_and_empty_inputs():
    from engine.stats import compare_choice_stats

    a = [{'option': 'A', 'n': 1, 'pct': 12.34, 'count_pct_label': 'original label'}]
    b = [{'option': 'A', 'n': 2, 'pct': 24.67, 'count_pct_label': 'other label'}]
    assert compare_choice_stats(a, b, 'a', 'b').loc['A'].tolist() == ['original label', 'other label', '+12.3pp']
    assert compare_choice_stats(b, a, 'a', 'b').loc['A', '差值'] == '-12.3pp'
    assert compare_choice_stats(a, a, 'a', 'b').loc['A', '差值'] == '0.0pp'
    assert compare_choice_stats([], a, 'a', 'b').loc['A', 'a'] == format_count_pct(0, 0)
    assert compare_choice_stats(a, [], 'a', 'b').loc['A', 'b'] == format_count_pct(0, 0)
    empty = compare_choice_stats([], [], 'a', 'b')
    assert empty.empty and empty.columns.tolist() == ['a', 'b', '差值']


def test_compare_numeric_only_mean_has_difference():
    from engine.stats import compare_numeric_stats

    a = numeric_stats(pd.Series([1, 2, 4, None]))
    b = numeric_stats(pd.Series([3, 4, 6, 7]))
    table = compare_numeric_stats(a, b, 'a', 'b')
    assert table.index.tolist() == ['N', '均值', '中位数', '最小', '最大']
    assert table.columns.tolist() == ['a', 'b', '差值']
    assert table['a'].tolist() == [3, 2.3, 2.0, 1.0, 4.0]
    assert table['b'].tolist() == [4, 5.0, 5.0, 3.0, 7.0]
    assert table['差值'].tolist() == ['', '+2.7', '', '', '']
    assert compare_numeric_stats(b, a, 'a', 'b').loc['均值', '差值'] == '-2.7'
    assert compare_numeric_stats(a, a, 'a', 'b').loc['均值', '差值'] == '0.0'
    empty = numeric_stats(pd.Series([], dtype=float))
    assert compare_numeric_stats(a, empty, 'a', 'b')['差值'].tolist() == [''] * 5


def test_comparisons_translate_headers_and_preserve_count_pct_format():
    from engine.i18n import set_lang
    from engine.stats import compare_choice_stats, compare_numeric_stats

    set_lang('en')
    rows = single_choice_stats(pd.Series(['A']))
    table = compare_choice_stats(rows, [], 'a', 'b')
    assert table.columns.tolist() == ['a', 'b', 'Difference']
    assert table.loc['A', 'a'] == format_count_pct(1, 1)
    assert table.loc['A', 'b'] == format_count_pct(0, 0)
    numeric = numeric_stats(pd.Series([1]))
    table = compare_numeric_stats(numeric, numeric, 'a', 'b')
    assert table.index.tolist() == ['N', 'Mean', 'Median', 'Minimum', 'Maximum']
    assert table.columns.tolist() == ['a', 'b', 'Difference']


def test_matching_question_candidates_kind_similarity_and_stable_ties():
    from engine.stats import matching_question_candidates

    current = {'kind': 'single', 'title': 'Favorite image'}
    candidates = [
        {'kind': 'single', 'title': 'Age'},
        {'kind': 'numeric', 'title': 'Favorite image'},
        {'kind': 'single', 'title': 'Favorite image?', 'id': 1},
        {'kind': 'single', 'title': 'Favorite image'},
        {'kind': 'single', 'title': 'Favorite image?', 'id': 2},
    ]
    original = candidates.copy()
    assert matching_question_candidates(current, candidates) == [candidates[i] for i in [3, 2, 4, 0]]
    assert candidates == original
    assert matching_question_candidates({'kind': 'multi', 'title': ''}, candidates) == []
    assert matching_question_candidates(current, []) == []
