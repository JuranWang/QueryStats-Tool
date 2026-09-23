"""用真实 section 8、临时 SQLite 和 AppTest 验证对称板块，不打开真实 app.db。"""

import ast
import base64
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from engine import db, persistence, stats, clean, chart_spec, export_word
from engine.i18n import t, set_lang

SOURCE = (Path(__file__).resolve().parents[1] / 'app_streamlit/app.py').read_text()
TREE = ast.parse(SOURCE)
FUNCTION_NAMES = {
    'render_crosstab_side', '_multi_select_list_series', 'assign_first_group',
    'all_matching_groups', 'dimension_stats_result', '_compute_crosstab_block_result',
    '_persist_crosstab_blocks', '_crosstab_blocks_payload', '_crosstab_state_payload', '_restore_extras',
}
FUNCTION_SOURCE = '\n\n'.join(
    ast.get_source_segment(SOURCE, node) for node in TREE.body
    if isinstance(node, ast.FunctionDef) and node.name in FUNCTION_NAMES
)
SECTION_SOURCE = next(
    ast.get_source_segment(SOURCE, node) for node in TREE.body
    if isinstance(node, ast.With) and 'key="section_paper_8"' in ast.get_source_segment(SOURCE, node).splitlines()[0]
)
SCRIPT = '''
import json
import pandas as pd
import streamlit as st
from engine import clean, stats, db, persistence, chart_spec
from engine.i18n import t, set_lang
set_lang(st.session_state.get("__TEST__lang", "zh"))
def _get_db_conn():
    return st.session_state["__TEST__conn"]
def render_chart(chart_type, config, key):
    st.session_state["__TEST__charts"].append((chart_type, config, key))
def _grouped_bar_snapshot_png_for_save(*args):
    return b"test png"
def _render_copy_image_button(png, key):
    st.caption(key)
def render_image_attachments_trigger(q_no):
    st.button("__TEST__insert", key="insert_" + q_no)
def render_image_attachments_grid(q_no):
    st.caption("__TEST__images")
st.session_state["__TEST__charts"] = []
loaded = persistence.load_analysis(_get_db_conn(), st.session_state["saved_document_id"])
units = loaded["units"]
df_valid = clean.filter_valid_samples(loaded["df_all"], loaded["screen_fail_values"])
''' + FUNCTION_SOURCE + '''
if st.session_state.pop("__TEST__restore", False):
    _restore_extras(loaded["extras"])
''' + SECTION_SOURCE + '\nst.caption("__TEST__later_sections")\n'


def functions(state=None):
    set_lang("zh")
    namespace = dict(pd=pd, stats=stats, clean=clean, chart_spec=chart_spec, persistence=persistence,
                     db=db, t=t, json=json, base64=base64, hashlib=hashlib,
                     st=SimpleNamespace(session_state={} if state is None else state))
    exec(FUNCTION_SOURCE, namespace)
    return namespace


def context(kind, values, groups=None, doc_id=None, label="版本一", rest=False):
    source = pd.Series(values)
    options = sorted(set(v for vals in values for v in vals), key=str) if kind == "multi" else sorted(source.dropna().unique(), key=str)
    groups = groups if groups is not None else [{"name": str(v), "values": [v]} for v in options]
    return dict(kind=kind, source_series=source, valid_groups=groups, include_rest=rest,
                group_order=[g["name"] for g in groups] + (["其余"] if rest else []),
                doc_id=doc_id, doc_label=label, unit={"display_no": "Q1"}, question_label="Q1｜Question")


def unit(kind, title, number, columns=None, section='正式'):
    return dict(kind=kind, title=title, display_no=number, columns=columns or [number], section=section)


@pytest.fixture
def comparison_app(tmp_path):
    conn = db.init_db(str(tmp_path / '__TEST__comparison.sqlite'))
    project = db.create_project(conn, '__TEST__current', 'en', 'zh')
    other_project = db.create_project(conn, '__TEST__other', 'en', 'zh')
    current_units = [
        unit('single', 'Favorite image', 'Q1'),
        unit('multi', 'Selected images', 'Q2', ['Q2 (A)', 'Q2 (B)']),
        unit('numeric', 'Rating', 'Q3'),
        unit('single', 'Screen', 'S1', section='筛选'),
    ]
    current_df = pd.DataFrame({
        'Q1': ['A', 'A', 'B', 'Excluded'], 'Q2 (A)': [True, True, False, True],
        'Q2 (B)': [True, False, True, True], 'Q3': [1, 2, 3, 100],
        'S1': ['pass', 'pass', 'pass', 'fail'],
    })
    other_units = [
        unit('single', 'Age group', 'Q9'),
        unit('numeric', 'Favorite image', 'Q8'),
        unit('single', 'Favorite image?', 'Q7'),
        unit('multi', 'Selected images?', 'Q6', ['Q6 (B)', 'Q6 (C)']),
        unit('numeric', 'Rating', 'Q5'),
        unit('single', 'Screen', 'S2', section='筛选'),
    ]
    other_df = pd.DataFrame({
        'Q9': ['X'] * 5, 'Q8': [7] * 5, 'Q7': ['B', 'C', 'C', 'C', 'Excluded'],
        'Q6 (B)': [True, False, False, False, True],
        'Q6 (C)': [True, True, True, False, True], 'Q5': [2, 4, 6, 8, 100],
        'S2': ['pass'] * 4 + ['fail'],
    })
    method = dict(platform_source=None, is_branched=False, branch_count=None,
                  screen_out_rule=None, skip_logic_note=None)
    current_id = persistence.save_analysis(conn, project, current_units, current_df, {'S1': ['fail']}, {}, method, [], 'v1.csv', title='版本一')
    target_id = persistence.save_analysis(conn, project, other_units, other_df, {'S2': ['fail']}, {}, method, [], 'v2.csv', title='版本二')
    external_id = persistence.save_analysis(conn, other_project, other_units, other_df, {'S2': ['fail']}, {}, method, [], 'v3.csv', title='版本三')
    db.add_document(conn, project, 'interview.csv', 'csv', research_type='qualitative')
    app = AppTest.from_string(SCRIPT)
    app.session_state['__TEST__conn'] = conn
    app.session_state['current_project_id'] = project
    app.session_state['saved_document_id'] = current_id
    app.session_state['document_title'] = '版本一'
    app.session_state['crosstab_history'] = {}
    app.run()
    assert not app.exception
    try:
        yield app, conn, project, other_project, target_id, external_id
    finally:
        conn.close()



@pytest.mark.parametrize("left_kind", ["single", "multi"])
@pytest.mark.parametrize("right_kind", ["single", "multi"])
def test_default_dimensions_equal_legacy_crosstab(left_kind, right_kind):
    # 人数顺序和选项顺序一致时，旧表和新表应逐项完全一致（含索引、轴名）。
    ns = functions()
    left = context(left_kind, ["A", "A", "B", "C"] if left_kind == "single" else [["A", "B"], ["A"], ["B"], ["C"]])
    right = context(right_kind, ["X", "X", "Y", "Z"] if right_kind == "single" else [["X", "Y"], ["X"], ["Y"], ["Z"]])
    group_col = left["source_series"].apply(lambda v: ns["assign_first_group"](v, left_kind, left["valid_groups"], False))
    legacy_input = pd.DataFrame({"分组": group_col.values, "对比题答案": right["source_series"].values})
    if right_kind == "multi":
        legacy_input = legacy_input.explode("对比题答案")
    legacy = stats.crosstab_counts(legacy_input, "分组", "对比题答案", group_order=left["group_order"],
                                  group_totals={g: int((group_col == g).sum()) for g in left["group_order"]})
    result = ns["_compute_crosstab_block_result"](left, right)
    pd.testing.assert_frame_equal(result["table"], legacy)
    assert result["chart_config"] is None and result["kind"] == "same_doc"


def test_same_doc_multi_groups_order_zero_counts_and_respondent_base():
    ns = functions()
    left = context("single", ["A", "A", "B", "C"], [dict(name=g, values=[g]) for g in ["C", "B", "A"]])
    right = context("multi", [["x", "y"], ["z"], ["y"], []], [
        dict(name="Combined", values=["x", "y"]), dict(name="Overlap", values=["y", "z"]), dict(name="Zero", values=["missing"]),
    ], rest=True)
    with patch.object(stats, "crosstab_counts", wraps=stats.crosstab_counts) as call:
        table = ns["_compute_crosstab_block_result"](left, right)["table"]
    assert call.call_args.kwargs == dict(group_order=["C", "B", "A"], answer_order=["Combined", "Overlap", "Zero", "其余"], group_totals={"C": 1, "B": 1, "A": 2})
    assert table.shape == (4, 4)
    assert table.loc["Combined", "A"] == "1人（50.0%）"
    assert table.loc["Overlap", "A"] == "2人（100.0%）"
    assert table.loc["Zero", "三组合计"] == "0人（0.0%）"
    assert table.loc["其余", "C"] == "1人（100.0%）"


def test_new_order_preserves_legacy_counts_even_when_legacy_sorted_by_frequency():
    ns = functions()
    left = context("single", ["A"] * 4)
    right = context("single", ["Z", "Z", "A", None])
    table = ns["_compute_crosstab_block_result"](left, right)["table"]
    legacy = stats.crosstab_counts(pd.DataFrame({"分组": ["A"] * 4, "对比题答案": ["Z", "Z", "A", None]}), "分组", "对比题答案", group_order=["A"], group_totals={"A": 4})
    assert list(table.index) == ["A", "Z"]
    pd.testing.assert_frame_equal(table, legacy.reindex(table.index))


def test_cross_doc_multi_counts_all_matches_without_exploding_denominator():
    ns = functions()
    left = context("multi", [["A", "B"], ["A"], ["B"], []], rest=True)
    right = context("single", ["B", "C", "C", "C"], doc_id=2, label="版本二")
    result = ns["_compute_crosstab_block_result"](left, right)
    table, config = result["table"], result["chart_config"]
    assert result["kind"] == "cross_doc"
    assert table.index.tolist() == ["A", "B", "其余", "C"]
    assert config["yAxis"]["data"] == list(table.index)
    assert [s["data"] for s in config["series"]] == [[50.0, 50.0, 25.0, 0.0], [0.0, 25.0, 0.0, 75.0]]
    assert table.loc["B", "差值"] == "-25.0pp"
    assert config["xAxis"]["axisLabel"] == {"formatter": "{value}%"}
    assert config["_footer"] == "有效样本：版本一 N=4；版本二 N=4"


def test_uncovered_missing_and_first_match_semantics():
    ns = functions()
    groups = [dict(name="First", values=["x"]), dict(name="Second", values=["x", "y"])]
    assert ns["assign_first_group"](["x", "y"], "multi", groups, False) == "First"
    assert ns["assign_first_group"](pd.NA, "single", groups, False) is None
    assert ns["all_matching_groups"](["x", "y"], groups, False) == ["First", "Second"]
    assert ns["all_matching_groups"]([], groups, False) == []
    rows = ns["dimension_stats_result"](pd.Series(["First", None]), ["First", "Zero"])
    assert [r["pct"] for r in rows] == [100.0, 0.0]
    assert ns["dimension_stats_result"](pd.Series([None]), ["First"])[0]["pct"] == 0.0


def test_save_crosstab_blocks_preserves_other_extras(tmp_path):
    conn = db.init_db(str(tmp_path / "test.sqlite"))
    try:
        project = db.create_project(conn, "Test", "en", "zh")
        doc = db.add_document(conn, project, "test.csv", "csv")
        extras = {"images": {"Q1": [{"name": "test.png"}]}, "ai_results": {"Q1": {"": {"categories": ["A"]}}}}
        db.write_document_extras(conn, doc, extras)
        payload = [{"id": "1", "left": {"doc_id": None, "question_key": "Q1"}, "right": {"doc_id": 2, "question_key": "Q2"}, "result": None}]
        persistence.save_crosstab_blocks(conn, doc, payload)
        assert db.read_document_extras(conn, doc) == {**extras, "crosstab_blocks": payload}
        persistence.save_crosstab_blocks(conn, doc, [])
        assert db.read_document_extras(conn, doc) == {**extras, "crosstab_blocks": []}
    finally:
        conn.close()


def test_grouped_bar_png_is_nonempty_and_valid(tmp_path):
    from PIL import Image
    target = tmp_path / "chart.png"
    export_word.render_grouped_bar_chart_image(["A", "B", "C"], [{"name": "Version 1", "data": [25, 50, 75]}, {"name": "Version 2", "data": [35, 45, 60]}], str(target), title="Comparison")
    assert target.stat().st_size > 1000
    with Image.open(target) as image:
        assert image.format == "PNG"
        image.verify()


def test_symmetric_selectors_exclude_current_numeric_and_include_all_projects(comparison_app):
    app, _, _, _, target_id, external_id = comparison_app
    assert not app.tabs
    for side in ["left", "right"]:
        select = app.selectbox(key=f"xtb_1_{side}_doc")
        # "本份问卷"这个选项对应的控件原始值是字符串哨兵 "__self__"，不是 Python 的
        # None——真机截图验证过：如果控件的选项列表里直接拿 None 当某个选项的值，
        # Streamlit 会把它跟"这个控件还没有任何选中项"搞混，界面上显示成占位提示
        # 文字而不是"本份问卷"，看起来像是什么都没选。app.py 里选完之后会在 Python
        # 逻辑里把这个哨兵值翻译回 None 再往下用（crosstab_blocks 落库格式等仍然是
        # None 表示本份问卷），这里断言的是控件本身的原始值，要跟着改。
        assert select.value == "__self__"
        assert len(select.options) == 3
        assert any(f"#{external_id}" in option for option in select.options)
        assert not any("Rating" in option for option in app.selectbox(key=f"xtb_1_{side}_question").options)
    app.selectbox(key="xtb_1_left_doc").select(external_id).run()
    app.selectbox(key="xtb_1_right_doc").select(target_id).run()
    app.button(key="xtb_1_run").click().run()
    assert not app.exception
    assert app.session_state["crosstab_blocks"][0]["result"]["kind"] == "cross_doc"


def test_two_blocks_roundtrip_groups_results_and_axes(comparison_app):
    app, conn, _, _, target_id, _ = comparison_app
    group_key = "xtb_1_left_groups::Q1｜Favorite image"
    app.text_input(key=f"{group_key}_name_0").set_value("Custom A").run()
    app.checkbox(key=f"{group_key}_rest").check().run()
    app.selectbox(key="xtb_1_right_question").select("Q2｜Selected images").run()
    app.button(key="xtb_1_run").click().run()
    app.button(key="xtb_add_block").click().run()
    app.selectbox(key="xtb_2_right_doc").select(target_id).run()
    app.selectbox(key="xtb_2_right_question").select("Q7｜Favorite image?").run()
    app.button(key="xtb_2_run").click().run()
    assert not app.exception
    blocks = app.session_state["crosstab_blocks"]
    extras = db.read_document_extras(conn, app.session_state["saved_document_id"])
    json.dumps(extras)
    assert len(extras["crosstab_blocks"]) == 2
    restored_state = {}
    functions(restored_state)["_restore_extras"](json.loads(json.dumps(extras)))
    for before, after in zip(blocks, restored_state["crosstab_blocks"]):
        assert before["left"] == after["left"] and before["right"] == after["right"]
        pd.testing.assert_frame_equal(before["result"]["table"], after["result"]["table"])
        assert before["result"]["chart_config"] == after["result"]["chart_config"]
    assert restored_state[group_key][0]["name"] == "Custom A"
    assert restored_state[f"{group_key}_rest"] is True
    reopened = AppTest.from_string(SCRIPT)
    for key in ["__TEST__conn", "saved_document_id", "document_title"]:
        reopened.session_state[key] = app.session_state[key]
    reopened.session_state["__TEST__restore"] = True
    reopened.run()
    assert not reopened.exception
    assert reopened.selectbox(key="xtb_1_right_question").value == "Q2｜Selected images"
    assert reopened.text_input(key=f"{group_key}_name_0").value == "Custom A"
    assert len(reopened.dataframe) == 2
    reopened.button(key="xtb_1_run").click().run()
    pd.testing.assert_frame_equal(blocks[0]["result"]["table"], reopened.session_state["crosstab_blocks"][0]["result"]["table"])


def test_delete_blocks_does_not_recycle_ids_or_export_old_results(comparison_app):
    app, conn, *_ = comparison_app
    app.button(key="xtb_1_run").click().run()
    app.button(key="xtb_add_block").click().run()
    app.button(key="xtb_1_delete_block").click().run()
    app.button(key="xtb_2_delete_block").click().run()
    assert app.session_state["crosstab_history"] == {}
    assert app.session_state["crosstab_blocks"] == []
    extras = db.read_document_extras(conn, app.session_state["saved_document_id"])
    state = {}
    functions(state)["_restore_extras"](extras)
    assert state["crosstab_next_block_id"] == 3
    app.button(key="xtb_add_block").click().run()
    assert not app.exception
    assert [b["id"] for b in app.session_state["crosstab_blocks"]] == ["3"]


def test_group_delete_reset_and_switch_do_not_reuse_widget_values(comparison_app):
    app, conn, _, _, target_id, _ = comparison_app
    key = "xtb_1_left_groups::Q1｜Favorite image"
    app.text_input(key=f"{key}_name_0").set_value("Custom").run()
    # 编辑中间状态不立即写库。
    assert "crosstab_blocks" not in db.read_document_extras(conn, app.session_state["saved_document_id"])
    app.button(key=f"{key}_del_0").click().run()
    assert app.text_input(key=f"{key}_name_0").value == "B"
    app.button(key=f"{key}_reset").click().run()
    assert app.text_input(key=f"{key}_name_0").value == "A"
    app.selectbox(key="xtb_1_left_doc").select(target_id).run()
    app.selectbox(key="xtb_1_left_doc").select(None).run()
    assert app.text_input(key=f"{key}_name_0").value == "A"
    assert not app.exception


def test_empty_survey_does_not_stop_later_sections(comparison_app):
    app, conn, _, _, target_id, _ = comparison_app
    conn.execute("UPDATE questions SET q_type = 'open' WHERE document_id = ?", (target_id,))
    conn.commit()
    app.selectbox(key="xtb_1_right_doc").select(target_id).run()
    assert not app.exception
    assert app.button(key="xtb_1_run").disabled
    assert app.caption[-1].value == "__TEST__later_sections"


def test_duplicate_document_labels_and_english_ui(comparison_app):
    app, conn, _, _, target_id, _ = comparison_app
    conn.execute("UPDATE documents SET title = '版本一' WHERE id = ?", (target_id,))
    conn.commit()
    app.selectbox(key="xtb_1_right_doc").select(target_id).run()
    app.button(key="xtb_1_run").click().run()
    assert app.dataframe[0].value.columns.tolist() == ["版本一（左侧）", "版本一（右侧）", "差值"]
    app.session_state["__TEST__lang"] = "en"
    app.run()
    assert app.selectbox(key="xtb_1_left_doc").label == "1. Choose a survey"
    assert app.button(key="xtb_add_block").label == "+ Add cross-analysis block"


def test_persist_no_document_is_noop():
    ns = functions({})
    with patch.object(persistence, "save_crosstab_blocks") as save:
        ns["_persist_crosstab_blocks"]()
    save.assert_not_called()


def test_grouped_bar_snapshot_cache_tracks_data_and_palette(tmp_path):
    import tempfile
    from engine.i18n import get_lang
    ns = functions()
    ns.update(Path=Path, tempfile=tempfile, get_lang=get_lang, export_word=export_word,
              _active_chart_palette=lambda: ["#123456", "#abcdef"])
    node = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == "_grouped_bar_snapshot_png_for_save")
    exec(ast.get_source_segment(SOURCE, node), ns)
    series = [{"name": "A", "data": [25.0, 75.0]}]
    with patch.object(export_word, "render_grouped_bar_chart_image", wraps=export_word.render_grouped_bar_chart_image) as render:
        first = ns["_grouped_bar_snapshot_png_for_save"]("test", ["X", "Y"], series, "Title")
        assert ns["_grouped_bar_snapshot_png_for_save"]("test", ["X", "Y"], series, "Title") == first
        assert render.call_count == 1
        series[0]["data"][0] = 50.0
        assert ns["_grouped_bar_snapshot_png_for_save"]("test", ["X", "Y"], series, "Title") != first
        ns["_active_chart_palette"] = lambda: ["#ff0000"]
        ns["_grouped_bar_snapshot_png_for_save"]("test", ["X", "Y"], series, "Title")
        assert render.call_count == 3


def test_manual_save_payload_keeps_blocks_images_and_named_axes():
    ns = functions()
    for node in ast.walk(TREE):
        if isinstance(node, ast.FunctionDef) and node.name in {"_extras_payload", "_images_payload", "_image_mime", "_collect_ai_results_for"}:
            exec(ast.get_source_segment(SOURCE, node), ns)
    import mimetypes
    ns.update(units=[], mimetypes=mimetypes)
    state = ns["st"].session_state
    result = ns["_compute_crosstab_block_result"](context("single", ["A"]), context("single", ["B"]))
    result["table"].columns.name = "Named columns"
    state["crosstab_blocks"] = [{"id": "7", "left": {"doc_id": None, "question_key": "Q1"}, "right": {"doc_id": None, "question_key": "Q1"}, "result": result}]
    state["crosstab_next_block_id"] = 10
    state["images_crosstab_block_7"] = [{"name": "test.png", "bytes": b"test", "caption": "Evidence"}]
    payload = json.loads(json.dumps(ns["_extras_payload"]()))
    assert payload["images"]["crosstab_block_7"][0]["caption"] == "Evidence"
    assert payload["crosstab_state"]["next_block_id"] == 10
    state.clear()
    ns["_restore_extras"](payload)
    pd.testing.assert_frame_equal(state["crosstab_blocks"][0]["result"]["table"], result["table"])
    assert state["images_crosstab_block_7"][0]["bytes"] == b"test"


def test_full_analysis_page_load_generate_and_reopen(comparison_app):
    app, conn, project, _, target_id, _ = comparison_app
    full = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app_streamlit/app.py"), default_timeout=30)
    full.session_state["db_conn"] = conn
    full.session_state["lang"] = "zh"
    full.session_state["analysis_mode"] = "load_existing"
    full.session_state["current_document_id"] = app.session_state["saved_document_id"]
    full.session_state["current_project_id"] = project
    full.run()
    assert not full.exception
    # 加载历史会清理早于加载区创建的主题控件；AppTest 需要显式补发浏览器的当前选择。
    full.selectbox(key="visual_theme").select("blue")
    full.button(key="xtb_1_run").click().run()
    assert not full.exception
    full.button(key="xtb_add_block").click().run()
    full.selectbox(key="xtb_2_right_doc").select(target_id).run()
    full.button(key="xtb_2_run").click().run()
    assert not full.exception
    saved = db.read_document_extras(conn, app.session_state["saved_document_id"])
    assert [b["result"]["kind"] for b in saved["crosstab_blocks"]] == ["same_doc", "cross_doc"]
    full.button(key="manual_save_button").click().run()
    assert not full.exception
    assert len(db.read_document_extras(conn, app.session_state["saved_document_id"])["crosstab_blocks"]) == 2
    del full.session_state["loaded_document_snapshot"]
    full.run()
    assert not full.exception
    assert len(full.session_state["crosstab_blocks"]) == 2
    assert len(full.session_state["crosstab_history"]) == 2
