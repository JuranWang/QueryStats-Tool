"""独立试验页：测试 streamlit-elements（react-grid-layout）的拖拽/调整大小能不能用。

这是一个隔离的试验，不接入主流程——万一这个组件跟当前 Streamlit 版本不兼容、渲染出错，
只有这一页坏，不影响①～⑪主分析流程。测试结果（能拖/不能拖/报错/卡顿）请直接告诉我。
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

st.title("拖拽排版试验")
st.caption(
    "试着拖动下面三个色块调整位置、拖右下角小三角调整大小——参考飞书文档里拖图片调整并排展示的手感。"
    "如果完全拖不动、报错、卡死，或者手感很差（卡顿/跳动），把具体现象告诉我。"
)

try:
    from streamlit_elements import dashboard, elements, mui
except Exception as exc:  # noqa: BLE001
    st.error(f"streamlit-elements 加载失败：{exc}")
    st.stop()

if "dragdrop_test_layout" not in st.session_state:
    st.session_state["dragdrop_test_layout"] = [
        dashboard.Item("box1", 0, 0, 2, 2),
        dashboard.Item("box2", 2, 0, 2, 2),
        dashboard.Item("box3", 0, 2, 4, 2),
    ]

BOX_STYLE = {
    "padding": "24px",
    "color": "white",
    "display": "flex",
    "alignItems": "center",
    "justifyContent": "center",
    "fontSize": "18px",
    "height": "100%",
}

with elements("dragdrop_test"):
    with dashboard.Grid(st.session_state["dragdrop_test_layout"]):
        mui.Paper("图片 A（占位）", key="box1", sx={**BOX_STYLE, "backgroundColor": "#1F3864"})
        mui.Paper("图片 B（占位）", key="box2", sx={**BOX_STYLE, "backgroundColor": "#2E7D52"})
        mui.Paper("图片 C（占位，更宽）", key="box3", sx={**BOX_STYLE, "backgroundColor": "#C2570C"})

st.divider()
if st.button("返回项目工作区"):
    st.switch_page("views/project_view.py")
