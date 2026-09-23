"""界面语言：默认英文，右上角（Deploy 旁边）有个 EN／中文 开关。

每个页面脚本最开头都要调一次 `init_language(conn)`——Streamlit 多页应用里每个页面既
可能由 Home.py 的 st.navigation 加载，也可能被单独跑（测试里就是直接跑 app.py），
所以不能只靠 Home.py 设置一次。语言选择存在 session_state（当前浏览器会话）和数据库
settings 表（`ui_language`，下次打开还是上次选的）。
"""

from __future__ import annotations

import streamlit as st

from engine import db
from engine.i18n import DEFAULT_LANG, SUPPORTED_LANGS, set_lang

LANG_LABELS = {"en": "EN", "zh": "中文"}


def init_language(conn) -> str:
    if "lang" not in st.session_state:
        saved = db.get_setting(conn, "ui_language", default=DEFAULT_LANG)
        st.session_state["lang"] = saved if saved in SUPPORTED_LANGS else DEFAULT_LANG
    lang = st.session_state["lang"]
    set_lang(lang)
    return lang


def render_language_switch(conn) -> None:
    """在页面右上角（Streamlit 自带的 Deploy 按钮左边）画一个 EN／中文 切换。

    Streamlit 没有给"往顶部工具栏里加控件"留接口，这里用 CSS 把一个普通控件固定定位到
    工具栏旁边（样式见 app.py/home_view.py 那一大块 CSS 之外的 lang_switch_css）。
    """

    lang = init_language(conn)
    # 固定定位到右上角、Deploy 按钮左边；字号/内边距压小，别抢工具栏的风头。
    # 短小的一段样式（不写 CSS 注释——大块或带星号注释的内联样式会被浏览器截断，见项目记忆）。
    st.markdown(
        """<style>
[class*="st-key-lang_switch"] {
    position: fixed;
    top: 0.55rem;
    right: 14.5rem;
    z-index: 1000001;
    width: auto !important;
}
[data-testid="stElementContainer"]:has([class*="st-key-lang_switch"]) {
    height: 0;
    min-height: 0;
    margin: -1rem 0 0 0;
}
[class*="st-key-lang_switch"] button {
    min-height: 1.9rem;
    padding: 0 0.7rem;
    font-size: 0.85rem;
}
</style>""",
        unsafe_allow_html=True,
    )
    with st.container(key="lang_switch"):
        picked = st.segmented_control(
            "Language",
            options=list(LANG_LABELS.keys()),
            format_func=lambda k: LANG_LABELS[k],
            default=lang,
            key="lang_switch_control",
            label_visibility="collapsed",
        )
    if picked and picked != lang:
        st.session_state["lang"] = picked
        db.set_setting(conn, "ui_language", picked)
        set_lang(picked)
        st.rerun()
