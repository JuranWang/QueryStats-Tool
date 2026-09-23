"""Run real ranking mapping/rendering code without starting the app or opening app.db."""

import ast
import textwrap
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from engine import db, ingest


SOURCE = (Path(__file__).resolve().parents[1] / "app_streamlit/app.py").read_text()
TREE = ast.parse(SOURCE)
FUNCTION_NAMES = {
    "build_units", "render_unit", "render_question_header", "_compute_label_map",
    "_is_chinese", "translate_texts_cached",
}
FUNCTION_SOURCE = "\n\n".join(
    ast.get_source_segment(SOURCE, node)
    for node in TREE.body
    if isinstance(node, ast.FunctionDef) and node.name in FUNCTION_NAMES
)
CONSTANT_SOURCE = "\n".join(
    ast.get_source_segment(SOURCE, node)
    for node in TREE.body
    if isinstance(node, ast.Assign)
    and any(isinstance(target, ast.Name) and target.id in {
        "CJK_PATTERN", "_EMBEDDED_QUESTION_NUMBER_RE"
    } for target in node.targets)
)
MAPPING_SOURCE = textwrap.dedent(SOURCE[
    SOURCE.index('    st.subheader(t("数据映射"), anchor="mapping-table")'):
    SOURCE.index('    # 4. 筛选设置')
])


@pytest.mark.parametrize("size,english", [(4, False), (6, True)])
def test_upload_shape_mapping_and_analysis_with_cached_labels(tmp_path, size, english):
    title = "__TEST__Rank materials" if english else "__TEST__以下几种材料是地毯背面的防滑点，\n请按价值感从高到低排序"
    labels = [f"Option {i}" for i in range(size)] if english else ["硅基", "铂金硅", "液态硅", "弹性硅"]
    columns = [f"{title}-{label}" for label in labels]
    df = pd.DataFrame(
        [[str((i + j) % size + 1) for j in range(size)] for i in range(size)],
        columns=columns,
    )
    path = tmp_path / "__TEST__credamo.csv"
    df.to_csv(path, index=False, encoding="utf-8-sig")
    uploaded = ingest.load_file(str(path))
    conn = db.init_db(str(tmp_path / "__TEST__ranking.sqlite"))
    script = '''
import hashlib
import re
import pandas as pd
import streamlit as st
from engine import clean, stats, chart_spec, mapping_memory
from engine.i18n import t, set_lang
set_lang("zh")
ALL_SECTIONS = ["筛选", "正式", "基础信息", "平台信息"]
def _get_db_conn():
    return st.session_state["__TEST__conn"]
def guess_is_platform_column(column):
    return False
def _translation_cache():
    return st.session_state["__TEST__cache"]
def _get_provider_or_none(purpose):
    raise AssertionError("Cached labels must not call a provider")
def _active_chart_palette():
    return ["#123456", "#abcdef"]
def render_image_attachments_trigger(q_no):
    st.button("__TEST__insert", key=q_no)
def render_image_attachments_grid(q_no):
    st.caption("__TEST__images")
def render_chart(chart_type, config, key):
    st.session_state["__TEST__charts"].append((chart_type, config, key))
    st.caption(key)
def render_chart_save_controls(download_col, copy_col, q_no, chart_kind, stats_result, title, title_suffix=""):
    # 真实版本会调 matplotlib/iframe，这个最小化 harness 不需要真的渲染那些——
    # 只记录调用参数，跟 render_chart 那个 stub 是同一个思路（避免真实渲染开销，
    # 只验证"确实按每个选项各自调用了一次、参数对不对"）。
    st.session_state["__TEST__save_controls"].append((q_no, chart_kind, title_suffix))
    with download_col:
        st.caption(f"__TEST__download_{q_no}")
    with copy_col:
        st.caption(f"__TEST__copy_{q_no}")
df_all = st.session_state["__TEST__data"]
st.session_state["__TEST__charts"] = []
st.session_state["__TEST__save_controls"] = []
''' + CONSTANT_SOURCE + "\n" + FUNCTION_SOURCE + "\n" + MAPPING_SOURCE + '''
units = build_units(mapping)
st.session_state["__TEST__units"] = units
for i, unit in enumerate(units):
    unit["display_no"] = f"Q{i + 1}"
    render_unit(unit, df_all, len(df_all))
'''
    try:
        app = AppTest.from_string(script)
        app.session_state["__TEST__conn"] = conn
        app.session_state["__TEST__data"] = uploaded
        app.session_state["__TEST__cache"] = {title: "__TEST__材料排序", **{v: f"材料{i}" for i, v in enumerate(labels)}} if english else {}
        app.run()
        assert not app.exception
        mapping = app.session_state["mapping"]
        assert mapping["q_type"].tolist() == ["ranking"] * size
        assert mapping["q_no"].tolist() == ["auto_rank_1"] * size
        assert any("1 道排序题" in info.value for info in app.info)
        units = app.session_state["__TEST__units"]
        assert len(units) == 1 and units[0]["columns"] == columns
        assert units[0]["kind"] == "ranking"
        assert any("【排序题】" in heading.value for heading in app.markdown)
        charts = app.session_state["__TEST__charts"]
        assert len(charts) == size
        for index, (kind, config, key) in enumerate(charts):
            assert kind == "pie"
            assert config["title"]["text"] == (f"材料{index}" if english else labels[index])
            assert config["color"][0] == "#123456"
            assert [v["name"] for v in config["series"][0]["data"]] == [f"第{i}名" for i in range(1, size + 1)]
            assert [v["value"] for v in config["series"][0]["data"]] == [1] * size
        assert len({key for _, _, key in charts}) == size
        assert app.table[0].value.shape == (size, size)
        assert app.table[0].value.columns.tolist() == ([f"材料{i}" for i in range(size)] if english else labels)
        # 真实反馈"这几张饼图也需要 copy/download"——每个选项都要调用一次
        # render_chart_save_controls，chart_kind 固定是 "single"（排序名次分布跟
        # 单选题图表结构一样），title_suffix 带着这个选项自己的展示名，identifier
        # （q_no 参数）互不相同（不然复制/下载按钮的 key 会撞车）。
        save_controls = app.session_state["__TEST__save_controls"]
        assert len(save_controls) == size
        assert {kind for _, kind, _ in save_controls} == {"single"}
        expected_labels = [f"材料{i}" for i in range(size)] if english else labels
        assert [suffix for _, _, suffix in save_controls] == [f"｜{label}" for label in expected_labels]
        assert len({save_id for save_id, _, _ in save_controls}) == size
        # Header has two columns; each option now also opens its own mini qbar
        # (3 columns: title/copy/download) alongside its outer per-option slot.
        assert len(app.get("column")) == 2 + size + 3 * size
        captions = [caption.value for caption in app.caption]
        assert captions.index("__TEST__images") < captions.index(charts[0][2])
        app.run()
        assert not app.exception
    finally:
        conn.close()


def test_build_units_keeps_types_and_sections_separate_even_with_same_key():
    namespace = {"pd": pd}
    function = next(node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name == "build_units")
    exec(ast.get_source_segment(SOURCE, function), namespace)
    mapping = pd.DataFrame([
        {"column": f"__TEST__{kind}_{section}_{i}", "q_type": kind, "section": section,
         "q_no": "__TEST__shared", "title": "__TEST__title"}
        for kind, section in [("multi", "正式"), ("ranking", "正式"), ("ranking", "基础信息")]
        for i in range(2)
    ])
    units = namespace["build_units"](mapping)
    assert [(u["kind"], u["section"], len(u["columns"])) for u in units] == [
        ("multi", "正式", 2), ("ranking", "正式", 2), ("ranking", "基础信息", 2)
    ]
