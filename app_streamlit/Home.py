"""入口文件：只负责多页导航，不直接渲染内容（Streamlit 标准写法——所有页面内容
包括"首页"本身都是独立文件，入口脚本只 set_page_config + st.navigation(...).run()）。

跑法（在项目根目录）：
    .venv/bin/streamlit run app_streamlit/Home.py

页面结构：
    Home.py（本文件，只做导航）
    views/home_view.py（首页：项目列表、新建项目、API/模型设置）
    views/project_view.py（项目工作区：定量问卷调研/定性访谈/案头研究）
    app.py（单份问卷分析：①～⑩，从项目工作区点"新建/打开分析"跳进来）
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from engine import db
from engine.i18n import t
from app_streamlit.lang_ui import init_language, render_language_switch

_conn = st.session_state.get("db_conn") or db.init_db(str(PROJECT_ROOT / "data" / "app.db"))
st.session_state["db_conn"] = _conn
init_language(_conn)

st.set_page_config(page_title=t("问卷可视化分析工具"), layout="wide", initial_sidebar_state="expanded")
render_language_switch(_conn)

pages = [
    st.Page("views/home_view.py", title=t("首页"), default=True),
    st.Page("views/project_view.py", title=t("项目工作区")),
    st.Page("app.py", title=t("问卷分析")),
]
# position="hidden"——所有页面切换这个 app 里都是用 st.switch_page 显式按钮做的
# （"打开项目"/"新建分析"/"返回首页" 这些），不依赖 Streamlit 自带的侧边栏页面切换器；
# 隐藏掉它，免得和 app.py 自己那份①～⑩模块导航在同一个侧边栏里挤在一起看着乱。
st.navigation(pages, position="hidden").run()
