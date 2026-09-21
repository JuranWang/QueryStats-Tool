"""快速体验版 Demo——10 部分整体框架（设计文档 v0.6）全部接了一版，范围仍然明确缩小：

- 没有 SQLite 持久化、没有项目管理，刷新页面就清空——正式版会接 engine/db.py（Milestone 3a 已建好那几张表）。
- 多选题的分组映射很简陋（同一个"分组键"打成 multi 类型的列会被合并）。
- 筛选题的"未通过筛选"判定只支持单选题（选中的值 = 未通过）；数值/开放题标成筛选题时会展示，但不参与过滤。
- ⑧交叉分析「对比到哪道题」只支持单选题，多选题作为对比对象暂不支持。
- ⑥⑦用了新依赖 streamlit-aggrid 做分组表头着色+点击选中；这块我只做到"数据组装逻辑单独测过、
  服务器能正常起来"，表头颜色和点击选中的真实效果需要你自己点一下确认——没有浏览器没法替你点。
- AI 相关功能（分类/翻译/洞察）需要在首页配置好 AI 供应商 + API key（或者设对应的环境变量），没配的话会提示，不会崩。

跑法（在项目根目录）：
    .venv/bin/streamlit run app_streamlit/app.py
"""

from __future__ import annotations

import base64
import hashlib
import html as html_lib
import json
import re
import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import streamlit as st
from streamlit_echarts import st_echarts

from datetime import datetime

from engine import (
    ai_classify,
    ai_insight,
    ai_translate,
    chart_spec,
    clean,
    db,
    export_word,
    ingest,
    persistence,
    project_naming,
    stats,
)


# st.set_page_config 不在这里调用——这个文件现在是 Home.py 多页应用里的一个子页面，
# set_page_config 每次运行只能调用一次，由入口 Home.py 统一负责。
#
# 左上角必须始终有一条退出这个页面的路——position="hidden" 关掉了 Streamlit 自带的
# 页面切换侧栏，之前"返回项目工作区"按钮只在 current_project_id 有值时才显示，
# session_state 被重置掉（比如服务端重启后浏览器还停在这一页）就彻底走不出去了。
nav_col1, nav_col2 = st.columns([1, 1])
with nav_col1:
    if st.button("← 返回首页"):
        st.switch_page("views/home_view.py")
if st.session_state.get("current_project_id") is not None:
    with nav_col2:
        if st.button("← 返回项目工作区"):
            st.switch_page("views/project_view.py")

# 视觉重设计 v2（设计文档 v0.12）：保留原来定下来的"蓝调报告"风格，另外新建一个
# "极简"风格供切换——参考的是你自己收的那批极简/建筑系审美范例（UI design
# reference/Minimalist 目录）：近乎不用色（除了一个链接色）、大号加粗无衬线标题
# （不是衬线体）、用一条细线分隔而不是圆角卡片。两个风格都保留，不是"极简"取代
# "蓝调"——下面 top_theme_col 那个下拉框负责切换。
#
# 有个跨不过去的限制要说清楚：Streamlit 原生控件（按钮/勾选框/下拉框）的颜色只能在
# .streamlit/config.toml 里配、只能在服务器启动时定死一份，没法跟着这个下拉框实时换。
# 这里把 config.toml 固定配成"蓝调"（两个风格里先定下来、更成熟的一份），"极简"风格
# 切换时只换页面里 CSS 够得着的部分（标题字体、题目外框、结论字号），原生控件颜色
# 仍然是蓝色——这是已知的、说清楚了的局限，不是遗漏。
VISUAL_THEMES = {
    "blue": {
        "label": "蓝调报告",
        "ink": "#1C2733",
        "line": "#DFE4EA",
        "surface": "#FFFFFF",
        "header_font": '"Noto Serif SC", "Source Han Serif SC", serif',
        "header_weight": "600",
        "header_letter_spacing": "normal",
        "title_font_size": "1.75rem",
        "conclusion_font_size": "1rem",
        "sidebar_link_color": "#57677A",
    },
    "minimalist": {
        "label": "极简",
        "ink": "#14181C",
        "line": "#DDDBD5",
        "surface": "#FFFFFF",
        "header_font": '"Familjen Grotesk", "IBM Plex Sans SC", "PingFang SC", sans-serif',
        "header_weight": "700",
        "header_letter_spacing": "-0.01em",
        "title_font_size": "1.85rem",
        "conclusion_font_size": "1.2rem",
        "sidebar_link_color": "#5B5F63",
        "card_hairline": True,
    },
}
# 读 session_state 要在下面 selectbox 真正渲染出来之前——selectbox 带了 key 之后，
# 它的值在上一次 rerun 就已经写进 session_state 了，这里提前读出来才能让这段位于
# 页面最上面的 CSS 用上"这次该显示哪个风格"，不用等 selectbox 那行代码跑到。第一次
# 打开页面 session_state 里还没有这个 key，退回默认的 "blue"。
visual_theme_name = st.session_state.get("visual_theme", "blue")
theme = VISUAL_THEMES[visual_theme_name]


def _active_chart_palette() -> list[str] | None:
    """图表用哪套色板，跟着界面风格走——"极简"用低饱和度的建筑材料感色板，
    "蓝调"用默认的十色（返回 None，交给 chart_spec/export_word 自己退回默认值）。
    这是个函数不是直接算好的变量，因为 `visual_theme_name` 在下面 selectbox 那行
    还会被重新赋值一次——调用这个函数的地方都在那行之后，函数体在调用的那一刻才
    读取 `visual_theme_name`，读到的已经是这次 rerun 真正选中的风格。
    """

    if visual_theme_name == "minimalist":
        return chart_spec.OPTION_COLOR_PALETTE_MINIMALIST
    return None

# 题目标题横条——深色底色本身就是"新的一题开始了"这个信号，不再需要另外画一条分隔线。
# 横条要跟上一题拉开明显的距离（margin-top），横条内部（标题文字/图标按钮）紧凑一点。
# 图标按钮（下载/复制/编辑文字/插入图片）统一做成不带边框、不带圆角的正方形，平时
# 底色跟横条融为一体、图标是白色，鼠标移上去颜色反转（底变白、图标变深色），这样
# "什么能点"只靠 hover 反馈说明，不需要平时就画一圈边框提醒。
#
# 横条底色不用纯黑/接近纯黑的 ink 色——真实反馈说太重了，改用"75% 黑"（黑色叠加
# 75% 透明度盖在白底上的效果，算出来是 rgb(64,64,64)），比 ink 色浅一些，两个风格
# 统一用这一个颜色（不跟着 theme['ink'] 走了，深浅问题本身就跟选了哪个风格无关）。
#
# 下面这几段 CSS 字符串里故意不写 /* ... */ 这种 CSS 注释——真实截图排查发现，
# 这一整块内容是通过 st.markdown(unsafe_allow_html=True) 插入的，Streamlit 仍然会
# 先跑一遍 Markdown 解析再当 HTML 用，CSS 注释里一堆星号会被 Markdown 当成
# 强调/斜体的标记符号，导致解析器在字符串中间某处判断出错，把后面的内容整段吞掉
# （真实表现：横条、纸张卡片背景色、表格滚动限制全部消失，但 Python 侧
# py_compile/pytest/AppTest 全部正常——这是浏览器端 Markdown 解析的问题，
# Python 测试工具够不到）。说明性文字统一挪到这里的 Python # 注释里，CSS 字符串
# 本身只留纯规则、不含星号，彻底避免这个坑。
#
# "AI 分类"按钮不用跟图标按钮一样强制正方形——正方形会把"AI 分类"四个字挤成
# "A..."看不清，下面有条更精确的选择器（多了一层 key）覆盖宽度，只固定高度对齐。
#
# 开放题原始数据表格的折叠/展开按钮是个普通 st.button，Streamlit 默认会画一个
# 浅灰底、带边框的小方框，在白色"纸张"卡片上很突兀；真实反馈是"这个地方的颜色
# 也要跟背景色保持一致"——去掉边框、背景改透明，让它融进纸张底色里。
#
# 图标列宽度这里保持"比例列 + gap=8"的原始写法：之前试过把非标题列改成
# flex:0 0 auto（跟着内容缩、贴到横条最右边），结果把"复制图片"那个 iframe
# （st.components.v1.html，宽度依赖父容器给出明确尺寸）搞崩了——父列变成
# width:auto 后 iframe 找不到确定宽度，退回浏览器默认尺寸，变成大小/颜色都不对
# 的浮空方块。这类纯 CSS 布局问题 AppTest 测不出来，真实反馈"改出了这么多问题"
# 之后已经整个撤回，图标间距这个诉求先保留现状，不再用这种改列宽模型的方式处理。
QBAR_BG = "#404040"
qbar_css = f"""
[class*="st-key-qbar_"] {{
    background: {QBAR_BG};
    padding: 0.35rem 0.9rem;
    margin-top: 2.75rem;
}}
[class*="st-key-qbar_"] p,
[class*="st-key-qbar_"] strong {{
    color: #FFFFFF !important;
}}
[class*="st-key-qbar_"] button {{
    background: {QBAR_BG} !important;
    border: none !important;
    border-radius: 0 !important;
    color: #FFFFFF !important;
    width: 1.8em !important;
    height: 1.8em !important;
    min-width: 1.8em !important;
    padding: 0 !important;
    transition: none;
}}
[class*="st-key-ai_classify_trigger_"] button {{
    width: auto !important;
    min-width: 5.2em !important;
    padding: 0 0.8rem !important;
}}
[class*="st-key-qbar_"] button:hover {{
    background: #FFFFFF !important;
    color: {theme['ink']} !important;
}}
[class*="st-key-toggle_raw_"] button {{
    background: transparent !important;
    border: none !important;
    color: {theme['ink']} !important;
}}
[class*="st-key-toggle_raw_"] button:hover {{
    background: transparent !important;
    color: {theme['ink']} !important;
}}
"""

# section_paper_css（同样不写 CSS 注释，理由见上面 qbar_css 前的说明）：
# - 开放题原始数据表格去掉外层卡片边框，只留表格本身的横竖线分隔。
# - 给表格滚动条画一条细长黑色竖条，提示可以上下拖动；::-webkit-scrollbar 这套写法
#   只有 Chrome/Edge/Safari 认，Firefox 会退回默认滚动条样式，不影响能不能用。
# - .oq-table 系列规则是开放题"原始数据"表格改用手写 HTML <table> 之后的样式——
#   这是真实 DOM，不是 st.dataframe 那种画在 canvas 上的表格，边框/底色/滚动条
#   这几处真实反馈都能被这里的 CSS 直接、稳定地控制，不会再因为够不到画布内部而
#   反复失灵。外层不画任何边框，只用横竖两组 1px 细线分隔单元格；行底色统一用
#   纸张卡片同一个颜色，不做隔行变色，避免颜色又对不上。
# - 曾经想去掉"关联展示"多选框自己的边框、顺手把"+"改粗，用的选择器精确到了
#   BaseWeb 下拉选项面板自己的容器，导致面板定位/尺寸整个乱掉（真实反馈截图看到
#   一个占满剩余页面的空白大方块）——已经整个撤回，这个诉求先不做。
section_paper_css = f"""
[class*="st-key-section_paper_"] {{
    background: {theme['surface']};
    padding: 2rem 2.2rem;
    margin-bottom: 2.5rem;
    border-radius: 0;
}}
[data-testid="stExpander"] {{
    border: none !important;
}}
[data-testid="stExpander"] summary {{
    flex-direction: row-reverse;
    justify-content: space-between;
}}
[data-testid="stExpander"] summary svg {{
    color: #000000 !important;
}}
[data-testid="stDataFrame"] {{
    border: none !important;
}}
[data-testid="stDataFrame"] div::-webkit-scrollbar {{
    width: 6px;
}}
[data-testid="stDataFrame"] div::-webkit-scrollbar-thumb {{
    background: #1a1a1a;
    border-radius: 0;
}}
[data-testid="stDataFrame"] div::-webkit-scrollbar-track {{
    background: transparent;
}}
.oq-table-wrap {{
    max-height: 320px;
    overflow-y: auto;
    overflow-x: auto;
    margin-bottom: 0.5rem;
}}
.oq-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.92rem;
}}
.oq-table th, .oq-table td {{
    border-bottom: 1px solid {theme['line']};
    border-right: 1px solid {theme['line']};
    padding: 6px 10px;
    text-align: left;
}}
.oq-table th:last-child, .oq-table td:last-child {{
    border-right: none;
}}
.oq-table thead th {{
    background: #F5F6F7;
    color: #6B7280;
    font-weight: 500;
    position: sticky;
    top: 0;
    z-index: 1;
}}
.oq-table td.oq-idx, .oq-table th.oq-idx {{
    color: #9CA3AF;
    width: 2.5em;
    text-align: right;
}}
.oq-table tbody tr {{
    background: {theme['surface']};
}}
.oq-table-wrap::-webkit-scrollbar {{
    width: 6px;
}}
.oq-table-wrap::-webkit-scrollbar-thumb {{
    background: #1a1a1a;
}}
.oq-table-wrap::-webkit-scrollbar-track {{
    background: transparent;
}}
"""

# 真实截图排查发现的 bug：这一大块 <link>+<style> 原来用 st.html() 插入，
# 结果浏览器里整段内容完全不渲染（不是样式没生效，是连 DOM 里都找不到这些
# 标签）——AppTest 的元素树检查测不出这个问题，只有真实浏览器截图 + 直接读
# document.querySelectorAll('style') 才发现。根因：st.html() 会用 DOMPurify
# 对内容做安全过滤，而且专门给"内容只有 <style> 标签"这种情况走一条独立的
# "event 容器"渲染路径（Streamlit 自己的 issue #9388），这条路径不保证出现在
# 主页面的可见 DOM 里；混进 <link> 标签会跳过那条特判、退回普通路径，这个版本
# 上普通路径同样不渲染这么大一块内联内容——试过"拆开成两次调用"（只有 style
# 那次会命中特判路径）也一样不显示，说明两条路径在这个版本上都靠不住。
# 换成 st.markdown(unsafe_allow_html=True)——这是 Streamlit 社区多年来插入
# 自定义 CSS 的标准做法，不走 st.html() 那套 DOMPurify + event 容器逻辑，会
# 直接原样插进主内容区的 DOM 里；本文件里开放题原始数据表格（.oq-table）用的
# 也是同一个 st.markdown(unsafe_allow_html=True)，已经在真实浏览器里验证过
# 能正常渲染，这里改成同一个可靠的机制。
# 下面这一大块 <style> 也不写 CSS 注释（理由见前面 qbar_css 之前的说明：
# st.markdown(unsafe_allow_html=True) 仍会先跑 Markdown 解析，CSS 注释里的星号
# 会被当成强调标记，把字符串从某处开始整段吞掉，浏览器端才能看出来）。这里把
# 各条规则原本的说明搬过来：
# - 字体分工：标题字体按当前选中的风格走（蓝调=衬线，极简=Familjen Grotesk 这种
#   "建筑事务所官网"式无衬线几何体），都只覆盖西文字形——中文自动落回 IBM Plex
#   Sans SC。等宽字体给人数/百分比这类要对齐的数字用。
# - 全局圆角清零：真实反馈"所有的长方形都不要圆角"——不只是我们自己手写 CSS
#   画的那几块，Streamlit 自带的原生控件（按钮、下拉框、输入框、表格、提示条…）
#   也有它自己默认的圆角，那部分源码在 Streamlit 内部、运行时才生成，够不到
#   具体数值去逐个改。用一条通配规则把全局圆角一次性清零，比逐个控件找出它的
#   圆角来源更可靠，也不用担心以后 Streamlit 升级版本换了圆角数值又要重新找一遍。
# - 板块间距：跟选了哪个风格无关，两个风格都一样需要——数字编号的大标题
#   （st.header，渲染成 h2）之前留出明显更大的空白，一眼就能看出"这是一个新的
#   大板块"，不是紧跟着上一段内容往下接。h3（st.subheader，段落内的小标题）
#   间距小一档，它们是大板块内部的细分，不需要跟大板块一样重的分隔。
# - conclusion_input/document_title_input 那两条要比通用的 input 规则更精确才能
#   生效——CSS 优先级比的是选择器本身的权重，不是谁写在后面；通用规则有两个
#   类/属性选择器（优先级 0,2,1），比不加 .stApp 前缀的写法（0,1,1）权重更高，
#   补一个 .stApp 前缀把两条规则的选择器权重拉平，后写的这两条才会真正生效。
# - 侧栏整体缩窄到原来的 2/3（约减少 1/3）——Streamlit 默认侧栏宽度是 21rem，
#   这里直接写死目标宽度；用户手动拖拽调整过宽度的话，这个固定值会覆盖掉那次
#   拖拽，这是预期内的取舍（先保证默认状态是窄的）。
# - 侧栏悬停做成"从左到右贯穿整条侧栏"的反色矩形——但侧栏内容区自己有左右
#   padding（具体数值是 Streamlit 内部样式，读不到），链接本身没法直接顶到
#   侧栏最左/最右边。用一个常见技巧绕开：给链接一个足够大的负 margin 往两边
#   "冲出"内容区的 padding，再用同样大小的正向 padding 把文字位置加回来，两者
#   相加等于原来的视觉留白，正常状态下看起来跟以前一模一样；等负 margin 超出
#   侧栏内容区自身宽度时，会被内容区的横向滚动裁切（侧栏是纵向滚动，横向不
#   允许溢出），效果反而正好是"精确贴到侧栏真正的边缘"，不需要猜精确的 padding
#   数值。悬停时只改背景/文字颜色，不碰 margin/padding，保证文字位置在两种
#   状态下完全不跳动。
st.markdown(f"""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@600;700&family=Familjen+Grotesk:wght@500;600;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Sans+SC:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
""", unsafe_allow_html=True)

# 真实截图排查确认：即使换成 st.markdown(unsafe_allow_html=True)、CSS 字符串本身
# 也不含任何星号（上面几段说明已经解释过为什么要避免星号），浏览器里这一整块
# <style> 内容还是会在几千字符左右的某个位置被截断——直接读浏览器
# document.querySelectorAll('style') 证实：Python 这边传过去的字符串本身是完整的
# （截断前用 Path(...).write_text() 存下来对比过，5005 字符一个字都不少），但是
# DOM 里最终落地的 <style> 标签只剩 2893 字符，从「.stApp」规则开始到 qbar_css
# 最后一条规则为止，section_paper_css 那部分完全不见——同样的内容单独放进一个
# 干净的最小复现页面却能完整渲染，说明这不是内容本身有问题，是这个版本的
# Streamlit 前端在"一次性塞一大块内联 CSS"这件事上有某种长度/复杂度相关的限制，
# 具体机制没能定位到（怀疑跟这个页面本身元素多、rerun 频繁有关，但没找到确凿
# 证据）。稳妥的做法是不去赌"多长算安全"，而是把这一整块拆成几个小的
# st.markdown() 调用——拆开之后每一段单独测过都能完整落地，浏览器端全部
# <style> 标签的效果是叠加的，拆几个调用跟写一个大 <style> 效果完全一样，
# 唯一的差别是不用再担心某一段太长被截断。
st.markdown(f"""
<style>
.stApp, .stApp textarea, .stApp button {{
    font-family: "IBM Plex Sans", "IBM Plex Sans SC", "PingFang SC", sans-serif;
}}
.stApp *, .stApp *::before, .stApp *::after {{
    border-radius: 0 !important;
}}
.stApp [class*="st-key-"] input {{
    font-family: "IBM Plex Sans", "IBM Plex Sans SC", "PingFang SC", sans-serif;
}}
.stApp h1, .stApp h2, .stApp h3 {{
    font-family: {theme['header_font']};
    font-weight: {theme['header_weight']};
    letter-spacing: {theme['header_letter_spacing']};
}}
.stApp h2 {{
    margin-top: 3.5rem !important;
}}
.stApp h3 {{
    margin-top: 1.75rem !important;
}}
</style>
""", unsafe_allow_html=True)

st.markdown(f"""
<style>
.stApp [class*="st-key-conclusion_input_"] input,
.stApp .st-key-document_title_input input {{
    font-family: {theme['header_font']};
    font-weight: {theme['header_weight']};
}}
.st-key-document_title_input input {{
    border: none;
    background: transparent;
    box-shadow: none;
    font-size: {theme['title_font_size']};
    font-weight: {theme['header_weight']};
    letter-spacing: {theme['header_letter_spacing']};
    padding: 0.15rem 0.3rem;
    color: {theme['ink']};
}}
.st-key-document_title_input input:hover,
.st-key-document_title_input input:focus {{
    border: 1px solid {theme['line']};
    background: {theme['surface']};
    border-radius: 0;
}}
[class*="st-key-conclusion_input_"] input {{
    border: none;
    background: transparent;
    box-shadow: none;
    font-size: {theme['conclusion_font_size']};
    color: {theme['ink']};
}}
[class*="st-key-conclusion_input_"] input:hover,
[class*="st-key-conclusion_input_"] input:focus {{
    border: 1px solid {theme['line']};
    background: {theme['surface']};
    border-radius: 0;
}}
</style>
""", unsafe_allow_html=True)

st.markdown(f"""
<style>
[data-testid="stSidebar"] {{
    width: 14rem !important;
    min-width: 14rem !important;
}}
[data-testid="stSidebarContent"] a,
[data-testid="stSidebar"] a {{
    display: block;
    margin: 1px -2rem;
    padding: 6px calc(4px + 2rem);
    border-radius: 0;
    color: {theme['sidebar_link_color']};
    text-decoration: none;
    font-size: 1.12rem;
    letter-spacing: 0.01em;
}}
[data-testid="stSidebarContent"] a:hover,
[data-testid="stSidebar"] a:hover {{
    background: #000000;
    color: #FFFFFF;
}}
</style>
""", unsafe_allow_html=True)

st.markdown(f"""
<style>
{qbar_css}
</style>
""", unsafe_allow_html=True)

st.markdown(f"""
<style>
{section_paper_css}
</style>
""", unsafe_allow_html=True)

top_title_col, top_theme_col, top_save_col = st.columns([6.3, 2.4, 1.3])
with top_theme_col:
    visual_theme_name = st.selectbox(
        "界面风格",
        options=list(VISUAL_THEMES.keys()),
        format_func=lambda k: VISUAL_THEMES[k]["label"],
        key="visual_theme",
        label_visibility="collapsed",
        help="切换标题字体／题目外框／结论字号；Streamlit 原生控件（按钮/勾选框/下拉框）固定跟随「蓝调报告」，这是已知限制，不是没切换生效。",
    )
st.caption("设计文档最新版本 1～10 全部框架的真实调用演示。")

# 圈码数字（①②③…）在换了新字体之后，个别字形在浏览器里会被替换成不搭配的后备字体、
# 渲染得特别大（真实截图看到 ⑥/⑪ 整个字符比旁边的标题文字大好几倍，还压住了后面的字）——
# 这些字符本来就是极小众的 Unicode 区块，不是所有字体都配了字形，风险比普通数字高得多。
# 换成"阿拉伯数字 + 点"，不依赖任何字体有没有配这批生僻字形。
SIDEBAR_NAV = [
    ("调整题型／分组", "mapping-table"),
    ("1. 结论", "sec1"),
    ("2. 测试方法", "sec2"),
    ("3. 筛选问题", "sec3"),
    ("4. 正式问卷", "sec4"),
    ("5. 基础信息探测", "sec5"),
    ("6. 完整数据表格", "sec6"),
    ("7. 受访者个人视角", "sec7"),
    ("8. 交叉分析", "sec8"),
    ("9. AI 洞察", "sec9"),
    ("10. 受访者信息", "sec10"),
    ("11. 导出 Word", "sec11"),
]
SECTION_ANCHOR = {"筛选": "sec3", "正式": "sec4", "基础信息": "sec5"}

CJK_PATTERN = re.compile(r"[一-鿿]")

# 平台自动收录字段的列名特征——命中就默认归类成"平台信息"（⑩），不进"正式问卷"。
# "id"/"pid"/"uid"/"sid" 必须是独立词（前后是空白/下划线/短横线/首尾），
# 不能用子串匹配，否则"Did you..."这种正常问题也会因为含"id"被误判。
_PLATFORM_ID_TOKEN_RE = re.compile(r"(?:^|[\s_-])(id|pid|uid|sid|ip)(?:$|[\s_-])", re.IGNORECASE)
_EMBEDDED_QUESTION_NUMBER_RE = re.compile(r"^[A-Za-z]{0,3}\d+[.\)、．]\s*")
_PLATFORM_KEYWORDS = (
    "submission", "respondent id", "prolific", "submitted", "timestamp",
    "ip address", "duration", "start date", "end date", "start time", "end time", "email",
)

# 见数/Credamo 每次导出都会带上这一批自己收集的元数据列（屏幕分辨率、经纬度、账号 ID、
# 问卷名称……），列名固定不变，不是研究者自己设计的问题。这里用"整列名精确相等"而不是
# 子串匹配——"省份""城市"这种词如果用子串匹配，会连"您所在的城市是？"这种真实的人口
# 统计学题目一起误伤，精确匹配就不会（真实问题不会整句话就叫"城市"两个字）。
_CREDAMO_METADATA_EXACT_COLUMNS = {
    "作答ID", "用户ID", "开始时间", "结束时间", "作答总时长(秒)", "作答渠道",
    "发布ID", "问卷发布名称", "IP", "经度", "纬度", "省份", "城市",
    "设备类型", "操作系统类型", "浏览器类型", "屏幕分辨率",
}


def guess_is_platform_column(col_name: str) -> bool:
    if col_name.strip() in _CREDAMO_METADATA_EXACT_COLUMNS:
        return True
    if _PLATFORM_ID_TOKEN_RE.search(col_name):
        return True
    lowered = col_name.lower()
    return any(keyword in lowered for keyword in _PLATFORM_KEYWORDS)


_PLATFORM_SOURCE_HINTS = {
    "prolific": "Prolific",
    "credamo": "Credamo 见数",
    "见数": "Credamo 见数",
    "pickfu": "PickFu",
    "tally": "Tally",
}


def guess_platform_source(columns: list[str]) -> str:
    lowered_cols = " ".join(columns).lower()
    hits = [label for hint, label in _PLATFORM_SOURCE_HINTS.items() if hint in lowered_cols]
    return "、".join(dict.fromkeys(hits))  # dict.fromkeys 去重但保顺序

# CHART_SECTIONS 是③④⑤要画图的三段；ALL_SECTIONS 多一个"平台信息"（⑩ 受访者信息，
# 平台自动收录的数据，不画图、不进③④⑤循环，只作为⑥完整数据表格里一个默认隐藏的列组，
# 以及⑦点开某人时顶部那一行）。
CHART_SECTIONS = ["筛选", "正式", "基础信息"]
ALL_SECTIONS = CHART_SECTIONS + ["平台信息"]
SECTION_ORDER = CHART_SECTIONS  # 兼容旧名字，③④⑤ 循环继续用这个
SECTION_PREFIX = {"筛选": "S", "正式": "Q", "基础信息": "C", "平台信息": "P"}
SECTION_HEADER = {
    "筛选": "3. 筛选问题",
    "正式": "4. 正式问卷",
    "基础信息": "5. 基础信息探测",
    "平台信息": "10. 受访者信息",
}


def _is_chinese(text: str) -> bool:
    return bool(CJK_PATTERN.search(str(text)))


DB_PATH = PROJECT_ROOT / "data" / "app.db"


def _get_db_conn():
    """整个 app 共用一个 SQLite 连接（存在 st.session_state 里，不用每次重开）。"""

    if "db_conn" not in st.session_state:
        st.session_state["db_conn"] = db.init_db(str(DB_PATH))
    return st.session_state["db_conn"]


def _get_provider_or_none(purpose: str = "general"):
    """按 Home 页设置的供应商/模型/API key 构造 provider；拿不到就返回 None，
    具体原因（没配 key、供应商名不对等）存进 st.session_state["_provider_error::<purpose>"]，
    调用方用 provider_error_message(purpose) 取出来显示给用户，不再是硬编码"没有 ANTHROPIC_API_KEY"。

    purpose="translation" 用的是首页可以单独配置的"翻译专用供应商"（默认推荐 DeepSeek，
    比通用设置里常配的 Claude 便宜很多）；没单独配的话自动退回通用供应商，见
    engine.llm_provider.get_provider 的 purpose 参数说明。分开存 error 是因为同一次渲染
    里"AI 分类"（general）和"自动翻译"（translation）可能都会调用，用同一个 key 会互相
    覆盖对方的报错信息。
    """

    from engine.llm_provider import get_provider

    conn = _get_db_conn()
    error_key = f"_provider_error::{purpose}"
    try:
        provider = get_provider(conn, purpose=purpose)
    except (RuntimeError, ValueError) as exc:
        st.session_state[error_key] = str(exc)
        return None
    st.session_state[error_key] = None
    return provider


def provider_error_message(purpose: str = "general") -> str:
    return st.session_state.get(f"_provider_error::{purpose}") or (
        "没有配置可用的 AI 供应商，去首页「API/模型设置」填一下。"
    )


TRANSLATION_CACHE_PATH = PROJECT_ROOT / "data" / "translation_cache.json"


def _translation_cache() -> dict:
    """本地持久化翻译缓存，按精确英文原文做 key——不是按题号。

    这样同一句话（比如同一批 tagline 在组1/组2/组3里重复出现，或者今天分析过的问卷
    明天又传一次）只会真正调用一次 API，其余全部命中缓存，跨 session、跨进程重启都有效
    （存在 data/translation_cache.json 里，不是 st.session_state）。
    """

    if "translation_cache" not in st.session_state:
        try:
            st.session_state["translation_cache"] = json.loads(
                TRANSLATION_CACHE_PATH.read_text(encoding="utf-8")
            )
        except (FileNotFoundError, json.JSONDecodeError):
            st.session_state["translation_cache"] = {}
    return st.session_state["translation_cache"]


def _persist_translation_cache(cache: dict) -> None:
    TRANSLATION_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TRANSLATION_CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def translate_texts_cached(texts: list[str]) -> tuple[dict[str, str], str | None]:
    """把 texts 里没缓存过的部分批量翻译、存回持久缓存；返回 (全量缓存, 出问题时的说明)。

    只有校验通过（ai_translate.translate_verbatims 判定 valid）的翻译才写入持久缓存——
    没通过校验的这次先不存，避免一条边界情况的坏翻译永久污染缓存，下次还会重试。
    """

    cache = _translation_cache()
    unique_texts = list(dict.fromkeys(texts))
    missing = [t for t in unique_texts if t not in cache]
    if not missing:
        return cache, None

    provider = _get_provider_or_none(purpose="translation")
    if provider is None:
        return cache, f"{provider_error_message('translation')}，暂时显示英文原文"

    items = [{"response_id": i, "text_en": t} for i, t in enumerate(missing)]
    try:
        results = ai_translate.translate_verbatims(provider, items, protected_terms=[])
    except Exception as exc:  # noqa: BLE001
        return cache, f"自动翻译失败（{exc}），暂时显示英文原文"

    changed = False
    bad_count = 0
    for r in results:
        source_text = missing[r["response_id"]]
        if r["valid"]:
            cache[source_text] = r["translation"]
            changed = True
        else:
            bad_count += 1
    if changed:
        _persist_translation_cache(cache)

    return cache, (f"有 {bad_count} 条翻译没通过校验，暂时显示英文原文，建议人工核对" if bad_count else None)


def render_question_header(
    q_no: str, title: str, type_label: str, option_values: list[str]
) -> tuple[dict[str, str], str | None]:
    """渲染标题横条里那一行加粗标题，返回 (label_map, caption_text)。

    caption_text（英文原题/翻译异常提示）不在这个函数里直接渲染——现在标题横条是深色底、
    只放标题文字和右边那排图标按钮，这行说明文字要在横条外面、正常的浅色背景上单独一行，
    调用方在横条的 `with` 块结束之后自己按需要调 `st.caption(caption_text)`；中文原生
    问卷不需要这行，`caption_text` 是 None。

    中文原生问卷：直接显示原文，不需要第二行英文，label 就是原值本身。
    英文问卷：自动翻译，不用点按钮确认；命中本地持久缓存的文本不会重新调用 API。

    有些问卷原文自己就带编号（比如"Q10. What made..."）——如果直接在前面再加我们自己
    生成的 q_no（比如这道题在"正式"这段恰好是第 11 道，生成的是"Q11"），会变成
    "Q11. Q10. ..."这种重复又对不上的编号。原文自带编号时只是不重复显示内部 q_no，
    session_state key、交叉分析引用、Word 导出等内部用法完全不受影响。
    """

    has_embedded_number = bool(_EMBEDDED_QUESTION_NUMBER_RE.match(title.strip()))
    display_prefix = "" if has_embedded_number else f"{q_no}. "
    label_map, title_zh, note = _compute_label_map(title, option_values)

    if _is_chinese(title):
        st.markdown(f"**{display_prefix}{title}【{type_label}】**")
        return label_map, None

    st.markdown(f"**{display_prefix}{title_zh}【{type_label}】**")
    caption = f"*{title}*"
    if note:
        caption += f"　（{note}）"
    return label_map, caption


def _compute_label_map(title: str, option_values: list[str]) -> tuple[dict[str, str], str, str | None]:
    """算出"原始选项 → 展示用标签"的映射，纯计算，不调用任何 st.markdown/st.caption。

    `render_question_header` 渲染页面时用这份逻辑，Word 导出的单选/多选题图表也要用
    同一份——导出以前只调了 `stats.single_choice_stats`/`multi_choice_stats`，没有
    经过这里，所以导出的图表选项一直是英文原文，跟网页上"中文／English"的双语展示
    对不上（真实审查发现的问题）。两边共用这一个函数，不会以后其中一边改了翻译逻辑、
    另一边忘了跟着改。

    返回 (label_map, title_zh, note)：label_map 给 `relabel()` 用；title_zh 是标题的
    中文展示版；note 是翻译异常提示，没有异常就是 None。
    """

    if _is_chinese(title):
        return {opt: opt for opt in option_values}, title, None

    texts = [title] + list(dict.fromkeys(option_values))
    cache, note = translate_texts_cached(texts)
    title_zh = cache.get(title, title)
    return {opt: cache.get(opt, opt) for opt in option_values}, title_zh, note


def relabel(stats_result: list[dict], label_map: dict[str, str]) -> list[dict]:
    """把 stats 结果里的原始 option 值换成中英双标的展示标签，不动 n/pct。"""

    relabeled = []
    for row in stats_result:
        raw = row["option"]
        zh = label_map.get(raw, raw)
        display = raw if zh == raw else f"{zh}／{raw}"
        relabeled.append({**row, "option": display})
    return relabeled


def render_label_override_editor(q_no: str, display_result: list[dict]) -> list[dict]:
    """图表上的文字（图例/坐标轴那一行字）支持手动改——默认还是用 relabel() 生成的
    "中文／英文"这套自动文本，改的只是"图表上显示成什么"，不影响背后真实的选项值和
    统计数字（人数/占比永远是 Python 自己算的，这个编辑框改不了这些，也不会影响
    交叉分析/AI 洞察这些引用同一份数字的地方）。
    """

    state_key = f"label_overrides_{q_no}"
    overrides = st.session_state.setdefault(state_key, {})
    with st.popover("", icon=":material/edit:", help="编辑图表上显示的文字"):
        st.caption("留空就用自动生成的文字；改了这里，下面的图表和排版截图会跟着变。")
        for row in display_result:
            original = row["option"]
            overrides[original] = st.text_input(
                original,
                value=overrides.get(original, ""),
                key=f"label_override_{q_no}_{original}",
                placeholder=original,
            )
    return [
        {**row, "option": overrides.get(row["option"]) or row["option"]}
        for row in display_result
    ]


def render_chart_save_controls(download_col, copy_col, q_no: str, chart_kind: str, stats_result: list[dict], title: str) -> None:
    """下载/复制这道题的图表——单独一张图，最上面带着问题原文的中文版，不用依赖
    网页上下文就能直接发给别人。中文标题优先用翻译缓存里的结果，题目本来就是中文的
    (translation_cache 查不到) 就用原文，两种情况 title_zh 都是"这道题该显示的中文"。
    """

    title_zh = st.session_state.get("translation_cache", {}).get(title, title)
    png_bytes = _chart_snapshot_png_for_save(q_no, chart_kind, stats_result, title_zh)
    with download_col:
        st.download_button(
            "",
            data=png_bytes,
            file_name=f"{q_no}.png",
            mime="image/png",
            icon=":material/download:",
            key=f"chart_download_{q_no}",
            help="下载这张图表",
        )
    with copy_col:
        _render_copy_image_button(png_bytes, key=f"chart_copy_{q_no}")


CONTEXT_LINK_WINDOW = 5  # "前后延伸5题"——候选范围是同一段里前后各 5 题，不是整段任选


def _context_candidates(unit_index: int, sec_units: list[dict]) -> list[dict]:
    """一道开放题可以关联的候选题目——同一段（③④⑤各自独立）里前后各 5 题，不含自己。"""

    start = max(0, unit_index - CONTEXT_LINK_WINDOW)
    end = min(len(sec_units), unit_index + CONTEXT_LINK_WINDOW + 1)
    return [u for i, u in enumerate(sec_units[start:end], start=start) if i != unit_index]


def render_open_context_picker(q_no: str, title: str, unit_index: int, sec_units: list[dict]) -> list[dict]:
    """开放题要不要展示"前一题/附近题"每个受访者自己的答案作为上下文——默认值靠一个
    便宜的关键词判断（题干像"为什么/原因"这种追问句就默认关联紧邻的上一题），但从来
    不强制：候选范围是前后 5 题以内的任意题目，用户随时可以在这里手动加/去掉。
    """

    candidates = _context_candidates(unit_index, sec_units)
    if not candidates:
        return []

    candidate_by_no = {u["display_no"]: u for u in candidates}
    default_no: list[str] = []
    if unit_index > 0 and clean.looks_like_reason_followup_question(title):
        prev_unit = sec_units[unit_index - 1]
        if prev_unit["kind"] != "open" and prev_unit["display_no"] in candidate_by_no:
            default_no = [prev_unit["display_no"]]

    state_key = f"context_link_{q_no}"
    if state_key not in st.session_state:
        st.session_state[state_key] = default_no

    selected_no = st.multiselect(
        "拓展其他问题回答",
        options=[u["display_no"] for u in candidates],
        format_func=lambda no: f"{no}｜{candidate_by_no[no]['title']}",
        key=state_key,
        placeholder="+",
        label_visibility="collapsed",
    )
    return [candidate_by_no[no] for no in selected_no]


def _multi_select_list_series(section_df: pd.DataFrame, columns: list[str]) -> pd.Series:
    """把一道多选题的原始列变成"每人一份选中项列表"的 pd.Series。

    正常上传的数据是 N 个布尔拆分列，要用 `merge_multi_select_columns` 合并；从历史
    记录加载回来的数据在存库那一刻就已经合并成一列（这一列的值本身就是 Python
    list），不用再合并一次——原始拆分列在写库时就没有保留，也没法再合并。这个判断
    这个项目里好几个地方都要用（正文图表、开放题关联展示、交叉分析、Word 导出），
    写成一个函数，不然某处改了判断标准、别处忘了跟着改，两边就不一致了。
    """

    already_merged = len(columns) == 1 and section_df[columns[0]].apply(lambda v: isinstance(v, list)).all()
    if already_merged:
        return section_df[columns[0]]
    option_col_labels = clean.option_labels_for_group(columns)
    return clean.merge_multi_select_columns(section_df, columns, option_labels=option_col_labels)


def _context_value_series(ctx_unit: dict, section_df: pd.DataFrame) -> pd.Series:
    """取一道"上下文题"每个受访者的展示值——跟正文图表用的是同一份翻译缓存，
    不重新翻译一遍；多选合并成顿号连接的字符串，单选/数值/开放原样（数值/开放没有
    需要翻译的选项文本）。"""

    cache = st.session_state.get("translation_cache", {})
    if ctx_unit["kind"] == "multi":
        list_series = _multi_select_list_series(section_df, ctx_unit["columns"])
        return list_series.apply(lambda vals: "、".join(cache.get(v, v) for v in vals) if vals else "")

    col = ctx_unit["columns"][0]
    raw = section_df[col]
    if ctx_unit["kind"] == "single":
        return raw.map(lambda v: cache.get(v, v) if pd.notna(v) else v)
    return raw


CHART_HEIGHT = {"pie": "460px", "bar_h": "380px"}


def _should_render_interactive_chart(q_no: str) -> bool:
    """这道题的图表要不要走网页上原来那条交互式 ECharts 路径。

    只有在"确实插了图片、且用户勾了要把图表也放进排版"的时候才关掉交互图——这两个
    条件都成立时，`render_image_attachments_grid` 会把同一份数据再画一张静态截图
    放进排版预览里，两张图同时出现只会让人confuse"这是不是同一个东西"（真实反馈过
    "下面多了一个不知道是什么的图"）。这里要在交互图表还没画之前就知道结果，
    但"是否要放进排版"这个勾选框本身是在 `render_image_attachments_grid` 里才渲染
    （在这一行代码执行之后）——用 session_state 提前读，是这个项目里已经用过好几次
    的写法：勾选框只要带了 key，它的值在上一次 rerun 就已经写进 session_state 了，
    不用等那一行代码真的跑到。
    """

    images = st.session_state.get(f"images_{q_no}", [])
    if not images:
        return True
    return not st.session_state.get(f"include_chart_in_grid_{q_no}", True)


def render_chart(chart_type: str, config: dict, key: str) -> None:
    config["title"] = {"text": "", "left": "center"}  # 标题已经在上面渲染过，图内不重复
    # ECharts 图表组件是用 iframe 渲染的，跟外面"纸张"卡片是两个独立的文档，CSS
    # 够不到里面——iframe 默认背景是白的，"纸张"背景也是白的，理论上应该看不出差别，
    # 但真实反馈说图表区域和标题区域的颜色对不上（可能是 iframe 默认背景和纸张的
    # 白不是同一个白，或者中间有细微的阴影/描边）。直接在 ECharts 配置里显式声明
    # backgroundColor，图表内部自己画的这块背景就一定跟纸张同色，不用猜 iframe
    # 默认值到底是什么。
    config["backgroundColor"] = theme["surface"]
    footer = config.pop("_footer", "")

    if chart_type == "bar_h":
        # 横条图的高度原来是写死的 380px，选项一多（比如多选题选项、AI 分类出来的
        # 类目）就会被压得又挤又矮，标签叠在一起。改成按选项数量算——每个选项分到
        # 固定的一份高度，选项越多图越高，选项少的时候也不会矮于原来的 380px。
        # 长标签（中英双语拼在一起）也是真实反馈过的问题，跟饼图标签用同一套办法：
        # 允许换行、给固定宽度，不让 ECharts 按单行硬截断。
        n_options = len(config.get("yAxis", {}).get("data", []))
        height = f"{max(380, 46 * n_options + 100)}px"
        config.setdefault("yAxis", {})["axisLabel"] = {"width": 170, "overflow": "break"}
    else:
        height = CHART_HEIGHT.get(chart_type, "380px")

    # 默认的 canvas 渲染器在高分屏（Retina）上会糊：ECharts 按 devicePixelRatio 决定
    # 画布内部实际画多少物理像素，这个组件的 Python 封装没有开放这个参数让我们传，
    # 一直是按 1 倍算，高分屏上被浏览器拉伸显示就会糊字。svg 是矢量渲染，不存在
    # "分辨率不够"这回事，不管什么屏幕都清晰——这几个图表数据量很小（几个选项的
    # 统计图），svg 在大数据量/频繁动画场景才会有的性能劣势基本不适用。
    st_echarts(
        options=config,
        height=height,
        width="100%",
        key=key,
        renderer="svg",
    )
    if footer:
        # 样本量放到右下角，不跟左边的图例/标签抢视线——用一个窄的右侧列把它推过去，
        # 比另外写 CSS controlling text-align 更简单，跟 st.caption 本身的样式完全一样。
        _, footer_col = st.columns([5, 1])
        with footer_col:
            st.caption(footer)


def render_open_ai_classify_trigger(q_no: str, series: pd.Series, filter_key: str = "") -> None:
    """开放题标题行最右边的星标按钮——点开一个小弹窗选封闭/开放分类，不占正文纵向空间。

    filter_key：如果这道开放题当前按关联题目的某个选项筛选过（比如只看"选了空气能
    空调"的人），传进来的 series 已经是筛完的子集，这里只是把分类结果存到一个带筛选
    条件的独立 key 上——不同筛选条件的分类结果互不覆盖，切换筛选条件之后各自的结果
    还能找回来，不用重新跑一遍。
    """

    ai_key = f"ai_result_{q_no}" if not filter_key else f"ai_result_{q_no}__{filter_key}"

    with st.popover("AI 分类", use_container_width=True, key=f"ai_classify_trigger_{q_no}_{filter_key}"):
        if filter_key:
            st.caption(f"当前只分析筛选出来的 {len(series)} 人（{filter_key}），不是全部受访者。")
        mode = st.radio(
            "选择分类方式",
            ["封闭分类（自己填类目）", "开放聚类（AI 自动提炼类目）", "自定义分析（自己写分析要求）"],
            key=f"mode_{q_no}_{filter_key}",
        )
        categories_input = ""
        instruction_input = ""
        if mode.startswith("封闭"):
            categories_input = st.text_input("候选类目（逗号分隔）", key=f"cats_{q_no}_{filter_key}")
        elif mode.startswith("自定义"):
            instruction_input = st.text_area(
                "分析要求（比如「判断每条回答有没有提到价格敏感」）",
                key=f"instruction_{q_no}_{filter_key}",
                placeholder="用自己的话描述想从这些开放题回答里提炼出什么——AI 会先按这个要求总结出几个类目，再把每条回答分到对应类目里，出来的还是图表能直接画的分类结果。",
            )

        if st.button("运行", key=f"run_ai_{q_no}_{filter_key}", type="primary"):
            provider = _get_provider_or_none()
            if provider is None:
                st.warning(provider_error_message())
            else:
                responses = [{"response_id": int(i), "text": str(text)} for i, text in series.items()]
                try:
                    with st.spinner("调用 AI 中…"):
                        if mode.startswith("封闭"):
                            categories = [c.strip() for c in categories_input.split(",") if c.strip()]
                            if not categories:
                                st.error("请先填至少一个候选类目。")
                                st.stop()
                            assignments = ai_classify.classify_closed(provider, responses, categories)
                            st.session_state[ai_key] = {"categories": categories, "assignments": assignments}
                        elif mode.startswith("自定义"):
                            if not instruction_input.strip():
                                st.error("请先填写分析要求。")
                                st.stop()
                            result = ai_classify.classify_custom(provider, responses, instruction_input)
                            st.session_state[ai_key] = result
                        else:
                            result = ai_classify.classify_open(provider, responses)
                            st.session_state[ai_key] = result
                except Exception as exc:  # noqa: BLE001
                    st.error(f"AI 调用失败：{exc}")


def render_open_ai_classify_results(q_no: str, series: pd.Series, filter_key: str = "") -> None:
    """AI 分类结果——渲染在正文里（不是弹窗里），弹窗关掉之后结果还在。

    filter_key 要跟 render_open_ai_classify_trigger 传的保持一致，才能读到同一份结果——
    这里的 series 也已经是筛过的子集，跟触发分类时用的是同一批人。
    """

    ai_key = f"ai_result_{q_no}" if not filter_key else f"ai_result_{q_no}__{filter_key}"
    if ai_key in st.session_state:
        assignments = st.session_state[ai_key]["assignments"]
        id_to_category = {a["response_id"]: a["category"] for a in assignments}
        display_df = series.to_frame(name="原文")
        display_df["AI 分类"] = [id_to_category.get(int(i), "") for i in series.index]
        st.dataframe(display_df)

        # Python 自己算数字，不采信 AI 的计数——分类结果喂回 stats 引擎
        category_series = pd.Series([a["category"] for a in assignments])
        cat_stats = stats.single_choice_stats(category_series)
        cat_chart_type = chart_spec.choose_chart_type("single", len(cat_stats))
        cat_config = chart_spec.build_chart_config(cat_chart_type, cat_stats, "", f"n = {len(category_series)}", color_palette=_active_chart_palette())
        st.caption("AI 分类分布")
        render_chart(cat_chart_type, cat_config, key=f"ai_chart_{q_no}_{filter_key}")


def _chart_snapshot_png(q_no: str, chart_kind: str, stats_result: list[dict]) -> bytes:
    """把图表渲染成一张 PNG（复用 export_word.py 已经测过的 matplotlib 渲染逻辑），
    结果按内容指纹缓存在 session_state 里。

    这个缓存不是可有可无的优化：拖拽画布里拖动/调整大小结束时会触发一次脚本重跑
    （Streamlit 自定义组件的通信方式就是"组件值一变就整页重跑一次脚本"）——如果不缓存，
    每次都要重新跑一次 matplotlib（几百毫秒的 CPU 工作），拖拽会卡到看起来像坏的。
    指纹只看 option/n，数据没变就直接用缓存，不重新画。
    """

    fingerprint = (chart_kind, tuple((row["option"], row["n"]) for row in stats_result))
    cache_key = f"chart_png_cache_{q_no}"
    cached = st.session_state.get(cache_key)
    if cached is not None and cached[0] == fingerprint:
        return cached[1]

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        export_word._render_chart_image(chart_kind, stats_result, tmp.name, color_palette=_active_chart_palette())
        png_bytes = Path(tmp.name).read_bytes()

    st.session_state[cache_key] = (fingerprint, png_bytes)
    return png_bytes


def _chart_snapshot_png_for_save(q_no: str, chart_kind: str, stats_result: list[dict], title_zh: str) -> bytes:
    """"保存单张图表"按钮用的版本——比 _chart_snapshot_png 多把问题原文（中文版）
    画在图表最上面，这样单独存下来/发给别人的这张图，不用额外说明是哪道题。跟排版
    画布用的那份缓存分开存（那份不带标题，两者用途不一样，不能共用一个缓存 key）。
    """

    fingerprint = (chart_kind, title_zh, tuple((row["option"], row["n"]) for row in stats_result))
    cache_key = f"chart_png_with_title_cache_{q_no}"
    cached = st.session_state.get(cache_key)
    if cached is not None and cached[0] == fingerprint:
        return cached[1]

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        export_word._render_chart_image(chart_kind, stats_result, tmp.name, title=title_zh, color_palette=_active_chart_palette())
        png_bytes = Path(tmp.name).read_bytes()

    st.session_state[cache_key] = (fingerprint, png_bytes)
    return png_bytes


def _render_copy_image_button(png_bytes: bytes, key: str) -> None:
    """一键把图表图片复制到系统剪贴板——用浏览器原生 Clipboard API 写一段自包含的
    静态 HTML+JS（st.components.v1.html，Streamlit 自带、稳定的核心功能，不是第三方
    组件），没有 Python↔JS 双向通信，跟这个 session 之前在 streamlit-elements 上
    栽的那两次跟头是完全不同的风险等级。

    没法在这边没有浏览器的环境里验证 Clipboard 写图片这个操作在具体浏览器版本上的
    实际效果——理论上现代 Chrome/Edge/Safari 都支持，个别较老的 Firefox 版本对写入
    图片到剪贴板的支持不完整；点了没反应的话大概率是这个原因，需要你实际点一下确认。
    """

    # 图标用内联 SVG 画，不用图标字体——这段 HTML 是在 st.components.v1.html 自己的
    # 沙盒 iframe 里跑的，跟主页面是两个独立文档，主页面上那份题目标题横条的 CSS
    # （st-key-qbar_ 那批规则）够不到这里面，横条同款的"方形/无边框/hover 反色"效果
    # 要在这段自包含 HTML 里自己重新写一遍。
    #
    # 真实截图发现的 bug：这里颜色一直写的是 theme['ink']，是横条改用统一的
    # QBAR_BG（"75%黑"，两个风格通用、不跟着 theme 走）之前的旧值，两个颜色不一样——
    # 蓝调风格下 theme['ink'] 是深蓝而不是横条真正的灰黑色，复制按钮这个小方块颜色
    # 跟周围横条对不上，看起来像是单独悬空的一个盒子。另外这段 HTML 是完整独立文档，
    # 浏览器默认会给 <body> 加 8px 外边距，没有显式清零的话，iframe 自己的（跟横条
    # 不一样的）背景会在按钮四周露出一圈，两个问题叠加在一起，视觉上就是"这个图标
    # 间距明显比其他图标大"——其实不是间距变了，是颜色和留白对不上。这里改成统一用
    # QBAR_BG，并且清零 body 的默认外边距、把 body 背景也设成 QBAR_BG，让这个 iframe
    # 内部跟外面的横条严丝合缝。
    b64 = base64.b64encode(png_bytes).decode("ascii")
    bar_color = QBAR_BG
    html = f"""
    <style>
    html, body {{
        margin:0; padding:0; background:{bar_color};
    }}
    #{key} {{
        width:2.3em;height:2.3em;padding:0;border:none;border-radius:0;
        background:{bar_color};cursor:pointer;
        display:flex;align-items:center;justify-content:center;
    }}
    #{key}:hover {{ background:#ffffff; }}
    #{key}:hover svg {{ stroke:{bar_color}; }}
    </style>
    <div style="display:flex;align-items:center;gap:8px;background:{bar_color};">
        <button id="{key}" title="复制这张图表到剪贴板">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#ffffff"
                 stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect x="9" y="9" width="13" height="13" rx="2"></rect>
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
            </svg>
        </button>
        <span id="{key}_status" aria-live="polite" style="font-size:12px;color:{bar_color};"></span>
    </div>
    <script>
    document.getElementById("{key}").addEventListener("click", async () => {{
        const status = document.getElementById("{key}_status");
        try {{
            const res = await fetch("data:image/png;base64,{b64}");
            const blob = await res.blob();
            await navigator.clipboard.write([new ClipboardItem({{"image/png": blob}})]);
            status.textContent = "已复制";
            status.style.color = "#2E7D52";
        }} catch (err) {{
            status.textContent = "复制失败";
            status.style.color = "#B23B3B";
            console.error(err);
        }}
        setTimeout(() => {{ status.textContent = ""; }}, 1500);
    }});
    </script>
    """
    st.components.v1.html(html, height=42)


def render_image_attachments_trigger(q_no: str) -> None:
    state_key = f"images_{q_no}"
    images = st.session_state.setdefault(state_key, [])

    with st.popover("", icon=":material/add_photo_alternate:", help="插入图片"):
        # file_uploader 有个坑：只要 key 不变，它会一直记得这次选过的文件、每次 rerun
        # 都原样交还给你，不是"只在你选文件的那一次"才返回——不是靠 key 换掉来复位的话，
        # 删除一张图片之后紧接着的那次 rerun，这里会看到"上传框里还有这个文件、但
        # images 里已经没有了"，判定成"新上传"又给加回去，delete 按钮等于白点了。
        # 换 key 强制这个控件复位，成功吃进一批文件之后就跟它没关系了。
        uploader_key_counter = st.session_state.setdefault(f"img_uploader_key_{q_no}", 0)
        uploaded_images = st.file_uploader(
            "选择图片（可多选，可重复调用多次追加）",
            type=["png", "jpg", "jpeg"],
            accept_multiple_files=True,
            key=f"img_upload_{q_no}_{uploader_key_counter}",
        )
        if uploaded_images:
            existing_names = {img["name"] for img in images}
            added = False
            for f in uploaded_images:
                if f.name not in existing_names:
                    content = f.getvalue()
                    # bytes_hash 只在插入这一刻算一次，存起来备用——判断"要不要触发新的
                    # 保存"的时候只比这个哈希，不用每次 rerun 都重新算一遍图片字节。
                    images.append(
                        {
                            "bytes": content,
                            "name": f.name,
                            "caption": "",
                            "bytes_hash": hashlib.md5(content).hexdigest(),
                        }
                    )
                    added = True
            if added:
                st.session_state[f"img_uploader_key_{q_no}"] += 1
                st.rerun()

        delete_index = None
        move_swap: tuple[int, int] | None = None
        for i, img in enumerate(images):
            image_col, action_col = st.columns([3, 1])
            image_col.image(img["bytes"], use_container_width=True)
            with action_col:
                # 排版顺序用"上移/下移"调整，不是拖拽——排版里这张图排第几个，就是它在
                # images 这个列表里的位置，跟下面按"每行放几张"分组渲染时用的是同一个顺序。
                if st.button("↑", key=f"img_up_{q_no}_{i}", disabled=i == 0, help="上移这张图片"):
                    move_swap = (i, i - 1)
                if st.button("↓", key=f"img_down_{q_no}_{i}", disabled=i == len(images) - 1, help="下移这张图片"):
                    move_swap = (i, i + 1)
                if st.button("删除", key=f"img_del_{q_no}_{i}", help="删除这张图片"):
                    delete_index = i
            img["caption"] = st.text_input(
                "图片描述", value=img["caption"], key=f"img_caption_{q_no}_{i}", label_visibility="collapsed",
                placeholder="给这张图配一行文字描述",
            )
            st.divider()
        if move_swap is not None:
            a, b = move_swap
            images[a], images[b] = images[b], images[a]
            st.rerun()
        if delete_index is not None:
            images.pop(delete_index)
            st.rerun()


def render_image_attachments_grid(
    q_no: str,
    chart_kind: str | None = None,
    chart_stats_result: list[dict] | None = None,
) -> None:
    """插入图片 + 文字描述；如果这道题有图表，图表也会作为"一块"参与排版，可以跟插入的
    图片放在同一行。排版用的是"每行放几张"+ 上下移动调整顺序，不是自由拖拽——原来那版
    用 streamlit-elements（react-grid-layout）做自由拖拽/调整大小，两轮下来都没能在真实
    浏览器里跑出预期效果（这个组件本身也确认过是个不算活跃维护的第三方库），排查成本
    已经不小；换成 Streamlit 原生的多栏布局，没有任何第三方 JS 组件依赖，图片按分到的
    那一栏宽度等比缩放、不会变形，"上下移动"也是最基础的按钮点击，不会有"这个事件到底
    有没有被真正触发"这种不确定性。

    没有插入图片时，图表还是走原来那条交互式 ECharts 路径（保留悬浮提示这些交互能力）——
    一旦插入了图片，图表就变成参与排版的静态截图，图表交互性和排版二选一，不能同时要。
    """

    state_key = f"images_{q_no}"
    images = st.session_state.setdefault(state_key, [])

    if not images:
        return

    # 图表要不要一起参与排版，问一下——之前是只要这道题有图表就自动塞进去，结果是
    # 上传好几张图之后突然多出一个不知道是什么的方块（图表被挤成 1/N 宽，缩得几乎
    # 看不清，标注文字"图表"两个字也小得容易被忽略）。改成显式勾选，默认还是勾上
    # （这是最早就有的设计意图——图表可以跟插入的图片并排），但至少不会莫名其妙。
    include_chart = False
    if chart_kind is not None:
        include_chart = st.checkbox(
            "这道题的图表也放进下面的排版里（跟插入的图片一起参与「每行放几张」分组）",
            value=st.session_state.get(f"include_chart_in_grid_{q_no}", True),
            key=f"include_chart_in_grid_{q_no}",
        )

    tiles: list[dict] = []
    if include_chart:
        tiles.append({"kind": "chart"})
    tiles.extend({"kind": "image", **img} for img in images)

    if include_chart:
        per_row_default = 2
        per_row_help = "图表算一张，跟插入的图片一起参与排版；改小/改大之后，下面立刻按新的行宽重新分组。"
    else:
        per_row_default = 1
        per_row_help = "没有把图表放进排版（或者这道题本来就没有图表），纯粹是插入的图片自己怎么分行。"
    per_row = st.number_input(
        "每行放几张",
        min_value=1,
        max_value=6,
        value=st.session_state.get(f"images_per_row_{q_no}", per_row_default),
        key=f"images_per_row_{q_no}",
        help=per_row_help,
    )

    for row_start in range(0, len(tiles), per_row):
        row_tiles = tiles[row_start : row_start + per_row]
        row_cols = st.columns(len(row_tiles))
        for col, tile in zip(row_cols, row_tiles):
            if tile["kind"] == "chart":
                chart_png = _chart_snapshot_png(q_no, chart_kind, chart_stats_result)
                col.image(chart_png, use_container_width=True)
                col.caption(f"↑ {q_no} 的图表")
            else:
                col.image(tile["bytes"], use_container_width=True)
                if tile["caption"]:
                    col.caption(tile["caption"])


def _render_open_answer_table(display_table: pd.DataFrame) -> None:
    """开放题的"原始数据"表格——特意不用 st.dataframe。

    这个坑踩了好几轮才看清楚：st.dataframe 背后是 Glide Data Grid，整个表格主体是
    画在一块 <canvas> 上的，不是普通的 DOM 节点——边框颜色、隔行底色这些，都是
    Streamlit 自己根据 .streamlit/config.toml 里的主题色算出来直接画上去的（对应
    Streamlit 内部的 theme.dataframeBorderColor / bgCellMedium 这些），我们在页面里
    注入的 CSS 完全够不到画布内部，边框去不掉、隔行底色跟纸张卡片对不上、自定义
    滚动条时有时无——这几个问题這一路上反复出现，本质都是同一个"画布不认 CSS"的
    根因，不是没改对，是改不到。

    这道题的表格本来就只是展示，从来没要过排序/筛选表头这些 st.dataframe 才有的
    交互，换成一个手写的普通 HTML <table>（真实 DOM）不损失任何功能，反而能让
    "去掉外边框、隔行颜色统一、滚动条稳定可见"这几条真实反馈一次性、彻底地满足，
    不用再跟第三方组件的内部实现来回拉锯。
    """

    columns = list(display_table.columns)
    header_cells = "".join(f"<th>{html_lib.escape(str(c))}</th>" for c in columns)
    body_rows = []
    for idx, row in zip(display_table.index, display_table.itertuples(index=False)):
        cells = "".join(
            f"<td>{html_lib.escape('' if pd.isna(v) else str(v))}</td>" for v in row
        )
        body_rows.append(f"<tr><td class='oq-idx'>{idx}</td>{cells}</tr>")

    table_html = f"""
    <div class="oq-table-wrap">
        <table class="oq-table">
            <thead><tr><th class="oq-idx"></th>{header_cells}</tr></thead>
            <tbody>{''.join(body_rows)}</tbody>
        </table>
    </div>
    """
    st.markdown(table_html, unsafe_allow_html=True)


def render_unit(
    unit: dict,
    section_df: pd.DataFrame,
    n_for_footer: int,
    sec_units: list[dict] | None = None,
    unit_index: int | None = None,
) -> None:
    """按题型渲染一个"题目单元"（单选/多选/开放/数值），section_df 已经是这一段该用的样本。

    sec_units/unit_index：开放题要在同一段里前后找候选关联题目才需要，其他题型用不上，
    默认 None 也不影响单选/多选/数值的渲染。
    """

    kind = unit["kind"]
    q_no = unit["display_no"]
    title = unit["title"]
    cols = unit["columns"]

    chart_kind = None
    chart_stats_result = None

    if kind == "single":
        col = cols[0]
        raw_result = stats.single_choice_stats(section_df[col])
        options = [r["option"] for r in raw_result]
        with st.container(key=f"qbar_{q_no}"):
            header_col, insert_col, edit_col, copy_col, download_col = st.columns([8.5, 1, 1, 1, 1], gap=8)
            with header_col:
                label_map, header_caption = render_question_header(q_no, title, "单选题", options)
            display_result = relabel(raw_result, label_map)
            with edit_col:
                display_result = render_label_override_editor(q_no, display_result)
            render_chart_save_controls(download_col, copy_col, q_no, "single", display_result, title)
            with insert_col:
                render_image_attachments_trigger(q_no)
        if header_caption:
            st.caption(header_caption)
        chart_type = chart_spec.choose_chart_type("single", len(display_result))
        config = chart_spec.build_chart_config(chart_type, display_result, "", f"n = {n_for_footer}", color_palette=_active_chart_palette())
        if _should_render_interactive_chart(q_no):
            render_chart(chart_type, config, key=f"chart_{q_no}")
        else:
            st.caption("这道题的图表已经放进下面的排版预览里了——把「插入图片」里「图表也放进排版」的勾去掉，可以换回上面这张交互图表。")
        chart_kind, chart_stats_result = "single", display_result

    elif kind == "numeric":
        col = cols[0]
        with st.container(key=f"qbar_{q_no}"):
            header_col, insert_col = st.columns([11, 1])
            with header_col:
                _, header_caption = render_question_header(q_no, title, "数值题", [])
            with insert_col:
                render_image_attachments_trigger(q_no)
        if header_caption:
            st.caption(header_caption)
        result = stats.numeric_stats(section_df[col])
        st.table(pd.DataFrame([result]))

    elif kind == "open":
        col = cols[0]
        series = section_df[col].dropna()

        with st.container(key=f"qbar_{q_no}"):
            header_col, insert_col, star_col = st.columns([9.5, 1, 2], gap=8)
            with header_col:
                _, header_caption = render_question_header(q_no, title, "开放题", [])
            with insert_col:
                render_image_attachments_trigger(q_no)
        if header_caption:
            st.caption(header_caption)

        # 原来这里是 st.expander("", expanded=False)——单独占一整行、只有一个箭头，
        # 跟下面"+"关联展示选择器又是另一整行，看起来是两个莫名其妙的空盒子，外面
        # 还带着 expander 自己的边框。改成不用 st.expander：折叠箭头和"+"选择器
        # 并到同一行（箭头在左，跟真实反馈里说的"隐藏键放到加号左边"一致），默认
        # 展开（划到这里直接看到表格，不用再点一下），自己用一个 session_state
        # 布尔值控制要不要显示表格，不会有任何外层边框。
        show_raw_key = f"show_raw_data_{q_no}"
        if show_raw_key not in st.session_state:
            st.session_state[show_raw_key] = True

        toggle_col, multiselect_col = st.columns([1, 11], gap=8)
        with toggle_col:
            toggle_icon = ":material/expand_less:" if st.session_state[show_raw_key] else ":material/expand_more:"
            if st.button("", icon=toggle_icon, key=f"toggle_raw_{q_no}", help="展开/收起原始数据"):
                st.session_state[show_raw_key] = not st.session_state[show_raw_key]
                st.rerun()
        with multiselect_col:
            context_units: list[dict] = []
            if sec_units is not None and unit_index is not None:
                context_units = render_open_context_picker(q_no, title, unit_index, sec_units)

        # 关联题目的筛选放到最前面算好——AI 分析要不要只看筛选出来的这部分人，
        # 得在调用分类之前就知道，不能等分类按钮点完了才筛（那样筛的只是显示的表格，
        # AI 用的还是全量数据）。筛选这部分不跟着"要不要显示表格"这个开关走——就算
        # 表格收起来了，筛选条件也要能正常配置、正常影响 AI 分类用的数据。
        context_series_by_label: dict[str, pd.Series] = {
            f"{ctx_unit['display_no']}｜{ctx_unit['title']}": _context_value_series(ctx_unit, section_df).reindex(series.index)
            for ctx_unit in context_units
        }

        filtered_index = series.index
        active_filters: list[tuple[str, str]] = []
        if context_series_by_label:
            context_items = list(context_series_by_label.items())
            FILTER_ROW_SIZE = 3
            for row_start in range(0, len(context_items), FILTER_ROW_SIZE):
                row_items = context_items[row_start : row_start + FILTER_ROW_SIZE]
                filter_cols = st.columns(len(row_items))
                for filter_col, (ctx_label, ctx_series) in zip(filter_cols, row_items):
                    options = ["（全部）"] + sorted(v for v in ctx_series.dropna().unique() if v != "")
                    picked = filter_col.selectbox(
                        f"按「{ctx_label}」筛选",
                        options,
                        key=f"context_filter_{q_no}_{ctx_label}",
                    )
                    if picked != "（全部）":
                        active_filters.append((ctx_label, picked))
                        filtered_index = filtered_index[ctx_series.reindex(filtered_index) == picked]

        if st.session_state[show_raw_key]:
            display_df = pd.DataFrame(index=series.index)
            for ctx_label, ctx_series in context_series_by_label.items():
                display_df[ctx_label] = ctx_series
            display_df["原文"] = series
            # 左边那一列编号用的是 pandas 原始 index——filtered_index 是从全量数据里
            # 筛出来的一部分，原始 index 值不是从 0 连续排的（比如筛完剩下第 2/5/8 行，
            # 编号就会显示 2、5、8），看着以为是数据变了，其实只是编号没归零。这里
            # 重新排一遍，不管有没有筛选过，显示出来的编号永远从 1 开始连续递增。
            display_table = display_df.loc[filtered_index].reset_index(drop=True)
            display_table.index = display_table.index + 1
            _render_open_answer_table(display_table)

        filtered_series = series.loc[filtered_index]
        # 筛选条件拼成一个稳定的字符串当 key 的一部分——同一道题、不同的筛选组合，
        # AI 分类结果分开存，不会因为换了个筛选条件重新点分类就把上一次（比如"全部人"
        # 或者"选了另一个选项的人"）的结果覆盖掉，回头切换筛选条件还能看到各自的结果。
        filter_key = "&".join(f"{label}={value}" for label, value in sorted(active_filters))

        with star_col:
            render_open_ai_classify_trigger(q_no, filtered_series, filter_key=filter_key)

        if active_filters:
            note = "、".join(f"「{label}」＝{value}" for label, value in active_filters)
            st.write(f"当前只看 {note} 这部分：{len(filtered_series)} 人（这道题总共 {len(series)} 人填写）。")
        else:
            st.write(f"{len(series)}人填写了这题。")

        render_open_ai_classify_results(q_no, filtered_series, filter_key=filter_key)

    elif kind == "multi":
        list_series = _multi_select_list_series(section_df, cols)
        raw_result = stats.multi_choice_stats(list_series)
        options = [r["option"] for r in raw_result]
        with st.container(key=f"qbar_{q_no}"):
            header_col, insert_col, edit_col, copy_col, download_col = st.columns([8.5, 1, 1, 1, 1], gap=8)
            with header_col:
                zh_map, header_caption = render_question_header(q_no, title, "多选题", options)
            display_result = relabel(raw_result, zh_map)
            with edit_col:
                display_result = render_label_override_editor(q_no, display_result)
            render_chart_save_controls(download_col, copy_col, q_no, "multi", display_result, title)
            with insert_col:
                render_image_attachments_trigger(q_no)
        if header_caption:
            st.caption(header_caption)
        config = chart_spec.build_chart_config("bar_h", display_result, "", f"n = {n_for_footer}", color_palette=_active_chart_palette())
        if _should_render_interactive_chart(q_no):
            render_chart("bar_h", config, key=f"chart_multi_{q_no}")
        else:
            st.caption("这道题的图表已经放进下面的排版预览里了——把「插入图片」里「图表也放进排版」的勾去掉，可以换回上面这张交互图表。")
        chart_kind, chart_stats_result = "multi", display_result

    render_image_attachments_grid(q_no, chart_kind, chart_stats_result)


def build_units(mapping: pd.DataFrame) -> list[dict]:
    """把映射表拆成题目单元：单选/开放/数值一行一个单元；多选按"分组键"相同的行合并成一个单元。"""

    units: list[dict] = []
    seen_multi_keys: set[tuple[str, str]] = set()
    for _, row in mapping.iterrows():
        if row["q_type"] == "忽略":
            continue
        if row["q_type"] == "multi":
            group_key = (row["section"], row["q_no"])
            if group_key in seen_multi_keys:
                continue
            seen_multi_keys.add(group_key)
            cols = mapping[
                (mapping["q_type"] == "multi")
                & (mapping["q_no"] == row["q_no"])
                & (mapping["section"] == row["section"])
            ]["column"].tolist()
            units.append(
                {"kind": "multi", "section": row["section"], "title": row["title"], "columns": cols}
            )
        else:
            units.append(
                {
                    "kind": row["q_type"],
                    "section": row["section"],
                    "title": row["title"],
                    "columns": [row["column"]],
                }
            )
    return units


def assign_display_numbers(units: list[dict], section: str) -> list[dict]:
    prefix = SECTION_PREFIX[section]
    sec_units = [u for u in units if u["section"] == section]
    for i, u in enumerate(sec_units, start=1):
        u["display_no"] = f"{prefix}{i}"
    return sec_units


def _restore_extras(extras: dict) -> None:
    """`_extras_payload()`（定义在本文件后面，⑪导出附近）的反函数——"打开历史分析"的
    时候，把数据库读回来的 extras 灌回各题目对应的 session_state key，图片/AI 分类
    结果/文字覆盖才会在页面上重新出现，不然加载历史记录看起来就跟这些东西从来没存过
    一样。定义放在这里（比调用它的"原始数据"那个 expander 靠前）是必须的——Python
    脚本从上往下顺序执行，函数得先经过 def 语句"登记"过，才能在后面的代码里被调用；
    这个函数是在 expander 里直接被调用的（不是嵌在另一个函数体里延迟执行），如果定义
    写在文件更后面，跑到调用这一行就会是 NameError，还没定义就调用。

    只应该在加载历史记录那一次性的分支里调用一次——不能每次 rerun 都调，不然用户
    在页面上刚做的修改（比如又加了一张图、改了个分类结果）会被这份旧快照覆盖回去。
    """

    for q_no, ai_result_map in extras.get("ai_results", {}).items():
        for filter_key, result in ai_result_map.items():
            key = f"ai_result_{q_no}" if not filter_key else f"ai_result_{q_no}__{filter_key}"
            st.session_state[key] = result

    for q_no, imgs in extras.get("images", {}).items():
        restored = []
        for img in imgs:
            content = base64.b64decode(img["bytes_b64"])
            restored.append(
                {
                    "bytes": content,
                    "name": img["name"],
                    "caption": img.get("caption", ""),
                    "bytes_hash": hashlib.md5(content).hexdigest(),
                }
            )
        st.session_state[f"images_{q_no}"] = restored

    for q_no, per_row in extras.get("images_per_row", {}).items():
        st.session_state[f"images_per_row_{q_no}"] = per_row

    for q_no, include_chart in extras.get("include_chart_in_grid", {}).items():
        st.session_state[f"include_chart_in_grid_{q_no}"] = include_chart

    for q_no, overrides in extras.get("label_overrides", {}).items():
        st.session_state[f"label_overrides_{q_no}"] = dict(overrides)


# ---------------------------------------------------------------------------
# 1. 上传
# ---------------------------------------------------------------------------

# 上传/映射/生成分析这一整块——生成分析之前需要一直展开着方便配置，生成分析之后
# 默认收起来（不是删掉，折叠状态下这里面的控件照样能用、照样能改，只是视觉上先让位
# 给下面的分析结果，不用的话不用一直占着屏幕最上面的空间）。
with st.expander("原始数据", expanded=not st.session_state.get("generated", False)):
    # 从项目工作区点"打开"进来的历史分析——project_view.py 那边已经把
    # analysis_mode/current_document_id 写进 session_state 再跳转过来，这里接手。
    # 实际读库/灌回 session_state 只做一次（用 loaded_document_snapshot 这个 key 当
    # 一次性开关），不然每次 rerun 都重新读一遍，会把用户在页面上刚做的修改
    # （结论、图片、AI 分类结果……）覆盖回加载那一刻的旧快照。
    if st.session_state.get("analysis_mode") == "load_existing":
        requested_document_id = st.session_state.get("current_document_id")
        already_loaded_id = st.session_state.get("loaded_document_snapshot", {}).get("document_id")
        if requested_document_id != already_loaded_id:
            # 同一个浏览器 session 里，先打开过一份历史记录 A，回项目工作区又点开了
            # 另一份 B——不能只判断"loaded_document_snapshot 存不存在"，那样 B 会被
            # 当成"已经加载过"直接跳过，页面上还显示着 A 的内容。这里改成比对具体的
            # document_id，不一样就重新走一遍加载。
            #
            # 清理旧状态不能只列举"我记得的那几个 key"——这个页面几乎所有交互控件的
            # key 都是按题号(q_no)拼的（比如 chart_download_Q1、label_override_Q1_xxx、
            # conclusion_input_0、document_title_input……），而 q_no 是"Q1""Q2""S1"这种
            # 按位置生成的通用编号，不同文档之间必然会撞号；Streamlit 的规则又是"widget
            # 一旦带 key、往后 value= 参数只在首次创建时生效"——只清掉数据层面的 key
            # （conclusions/document_title 这些"值"）没用，widget 自己那份 key（
            # conclusion_input_0/document_title_input 这些）不清的话，界面上显示的还是
            # 上一份文档在那个 widget 里留下的旧内容。与其列一份清单、以后加新 widget
            # 忘了往这份清单里加又出现同样的串号问题，不如换个方向：除了几个真正跨文档
            # 都要保留的基础设施 key，其余全部清空，重新从数据库加载的内容会重新把
            # 该有的 key 填回去。AI 供应商/API key 这些是存在数据库 settings 表里的
            # （见 _get_provider_or_none），不在 session_state 里，清空不会影响到。
            keep_keys = {"db_conn", "analysis_mode", "current_document_id", "current_project_id"}
            for key in list(st.session_state.keys()):
                if key not in keep_keys:
                    del st.session_state[key]

            document_id = requested_document_id
            if document_id is None:
                st.error("没有找到要加载的历史分析，请回到项目工作区重新选择。")
                st.stop()
            try:
                loaded = persistence.load_analysis(_get_db_conn(), document_id)
            except Exception as exc:  # noqa: BLE001
                st.error(f"加载历史分析失败：{exc}")
                st.stop()

            # 多选题现在存库时保留的是每个原始拆分列各自的真假值（见
            # persistence._write_questions_and_responses），加载回来的 `u["columns"]`
            # 就是原始拆分列名本身——这里给多选题的每一个原始列各生成一行映射表，
            # "分组键"（q_no）默认都填成这道题的 display_no（保持读回来的默认分组
            # 跟原来一致），但可以在下面的映射表里手动改，改了会真的重新分组
            # （build_units 就是按这张表的"分组键"分组的）。老数据（这次改动之前存的，
            # 原始拆分列信息已经不在了）会退化成 `u["columns"] == [u["display_no"]]`，
            # 这里自然只生成一行，效果跟以前一样——不需要额外判断新旧格式。
            st.session_state["mapping"] = pd.DataFrame(
                [
                    {
                        "column": col,
                        "q_type": u["kind"],
                        "section": u["section"],
                        "q_no": u["display_no"],
                        "title": u["title"],
                    }
                    for u in loaded["units"]
                    for col in u["columns"]
                ]
            )
            st.session_state["translation_cache"] = loaded["translation_cache"]
            st.session_state["test_method"] = loaded["test_method"]
            st.session_state["conclusions"] = loaded["conclusions"]
            st.session_state["document_title"] = loaded["title"]
            st.session_state["saved_document_id"] = document_id
            st.session_state["current_project_id"] = loaded["project_id"]
            for col, fail_values in loaded["screen_fail_values"].items():
                st.session_state.setdefault(f"screenfail_{col}", fail_values)
            _restore_extras(loaded["extras"])

            st.session_state["loaded_document_snapshot"] = {
                "df_all": loaded["df_all"],
                "document_id": document_id,
            }
            st.session_state["generated"] = True

        df_all = st.session_state["loaded_document_snapshot"]["df_all"]
        id_col = "（不去重）"  # 历史记录里的数据已经是去重后的最终结果，不用再选一次
        st.info(f"已从历史记录加载：{st.session_state.get('document_title', '')}（{len(df_all)} 人）")
    else:
        uploaded = st.file_uploader("上传问卷原始数据（CSV / xlsx）", type=["csv", "xlsx"])

        if uploaded is None:
            st.info("上传一个文件开始。没有现成数据的话，随便导出一份 Qualtrics/问卷星/Google Forms 的 CSV 都行。")
            st.stop()

        upload_dir = PROJECT_ROOT / "data" / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        save_path = upload_dir / uploaded.name
        save_path.write_bytes(uploaded.getvalue())

        try:
            raw_df = ingest.load_file(str(save_path))
        except Exception as exc:  # noqa: BLE001 - 展示给用户看，不静默
            st.error(f"解析失败：{exc}")
            st.stop()

        # 有些问卷平台（见数等）导出的 CSV 有两行表头：第一行是完整题目文本（已经被当列名用了），
        # 第二行是内部字段代码（"作答ID""Q1""Q5_1"这种）——不剔除的话会被当成第一个人的真实答案，
        # 表现出来就是某道题的分布里冒出一个奇怪的、n=1 的选项，值正好是字段代码或者一段 <img> 标签。
        raw_df, dropped_metadata_row = clean.drop_leading_metadata_row(raw_df)
        if dropped_metadata_row:
            st.info("检测到并自动剔除了第一行——它看起来是问卷平台的字段代码行，不是真实作答（比如「作答ID」「Q1」这种），不算进统计。")

        st.success(f"读取成功：{len(raw_df)} 行 × {len(raw_df.columns)} 列")
        with st.expander("预览原始数据（前 5 行）", expanded=False):
            st.dataframe(raw_df.head())

        # ---------------------------------------------------------------------------
        # 2. 去重
        # ---------------------------------------------------------------------------

        id_col = st.selectbox(
            "哪一列是受访者 ID？（用于去重，选'不去重'跳过）",
            ["（不去重）"] + list(raw_df.columns),
        )
        df_all = raw_df
        if id_col != "（不去重）":
            before = len(df_all)
            df_all = clean.dedupe(df_all, id_col)
            dropped = before - len(df_all)
            if dropped:
                st.warning(f"去重剔除了 {dropped} 行重复 {id_col}。")

    # ---------------------------------------------------------------------------
    # 3. 数据映射：题型 + 分类（筛选/正式/基础信息）+ 分组键
    # ---------------------------------------------------------------------------

    st.subheader("数据映射", anchor="mapping-table")
    st.caption(
        "题型决定怎么统计和画图；「分类」决定这题算 3.筛选、4.正式问卷还是 5.基础信息——"
        "显示的题号（S1/Q1/C1…）由分类自动生成，不用手填。「分组键」只在多选题里有用："
        "同一分类下分组键相同的几列会被合并成一道多选题。"
    )
    st.caption(
        "点了「生成分析」之后这张表还是可以改的，不用重新上传文件——比如自动识别的多选题"
        "分组不对、某道题类型判断错了，直接在下面这张表里改对应的行，改完页面会立刻按新的"
        "设置重新生成整份报告。侧边栏导航最上面「调整题型／分组」可以随时跳回这里。"
    )

    if "mapping" not in st.session_state or list(st.session_state["mapping"]["column"]) != list(df_all.columns):
        # 自动识别多选题拆分列（不管是见数"题干-选项"还是 Tally"题干 (选项)"这两种命名规律，
        # 只要取值以布尔值为主就认），同一组的列默认打成 multi + 同一个分组键；Tally 那种额外
        # 带的"选项逗号拼接"汇总列默认忽略，不然会被当成一道假开放题重复分析。
        multi_groups, multi_summary_columns = clean.detect_multi_select_groups(df_all)
        column_to_group: dict[str, tuple[str, str]] = {}  # column -> (分组键, 题干)
        for group_index, (prefix, option_columns) in enumerate(multi_groups.items(), start=1):
            group_key = f"auto_multi_{group_index}"
            for col in option_columns:
                column_to_group[col] = (group_key, prefix)

        default_rows = []
        for i, col in enumerate(df_all.columns):
            if col in multi_summary_columns:
                default_rows.append(
                    {"column": col, "q_type": "忽略", "section": "正式", "q_no": f"g{i + 1}", "title": col}
                )
                continue
            if col in column_to_group:
                group_key, prefix = column_to_group[col]
                default_rows.append(
                    {"column": col, "q_type": "multi", "section": "正式", "q_no": group_key, "title": prefix}
                )
                continue
            if guess_is_platform_column(col):
                # 平台自动收录的字段（ID、提交时间等）——不是问卷题目，默认归到"平台信息"，
                # 不进"正式问卷"。题型给个不会触发图表渲染的默认值，反正 CHART_SECTIONS 循环
                # 根本不会跑到"平台信息"这段。
                default_rows.append(
                    {"column": col, "q_type": "open", "section": "平台信息", "q_no": f"g{i + 1}", "title": col}
                )
                continue
            if pd.api.types.is_numeric_dtype(df_all[col]) and df_all[col].nunique() > 15:
                guess = "numeric"
            elif df_all[col].nunique(dropna=True) <= 12:
                guess = "single"
            else:
                guess = "open"
            default_rows.append(
                {
                    "column": col,
                    "q_type": guess,
                    "section": "正式",
                    "q_no": f"g{i + 1}",
                    "title": col,
                }
            )
        st.session_state["mapping"] = pd.DataFrame(default_rows)
        st.session_state["generated"] = False
        if multi_groups:
            st.info(
                f"自动识别出 {len(multi_groups)} 道多选题（按选项列名规律+布尔取值判断），"
                "已经在下面的映射表里合并成 multi 类型，不用手动一个个改分组键了；"
                "不对的话可以在表格里直接调整。"
            )

    mapping = st.data_editor(
        st.session_state["mapping"],
        column_config={
            "column": st.column_config.TextColumn("原始列名", disabled=True),
            "q_type": st.column_config.SelectboxColumn(
                "题型", options=["single", "multi", "open", "numeric", "忽略"]
            ),
            "section": st.column_config.SelectboxColumn("分类", options=ALL_SECTIONS),
            "q_no": st.column_config.TextColumn("分组键（多选题共享同一个值才会合并）"),
            "title": st.column_config.TextColumn("题目文本（英文原题，或已经是中文就直接填中文）"),
        },
        hide_index=True,
        use_container_width=True,
        key="mapping_editor",
    )
    st.session_state["mapping"] = mapping

    # ---------------------------------------------------------------------------
    # 4. 筛选设置：哪些"筛选"分类的单选题、选中哪些值算「未通过」
    # ---------------------------------------------------------------------------

    screen_rows = mapping[(mapping["section"] == "筛选") & (mapping["q_type"] == "single")]
    screen_fail_values: dict[str, list[str]] = {}

    if not screen_rows.empty:
        st.subheader("筛选设置")
        st.caption("选中的值 = 未通过筛选（screen out）；不选就当这道题不参与过滤，只在「3. 筛选问题」里展示分布。")
        for _, row in screen_rows.iterrows():
            col = row["column"]
            unique_values = sorted(df_all[col].dropna().unique().tolist(), key=str)
            screen_fail_values[col] = st.multiselect(
                f"「{row['title']}」——哪些取值算未通过？", unique_values, key=f"screenfail_{col}"
            )

    other_screen_rows = mapping[(mapping["section"] == "筛选") & (mapping["q_type"] != "single")]
    if not other_screen_rows.empty:
        st.info(
            "以下筛选题不是单选题，本 demo 暂不支持据此过滤样本，只会在「3. 筛选问题」里展示，不影响「4. 正式问卷」「5. 基础信息探测」的有效样本："
            + "、".join(other_screen_rows["title"].tolist())
        )

    if st.button("生成分析", type="primary"):
        st.session_state["generated"] = True

    # 用 session_state 存"已经生成过"这件事，而不是直接判断按钮这次刷新的返回值——
    # st.button 只在真正被点击的那一次刷新返回 True，下面任何一个 widget（AI 分类的
    # radio/按钮、翻译按钮、expander）触发的刷新里它都会变回 False。如果直接
    # `if not st.button(...): st.stop()`，点完"生成分析"以后只要再碰一下下面任何交互
    # 控件，整个结果区就会被 st.stop() 清空——这是这版之前就有的一个真实 bug，这次顺手修了。
    if not st.session_state.get("generated"):
        st.stop()

# 侧边栏模块导航——点标题跳转到对应区域（靠 st.header 的 anchor 参数配合 #锚点链接实现，
# 不是自己拼 HTML）。只在真正生成了分析之后才显示，没数据之前跳转目标还不存在。
# 原来这里还有个"隐藏模块导航"勾选框——多余了，侧栏本身顶部就有 Streamlit 原生的
# 收起箭头，两个功能重复，删掉自己这个，只留原生那个。"### 模块导航"这行标题文字
# 也去掉了——链接列表本身就是导航，不需要额外一行字说明"这是导航"。
for label, anchor in SIDEBAR_NAV:
    st.sidebar.markdown(f"[{label}](#{anchor})")

# 有效样本：任一筛选题命中"未通过"取值，就整体剔除
valid_mask = pd.Series(True, index=df_all.index)
total_screened_out = 0
for col, fail_values in screen_fail_values.items():
    if fail_values:
        hit = df_all[col].isin(fail_values)
        total_screened_out += int(hit.sum())
        valid_mask &= ~hit
df_valid = df_all[valid_mask]

if screen_fail_values and any(screen_fail_values.values()):
    st.info(f"筛选后：全量 {len(df_all)} 人 → 有效样本 {len(df_valid)} 人（剔除 {len(df_all) - len(df_valid)} 人）。")

has_screening = bool(screen_fail_values) and any(screen_fail_values.values())

# ---------------------------------------------------------------------------
# 5. ① 结论 + ② 测试方法——渲染顺序在③④⑤之前，对应整体页面框架的 1、2 两部分。
#    这两部分都是手填/自动统计，不需要 engine 的统计引擎，先用 session_state 存，
#    还没接 engine/db.py 的 conclusions/test_method 表——那张表已经在 Milestone 3a
#    建好了，等这个 demo 真的要"保存项目"的时候再接，现在每次刷新还是会清空。
# ---------------------------------------------------------------------------

with st.container(key="section_paper_1"):
    st.header("1. 结论", anchor="sec1")
    st.caption("一句话最重要的结论，默认 1 条，带数字；可以再加。")

    if "conclusions" not in st.session_state:
        st.session_state["conclusions"] = [""]

    for i in range(len(st.session_state["conclusions"])):
        col_num, col_text, col_del = st.columns([0.6, 9.4, 1])
        col_num.markdown(f"**{i + 1}.**")
        st.session_state["conclusions"][i] = col_text.text_input(
            f"结论 {i + 1}",
            value=st.session_state["conclusions"][i],
            key=f"conclusion_input_{i}",
            placeholder="例：179人中，选择最多的是「新西兰羊毛精工打造」，86人（48.0%）。",
            label_visibility="collapsed",
        )
        if col_del.button("删除", key=f"conclusion_del_{i}") and len(st.session_state["conclusions"]) > 1:
            st.session_state["conclusions"].pop(i)
            st.rerun()

    if st.button("+ 新增一条结论", key="conclusion_add"):
        st.session_state["conclusions"].append("")
        st.rerun()

with st.container(key="section_paper_2"):
    st.header("2. 测试方法", anchor="sec2")

    # setdefault 只在第一次创建时生效——(a) 的初始值用列名做一次启发式猜测（命中 Prolific/
    # Credamo/PickFu/Tally 等平台特征词就预填），猜完之后完全交给你编辑，不会每次刷新都被
    # 悄悄改回去（Streamlit 的规律：widget 一旦带了 key，往后 value= 参数只在"首次创建"时
    # 起作用，所以猜测必须放在 setdefault 的默认值里，不能指望后面再动态覆盖）。
    tm = st.session_state.setdefault(
        "test_method",
        {
            "platform_source": guess_platform_source(list(df_all.columns)),
            "is_branched": False,
            "branch_count": 1,
            "skip_logic_note": "",
        },
    )
    tm["platform_source"] = st.text_input(
        "(a) 测试平台与样本来源（根据列名猜的，不准就自己改）",
        value=tm["platform_source"],
        key="tm_platform_source",
        placeholder="如 Prolific + Tally / PickFu / Credamo 见数",
    )
    tm["is_branched"] = st.checkbox("(b) 是否有分流设计", value=tm["is_branched"], key="tm_is_branched")
    if tm["is_branched"]:
        tm["branch_count"] = st.number_input(
            "分几份问卷", min_value=1, step=1, value=tm["branch_count"] or 1, key="tm_branch_count"
        )
        st.caption(
            "这版 demo 一次只处理一份上传文件，没法从单个 CSV 自动判断是不是分流问卷，"
            "这项只能你自己勾；分几份问卷各自的样本量需要分开上传后自己核对——"
            "跨文件合并统计留给正式版（`engine/db.py` 已经有 `documents.branch_label` 字段接这个）。"
        )
    else:
        tm["branch_count"] = None

    sample_line = f"**(c) 样本量**：全量 {len(df_all)} 人"
    if has_screening:
        sample_line += f"，有效样本 {len(df_valid)} 人"
    sample_line += "（自动统计，不用手填）"
    st.markdown(sample_line)

    # (d) 筛选逻辑：不是一个可编辑输入框——直接从"筛选设置"步骤里你已经勾选的内容拼出来，
    # 全自动、不能手改（改的地方应该回"筛选设置"改，不是这里，两处不一致会更乱）。
    screen_rule_parts = []
    for col, fail_values in screen_fail_values.items():
        if fail_values:
            col_title = mapping.loc[mapping["column"] == col, "title"].iloc[0]
            screen_rule_parts.append(f"「{col_title}」选中 {fail_values} 视为未通过")
    tm["screen_out_rule"] = "；".join(screen_rule_parts) if screen_rule_parts else "无"
    st.markdown(f"**(d) 筛选逻辑**：{tm['screen_out_rule']}（根据上面「筛选设置」自动生成，不用手填）")

    # (e) 跳转逻辑没法从导出的平铺 CSV 里可靠推断（跳转是问卷设计时的分支规则，答题数据本身
    # 看不出"是因为跳转没看到题"还是"看到了但没填"），这项保留手填。
    tm["skip_logic_note"] = st.text_area(
        "(e) 跳转逻辑（没法从数据自动判断，需要你回忆问卷设计手填）",
        value=tm["skip_logic_note"],
        key="tm_skip_logic_note",
        placeholder="没有就填「无」",
    )

# ---------------------------------------------------------------------------
# 6. 逐段渲染：③筛选问题（看全量）→ ④正式问卷（看有效样本）→ ⑤基础信息探测（看有效样本）
# ---------------------------------------------------------------------------

units = build_units(mapping)

for section in SECTION_ORDER:
    sec_units = assign_display_numbers(units, section)
    if not sec_units:
        continue

    with st.container(key=f"section_paper_{section}"):
        section_df = df_all if section == "筛选" else df_valid
        st.header(SECTION_HEADER[section], anchor=SECTION_ANCHOR[section])
        if section == "筛选":
            st.caption("筛选题看的是筛选前的全量样本，不是有效样本——这道题本来就是拿来筛人的。")

        for unit_index, unit in enumerate(sec_units):
            render_unit(unit, section_df, n_for_footer=len(section_df), sec_units=sec_units, unit_index=unit_index)

# ---------------------------------------------------------------------------
# 7. ⑥ 完整数据表格 + ⑦ 受访者个人视角
#
# 用 streamlit-aggrid（新依赖，设计文档 v0.5 第 4 节评估过）——st.dataframe 原生做不出
# "三段用三种主题色区分表头"这个要求，ag-Grid 的列分组表头原生支持这个。
# 只展示有效样本（跟 Excel 版 skill 的口径一致：被筛掉的人不进这页），⑩ 平台信息列
# 这版demo 还没做（还没有 platform_auto 这个分类选项），先不出现在表里。
# ---------------------------------------------------------------------------

from st_aggrid import AgGrid, GridOptionsBuilder  # noqa: E402  （延后 import，避免影响上面纯计算逻辑的可测性）

with st.container(key="section_paper_6"):
    st.header("6. 完整数据表格", anchor="sec6")
    st.caption("只展示通过筛选的有效样本；点一行，下面「7. 受访者个人视角」会展开这个人的完整作答。")

    SECTION_HEADER_CLASS = {
        "筛选": "hdr-screen",
        "正式": "hdr-official",
        "基础信息": "hdr-background",
        "平台信息": "hdr-platform",
    }
    SECTION_BG_COLOR = {
        "筛选": "#2E579733",
        "正式": "#2E7D5233",
        "基础信息": "#C2570C33",
        "平台信息": "#45566433",
    }

    raw_table_units = {section: assign_display_numbers(units, section) for section in ALL_SECTIONS}

    # ---------------------------------------------------------------------------
    # 保存——分两条线，互不覆盖：
    #   - 手动保存：点下面「手动保存」按钮，整份覆盖写进 questions/responses/conclusions
    #     这几张"正式"的表——这是"打开历史分析""导出 Word"真正会读到的那份数据。
    #   - 自动保存：不用你点任何东西，只要映射表/筛选设置/测试方法/结论文本这些内容跟上次
    #     保存（不管是手动保存还是上一次自动保存）不一样、且离上次自动保存已经超过
    #     AUTOSAVE_INTERVAL_SECONDS，就把当前状态整份写进 autosaves 表——这张表跟"正式"
    #     的表是分开的两套数据，每份问卷（document_id）只占一行，新草稿直接顶掉旧草稿，
    #     结构上就不可能覆盖你手动保存的内容。
    #
    # 多选题选项级别的翻译存取（persistence.py 那边）已经修好：save_analysis/update_analysis
    # 现在存的是 clean.option_labels_for_group 算出来的短选项名（比如"热熔胶"），
    # translation_cache 查询也按同一份短标签，两边终于对得上了——这是之前长期存在的一个
    # 已知缺口，这次和"打开历史分析"前置工作一起修的。
    #
    # AI 分类结果 / 图片 / 拖拽排版这三项也纳入保存范围了（写进 document_extras 表，见
    # persistence.save_analysis/update_analysis 的 extras 参数）——具体怎么归拢、怎么在
    # 不每次 rerun 都重新编码图片字节的前提下判断"变没变"，见下面 _extras_payload /
    # _extras_fingerprint 这两个函数的说明。
    AUTOSAVE_INTERVAL_SECONDS = 20


    def _collect_ai_results_for(q_no: str) -> dict[str, dict]:
        """收集一道开放题名下所有筛选组合的 AI 分类结果——"" 这个 key 代表没筛选（全部人），
        其余 key 是筛选条件字符串（比如"Q2｜冬天用来制热...＝空气能空调"）。每种筛选组合的
        结果分开存、互不覆盖，见 render_open_ai_classify_trigger 里 ai_key 的拼法
        （f"ai_result_{{q_no}}" 或者 f"ai_result_{{q_no}}__{{filter_key}}"）。
        """

        exact_key = f"ai_result_{q_no}"
        prefix = f"ai_result_{q_no}__"
        results: dict[str, dict] = {}
        if exact_key in st.session_state:
            results[""] = st.session_state[exact_key]
        for key, value in st.session_state.items():
            if key.startswith(prefix):
                results[key[len(prefix):]] = value
        return results


    def _extras_payload() -> dict:
        """AI 分类结果 / 图片（含字节，顺序就是排版顺序）/ 每题"每行放几张"——按题号归拢成
        一份可以整个存进数据库、也可以整个读回来的结构。只在真的要写库的时候调用（手动保存 /
        自动保存触发那一刻），不在每次 rerun 都调用——图片字节转 base64 有实际的 CPU 成本，
        不能每次 rerun 都做一遍（chart PNG 也是同样道理缓存的）。
        """

        ai_results: dict = {}
        images: dict = {}
        images_per_row: dict = {}
        include_chart_in_grid: dict = {}
        label_overrides: dict = {}
        for u in units:
            q_no = u["display_no"]
            ai_result_map = _collect_ai_results_for(q_no)
            if ai_result_map:
                ai_results[q_no] = ai_result_map
            imgs = st.session_state.get(f"images_{q_no}")
            if imgs:
                images[q_no] = [
                    {
                        "name": img["name"],
                        "caption": img["caption"],
                        "bytes_b64": base64.b64encode(img["bytes"]).decode("ascii"),
                    }
                    for img in imgs
                ]
            per_row = st.session_state.get(f"images_per_row_{q_no}")
            if per_row is not None:
                images_per_row[q_no] = per_row
            include_chart = st.session_state.get(f"include_chart_in_grid_{q_no}")
            if include_chart is not None:
                include_chart_in_grid[q_no] = include_chart
            overrides = st.session_state.get(f"label_overrides_{q_no}")
            if overrides:
                # 空字符串的覆盖值等于"没改"，不用存——存了也只是占地方，读回来也是
                # 一样的效果（渲染时空字符串会退回原文）。
                non_empty = {k: v for k, v in overrides.items() if v}
                if non_empty:
                    label_overrides[q_no] = non_empty
        return {
            "ai_results": ai_results,
            "images": images,
            "images_per_row": images_per_row,
            "include_chart_in_grid": include_chart_in_grid,
            "label_overrides": label_overrides,
        }


    def _extras_fingerprint() -> tuple:
        """判断"AI 分类结果/图片/排版有没有变"的便宜版本——图片只看哈希不看字节，
        每次 rerun 都要跑，所以不能带真的图片字节编码进来（哈希是插入图片那一刻算好存在
        session_state 里的，见 render_image_attachments，这里不重新算）。图片列表本身是
        按 tuple 顺序比较的，所以上下移动调整顺序也会被这个指纹感知到，不用额外处理。"""

        ai_entries = []
        for u in units:
            result_map = _collect_ai_results_for(u["display_no"])
            if result_map:
                ai_entries.append((u["display_no"], json.dumps(result_map, sort_keys=True, ensure_ascii=False)))
        ai_fp = tuple(sorted(ai_entries))
        image_fp = tuple(
            sorted(
                (
                    u["display_no"],
                    tuple(
                        (img["name"], img["caption"], img.get("bytes_hash"))
                        for img in st.session_state[f"images_{u['display_no']}"]
                    ),
                )
                for u in units
                if st.session_state.get(f"images_{u['display_no']}")
            )
        )
        per_row_fp = tuple(
            sorted(
                (u["display_no"], st.session_state[f"images_per_row_{u['display_no']}"])
                for u in units
                if st.session_state.get(f"images_per_row_{u['display_no']}") is not None
            )
        )
        include_chart_fp = tuple(
            sorted(
                (u["display_no"], st.session_state[f"include_chart_in_grid_{u['display_no']}"])
                for u in units
                if st.session_state.get(f"include_chart_in_grid_{u['display_no']}") is not None
            )
        )
        label_override_fp = tuple(
            sorted(
                (u["display_no"], json.dumps(st.session_state[f"label_overrides_{u['display_no']}"], sort_keys=True, ensure_ascii=False))
                for u in units
                if st.session_state.get(f"label_overrides_{u['display_no']}")
            )
        )
        return (ai_fp, image_fp, per_row_fp, include_chart_fp, label_override_fp)


    def _save_snapshot() -> dict:
        """归拢"决定要不要重新保存"要看的那几块状态——跟 persistence.save_analysis /
        update_analysis 实际落库的字段对应。extras_fingerprint 那部分只是"变没变"的便宜
        指纹，不是真正落库的内容——真正写库时用的是 _extras_payload()（在需要保存的那一刻
        单独调用一次，见下面 if/else 分支）。"""

        return {
            "mapping": st.session_state["mapping"].to_dict("records"),
            "id_col": id_col,
            "screen_fail_values": screen_fail_values,
            "test_method": tm,
            "conclusions": st.session_state.get("conclusions", []),
            "extras_fingerprint": _extras_fingerprint(),
        }


    if "document_title" not in st.session_state:
        st.session_state["document_title"] = uploaded.name

    with top_title_col:
        st.session_state["document_title"] = st.text_input(
            "问卷标题",
            value=st.session_state["document_title"],
            key="document_title_input",
            label_visibility="collapsed",
        )
        # 元信息条——客户翻开报告第一眼要确认的东西（样本量/来源/最近更新），之前完全没地方
        # 展示。放在标题正下方，跟标题共用同一个视觉分组；保存时间用真实墙钟时间，不是
        # _last_autosave_at 那个 monotonic 值（那个只用来算"距上次保存过了多久"，不能拿来显示）。
        saved_at = st.session_state.get("_last_saved_wallclock")
        saved_label = f"更新于 {saved_at:%H:%M:%S}" if saved_at else "尚未保存"
        st.caption(f"N = {len(df_all)}　·　{tm.get('platform_source') or '未识别来源'}　·　{saved_label}")


    if "saved_document_id" not in st.session_state:
        project_id = st.session_state.get("current_project_id")
        if project_id is None:
            # 没有从首页/项目工作区进来（比如直接跑 `streamlit run app.py`）——自动开一个
            # 项目，不让保存这件事因为没有项目而直接跳过。origin="auto" 标记成"系统代劳
            # 建的"，首页可以按这个筛掉/挑出来，不会跟手动新建的项目混在一起。
            # 名字尽量别叫"未命名项目"——配了 AI 就让它从题目里总结一个有区分度的名字，
            # 没配就退回纯 Python 挑一道代表性问题当名字，都比一律叫"未命名项目"更好认。
            naming_provider = _get_provider_or_none()
            if naming_provider is not None:
                auto_name = project_naming.summarize_project_name(naming_provider, units)
            else:
                auto_name = project_naming.guess_project_name_from_questions(units)
            project_id = db.create_project(_get_db_conn(), auto_name, "en", "zh-CN", origin="auto")
            st.session_state["current_project_id"] = project_id
        try:
            document_id = persistence.save_analysis(
                _get_db_conn(),
                project_id,
                units,
                df_all,
                screen_fail_values,
                st.session_state.get("translation_cache", {}),
                tm,
                st.session_state.get("conclusions", []),
                filename=uploaded.name,
                title=st.session_state["document_title"],
                extras=_extras_payload(),
            )
            st.session_state["saved_document_id"] = document_id
            st.session_state["_last_saved_snapshot"] = _save_snapshot()
            st.session_state["_last_autosave_at"] = time.monotonic()
            st.session_state["_last_saved_wallclock"] = datetime.now()
            st.toast(f"已保存到数据库（document_id={document_id}）")
        except Exception as exc:  # noqa: BLE001 —— 保存失败不能挡住页面正常显示分析结果
            st.warning(f"保存失败，不影响当前页面查看：{exc}")
    else:
        document_id = st.session_state["saved_document_id"]
        project_id = st.session_state.get("current_project_id")

        with top_save_col:
            manual_save_clicked = st.button("保存", key="manual_save_button", type="primary")

        if manual_save_clicked:
            try:
                persistence.update_analysis(
                    _get_db_conn(),
                    document_id,
                    project_id,
                    units,
                    df_all,
                    screen_fail_values,
                    st.session_state.get("translation_cache", {}),
                    tm,
                    st.session_state.get("conclusions", []),
                    title=st.session_state["document_title"],
                    extras=_extras_payload(),
                )
                st.session_state["_last_saved_snapshot"] = _save_snapshot()
                st.session_state["_last_autosave_at"] = time.monotonic()
                st.session_state["_last_saved_wallclock"] = datetime.now()
                st.toast(f"已手动保存（{datetime.now():%H:%M:%S}），并清掉了这份问卷的自动保存草稿。")
            except Exception as exc:  # noqa: BLE001
                st.toast(f"手动保存失败：{exc}")
        else:
            current_snapshot = _save_snapshot()
            changed = current_snapshot != st.session_state.get("_last_saved_snapshot")
            elapsed = time.monotonic() - st.session_state.get("_last_autosave_at", 0.0)
            if changed and elapsed >= AUTOSAVE_INTERVAL_SECONDS:
                try:
                    # 草稿要存"能整份恢复"的完整内容（含图片字节），不是拿 current_snapshot
                    # 里那份只带指纹的版本直接存——那份是给"变没变"判断用的，不是给恢复用的。
                    draft_payload = {**current_snapshot, **_extras_payload()}
                    draft_payload.pop("extras_fingerprint", None)
                    db.write_autosave(_get_db_conn(), document_id, draft_payload)
                    st.session_state["_last_saved_snapshot"] = current_snapshot
                    st.session_state["_last_autosave_at"] = time.monotonic()
                    st.session_state["_last_saved_wallclock"] = datetime.now()
                    st.toast(f"已自动保存草稿（{datetime.now():%H:%M:%S}）——不会覆盖手动保存，点「保存」才会写入正式数据。")
                except Exception as exc:  # noqa: BLE001
                    st.toast(f"自动保存草稿失败：{exc}")

    show_platform = False
    if raw_table_units["平台信息"]:
        show_platform = st.checkbox("显示平台信息列（10. 受访者信息，默认隐藏）", value=False, key="show_platform_cols")

    if id_col != "（不去重）":
        id_series = df_valid[id_col].astype(str)
    else:
        id_series = pd.Series(df_valid.index.astype(str), index=df_valid.index)

    table_df = pd.DataFrame({"受访者ID": id_series.values}, index=df_valid.index)
    column_groups: list[dict] = []

    table_sections = ALL_SECTIONS if show_platform else CHART_SECTIONS
    for section in table_sections:
        sec_units = raw_table_units[section]
        if not sec_units:
            continue
        children = []
        for u in sec_units:
            colname = f"{u['display_no']}｜{u['title']}"
            if u["kind"] == "multi":
                list_series = _multi_select_list_series(df_valid, u["columns"])
                table_df[colname] = list_series.apply(lambda vals: "、".join(vals) if vals else "").values
            else:
                table_df[colname] = df_valid[u["columns"][0]].values
            children.append({"field": colname})
        column_groups.append(
            {"headerName": SECTION_HEADER[section], "headerClass": SECTION_HEADER_CLASS[section], "children": children}
        )

    use_set_filter = st.checkbox(
        "按具体取值筛选（勾选框选答案，需要 ag-Grid 企业版 Set Filter，没有授权会在表格上出现"
        "「For Trial Use Only」水印——内部用可以接受就勾；不勾的话用免费版的文本筛选，"
        "点表头筛选图标、输入关键字也能缩小范围，只是不是勾选框）",
        value=False,
        key="raw_grid_use_set_filter",
    )
    filter_type = "agSetColumnFilter" if use_set_filter else "agTextColumnFilter"

    gb = GridOptionsBuilder.from_dataframe(table_df)
    gb.configure_selection(selection_mode="single")
    gb.configure_default_column(filter=filter_type, floatingFilter=True, sortable=True, resizable=True)
    grid_options = gb.build()
    grid_options["columnDefs"] = [{"field": "受访者ID", "pinned": "left", "filter": filter_type}] + column_groups

    custom_css = {f".{cls}": {"background-color": f"{color} !important"} for cls, color in zip(
        SECTION_HEADER_CLASS.values(), SECTION_BG_COLOR.values()
    )}
    # 真实反馈：这个表格外面也有一圈边框，跟纸张卡片自己的留白叠在一起显得很重。
    # ag-Grid 是普通 DOM 渲染（不像 st.dataframe 那样画在 canvas 上），边框就是
    # 普通 CSS border 属性，能直接用 custom_css 去掉，不需要额外的技巧。
    custom_css[".ag-root-wrapper"] = {"border": "none !important"}
    custom_css[".ag-header"] = {"border": "none !important"}
    # 真实反馈："表格底色改成白的，和周围一圈看不出区别"——ag-Grid 默认主题的
    # 表格主体背景不是纯白（比纸张卡片的纯白 #FFFFFF 略灰一点点），两块白色
    # 挨在一起有一条不易察觉但存在的接缝。这里把主体背景、单元格背景都强制成
    # 纯白，跟纸张卡片统一成同一个白，不再留这条接缝；表头（受访者ID/板块分组）
    # 保持原来单独设置的底色不受影响，因为下面这几条选择器都没有覆盖到
    # header 相关的类。
    custom_css[".ag-root-wrapper"]["background-color"] = "#FFFFFF !important"
    custom_css[".ag-body-viewport"] = {"background-color": "#FFFFFF !important"}
    custom_css[".ag-center-cols-viewport"] = {"background-color": "#FFFFFF !important"}
    custom_css[".ag-row"] = {"background-color": "#FFFFFF !important"}
    custom_css[".ag-row-odd"] = {"background-color": "#FFFFFF !important"}
    custom_css[".ag-row-even"] = {"background-color": "#FFFFFF !important"}

    grid_response = AgGrid(
        table_df,
        gridOptions=grid_options,
        height=420,
        update_on=["selectionChanged"],
        custom_css=custom_css,
        show_toolbar=True,  # 工具栏里带全屏展开按钮 + 搜索 + 下载 CSV
        enable_enterprise_modules=use_set_filter,
        key="raw_data_grid",
    )

with st.container(key="section_paper_7"):
    st.header("7. 受访者个人视角", anchor="sec7")

    selected = grid_response.selected_rows
    has_selection = selected is not None and (
        (hasattr(selected, "empty") and not selected.empty) or (isinstance(selected, list) and len(selected) > 0)
    )

    if not has_selection:
        st.info("在上面表格里点一行，这里会展开这个人的完整作答。")
    else:
        row = selected.iloc[0] if hasattr(selected, "iloc") else selected[0]
        respondent_id = row["受访者ID"]
        st.markdown(f"**受访者：{respondent_id}**")

        # 用"受访者ID"字符串匹配去 df_valid 里找这一行，不用 ag-Grid 返回的行位置/索引——
        # ag-Grid 把数据序列化给前端再传回来，不一定保得住 pandas 原来的 index，只有实际
        # 列值（受访者ID）是可靠的。
        id_matches = df_valid.index[id_series.astype(str) == str(respondent_id)]
        match_idx = id_matches[0] if len(id_matches) > 0 else None

        # 平台信息顶部一行展示（不管⑥的"显示平台信息列"开关有没有开，⑦都单独查，
        # 因为个人视角本来就该看全，不受表格列显隐影响）。
        platform_units = raw_table_units.get("平台信息", [])
        if platform_units and match_idx is not None:
            parts = []
            for u in platform_units:
                value = df_valid.loc[match_idx, u["columns"][0]]
                parts.append(f"{u['title']}：{value if pd.notna(value) else '—'}")
            st.caption("　".join(parts))

        # ⑦ 剩下的部分顺序是"筛选→基础信息→正式"，跟整体页面顺序（③④⑤=筛选→正式→基础信息）不一样——
        # 这是设计文档 v0.5 第 4 节原话定的，不是笔误。
        for section in ["筛选", "基础信息", "正式"]:
            sec_units = raw_table_units[section]
            if not sec_units:
                continue
            st.subheader(SECTION_HEADER[section])
            for u in sec_units:
                colname = f"{u['display_no']}｜{u['title']}"
                value = row[colname]
                # 之前这里读的是 "title_zh::<题号>" 这个 key，但整个项目里从来没有任何地方
                # 往这个 key 写过东西——一直在读一个永远是空的缓存，个人视角这里从来没有
                # 真的显示过中文翻译，一直在退回原始题干。翻译结果实际存在 session_state
                # 的 "translation_cache" 里、按原文文本查（不是按题号），这跟正文图表、
                # 保存单张图那些地方查缓存用的是同一套逻辑（见 render_chart_save_controls
                # 里 title_zh 的算法），这里改成一样的查法，个人视角才会真的显示中文标题。
                title_zh = st.session_state.get("translation_cache", {}).get(u["title"], u["title"])
                question_line = f"{u['display_no']}. {title_zh}"
                # 问题单独一行，答案另起一行——不要挤在同一行里，长题目+长答案挤一起很难读。
                st.markdown(f"**{question_line}**")
                st.write(value if pd.notna(value) and value != "" else "（未作答/未看到这题）")
                st.write("")

# ---------------------------------------------------------------------------
# 8. ⑧ 交叉分析——手动配置任意数量的对比维度（不是"圈选 vs 其余"二选一）：
#    默认每个选项各自成一个维度（对应"圈选的选项可以单独成为一个维度"），可以合并几个
#    选项成一个自定义命名的维度（比如叫"圈选组"），可以新增/删除维度、无上限，
#    对应设计文档原话"维度支持无限增加，其对比选项支持增删"。
#    "对比到哪道题"这版只支持单选题（crosstab_counts 目前只吃标量答案列）。
# ---------------------------------------------------------------------------

with st.container(key="section_paper_8"):
    st.header("8. 交叉分析", anchor="sec8")
    st.caption("手动配置，不预设。维度数量不限——默认每个选项各自一组，可以合并/改名/增删。「对比到哪道题」这版只支持单选题。")

    from_options = {
        f"{u['display_no']}｜{u['title']}": u
        for section in CHART_SECTIONS
        for u in raw_table_units[section]
        if u["kind"] in ("single", "multi")
    }
    to_options = {
        f"{u['display_no']}｜{u['title']}": u
        for section in CHART_SECTIONS
        for u in raw_table_units[section]
        if u["kind"] == "single"
    }

    if not from_options or not to_options:
        st.info("至少需要一道单选/多选题（用来圈人群）和一道单选题（用来对比），才能配置交叉分析。")
    else:
        from_key = st.selectbox("1. 从哪道题圈人群", list(from_options.keys()), key="crosstab_from")
        from_unit = from_options[from_key]

        from_list_series = None
        if from_unit["kind"] == "single":
            candidate_values = sorted(df_valid[from_unit["columns"][0]].dropna().unique().tolist(), key=str)
        else:
            from_list_series = _multi_select_list_series(df_valid, from_unit["columns"])
            candidate_values = sorted({v for vals in from_list_series for v in vals}, key=str)

        # 维度列表按"从哪道题圈人群"分别记，换一道题就是一套新的默认维度（每个选项各自一组）。
        groups_key = f"crosstab_groups::{from_key}"
        if groups_key not in st.session_state:
            st.session_state[groups_key] = [{"name": v, "values": [v]} for v in candidate_values]

        st.markdown("2. 配置对比维度")
        groups = st.session_state[groups_key]
        # 每一行的输入框标签都隐藏了（label_visibility="collapsed"，是为了不在每一行都
        # 重复"维度名／包含取值"这种大家已经知道意思的文字），但一整列都不显示是什么，
        # 只看默认填的选项文字容易看不出这两列到底是干嘛的——加一行可见的列标题，只显示
        # 一次，不用每行都重复。
        header_name_col, header_values_col, _ = st.columns([3, 6, 1])
        header_name_col.caption("维度名称")
        header_values_col.caption("包含哪些取值")
        delete_index = None
        for gi, group in enumerate(groups):
            name_col, values_col, del_col = st.columns([3, 6, 1])
            group["name"] = name_col.text_input(
                f"维度名 {gi}", value=group["name"], key=f"{groups_key}_name_{gi}", label_visibility="collapsed"
            )
            group["values"] = values_col.multiselect(
                f"包含取值 {gi}",
                candidate_values,
                default=[v for v in group["values"] if v in candidate_values],
                key=f"{groups_key}_values_{gi}",
                label_visibility="collapsed",
            )
            if del_col.button("删除", key=f"{groups_key}_del_{gi}"):
                delete_index = gi
        if delete_index is not None:
            groups.pop(delete_index)
            st.rerun()

        btn_col1, btn_col2, _ = st.columns([1, 1, 4])
        if btn_col1.button("+ 新增维度", key=f"{groups_key}_add"):
            groups.append({"name": f"维度{len(groups) + 1}", "values": []})
            st.rerun()
        if btn_col2.button("按选项重置", key=f"{groups_key}_reset"):
            st.session_state[groups_key] = [{"name": v, "values": [v]} for v in candidate_values]
            st.rerun()

        include_rest = st.checkbox("把没被任何维度覆盖的人另算一个「其余」维度", key=f"{groups_key}_rest")

        to_key = st.selectbox("3. 对比到哪道题", list(to_options.keys()), key="crosstab_to")
        to_unit = to_options[to_key]

        valid_groups = [g for g in groups if g["values"] and g["name"].strip()]

        if valid_groups and st.button("生成交叉分析", key="crosstab_run"):
            source_series = df_valid[from_unit["columns"][0]] if from_unit["kind"] == "single" else from_list_series

            def assign_group(raw_value):
                for g in valid_groups:
                    if from_unit["kind"] == "single":
                        if raw_value in g["values"]:
                            return g["name"]
                    elif set(g["values"]) & set(raw_value):
                        return g["name"]
                return "其余" if include_rest else None

            group_col = source_series.apply(assign_group)
            group_order = [g["name"] for g in valid_groups] + (["其余"] if include_rest else [])

            crosstab_input = pd.DataFrame(
                {"分组": group_col.values, "对比题答案": df_valid[to_unit["columns"][0]].values}
            )
            result_table = stats.crosstab_counts(crosstab_input, "分组", "对比题答案", group_order=group_order)
            crosstab_title = f"{from_key} 按 {len(valid_groups)} 个维度分组，对比 {to_key} 上的分布"
            st.markdown(f"**{crosstab_title}**")
            st.dataframe(result_table)

            # 这张表算完就是个局部变量，下一次脚本重跑（比如切到⑪点"生成 Word 报告"）就
            # 没了——存进 session_state，导出 Word 的时候才有得取。按标题去重：同一组
            # "从哪道题→对比到哪道题"重新点一次生成，是更新这一条，不是越攒越多条重复的。
            st.session_state.setdefault("crosstab_history", {})[crosstab_title] = result_table

# ---------------------------------------------------------------------------
# 9. ⑨ AI 洞察——不自动展示，点按钮才生成；每条洞察引用的数字都要先在 Python 算好的
#    统计里核对过，核对不上的整条丢弃（engine/ai_insight.py 里做的）。
# ---------------------------------------------------------------------------

with st.container(key="section_paper_9"):
    st.header("9. AI 洞察", anchor="sec9")
    st.caption("不自动生成。点下面按钮才会调用 AI；引用了编造数字的洞察会被整条丢弃，不会显示出来。")

    if st.button("生成 AI 洞察", key="run_insight"):
        provider = _get_provider_or_none()
        if provider is None:
            st.warning(provider_error_message())
        else:
            bundle: dict = {}
            for section in ["正式", "基础信息"]:
                for u in raw_table_units[section]:
                    if u["kind"] == "single":
                        bundle[u["display_no"]] = stats.single_choice_stats(df_valid[u["columns"][0]])
                    elif u["kind"] == "numeric":
                        bundle[u["display_no"]] = stats.numeric_stats(df_valid[u["columns"][0]])
                    elif u["kind"] == "multi":
                        list_series = _multi_select_list_series(df_valid, u["columns"])
                        bundle[u["display_no"]] = stats.multi_choice_stats(list_series)
            try:
                with st.spinner("生成中…"):
                    insights = ai_insight.generate_insights(provider, bundle)
            except Exception as exc:  # noqa: BLE001
                st.error(f"AI 调用失败：{exc}")
            else:
                st.session_state["ai_insights"] = insights

    if "ai_insights" in st.session_state:
        if not st.session_state["ai_insights"]:
            st.info("这次没有生成出数字能对上的洞察（可能是模型输出没通过校验），可以重新点一次试试。")
        else:
            for item in st.session_state["ai_insights"]:
                st.markdown(f"- {item['text']}")

# ---------------------------------------------------------------------------
# 10. ⑩ 受访者信息——问卷平台自动收录的数据，如实展示，不聚合不加工。
#    跟⑥里那个"显示平台信息列"复选框是两回事：那个是给完整数据表格用的、默认藏起来
#    避免表格太挤；这里是单独一节，不隐藏（"如实展示"是设计文档原话）。
#    之前这节看起来"消失了"，其实是因为默认的题型/分类猜测从来没把任何列猜成"平台信息"，
#    Submission ID / Respondent ID 这些字段全被当成了普通正式问卷题——已经在数据映射那步的
#    自动猜测里修了（guess_is_platform_column），不是这里的问题。
# ---------------------------------------------------------------------------

with st.container(key="section_paper_10"):
    st.header("10. 受访者信息", anchor="sec10")

    platform_units_all = raw_table_units.get("平台信息", [])
    if not platform_units_all:
        st.info("没有列被标成「平台信息」——如果你的数据里有 ID/提交时间这类平台自动收录的字段，去上面「数据映射」表里把对应行的「分类」改成「平台信息」。")
    else:
        platform_table = pd.DataFrame({"受访者ID": id_series.values}, index=df_valid.index)
        for u in platform_units_all:
            platform_table[f"{u['display_no']}｜{u['title']}"] = df_valid[u["columns"][0]].values
        st.caption("如实展示，不聚合、不加工。")
        st.dataframe(platform_table, use_container_width=True)

# ---------------------------------------------------------------------------
# 11. ⑪ 导出 Word——把①②④⑤（正式问卷+基础信息，筛选题不导出，跟 export_word 模块的
#    既定规则一致）+⑨AI洞察 导出成一份 Word 文档。范围说明：
#    - 开放题的"中文翻译"是导出这一步现场调用 AI 逐条翻译的（按需触发，不是页面浏览时就
#      翻译好的——那是另一件事，是题目标题/选项的翻译，不是受访者原始作答的翻译）。
#    - ⑧交叉分析的结果这版不接入导出——交叉分析是你手动配置、点一次生成一次，没有存成
#      一个"要导出哪些交叉表"的列表，这个留给后面做。
# ---------------------------------------------------------------------------

with st.container(key="section_paper_11"):
    st.header("11. 导出 Word", anchor="sec11")
    st.caption("导出 1/2/4/5 + 9（筛选题、6/7/8/10 不导出——那些是网页交互功能，静态 Word 文档没有对应的东西）。")

    if st.button("生成 Word 报告", type="primary", key="export_word_button"):
        # 开放题逐条翻译走"翻译专用"供应商（默认更便宜），跟题目/选项翻译用的是同一个设置，
        # 不是导出这里另外单独配一份。
        export_provider = _get_provider_or_none(purpose="translation")
        stats_by_unit: dict = {}
        n_by_unit: dict = {}
        title_zh_by_unit: dict = {}  # 单选/多选/数值题标题的中文展示版——跟图表里选项用
        # 同一份 translation_cache，避免"图表是中文、标题还是英文"这种半吊子结果。
        units_by_display_no = {u["display_no"]: u for u in units}

        for unit in units:
            if unit["section"] not in ("正式", "基础信息"):
                continue
            kind = unit["kind"]
            display_no = unit["display_no"]
            n_by_unit[display_no] = len(df_valid)

            if kind == "single":
                raw_result = stats.single_choice_stats(df_valid[unit["columns"][0]])
                label_map, title_zh, _ = _compute_label_map(unit["title"], [r["option"] for r in raw_result])
                stats_by_unit[display_no] = relabel(raw_result, label_map)
                title_zh_by_unit[display_no] = title_zh
            elif kind == "multi":
                list_series = _multi_select_list_series(df_valid, unit["columns"])
                raw_result = stats.multi_choice_stats(list_series)
                label_map, title_zh, _ = _compute_label_map(unit["title"], [r["option"] for r in raw_result])
                stats_by_unit[display_no] = relabel(raw_result, label_map)
                title_zh_by_unit[display_no] = title_zh
            elif kind == "numeric":
                stats_by_unit[display_no] = stats.numeric_stats(df_valid[unit["columns"][0]])
                _, title_zh, _ = _compute_label_map(unit["title"], [])
                title_zh_by_unit[display_no] = title_zh
            elif kind == "open":
                _, title_zh, _ = _compute_label_map(unit["title"], [])
                title_zh_by_unit[display_no] = title_zh
                series = df_valid[unit["columns"][0]].dropna()
                translations: dict[int, str] = {}
                if export_provider is not None and len(series) > 0:
                    items = [{"response_id": i, "text_en": str(text)} for i, text in enumerate(series)]
                    try:
                        with st.spinner(f"翻译 {display_no} 的开放题原文中…"):
                            results = ai_translate.translate_verbatims(export_provider, items, protected_terms=[])
                        translations = {r["response_id"]: r["translation"] for r in results}
                    except Exception as exc:  # noqa: BLE001
                        st.warning(f"{display_no} 的开放题翻译失败（{exc}），Word 里这道题的中文翻译列会留空。")

                # 跟正文页面用的是同一份"关联题目"选择（session_state 里的 context_link_<题号>），
                # 不是导出这里单独再选一遍——页面上点了关联什么，导出的 Word 表格里"对应选择"
                # 这一列就是什么。
                context_units = [
                    units_by_display_no[no]
                    for no in st.session_state.get(f"context_link_{display_no}", [])
                    if no in units_by_display_no
                ]
                context_labels: list[str | None]
                if context_units:
                    context_series_list = [
                        (cu["display_no"], _context_value_series(cu, df_valid).reindex(series.index))
                        for cu in context_units
                    ]
                    context_labels = []
                    for pos in range(len(series)):
                        parts = [
                            f"{label}：{cs.iloc[pos]}"
                            for label, cs in context_series_list
                            if pd.notna(cs.iloc[pos]) and cs.iloc[pos] != ""
                        ]
                        context_labels.append("；".join(parts) or None)
                else:
                    context_labels = [None] * len(series)

                stats_by_unit[display_no] = [
                    {
                        "raw": str(text),
                        "translation": translations.get(i, ""),
                        "corresponding_choice": context_labels[i],
                    }
                    for i, text in enumerate(series)
                ]

        project_name = "问卷分析"
        project_id = st.session_state.get("current_project_id")
        if project_id is not None:
            row = _get_db_conn().execute("SELECT name FROM projects WHERE id = ?", (project_id,)).fetchone()
            if row:
                project_name = row["name"]

        export_dir = PROJECT_ROOT / "data" / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        export_filename = f"{project_name}-Word-{datetime.now():%m%d}.docx"
        export_path = export_dir / export_filename

        # 标题也要用中文展示版——只翻译图表里的选项、标题还留着英文原文，会是个半吊子
        # 结果。用同一份 title_zh_by_unit 替换掉这几种题型的标题，不动原始 units 列表本身
        # （这份列表这次脚本运行里后面用不到了，但还是拷贝一份更安全，不依赖"后面不会用到"
        # 这种脆弱的顺序假设）。
        export_units = [
            {**u, "title": title_zh_by_unit[u["display_no"]]} if u["display_no"] in title_zh_by_unit else u
            for u in units
        ]

        # ⑧交叉分析本来算完就丢了（一个局部变量，下一次脚本重跑就没了）——用户点"生成交叉
        # 分析"的时候顺手存进 session_state，这里才有得导出。按标题去重/覆盖，同一组
        # 「从哪道题→对比到哪道题」重新生成一次就更新那一条，不会越攒越多重复的。
        crosstab_history = st.session_state.get("crosstab_history", {})
        crosstabs = [{"title": k, "table": v} for k, v in crosstab_history.items()] or None

        try:
            export_word.export_analysis_to_docx(
                str(export_path),
                project_name=project_name,
                conclusions=[c for c in st.session_state.get("conclusions", []) if c],
                test_method=tm,
                units=export_units,
                stats_by_unit=stats_by_unit,
                n_by_unit=n_by_unit,
                ai_insights=st.session_state.get("ai_insights"),
                crosstabs=crosstabs,
                color_palette=_active_chart_palette(),
            )
        except Exception as exc:  # noqa: BLE001
            st.error(f"导出失败：{exc}")
        else:
            st.success(f"已生成：{export_filename}")
            with open(export_path, "rb") as f:
                st.download_button(
                    "下载 Word 文件",
                    f.read(),
                    file_name=export_filename,
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
