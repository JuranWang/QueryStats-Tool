"""真实反馈："它识别筛选题的逻辑是错误的，如果是 Tally 问卷平台回收的结果，
S 开头的问题都是筛选问题"——原来"数据映射"自动分类默认把所有列统统归成
"正式"，不管题干写的是什么，筛选题每次都要手动一道一道改。

这组测试锁定两层行为：
1. guess_is_screening_column() 本身的匹配规则（纯函数单元测试，不启动 Streamlit）。
2. 真实的"数据映射"自动分类流程——用跟 Tally 导出结构一致的合成数据（含一道
   多选筛选题、一道单选筛选题、一道正式问卷开放题），走一遍真正的 default_rows
   构建代码（不是在测试里复制一份判断逻辑自己再判一遍），确认分类结果对。
"""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from engine import db

SOURCE = (Path(__file__).resolve().parents[1] / "app_streamlit/app.py").read_text()
TREE = ast.parse(SOURCE)


def _source_of(name: str) -> str:
    for node in TREE.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(SOURCE, node)
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == name
        ):
            return ast.get_source_segment(SOURCE, node)
    raise AssertionError(f"没能在 app_streamlit/app.py 里找到 {name}，这个名字是不是改了？")


# 单元测试：只摘这一个函数 + 它依赖的正则常量，不用启动整个 app——真实依赖的
# 是 app.py 里实际跑着的那份代码，不是在这里重新抄一遍判断逻辑。
_namespace = {"re": __import__("re")}
exec(_source_of("_SCREENING_QUESTION_NUMBER_RE"), _namespace)
exec(_source_of("guess_is_screening_column"), _namespace)
guess_is_screening_column = _namespace["guess_is_screening_column"]


@pytest.mark.parametrize("column, expected", [
    # 真实反馈的那份 Tally 导出（Home Shopping Study）原始列名，照抄不编造。
    ("S1. Which of these have you bought for your home in the past 12 months? Select all that apply.", True),
    ("S2. Thinking about that rug — how much did you pay for it?", True),
    ("S6. What's your ZIP code?", True),
    ("S10. 两位数的筛选题编号也要认得出来", True),
    ("  S3. 前后带空白也要认得出来", True),
    ("Q7. What got you thinking about buying a rug in the first place?", False),
    ("Season tickets available?", False),  # "S" 开头但不是"数字+标点"的编号格式，不能误伤
    ("Some question mentions S1 visas in the middle of the sentence", False),  # "S1" 不在开头
])
def test_guess_is_screening_column_matches_tally_s_prefix_convention(column, expected):
    assert guess_is_screening_column(column) == expected


@pytest.fixture
def conn(tmp_path):
    path = tmp_path / "__TEST__screening.sqlite"
    connection = db.init_db(str(path))
    try:
        yield connection
    finally:
        connection.close()
        path.unlink(missing_ok=True)


def _mapping_app(conn, data: pd.DataFrame):
    """照 tests/test_mapping_memory.py 的 mapping_app 同一个模式摘取"数据映射"
    那段真实代码，区别是这里不把 guess_is_screening_column stub 掉——就是要跑
    真实判断逻辑，不是绕开它。guess_is_platform_column 跟这组测试要验证的行为
    无关，照旧 stub 成 False，避免节外生枝。
    """

    block = textwrap.dedent(SOURCE[
        SOURCE.index('    st.subheader(t("数据映射"), anchor="mapping-table")'):
        SOURCE.index('    # 4. 筛选设置')
    ])
    app = AppTest.from_string(f'''
import re
import pandas as pd
import streamlit as st
from engine import clean, mapping_memory
from engine.i18n import t, set_lang
set_lang("zh")
ALL_SECTIONS = ["筛选", "正式", "基础信息", "平台信息"]
def _get_db_conn():
    return st.session_state["__TEST__conn"]
def guess_is_platform_column(column):
    return False
{_source_of("_SCREENING_QUESTION_NUMBER_RE")}
{_source_of("guess_is_screening_column")}
df_all = st.session_state["__TEST__data"]
''' + block)
    app.session_state["__TEST__conn"] = conn
    app.session_state["__TEST__data"] = data
    return app


def test_single_choice_screening_question_defaults_to_screening_section(conn):
    data = pd.DataFrame({
        "S2. Thinking about that rug — how much did you pay for it?": ["$200-350", "$350-600", "$600+"],
        "Q8. Which of these comes closest?": ["A", "B", "A"],
    })
    app = _mapping_app(conn, data)
    app.run()
    assert not app.exception
    mapping = app.session_state["mapping"]
    sections = dict(zip(mapping["column"], mapping["section"]))
    assert sections["S2. Thinking about that rug — how much did you pay for it?"] == "筛选"
    assert sections["Q8. Which of these comes closest?"] == "正式"


def test_multi_select_screening_group_defaults_to_screening_section(conn):
    # 真实 Tally 导出的多选题形状：一个"题干本身"的汇总列（逗号拼接文本，会被
    # detect_multi_select_groups 识别成多余的汇总列、type 标成"忽略"）+ 好几个
    # "题干 (选项)"的布尔拆分列（这些才是真正参与分组、需要被分类成"筛选"的）。
    stem = "S1. Which of these have you bought for your home in the past 12 months? Select all that apply."
    data = pd.DataFrame({
        stem: ["An area rug", "A sofa or armchair"],
        f"{stem} (An area rug)": [True, False],
        f"{stem} (A sofa or armchair)": [False, True],
        "Q7. What got you thinking about buying a rug in the first place?": ["needed one", "redecorating"],
    })
    app = _mapping_app(conn, data)
    app.run()
    assert not app.exception
    mapping = app.session_state["mapping"]
    option_rows = mapping[mapping["column"].isin([f"{stem} (An area rug)", f"{stem} (A sofa or armchair)"])]
    assert set(option_rows["section"]) == {"筛选"}
    assert set(option_rows["q_type"]) == {"multi"}
    # 正式问卷题不受影响，默认还是"正式"。
    open_row = mapping[mapping["column"] == "Q7. What got you thinking about buying a rug in the first place?"]
    assert open_row.iloc[0]["section"] == "正式"
