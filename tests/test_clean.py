import pandas as pd
import pytest

from engine.clean import (
    apply_screen_out,
    dedupe,
    detect_multi_select_groups,
    detect_ranking_groups,
    drop_leading_metadata_row,
    looks_like_metadata_row,
    looks_like_reason_followup_question,
    merge_ab,
    merge_multi_select_columns,
    option_labels_for_group,
    summarize_dropouts,
)


def test_detect_ranking_groups_credamo_and_mixed_multi():
    title = "__TEST__以下几种材料是地毯背面的防滑点，\n请按价值感从高到低排序"
    columns = [f"{title}-{option}" for option in ("硅基", "铂金硅", "液态硅", "弹性硅")]
    df = pd.DataFrame([["1", "2", "3", "4"], ["4", "3", "1", "2"]], columns=columns)
    df["__TEST__多选-A"] = [True, False]
    df["__TEST__多选-B"] = [False, True]
    assert detect_ranking_groups(df) == {title: columns}
    assert detect_multi_select_groups(df) == (
        {"__TEST__多选": ["__TEST__多选-A", "__TEST__多选-B"]}, set()
    )


@pytest.mark.parametrize("values", [
    [[1], [1]],
    [["1", "bad"]],
    [[0, 2]],
    [[1, 3]],
    [[1.5, 2]],
    [[float("inf"), 2]],
    [[5, 5, 5, 5, 5]],
    [[1, 1], [2, 2]],
    [[None, None]],
    [],
])
def test_detect_ranking_groups_rejects_invalid_or_rating_matrix(values):
    size = len(values[0]) if values else 2
    df = pd.DataFrame(values, columns=[f"__TEST__题干-{i}" for i in range(size)])
    assert detect_ranking_groups(df) == {}


@pytest.mark.parametrize("complete_count,expected", [(9, True), (8, False)])
def test_detect_ranking_groups_90_percent_of_answered_rows(complete_count, expected):
    columns = ["__TEST__Rank (A)", "__TEST__Rank (B)"]
    df = pd.DataFrame(
        [["1", "2"]] * complete_count
        + [["1", None]] * (10 - complete_count)
        + [[None, None]] * 20,
        columns=columns,
    )
    assert detect_ranking_groups(df) == ({"__TEST__Rank": columns} if expected else {})


def test_dedupe_keeps_first_respondent_row():
    df = pd.DataFrame(
        {"respondent_id": ["r1", "r1", "r2"], "answer": ["first", "later", "only"]}
    )

    result = dedupe(df, "respondent_id")

    assert result.to_dict("records") == [
        {"respondent_id": "r1", "answer": "first"},
        {"respondent_id": "r2", "answer": "only"},
    ]


def test_apply_screen_out_separates_invalid_rows():
    df = pd.DataFrame(
        {"respondent_id": ["r1", "r2", "r3"], "status": ["valid", "screened", "valid"]}
    )

    valid, screened = apply_screen_out(df, "status", ["screened"])

    assert valid["respondent_id"].tolist() == ["r1", "r3"]
    assert screened["respondent_id"].tolist() == ["r2"]
    assert set(valid["respondent_id"]).isdisjoint(screened["respondent_id"])


def test_merge_ab_retains_only_submitted_b_and_suffixes_overlap():
    df_a = pd.DataFrame(
        {"respondent_id": ["r1", "r2", "r3"], "score": [1, 2, 3]}
    )
    df_b = pd.DataFrame(
        {
            "respondent_id": ["r1", "r2", "r3"],
            "submitted": [True, "yes", "否"],
            "score": [4, 5, 6],
        }
    )

    result = merge_ab(df_a, df_b, "respondent_id", "submitted")

    assert result["respondent_id"].tolist() == ["r1", "r2"]
    assert result.columns.tolist() == ["respondent_id", "score", "submitted", "score_b"]
    assert result["score"].tolist() == [1, 2]
    assert result["score_b"].tolist() == [4, 5]


def test_summarize_dropouts_only_returns_counts_and_ids():
    before = pd.DataFrame({"respondent_id": ["r1", "r2", "r3"]})
    after = pd.DataFrame({"respondent_id": ["r1", "r3"]})

    assert summarize_dropouts(before, after, "respondent_id") == {
        "before": 3,
        "after": 2,
        "dropped": 1,
        "dropped_ids": ["r2"],
    }


def test_merge_multi_select_columns_uses_labels_and_column_order():
    df = pd.DataFrame(
        {"quality": [1, 0], "price": [True, False], "design": [0, "是"]}
    )

    result = merge_multi_select_columns(
        df,
        ["quality", "price", "design"],
        {"quality": "品质", "price": "价格", "design": "设计"},
    )

    assert result.tolist() == [["品质", "价格"], ["设计"]]


def test_merge_multi_select_columns_recognizes_string_one_and_zero():
    # 真实见数/Credamo 导出的一份数据里，多选题布尔列的取值是字符串"1"/"0"（不是原生
    # 数字或布尔值）——之前 _is_truthy 的字符串分支只认"是"/"yes"，字符串"1"会被判定成
    # "未选中"，导致这道多选题 150 人全部零选择，图表整个是空的。
    df = pd.DataFrame({"opt_a": ["1", "0"], "opt_b": ["0", "1"]})

    result = merge_multi_select_columns(df, ["opt_a", "opt_b"])

    assert result.tolist() == [["opt_a"], ["opt_b"]]


def test_option_labels_for_group_recognizes_tally_style():
    assert option_labels_for_group(["Q1 (A)", "Q1 (B)"]) == {
        "Q1 (A)": "A",
        "Q1 (B)": "B",
    }


def test_option_labels_for_group_preserves_nested_parentheses_in_tally_option():
    cols = [
        "Q6. How is the heat delivered? (Warm air blown through vents/ducts (forced air))",
        "Q6. How is the heat delivered? (Not sure)",
    ]

    result = option_labels_for_group(cols)

    assert result[cols[0]] == "Warm air blown through vents/ducts (forced air)"
    assert result[cols[1]] == "Not sure"


def test_option_labels_for_group_recognizes_credamo_dash_style():
    assert option_labels_for_group(["胶-热熔胶", "胶-硅胶"]) == {
        "胶-热熔胶": "热熔胶",
        "胶-硅胶": "硅胶",
    }


def test_option_labels_for_group_keeps_single_column_unchanged():
    assert option_labels_for_group(["Q1 (A)"]) == {"Q1 (A)": "Q1 (A)"}


def test_looks_like_metadata_row_flags_field_code_row():
    # 见数式两行表头：第一行（已经是列名）是完整题目，第二行是内部字段代码。
    df = pd.DataFrame(
        {
            "作答ID": ["作答ID", "r_1001", "r_1002"],
            "您的年龄": ["Q1", "28", "35"],
            "以下这些东西，你会把哪些算作胶-热熔胶": ["Q5_1", "是", "否"],
        }
    )

    assert looks_like_metadata_row(df.iloc[0])
    assert not looks_like_metadata_row(df.iloc[1])


def test_looks_like_metadata_row_does_not_flag_real_open_ended_answers():
    df = pd.DataFrame(
        {
            "respondent_id": ["r1", "r2"],
            "为什么这么觉得？": [
                "因为硅胶本身不算胶水，只是材质相似，不应该混为一谈。",
                "我觉得只要能粘合固定作用的都算胶。",
            ],
        }
    )

    assert not looks_like_metadata_row(df.iloc[0])


def test_looks_like_metadata_row_flags_code_prefix_glued_to_original_title():
    # 分流/多轮重复题（比如同一套子问题在 Q1/Q2/Q3 三轮里各出现一次）的字段代码行，
    # 见数/Credamo 有时给的不是干净的"Q5_1"，而是"Q1_1_"这种代码前缀直接拼上原始题干——
    # 整体不满足"纯代码"格式（含中文、超长），但前缀部分仍然一望而知是内部字段代码。
    df = pd.DataFrame(
        {
            "这个人给你的第一印象是？[image]": [
                "Q1_1_这个人给你的第一印象是？[image]",
                "稳重、专业。",
            ],
            "以下两位男士，你对哪一位更有好感": [
                "Q1_7_以下两位男士，你对哪一位更有好感",
                "左边那位",
            ],
        }
    )

    assert looks_like_metadata_row(df.iloc[0])
    assert not looks_like_metadata_row(df.iloc[1])


def test_drop_leading_metadata_row_strips_only_when_detected():
    with_metadata = pd.DataFrame(
        {"id": ["id", "r1", "r2"], "age": ["Q1", "28", "35"]}
    )
    cleaned, dropped = drop_leading_metadata_row(with_metadata)
    assert dropped is True
    assert cleaned["id"].tolist() == ["r1", "r2"]
    assert cleaned.index.tolist() == [0, 1]

    without_metadata = pd.DataFrame({"id": ["r1", "r2"], "age": ["28", "35"]})
    cleaned2, dropped2 = drop_leading_metadata_row(without_metadata)
    assert dropped2 is False
    assert cleaned2.equals(without_metadata)


def test_looks_like_reason_followup_question_recognizes_reason_wording():
    assert looks_like_reason_followup_question("简单说一下原因")
    assert looks_like_reason_followup_question("为什么这么选择？")
    assert looks_like_reason_followup_question("Why did you choose that?")


def test_looks_like_reason_followup_question_does_not_flag_unrelated_open_question():
    assert not looks_like_reason_followup_question("某人在产生这类需求时会搜索什么？")


def test_detect_multi_select_groups_handles_option_text_with_nested_parentheses():
    # 真实 Tally 数据复现过的 bug：多选题的某个选项文字本身带括号说明（比如
    # "Warm air blown through vents/ducts (forced air)"），拆分列名就变成
    # "题干 (选项 (说明))" 这种嵌套括号。之前用 rindex(" (") 找最后一个左括号，
    # 会切到内层的左括号，算出来的"题干"带着半截选项文字，跟其他兄弟列的题干对不上，
    # 这一列就会掉出分组、退化成一道假的单选题。
    df = pd.DataFrame(
        {
            "Q6. How is the heat delivered? (Warm air blown through vents/ducts (forced air))": [True, False],
            "Q6. How is the heat delivered? (Radiant floor heating (warmth from the floor))": [False, True],
            "Q6. How is the heat delivered? (Not sure)": [False, False],
        }
    )

    groups, _ = detect_multi_select_groups(df)

    assert groups == {
        "Q6. How is the heat delivered?": [
            "Q6. How is the heat delivered? (Warm air blown through vents/ducts (forced air))",
            "Q6. How is the heat delivered? (Radiant floor heating (warmth from the floor))",
            "Q6. How is the heat delivered? (Not sure)",
        ]
    }


def test_looks_like_metadata_row_does_not_flag_real_respondent_heavy_in_booleans():
    # 真实数据复现过的另一个 bug：一份多选题很多的问卷，一个真实受访者的答案里
    # True/False 布尔值占了大多数（每道多选题拆出来的每个选项各占一列）——"True"/
    # "False" 本身字面上符合"字母开头、只有字母数字"这个"像字段代码"的粗筛条件，
    # 比例很容易冲到 70% 以上，会把一个完全正常的真实 respondent 误判成表头行整行
    # 剔除。真实的布尔值不该被当成"像代码"计入判断。
    df = pd.DataFrame(
        {
            "Q1. What type of home do you live in?": ["Single-family detached house"],
            "Q5 (Natural gas)": [True],
            "Q5 (Electricity)": [False],
            "Q5 (Propane)": [False],
            "Q5 (Solar)": [False],
            "Q5 (Wood)": [False],
            "Q5 (Not sure)": [False],
            "Q5 (Other)": [False],
        }
    )

    assert not looks_like_metadata_row(df.iloc[0])


def test_detect_multi_select_groups_recognizes_tally_style_with_summary_column():
    df = pd.DataFrame(
        {
            "Q4. Pick all that apply.": ["A, B", "B"],
            "Q4. Pick all that apply. (A)": [True, False],
            "Q4. Pick all that apply. (B)": [True, True],
            "Q1. Age": ["28", "35"],
        }
    )

    groups, summary_columns = detect_multi_select_groups(df)

    assert groups == {
        "Q4. Pick all that apply.": [
            "Q4. Pick all that apply. (A)",
            "Q4. Pick all that apply. (B)",
        ]
    }
    assert summary_columns == {"Q4. Pick all that apply."}


def test_detect_multi_select_groups_recognizes_credamo_style_without_summary_column():
    df = pd.DataFrame(
        {
            "你会把哪些算作胶-热熔胶": ["1", "0"],
            "你会把哪些算作胶-硅胶": ["0", "1"],
            "respondent_id": ["r1", "r2"],
        }
    )

    groups, summary_columns = detect_multi_select_groups(df)

    assert groups == {
        "你会把哪些算作胶": ["你会把哪些算作胶-热熔胶", "你会把哪些算作胶-硅胶"]
    }
    assert summary_columns == set()


def test_detect_multi_select_groups_ignores_non_boolean_lookalikes():
    # 价格区间"0-100"这种正常单选题，即使名字里带短横线，取值不是布尔值，不该被分组。
    df = pd.DataFrame(
        {
            "预算-0-100": ["常见", "少见"],
            "预算-100-200": ["少见", "常见"],
        }
    )

    groups, _ = detect_multi_select_groups(df)

    assert groups == {}


def test_detect_multi_select_groups_requires_at_least_two_sibling_columns():
    df = pd.DataFrame({"唯一选项-A": ["1", "0"], "respondent_id": ["r1", "r2"]})

    groups, _ = detect_multi_select_groups(df)

    assert groups == {}


def test_filter_valid_samples_matches_any_screen_out_and_preserves_input():
    from engine.clean import filter_valid_samples

    df = pd.DataFrame({'s1': ['fail', 'pass', 'fail', None, 'pass'],
                       's2': ['fail', 'fail', 'pass', None, 'pass']}, index=[8, 3, 9, 4, 2])
    original = df.copy(deep=True)
    result = filter_valid_samples(df, {'s1': ['fail'], 's2': ['fail'], 'unused': []})
    pd.testing.assert_frame_equal(result, df.loc[[4, 2]])
    pd.testing.assert_frame_equal(df, original)
    pd.testing.assert_frame_equal(filter_valid_samples(df, {}), df)
    pd.testing.assert_frame_equal(filter_valid_samples(df, {'s1': []}), df)
    assert filter_valid_samples(df.iloc[:0], {'s1': ['fail']}).empty
    assert filter_valid_samples(df.iloc[:3], {'s1': ['fail'], 's2': ['fail']}).empty
