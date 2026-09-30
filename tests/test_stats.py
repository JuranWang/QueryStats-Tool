import pandas as pd

from engine.stats import (
    crosstab_counts,
    format_count_pct,
    format_pct,
    loop_path_length_stats,
    multi_choice_stats,
    numeric_stats,
    ranking_option_stats,
    ranking_table,
    reshape_repeated_rounds,
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


# 真实反馈的问卷结构（"Home Shopping Study"）：受访者按时间顺序还原购买路径，
# 每一轮三道题——这一步做什么（action）、去哪个平台（platform）、为什么去那儿
# （开放题，这两个函数用不上）。最少两轮，最多五轮，第三轮起出现"退出"选项。
# 下面的列名/选项文字直接照抄真实问卷（不是编的），只是把受访人数缩小成方便
# 手算的规模。
EXIT_OPTION = "That was it — I was ready to buy"
ROUND_ACTION_COLS = ["Q9", "Q12", "Q15", "Q18", "Q21"]
ROUND_PLATFORM_COLS = ["Q10", "Q13", "Q16", "Q19", "Q22"]
ROUNDS = [
    {"action_col": a, "platform_col": p} for a, p in zip(ROUND_ACTION_COLS, ROUND_PLATFORM_COLS)
]


def _rug_journey_df() -> pd.DataFrame:
    # 4 位受访者，路径长度分别是 2/3/2/5（最短 2 轮、最长 5 轮，覆盖"最少两轮，
    # 最多五轮"这个真实约束），其中受访者 B 在第 3 轮主动选了退出选项。
    return pd.DataFrame({
        "Q9": [
            "Looking for ideas on what style would work",
            "Getting a sense of what rugs like this cost",
            "Looking for ideas on what style would work",
            "Getting a sense of what rugs like this cost",
        ],
        "Q10": [
            "Pinterest",
            "An online retailer (Amazon, Wayfair, Target, West Elm, etc.)",
            "Pinterest",
            "An online retailer (Amazon, Wayfair, Target, West Elm, etc.)",
        ],
        "Q12": [
            "Getting a sense of what rugs like this cost",
            "Reading what buyers said about a brand or a rug",
            "Getting a sense of what rugs like this cost",
            "Figuring out what material to get",
        ],
        "Q13": [
            "An online retailer (Amazon, Wayfair, Target, West Elm, etc.)",
            "Reddit",
            "An online retailer (Amazon, Wayfair, Target, West Elm, etc.)",
            "Google search",
        ],
        # respondent A：第 2 轮之后没再填，正常"只走了 2 轮"（不是主动退出）。
        "Q15": [None, EXIT_OPTION, None, "Reading what buyers said about a brand or a rug"],
        "Q16": [None, None, None, "Reddit"],
        "Q18": [None, None, None, "Looking for a better price on one I'd found"],
        "Q19": [None, None, None, "An online retailer (Amazon, Wayfair, Target, West Elm, etc.)"],
        "Q21": [None, None, None, EXIT_OPTION],
        "Q22": [None, None, None, None],
    })


class TestReshapeRepeatedRounds:
    """锁定"把 N 轮并列列展开成长表"这个核心行为——这是真实反馈里"matrix 逻辑"
    两个分析方向共同的数据基础，两个方向的统计（动作分布、动作×平台交叉）都是
    在这张长表上面算出来的，不是分别重新解析一遍原始列。
    """

    def test_skips_rounds_the_respondent_never_reached(self):
        df = _rug_journey_df()
        long_df = reshape_repeated_rounds(df, ROUNDS)
        # respondent 0（A）只填了第 1、2 轮，第 3～5 轮全是空值——长表里就该只有
        # 这个人的 2 行，不该出现"action 是 None"这种占位行。
        rows_for_a = long_df[long_df["respondent_id"] == 0]
        assert rows_for_a["round"].tolist() == [1, 2]

    def test_exit_option_row_is_kept_with_blank_platform(self):
        df = _rug_journey_df()
        long_df = reshape_repeated_rounds(df, ROUNDS)
        # respondent 1（B）第 3 轮选了退出选项——这一行的 action 应该原样保留
        # （长表本身对"退出"没有任何预设，只是如实展开），但 platform 是空的
        # （问卷设计里选了退出，后面的"去哪个平台"这道题本来就会被跳过）。
        exit_row = long_df[(long_df["respondent_id"] == 1) & (long_df["round"] == 3)]
        assert len(exit_row) == 1
        assert exit_row.iloc[0]["action"] == EXIT_OPTION
        assert pd.isna(exit_row.iloc[0]["platform"])

    def test_pooled_action_distribution_counts_across_all_rounds(self):
        # 真实反馈的第一个分析方向："不分第几轮，大家整体会做什么"——同一个
        # 动作在不同人身上可能发生在不同轮次，要能合并统计，不能只看某一轮。
        df = _rug_journey_df()
        long_df = reshape_repeated_rounds(df, ROUNDS)
        overall = single_choice_stats(long_df["action"])
        counts = {row["option"]: row["n"] for row in overall}
        # "Getting a sense of what rugs like this cost" 在 respondent 1、3 的第 1
        # 轮和 respondent 0、2 的第 2 轮都出现过，一共 4 次，尽管出现在不同的
        # 轮次里、不同的人身上。
        assert counts["Getting a sense of what rugs like this cost"] == 4

    def test_action_by_platform_crosstab_answers_where_people_go_for_an_action(self):
        # 真实反馈的第二个分析方向："做某个具体动作的人，主要去了哪个平台"——
        # 这是真正跨轮次的交叉表：respondent_id 相同的人可能这次是在第 1 轮做
        # 这件事、下次是在第 2 轮，都要能配对到各自当时去的平台。
        df = _rug_journey_df()
        long_df = reshape_repeated_rounds(df, ROUNDS)
        paired = long_df.dropna(subset=["platform"])
        table = crosstab_counts(paired, group_col="action", answer_col="platform")
        # "Looking for ideas on what style would work"这个动作，respondent 0 和
        # respondent 2 都在第 1 轮做过、都去了 Pinterest——分母是"做过这件事的
        # 2 个人"，不是"长表里这个动作出现的行数"（虽然这次两者恰好相等）。
        assert table.loc["Pinterest", "Looking for ideas on what style would work"] == format_count_pct(2, 2)


class TestLoopPathLengthStats:
    """锁定"路径长度/退出点"这个派生指标——真实反馈"哪一步之后人们觉得够了可以
    买了，这是转化临界点"，需要能区分"主动选了退出"和"就是没有再往下填"两种
    没有更多数据的情况。
    """

    def test_distinguishes_natural_stop_from_explicit_exit_choice(self):
        df = _rug_journey_df()
        result = loop_path_length_stats(df, ROUND_ACTION_COLS, exit_values=[EXIT_OPTION])
        by_id = {row["respondent_id"]: row for _, row in result.iterrows()}

        # respondent 0（A）：填到第 2 轮就留空，不是主动退出——path_length=2，
        # exit_round 是 pd.NA。
        assert by_id[0]["path_length"] == 2
        assert pd.isna(by_id[0]["exit_round"])

        # respondent 1（B）：第 3 轮主动选了退出——真正走过的是前 2 轮
        # （path_length=2，退出那一轮不算"做了什么"），exit_round=3。
        assert by_id[1]["path_length"] == 2
        assert by_id[1]["exit_round"] == 3

        # respondent 3（D）：走满全部 5 轮，最后一轮本身就是主动退出。
        assert by_id[3]["path_length"] == 4
        assert by_id[3]["exit_round"] == 5

    def test_path_length_distribution_matches_manual_count(self):
        # 4 人里：respondent 0 和 2 都是 2 轮，respondent 1 是 2 轮，
        # respondent 3 是 4 轮——path_length=2 的应该有 3 人。
        df = _rug_journey_df()
        result = loop_path_length_stats(df, ROUND_ACTION_COLS, exit_values=[EXIT_OPTION])
        distribution = single_choice_stats(result["path_length"].astype(str))
        counts = {row["option"]: row["n"] for row in distribution}
        assert counts["2"] == 3
        assert counts["4"] == 1
