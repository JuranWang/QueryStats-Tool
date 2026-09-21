import sqlite3

import pandas as pd
import pytest

from engine.db import (
    add_document,
    create_project,
    init_db,
    list_conclusions,
    list_documents,
    read_autosave,
    touch_document,
    touch_project,
    write_autosave,
)
from engine.persistence import load_analysis, save_analysis, update_analysis


def _project(conn):
    return create_project(conn, "测试项目", "en", "zh-CN")


def test_schema_extensions_are_created(tmp_path):
    conn = init_db(str(tmp_path / "schema.sqlite"))
    columns = {
        table: {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        for table in ("projects", "documents", "questions")
    }
    assert "updated_at" in columns["projects"]
    assert {"research_type", "title", "updated_at"} <= columns["documents"]
    assert "meta_json" in columns["questions"]


def test_add_document_defaults_overrides_and_check_constraint(tmp_path):
    conn = init_db(str(tmp_path / "documents.sqlite"))
    project_id = _project(conn)
    default_id = add_document(conn, project_id, "default.csv", "csv")
    custom_id = add_document(
        conn,
        project_id,
        "custom.csv",
        "csv",
        research_type="qualitative",
        title="访谈分析",
    )

    default = conn.execute(
        "SELECT research_type, title FROM documents WHERE id = ?", (default_id,)
    ).fetchone()
    custom = conn.execute(
        "SELECT research_type, title FROM documents WHERE id = ?", (custom_id,)
    ).fetchone()
    assert tuple(default) == ("quant_survey", "default.csv")
    assert tuple(custom) == ("qualitative", "访谈分析")
    with pytest.raises(sqlite3.IntegrityError):
        add_document(
            conn, project_id, "invalid.csv", "csv", research_type="invalid"
        )


def test_list_documents_orders_and_filters(tmp_path):
    conn = init_db(str(tmp_path / "list.sqlite"))
    project_id = _project(conn)
    first = add_document(conn, project_id, "first.csv", "csv")
    second = add_document(
        conn, project_id, "second.csv", "csv", research_type="qualitative"
    )
    third = add_document(conn, project_id, "third.csv", "csv")
    for document_id, timestamp in (
        (first, "2026-01-01 00:00:00"),
        (second, "2026-01-03 00:00:00"),
        (third, "2026-01-02 00:00:00"),
    ):
        conn.execute(
            "UPDATE documents SET updated_at = ? WHERE id = ?",
            (timestamp, document_id),
        )
    conn.commit()

    assert [row["id"] for row in list_documents(conn, project_id)] == [
        second,
        third,
        first,
    ]
    assert [
        row["id"]
        for row in list_documents(conn, project_id, research_type="quant_survey")
    ] == [third, first]
    assert all(isinstance(row, dict) for row in list_documents(conn, project_id))


def test_save_and_load_analysis_round_trip(tmp_path):
    conn = init_db(str(tmp_path / "round-trip.sqlite"))
    project_id = _project(conn)
    df_all = pd.DataFrame(
        {
            "screen_col": ["Yes", "No", "Yes"],
            "single_col": ["A", "B", "A"],
            "multi_opt1": [True, False, True],
            "multi_opt2": [False, True, True],
            "open_col": ["good", "bad", "ok"],
            "numeric_col": [10, 20, 30],
        }
    )
    units = [
        {"kind": "single", "section": "筛选", "title": "Are you 18+?", "display_no": "S1", "columns": ["screen_col"]},
        {"kind": "single", "section": "正式", "title": "Pick one", "display_no": "Q1", "columns": ["single_col"]},
        {"kind": "multi", "section": "正式", "title": "Pick many", "display_no": "Q2", "columns": ["multi_opt1", "multi_opt2"]},
        {"kind": "open", "section": "正式", "title": "Why?", "display_no": "Q3", "columns": ["open_col"]},
        {"kind": "numeric", "section": "基础信息", "title": "Age", "display_no": "C1", "columns": ["numeric_col"]},
    ]
    test_method = {
        "platform_source": "Prolific",
        "is_branched": False,
        "branch_count": None,
        "screen_out_rule": "选 No 未通过",
        "skip_logic_note": "无",
    }
    document_id = save_analysis(
        conn,
        project_id,
        units,
        df_all,
        {"screen_col": ["No"]},
        {"Pick one": "选一个", "A": "甲", "Why?": "为什么？"},
        test_method,
        ["核心结论第一条", ""],
        "test.csv",
    )

    result = load_analysis(conn, document_id)
    assert result["df_all"]["S1"].tolist() == ["Yes", "No", "Yes"]
    assert result["df_all"]["Q1"].tolist() == ["A", "B", "A"]
    # 多选题现在存的是每个原始拆分列各自的真假值，加载回来要能重建出跟当初上传时
    # 一模一样的 N 个布尔列——不是合并好的选中项列表——"调整分组键"才有原始材料可以
    # 重新分组（真实反馈过：调整分组键改了没有实际效果，根源就是原来只存了合并结果）。
    assert result["df_all"]["multi_opt1"].tolist() == [True, False, True]
    assert result["df_all"]["multi_opt2"].tolist() == [False, True, True]
    assert result["df_all"]["Q3"].tolist() == ["good", "bad", "ok"]
    assert [int(value) for value in result["df_all"]["C1"]] == [10, 20, 30]
    assert result["screen_fail_values"] == {"S1": ["No"]}
    assert result["translation_cache"]["Pick one"] == "选一个"
    assert result["translation_cache"]["Why?"] == "为什么？"
    assert result["translation_cache"]["A"] == "甲"
    assert result["test_method"]["platform_source"] == "Prolific"
    assert result["conclusions"] == ["核心结论第一条"]
    assert result["research_type"] == "quant_survey"
    assert result["title"] == "test.csv"
    # 多选题的 columns 现在是原始拆分列名（能重新分组），其它题型还是老样子——
    # 内部生成的 display_no 当唯一一列。
    expected_units = [
        {**unit, "columns": unit["columns"] if unit["kind"] == "multi" else [unit["display_no"]]}
        for unit in units
    ]
    assert result["units"] == expected_units


def test_save_and_load_multi_select_uses_short_labels_and_option_translations(tmp_path):
    conn = init_db(str(tmp_path / "multi-labels.sqlite"))
    project_id = _project(conn)
    df_all = pd.DataFrame(
        {
            "Q1. Pick? (选项A)": [True, False, True],
            "Q1. Pick? (选项B)": [False, True, True],
        }
    )
    units = [
        {
            "kind": "multi",
            "section": "正式",
            "title": "Q1. Pick?",
            "display_no": "Q1",
            "columns": ["Q1. Pick? (选项A)", "Q1. Pick? (选项B)"],
        },
    ]
    test_method = {
        "platform_source": None,
        "is_branched": False,
        "branch_count": None,
        "screen_out_rule": None,
        "skip_logic_note": None,
    }

    document_id = save_analysis(
        conn,
        project_id,
        units,
        df_all,
        {},
        {"选项A": "Option A 中文", "选项B": "Option B 中文"},
        test_method,
        [],
        "test.csv",
    )

    result = load_analysis(conn, document_id)

    # 重建出来的是原始拆分列本身（布尔值），不是合并好的列表——这样"调整分组键"
    # 才能拿这两列重新分组，不是拿一个已经合并死的结果。
    assert result["df_all"]["Q1. Pick? (选项A)"].tolist() == [True, False, True]
    assert result["df_all"]["Q1. Pick? (选项B)"].tolist() == [False, True, True]
    assert result["units"][0]["columns"] == ["Q1. Pick? (选项A)", "Q1. Pick? (选项B)"]
    assert result["translation_cache"]["选项A"] == "Option A 中文"
    assert result["translation_cache"]["选项B"] == "Option B 中文"
    conn.close()


def test_load_multi_select_falls_back_for_legacy_merged_format(tmp_path):
    """兼容这次改动之前存的旧数据——那时候 raw_value 存的是"选中项标签用 ␟ 拼起来的
    字符串"，不是 JSON。旧数据要能正常加载（退化成一个合并列，没法重新分组，但至少
    不会因为格式换了就读不出来、甚至抛异常）。"""

    conn = init_db(str(tmp_path / "legacy-multi.sqlite"))
    project_id = _project(conn)
    df_all = pd.DataFrame(
        {
            "multi_opt1": [True, False, True],
            "multi_opt2": [False, True, True],
        }
    )
    units = [
        {
            "kind": "multi",
            "section": "正式",
            "title": "Pick many",
            "display_no": "Q2",
            "columns": ["multi_opt1", "multi_opt2"],
        },
    ]
    test_method = {
        "platform_source": None,
        "is_branched": False,
        "branch_count": None,
        "screen_out_rule": None,
        "skip_logic_note": None,
    }
    document_id = save_analysis(
        conn, project_id, units, df_all, {}, {}, test_method, [], "test.csv",
    )

    # 手动把这道题的 responses 改回旧格式（选中项标签用 ␟ 拼起来的字符串），
    # 模拟"这份文档是这次改动之前存的"。
    from engine.persistence import MULTI_VALUE_SEPARATOR

    question_id = conn.execute(
        "SELECT id FROM questions WHERE document_id = ? AND q_no = 'Q2'", (document_id,)
    ).fetchone()["id"]
    legacy_values = ["opt1", "opt2", MULTI_VALUE_SEPARATOR.join(["opt1", "opt2"])]
    for order_index, value in enumerate(legacy_values):
        conn.execute(
            "UPDATE responses SET raw_value = ? WHERE question_id = ? AND order_index = ?",
            (value, question_id, order_index),
        )
    conn.commit()

    result = load_analysis(conn, document_id)
    assert result["df_all"]["Q2"].tolist() == [["opt1"], ["opt2"], ["opt1", "opt2"]]
    assert result["units"][0]["columns"] == ["Q2"]
    conn.close()


def test_update_analysis_overwrites_in_place_without_duplicating_conclusions(tmp_path):
    # 手动保存：document_id 不变（历史列表里不多出一条），结论整份替换（不越存越多），
    # 而且要顺手清掉这份问卷的自动保存草稿——草稿已经不比这次手动保存新了。
    conn = init_db(str(tmp_path / "update.sqlite"))
    project_id = _project(conn)
    df_v1 = pd.DataFrame({"single_col": ["A", "B"]})
    units_v1 = [
        {"kind": "single", "section": "正式", "title": "Pick one", "display_no": "Q1", "columns": ["single_col"]},
    ]
    test_method = {
        "platform_source": "Prolific",
        "is_branched": False,
        "branch_count": None,
        "screen_out_rule": None,
        "skip_logic_note": None,
    }
    document_id = save_analysis(
        conn, project_id, units_v1, df_v1, {}, {}, test_method, ["第一版结论"], "test.csv",
    )
    write_autosave(conn, document_id, {"mapping": [{"column": "single_col"}]})

    df_v2 = pd.DataFrame({"single_col": ["A", "B", "C"]})
    units_v2 = [
        {"kind": "single", "section": "正式", "title": "Pick one", "display_no": "Q1", "columns": ["single_col"]},
    ]
    update_analysis(
        conn,
        document_id,
        project_id,
        units_v2,
        df_v2,
        {},
        {},
        test_method,
        ["第二版结论"],
        title="改过的标题",
    )

    assert len(list_documents(conn, project_id)) == 1
    result = load_analysis(conn, document_id)
    assert result["df_all"]["Q1"].tolist() == ["A", "B", "C"]
    assert result["title"] == "改过的标题"
    assert [c["text"] for c in list_conclusions(conn, project_id)] == ["第二版结论"]
    assert read_autosave(conn, document_id) is None
    conn.close()


def test_save_and_update_analysis_round_trip_extras(tmp_path):
    # AI 分类结果/图片/拖拽排版这些形状不适合拆表的内容——save_analysis 建档时能存，
    # update_analysis 手动保存时能整份覆盖（包括"这次没有了就该清空"），load_analysis
    # 能读回来，不会因为改了 questions/responses 就把 extras 落下。
    conn = init_db(str(tmp_path / "extras.sqlite"))
    project_id = _project(conn)
    df_v1 = pd.DataFrame({"single_col": ["A", "B"]})
    units = [
        {"kind": "single", "section": "正式", "title": "Pick one", "display_no": "Q1", "columns": ["single_col"]},
    ]
    test_method = {
        "platform_source": None, "is_branched": False, "branch_count": None,
        "screen_out_rule": None, "skip_logic_note": None,
    }
    extras_v1 = {
        "ai_results": {"Q3": {"categories": ["好", "差"], "assignments": [{"response_id": 0, "category": "好"}]}},
        "images": {"Q1": [{"name": "a.png", "caption": "示意图", "bytes_b64": "aGVsbG8="}]},
        "images_per_row": {"Q1": 2},
    }

    document_id = save_analysis(
        conn, project_id, units, df_v1, {}, {}, test_method, [], "test.csv", extras=extras_v1,
    )

    result = load_analysis(conn, document_id)
    assert result["extras"] == extras_v1

    # 手动保存时这次没有图片了（全删掉了）——extras 应该整份覆盖成新的，不是残留旧图片。
    extras_v2 = {"ai_results": {}, "images": {}, "images_per_row": {}}
    update_analysis(
        conn, document_id, project_id, units, df_v1, {}, {}, test_method, [], extras=extras_v2,
    )

    result2 = load_analysis(conn, document_id)
    assert result2["extras"] == extras_v2
    conn.close()


def test_save_analysis_without_extras_defaults_to_empty_dict(tmp_path):
    conn = init_db(str(tmp_path / "no-extras.sqlite"))
    project_id = _project(conn)
    df_all = pd.DataFrame({"single_col": ["A"]})
    units = [
        {"kind": "single", "section": "正式", "title": "Pick one", "display_no": "Q1", "columns": ["single_col"]},
    ]
    test_method = {
        "platform_source": None, "is_branched": False, "branch_count": None,
        "screen_out_rule": None, "skip_logic_note": None,
    }

    document_id = save_analysis(conn, project_id, units, df_all, {}, {}, test_method, [], "test.csv")

    assert load_analysis(conn, document_id)["extras"] == {}
    conn.close()


def test_touch_timestamps_are_present_and_non_decreasing(tmp_path):
    conn = init_db(str(tmp_path / "touch.sqlite"))
    project_id = _project(conn)
    document_id = add_document(conn, project_id, "test.csv", "csv")
    project_before = conn.execute(
        "SELECT updated_at FROM projects WHERE id = ?", (project_id,)
    ).fetchone()[0]
    document_before = conn.execute(
        "SELECT updated_at FROM documents WHERE id = ?", (document_id,)
    ).fetchone()[0]

    touch_project(conn, project_id)
    touch_document(conn, document_id)
    project_after = conn.execute(
        "SELECT updated_at FROM projects WHERE id = ?", (project_id,)
    ).fetchone()[0]
    document_after = conn.execute(
        "SELECT updated_at FROM documents WHERE id = ?", (document_id,)
    ).fetchone()[0]
    assert project_after is not None and project_after >= project_before
    assert document_after is not None and document_after >= document_before
