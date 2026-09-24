"""真实反馈的严重 bug 的回归测试："新建问卷分析"默认填的标题是上一份问卷的标题，
点保存直接把上一份问卷覆盖掉了——根源是 session_state 里 document_title/
saved_document_id 这些上一份分析残留的值，没有在"新建"这个动作里被清空。

这里直接从 app_streamlit/app.py 里摘出真正的那段清空逻辑（跟 tests/test_mapping_memory.py
的 mapping_app fixture用的是同一个"按源码里的唯一标记切片"手法），不是照着逻辑手写一份
复制品去测——手写复制品测的是"我以为代码是这样"，源码真的改了这份测试也不会跟着反映
出来，等于白测。
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest


@pytest.fixture
def new_analysis_reset_app():
    from streamlit.testing.v1 import AppTest

    source = (Path(__file__).resolve().parents[1] / "app_streamlit/app.py").read_text()
    start_marker = '    else:\n        # 真实反馈的严重 bug'
    end_marker = '        uploaded = st.file_uploader'
    start = source.index(start_marker)
    end = source.index(end_marker)
    block = textwrap.dedent(source[start:end].replace("    else:\n", "", 1))

    app = AppTest.from_string(
        "import streamlit as st\n" + block + '\nst.write("done")\n'
    )
    return app


def test_new_mode_clears_stale_title_and_saved_id_from_previous_document(new_analysis_reset_app):
    app = new_analysis_reset_app
    # 模拟"刚分析完文档 A、点了 + 新建问卷分析"这一刻的 session_state：project_view.py
    # 的按钮已经把 analysis_mode 设成 "new"，但 document_title/saved_document_id 这些
    # 还是文档 A 分析时留下的旧值。
    app.session_state["analysis_mode"] = "new"
    app.session_state["document_title"] = "__TEST__文档A的标题"
    app.session_state["saved_document_id"] = 999
    app.session_state["mapping"] = "__TEST__文档A的映射表"
    app.session_state["conclusions"] = ["__TEST__文档A的结论"]
    app.session_state["current_document_id"] = None
    app.session_state["current_project_id"] = 1
    app.session_state["db_conn"] = "__TEST__fake_conn"
    app.session_state["lang"] = "zh"

    app.run()
    assert not app.exception

    # 核心断言：残留的文档 A 数据必须被清空，不能带进"新建"这次分析。
    assert "document_title" not in app.session_state
    assert "saved_document_id" not in app.session_state
    assert "mapping" not in app.session_state
    assert "conclusions" not in app.session_state
    # "new" 这个一次性开关本身也应该被消费掉（pop 掉），不然每次 rerun 都会重新清空，
    # 用户在这次新建分析里刚填的映射表/标题会被反复抹掉，没法正常操作。
    assert "analysis_mode" not in app.session_state
    # 几个真正需要跨"新建"这个动作保留的基础设施 key 必须原样保留。
    assert app.session_state["current_project_id"] == 1
    assert app.session_state["db_conn"] == "__TEST__fake_conn"
    assert app.session_state["lang"] == "zh"


def test_second_run_without_new_mode_does_not_wipe_state_again(new_analysis_reset_app):
    """"new" 这个开关必须是一次性的——同一次"新建分析"过程中用户上传文件、填映射表
    触发的后续 rerun，不能把用户刚填的内容又清空一遍。"""

    app = new_analysis_reset_app
    app.session_state["analysis_mode"] = "new"
    app.session_state["db_conn"] = "__TEST__fake_conn"
    app.run()
    assert "analysis_mode" not in app.session_state

    # 模拟"新建分析"过程中用户已经填了一些内容的后续 rerun——这次 analysis_mode
    # 已经不存在了（上一轮 pop 掉了），不应该再次触发清空。
    app.session_state["document_title"] = "__TEST__用户刚填的新标题"
    app.run()
    assert not app.exception
    assert app.session_state["document_title"] == "__TEST__用户刚填的新标题"
