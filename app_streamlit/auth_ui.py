"""登录门禁 + 右上角"当前账号 / 退出登录"标识。

只在 Home.py（唯一真正的入口脚本，见 Home.py 文件头注释）里调一次
`require_login()`——st.navigation 选中的子页面代码是在同一个脚本执行 session 里
继续跑的，project_view.py/app.py 不用重复校验，也不需要知道账号系统的存在，只在
需要按账号过滤数据的地方（home_view.py 的项目列表）读 `st.session_state["current_account"]`。

账号本身的设计取舍见 engine/accounts.py 开头的注释——内部团队工具，不是公网安全边界。
"""

from __future__ import annotations

import streamlit as st

from engine.accounts import ACCOUNTS, check_password
from engine.i18n import t


def require_login() -> str:
    """没登录就画登录表单并 `st.stop()`（调用处往下的代码这次脚本运行不会再执行）；
    已经登录过（`current_account` 在 session_state 里）直接返回账号名。
    """

    account = st.session_state.get("current_account")
    if account:
        return account

    st.title(t("登录"))
    st.caption(t("账号是你的名字，密码是名字的全小写拼音。"))
    with st.expander(t("忘记密码了？点开看提示")):
        for name, pwd in ACCOUNTS.items():
            st.caption(f"{name}：{pwd}")

    with st.form("login_form"):
        name = st.selectbox(t("账号"), list(ACCOUNTS.keys()), key="login_account_select")
        password = st.text_input(t("密码"), type="password", key="login_password_input")
        submitted = st.form_submit_button(t("登录"))
    if submitted:
        if check_password(name, password):
            st.session_state["current_account"] = name
            st.rerun()
        else:
            st.error(t("密码不对，再试一下——提示就在上面「忘记密码了？」里。"))
    st.stop()


def render_account_bar() -> None:
    """右上角固定一个"账号名 · 退出登录"按钮——跟 lang_ui.py 的 EN／中文 开关用
    同一套固定定位手法，摆在语言开关再往左一点，两者不会叠在一起。
    """

    account = st.session_state.get("current_account")
    if not account:
        return
    st.markdown(
        """<style>
[class*="st-key-account_bar"] {
    position: fixed;
    top: 0.55rem;
    right: 19.5rem;
    z-index: 1000001;
    width: auto !important;
}
[data-testid="stElementContainer"]:has([class*="st-key-account_bar"]) {
    height: 0;
    min-height: 0;
    margin: -1rem 0 0 0;
}
[class*="st-key-account_bar"] button {
    min-height: 1.9rem;
    padding: 0 0.7rem;
    font-size: 0.85rem;
}
</style>""",
        unsafe_allow_html=True,
    )
    with st.container(key="account_bar"):
        if st.button(t("{account} · 退出登录", account=account), key="account_logout_button"):
            del st.session_state["current_account"]
            st.rerun()
