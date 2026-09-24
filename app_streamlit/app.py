"""快速体验版 Demo——10 部分整体框架（设计文档 v0.6）全部接了一版，范围仍然明确缩小：

- 没有 SQLite 持久化、没有项目管理，刷新页面就清空——正式版会接 engine/db.py（Milestone 3a 已建好那几张表）。
- 多选题的分组映射很简陋（同一个"分组键"打成 multi 类型的列会被合并）。
- 筛选题的"未通过筛选"判定只支持单选题（选中的值 = 未通过）；数值/开放题标成筛选题时会展示，但不参与过滤。
- ⑧交叉分析「对比到哪道题」单选/多选题都支持了（多选题按"这个分组里有百分之多少的人
  选了这个选项"算，分母是分组人数，不是选中次数——一个人选多个选项不会把分母算错）。
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
import io
import json
import mimetypes
import re
import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import streamlit as st
from PIL import Image as PILImage
from streamlit_echarts import st_echarts

from datetime import datetime

from engine.i18n import get_lang, t
from app_streamlit.lang_ui import init_language

from engine import (
    ai_classify,
    ai_insight,
    ai_translate,
    chart_spec,
    clean,
    db,
    export_markdown,
    export_pdf,
    export_word,
    ingest,
    mapping_memory,
    persistence,
    project_naming,
    stats,
)


DB_PATH = PROJECT_ROOT / "data" / "app.db"


def _get_db_conn():
    """整个 app 共用一个 SQLite 连接（存在 st.session_state 里，不用每次重开）。"""

    if "db_conn" not in st.session_state:
        st.session_state["db_conn"] = db.init_db(str(DB_PATH))
    return st.session_state["db_conn"]


init_language(_get_db_conn())


# st.set_page_config 不在这里调用——这个文件现在是 Home.py 多页应用里的一个子页面，
# set_page_config 每次运行只能调用一次，由入口 Home.py 统一负责。
#
# 左上角必须始终有一条退出这个页面的路——position="hidden" 关掉了 Streamlit 自带的
# 页面切换侧栏，之前"返回项目工作区"按钮只在 current_project_id 有值时才显示，
# session_state 被重置掉（比如服务端重启后浏览器还停在这一页）就彻底走不出去了。
nav_col1, nav_col2 = st.columns([1, 1])
with nav_col1:
    if st.button(t("← 返回首页")):
        st.switch_page("views/home_view.py")
if st.session_state.get("current_project_id") is not None:
    with nav_col2:
        if st.button(t("← 返回项目工作区")):
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
if visual_theme_name not in VISUAL_THEMES:
    # 真实反馈：这个 key 有时候会被塞进一个不是 "blue"/"minimalist" 的值（目前怀疑是
    # Streamlit 热重载时前端缓存的旧 widget 状态跟服务端重新对齐，把显示用的中文/英文
    # 标签文字当成了真正的值传回来——没有确凿证据坐实，但不管起因是什么，这道防线都该
    # 加：读到一个不认识的值就退回默认风格，不能让整页直接崩掉。同时把 session_state
    # 纠正回来，不然下面 478 行那个下拉框还会再读到同一个坏值。
    visual_theme_name = "blue"
    st.session_state["visual_theme"] = "blue"
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
        t("界面风格"),
        options=list(VISUAL_THEMES.keys()),
        format_func=lambda k: t(VISUAL_THEMES[k]["label"]),
        key="visual_theme",
        label_visibility="collapsed",
        help=t("切换标题字体／题目外框／结论字号；Streamlit 原生控件（按钮/勾选框/下拉框）固定跟随「蓝调报告」，这是已知限制，不是没切换生效。"),
    )
st.caption(t("设计文档最新版本 1～10 全部框架的真实调用演示。"))

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
    ("11. 导出", "sec11"),
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
        t("没有配置可用的 AI 供应商，去首页「API/模型设置」填一下。")
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
        return cache, t("{error}，暂时显示英文原文", error=provider_error_message('translation'))

    items = [{"response_id": i, "text_en": t} for i, t in enumerate(missing)]
    try:
        results = ai_translate.translate_verbatims(provider, items, protected_terms=[])
    except Exception as exc:  # noqa: BLE001
        return cache, t("自动翻译失败（{error}），暂时显示英文原文", error=exc)

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

    return cache, (t("有 {count} 条翻译没通过校验，暂时显示英文原文，建议人工核对", count=bad_count) if bad_count else None)


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
        st.markdown(t("**{prefix}{title}【{question_type}】**", prefix=display_prefix, title=title, question_type=type_label))
        return label_map, None

    st.markdown(t("**{prefix}{title}【{question_type}】**", prefix=display_prefix, title=title_zh, question_type=type_label))
    caption = f"*{title}*"
    if note:
        caption += t("　（{note}）", note=note)
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
    with st.popover("", icon=":material/edit:", help=t("编辑图表上显示的文字")):
        st.caption(t("留空就用自动生成的文字；改了这里，下面的图表和排版截图会跟着变。"))
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


def render_chart_save_controls(
    download_col, copy_col, q_no: str, chart_kind: str, stats_result: list[dict], title: str, title_suffix: str = ""
) -> None:
    """下载/复制这道题的图表——单独一张图，最上面带着问题原文的中文版，不用依赖
    网页上下文就能直接发给别人。中文标题优先用翻译缓存里的结果，题目本来就是中文的
    (translation_cache 查不到) 就用原文，两种情况 title_zh 都是"这道题该显示的中文"。
    """

    title_zh = st.session_state.get("translation_cache", {}).get(title, title) + title_suffix
    png_bytes = _chart_snapshot_png_for_save(q_no, chart_kind, stats_result, title_zh)
    with download_col:
        st.download_button(
            "",
            data=png_bytes,
            file_name=f"{q_no}.png",
            mime="image/png",
            icon=":material/download:",
            key=f"chart_download_{q_no}",
            help=t("下载这张图表"),
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
        t("拓展其他问题回答"),
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


def assign_first_group(raw_value_or_list, kind, valid_groups, include_rest):
    """左侧圈人群、单选题归组：每个人只进第一个匹配的维度。"""

    for group in valid_groups:
        if kind == "single":
            if pd.notna(raw_value_or_list) and raw_value_or_list in group["values"]:
                return group["name"]
        elif set(group["values"]) & set(raw_value_or_list):
            return group["name"]
    return t("其余") if include_rest else None


def all_matching_groups(selected_values, valid_groups, include_rest):
    """右侧多选题按匹配维度展开，同一维度里选了几个选项仍只算一个人。"""

    matched = [g["name"] for g in valid_groups if set(g["values"]) & set(selected_values)]
    return matched or ([t("其余")] if include_rest else [])


def dimension_stats_result(group_col: pd.Series, group_order: list[str]) -> list[dict]:
    """汇总独立问卷的维度占比；列表表示一个人匹配多个维度，分母仍按人算。

    跟 multi_choice_stats 一样，多选各维度的占比加起来可以超过 100%。未覆盖且
    没启用「其余」的人不参与本次分析，空列表由调用方转成 None，不按展开后的行数算。
    """

    n_total = int(group_col.notna().sum())
    rows = []
    for name in group_order:
        n = int(group_col.apply(lambda value: name in value if isinstance(value, list) else value == name).sum())
        pct = round(n / n_total * 100, 1) if n_total else 0.0
        rows.append({"option": name, "n": n, "pct": pct, "count_pct_label": stats.format_count_pct(n, n_total)})
    return rows


def _compute_crosstab_block_result(left_ctx: dict, right_ctx: dict) -> dict:
    """同问卷算联合交叉表，跨问卷分别算分布；两种结果共用板块和保存格式。"""

    def first_groups(ctx):
        return ctx["source_series"].apply(
            lambda v: assign_first_group(v, ctx["kind"], ctx["valid_groups"], ctx["include_rest"])
        )

    left_label, right_label = left_ctx["doc_label"], right_ctx["doc_label"]
    same_doc = left_ctx["doc_id"] is None and right_ctx["doc_id"] is None
    chart_config = None
    if same_doc:
        group_col_left = first_groups(left_ctx)
        group_totals = {g: int((group_col_left == g).sum()) for g in left_ctx["group_order"]}
        if right_ctx["kind"] == "single":
            answer_col = first_groups(right_ctx)
        else:
            answer_col = right_ctx["source_series"].apply(
                lambda vals: all_matching_groups(vals, right_ctx["valid_groups"], right_ctx["include_rest"])
            )
        crosstab_input = pd.DataFrame({"分组": group_col_left.values, "对比题答案": answer_col.values})
        if right_ctx["kind"] == "multi":
            crosstab_input = crosstab_input.explode("对比题答案")
        result_table = stats.crosstab_counts(
            crosstab_input, "分组", "对比题答案", group_order=left_ctx["group_order"],
            answer_order=right_ctx["group_order"], group_totals=group_totals,
        )
        title = t("{source} 按 {count} 个维度分组，对比 {target} 上的分布",
                  source=left_ctx["question_label"], count=len(left_ctx["valid_groups"]), target=right_ctx["question_label"])
    else:
        # 同名文档、甚至两栏显式选了同一份外部文档时，图例和表头也必须可区分。
        if left_label == right_label:
            left_label = t("{label}（左侧）", label=left_label)
            right_label = t("{label}（右侧）", label=right_label)
        rows = []
        totals = []
        for ctx in (left_ctx, right_ctx):
            if ctx["kind"] == "multi":
                group_col = ctx["source_series"].apply(
                    lambda vals: all_matching_groups(vals, ctx["valid_groups"], ctx["include_rest"]) or None
                )
            else:
                group_col = first_groups(ctx)
            rows.append(dimension_stats_result(group_col, ctx["group_order"]))
            totals.append(int(group_col.notna().sum()))
        result_table = stats.compare_choice_stats(rows[0], rows[1], left_label, right_label)
        title = t("跨问卷对比｜{label_a}·{question_a} vs {label_b}·{question_b}",
                  label_a=left_label, question_a=left_ctx["unit"]["display_no"],
                  label_b=right_label, question_b=right_ctx["unit"]["display_no"])
        categories = result_table.index.tolist()
        series = []
        for label, result_rows in zip((left_label, right_label), rows):
            percentages = {row["option"]: row["pct"] for row in result_rows}
            series.append({"name": label, "data": [percentages.get(c, 0.0) for c in categories]})
        chart_config = chart_spec.build_multi_series_chart_config(
            categories, series, title,
            t("有效样本：{label_a} N={n_a}；{label_b} N={n_b}",
              label_a=left_label, n_a=totals[0], label_b=right_label, n_b=totals[1]),
        )
        chart_config["xAxis"]["axisLabel"] = {"formatter": "{value}%"}
    return {"kind": "same_doc" if same_doc else "cross_doc", "title": title, "table": result_table,
            "chart_config": chart_config, "left_label": left_label, "right_label": right_label}


def render_crosstab_side(block_id: str, side: str, side_state: dict, units: list[dict], df_valid: pd.DataFrame) -> dict | None:
    """左右两栏共用的三层配置：问卷、题目、选项维度。"""

    conn = _get_db_conn()
    current_document_id = st.session_state.get("saved_document_id")
    other_docs = []
    for project in conn.execute("SELECT id, name FROM projects ORDER BY id DESC").fetchall():
        for doc in db.list_documents(conn, project["id"], research_type="quant_survey"):
            if doc["id"] != current_document_id:
                other_docs.append((doc["id"], f"{project['name']} · {doc['title']} · #{doc['id']}"))
    # 真实验证发现的坑：st.selectbox 的选项列表里如果直接放 Python 的 None 当某个
    # 选项的值（这里原来想用 None 表示"本份问卷"），Streamlit 没法区分"用户确实选中
    # 了这个值恰好是 None 的选项"和"这个控件还没有任何选中项"——组件会当成后者，
    # 界面上显示的是占位提示文字"Choose an option"而不是"本份问卷"，看起来像是
    # 什么都没选中，其实内部选中的就是（唯一的）默认项，真机截图对比才发现这个问题。
    # 改成用一个不会跟真实 document_id 撞上的字符串哨兵值给控件本身用，选完之后
    # 再翻译回 None——除了这一段，后面所有"doc_id is None 表示本份问卷"的逻辑
    # （落库格式、_compute_crosstab_block_result 等）都不用跟着改。
    SELF_DOC_SENTINEL = "__self__"
    doc_choice_ids = [SELF_DOC_SENTINEL] + [d[0] for d in other_docs]
    doc_choice_labels = {SELF_DOC_SENTINEL: t("本份问卷"), **dict(other_docs)}
    prefix = f"xtb_{block_id}_{side}"
    current_choice = SELF_DOC_SENTINEL if side_state["doc_id"] is None else side_state["doc_id"]
    picked_choice = st.selectbox(
        t("1. 选择问卷"), doc_choice_ids, format_func=lambda v: doc_choice_labels[v],
        index=doc_choice_ids.index(current_choice) if current_choice in doc_choice_ids else 0,
        key=f"{prefix}_doc",
    )
    picked_doc_id = None if picked_choice == SELF_DOC_SENTINEL else picked_choice
    if picked_doc_id != side_state["doc_id"]:
        # 不同问卷可以有完全相同的题号/题干，换问卷时不能串用上一份的选项和控件值。
        for key in list(st.session_state):
            if key.startswith(f"{prefix}_groups::") or key == f"{prefix}_question":
                del st.session_state[key]
        side_state["question_key"] = None
    side_state["doc_id"] = picked_doc_id
    if picked_doc_id is None:
        side_units, side_df = units, df_valid
        doc_label = st.session_state.get("document_title", t("本份问卷"))
    else:
        loaded = persistence.load_analysis(conn, picked_doc_id)
        side_units = loaded["units"]
        side_df = clean.filter_valid_samples(loaded["df_all"], loaded["screen_fail_values"])
        doc_label = loaded["title"]
    candidate_units = [u for u in side_units if u["kind"] in ("single", "multi")]
    if not candidate_units:
        st.info(t("这份问卷没有可用的单选/多选题。"))
        return None
    q_options = {f"{u['display_no']}｜{u['title']}": u for u in candidate_units}
    q_keys = list(q_options)
    q_key = st.selectbox(
        t("2. 选择题目"), q_keys,
        index=q_keys.index(side_state["question_key"]) if side_state["question_key"] in q_keys else 0,
        key=f"{prefix}_question",
    )
    side_state["question_key"] = q_key
    unit = q_options[q_key]
    if unit["kind"] == "single":
        source_series = side_df[unit["columns"][0]]
        candidate_values = sorted(source_series.dropna().unique().tolist(), key=str)
    else:
        source_series = _multi_select_list_series(side_df, unit["columns"])
        candidate_values = sorted({v for vals in source_series for v in vals}, key=str)
    groups_key = f"{prefix}_groups::{q_key}"
    st.session_state.setdefault(groups_key, [{"name": str(v), "values": [v]} for v in candidate_values])
    # 删除/重置后行号会换人；下一次创建控件前清掉旧值，跟图片管理组件的做法一致。
    reset_count = st.session_state.pop(f"{groups_key}_reset_widgets", 0)
    for gi in range(reset_count):
        st.session_state.pop(f"{groups_key}_name_{gi}", None)
        st.session_state.pop(f"{groups_key}_values_{gi}", None)
    st.markdown(t("3. 选择选项（分组）"))
    groups = st.session_state[groups_key]

    # 排序方式——按当前这道题原始选项的出现次数（分组内取值之和）给维度排一次序，
    # 不是"锁死一直按比例排"：选中某个排序方式的那一刻重排一次，之后用户用下面的
    # ↑↓ 手动调整完全不会被这里再次打回去（只有再换一次排序方式才会重新触发）。
    # "默认顺序"本身不做任何重排，只是清掉"已经按某种比例排过"的记录，不等于
    # "恢复成最初的选项顺序"（那是下面「按选项重置」按钮的职责，重置连分组内容
    # 一起清空，跟这里"只调顺序、不动分组内容"是两回事）。
    sort_labels = {"default": t("默认顺序"), "pct_desc": t("占比从高到低"), "pct_asc": t("占比从低到高")}
    sort_choice_key = f"{groups_key}_sort_choice"
    sort_applied_key = f"{groups_key}_sort_applied"
    picked_sort = st.selectbox(
        t("排序方式"), list(sort_labels), format_func=lambda k: sort_labels[k],
        key=sort_choice_key,
    )
    if picked_sort != "default" and st.session_state.get(sort_applied_key) != picked_sort:
        if unit["kind"] == "single":
            value_counts = source_series.value_counts().to_dict()
        else:
            value_counts: dict = {}
            for vals in source_series:
                for v in vals:
                    value_counts[v] = value_counts.get(v, 0) + 1
        groups.sort(
            key=lambda g: sum(value_counts.get(v, 0) for v in g["values"]),
            reverse=(picked_sort == "pct_desc"),
        )
        st.session_state[sort_applied_key] = picked_sort
        st.session_state[f"{groups_key}_reset_widgets"] = len(groups)
        st.rerun()
    elif picked_sort == "default":
        st.session_state[sort_applied_key] = None

    header_name_col, header_values_col, _, _, _ = st.columns([3, 5, 0.6, 0.6, 1])
    header_name_col.caption(t("维度名称"))
    header_values_col.caption(t("包含哪些取值"))
    delete_index = None
    move_swap: tuple[int, int] | None = None
    for gi, group in enumerate(groups):
        name_col, values_col, up_col, down_col, del_col = st.columns([3, 5, 0.6, 0.6, 1])
        group["name"] = name_col.text_input(
            t("维度名 {index}", index=gi), value=group["name"], key=f"{groups_key}_name_{gi}", label_visibility="collapsed"
        )
        group["values"] = values_col.multiselect(
            t("包含取值 {index}", index=gi), candidate_values,
            default=[v for v in group["values"] if v in candidate_values],
            key=f"{groups_key}_values_{gi}", label_visibility="collapsed",
        )
        # 手动微调顺序——不依赖拖拽（这个项目里拖拽类组件之前踩过坑，见 CLAUDE.md），
        # 跟图片管理组件的"↑↓调整顺序"是同一套模式，点了立刻生效，不需要额外确认。
        if up_col.button("↑", key=f"{groups_key}_up_{gi}", disabled=gi == 0, help=t("上移这个维度")):
            move_swap = (gi, gi - 1)
        if down_col.button("↓", key=f"{groups_key}_down_{gi}", disabled=gi == len(groups) - 1, help=t("下移这个维度")):
            move_swap = (gi, gi + 1)
        if del_col.button(t("删除"), key=f"{groups_key}_del_{gi}"):
            delete_index = gi
    if move_swap is not None:
        a, b = move_swap
        groups[a], groups[b] = groups[b], groups[a]
        st.session_state[f"{groups_key}_reset_widgets"] = len(groups)
        st.rerun()
    if delete_index is not None:
        st.session_state[f"{groups_key}_reset_widgets"] = len(groups)
        groups.pop(delete_index)
        st.rerun()
    btn_col1, btn_col2 = st.columns(2)
    if btn_col1.button(t("+ 新增维度"), key=f"{groups_key}_add"):
        groups.append({"name": t("维度{n}", n=len(groups) + 1), "values": []})
        st.rerun()
    if btn_col2.button(t("按选项重置"), key=f"{groups_key}_reset"):
        st.session_state[f"{groups_key}_reset_widgets"] = len(groups)
        st.session_state[groups_key] = [{"name": str(v), "values": [v]} for v in candidate_values]
        st.rerun()
    include_rest = st.checkbox(t("其余未覆盖的人另算一组"), key=f"{groups_key}_rest")
    valid_groups = [g for g in groups if g["values"] and g["name"].strip()]
    names = [g["name"] for g in valid_groups] + ([t("其余")] if include_rest else [])
    if len(set(names)) != len(names):
        st.info(t("维度名称不能重复，请修改后再生成。"))
        return None
    if not valid_groups:
        return None
    return {"unit": unit, "kind": unit["kind"], "source_series": source_series,
            "valid_groups": valid_groups, "include_rest": include_rest, "group_order": names,
            "doc_id": picked_doc_id, "doc_label": doc_label, "df": side_df, "question_label": q_key}


def _persist_ai_results() -> None:
    """把 session_state 里当前所有 AI 分类结果整份写进这份文档的正式数据（不等手动保存）。

    真实反馈"每次选完 AI 开放题分析，下次打开结果就没了"——AI 结果原来只跟"手动保存"/
    20 秒自动保存草稿走，重新打开读的是正式数据，草稿不读，所以两次保存之间跑的 AI 分类
    关页面就丢。现在分类跑完、清除的那一刻就直接落库。文档还没有 saved_document_id
    （理论上不会——页面开头会先把这份分析存一遍）就什么都不做。
    """

    document_id = st.session_state.get("saved_document_id")
    if document_id is None:
        return
    ai_results: dict = {}
    for key, value in st.session_state.items():
        if isinstance(key, str) and key.startswith("ai_result_"):
            q_no, sep, filter_key = key[len("ai_result_"):].partition("__")
            ai_results.setdefault(q_no, {})[filter_key if sep else ""] = value
    persistence.save_ai_results(_get_db_conn(), document_id, ai_results)


def render_open_ai_classify_trigger(q_no: str, series: pd.Series, filter_key: str = "") -> None:
    """开放题标题行最右边的星标按钮——点开一个小弹窗选封闭/开放分类，不占正文纵向空间。

    filter_key：如果这道开放题当前按关联题目的某个选项筛选过（比如只看"选了空气能
    空调"的人），传进来的 series 已经是筛完的子集，这里只是把分类结果存到一个带筛选
    条件的独立 key 上——不同筛选条件的分类结果互不覆盖，切换筛选条件之后各自的结果
    还能找回来，不用重新跑一遍。
    """

    ai_key = f"ai_result_{q_no}" if not filter_key else f"ai_result_{q_no}__{filter_key}"

    with st.popover(t("AI 分类"), use_container_width=True, key=f"ai_classify_trigger_{q_no}_{filter_key}"):
        if filter_key:
            st.caption(t("当前只分析筛选出来的 {count} 人（{filter}），不是全部受访者。", count=len(series), filter=filter_key))
        mode = st.radio(
            t("选择分类方式"),
            ["封闭分类（自己填类目）", "开放聚类（AI 自动提炼类目）", "自定义分析（自己写分析要求）"],
            key=f"mode_{q_no}_{filter_key}",
            format_func=t,
        )
        categories_input = ""
        instruction_input = ""
        if mode.startswith("封闭"):
            categories_input = st.text_input(t("候选类目（逗号分隔）"), key=f"cats_{q_no}_{filter_key}")
        elif mode.startswith("自定义"):
            instruction_input = st.text_area(
                t("分析要求（比如「判断每条回答有没有提到价格敏感」）"),
                key=f"instruction_{q_no}_{filter_key}",
                placeholder=t("用自己的话描述想从这些开放题回答里提炼出什么——AI 会先按这个要求总结出几个类目，再把每条回答分到对应类目里，出来的还是图表能直接画的分类结果。"),
            )

        has_existing_result = ai_key in st.session_state
        if has_existing_result:
            st.caption(t("这道题已经有一份 AI 分析结果，已自动保存。重新生成会先清除上一次的结果。"))
            if st.button(t("清除已有结果"), key=f"clear_ai_{q_no}_{filter_key}"):
                del st.session_state[ai_key]
                _persist_ai_results()
                st.rerun()
        if st.button(
            t("重新生成（清除上一次结果）") if has_existing_result else t("运行"),
            key=f"run_ai_{q_no}_{filter_key}",
            type="primary",
        ):
            provider = _get_provider_or_none()
            if provider is None:
                st.warning(provider_error_message())
            else:
                responses = [{"response_id": int(i), "text": str(text)} for i, text in series.items()]
                try:
                    with st.spinner(t("调用 AI 中…")):
                        if mode.startswith("封闭"):
                            categories = [c.strip() for c in categories_input.split(",") if c.strip()]
                            if not categories:
                                st.error(t("请先填至少一个候选类目。"))
                                st.stop()
                            assignments = ai_classify.classify_closed(provider, responses, categories)
                            st.session_state[ai_key] = {"categories": categories, "assignments": assignments}
                        elif mode.startswith("自定义"):
                            if not instruction_input.strip():
                                st.error(t("请先填写分析要求。"))
                                st.stop()
                            result = ai_classify.classify_custom(provider, responses, instruction_input)
                            st.session_state[ai_key] = result
                        else:
                            result = ai_classify.classify_open(provider, responses)
                            st.session_state[ai_key] = result
                    _persist_ai_results()
                    st.toast(t("AI 分析结果已自动保存。"))
                except Exception as exc:  # noqa: BLE001
                    st.error(t("AI 调用失败：{error}", error=exc))


def render_open_ai_classify_results(q_no: str, series: pd.Series, filter_key: str = "", title: str = "") -> None:
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
        st.dataframe(display_df, column_config={"原文": t("原文"), "AI 分类": t("AI 分类")})

        # Python 自己算数字，不采信 AI 的计数——分类结果喂回 stats 引擎
        category_series = pd.Series([a["category"] for a in assignments])
        cat_stats = stats.single_choice_stats(category_series)
        cat_chart_type = chart_spec.choose_chart_type("single", len(cat_stats))
        cat_config = chart_spec.build_chart_config(cat_chart_type, cat_stats, "", t("n = {n}", n=len(category_series)), color_palette=_active_chart_palette())
        # 跟单选题图表一样的"复制/下载"入口：一条深色小横条，标题在左、图标在右。
        # 缓存/控件 key 要跟这道题本身（开放题没有正文图表，但保险起见）和"不同筛选条件下的
        # 分类结果"都区分开，用 q_no + ai + filter_key 拼一个独立的 id。
        # filter_key 可能带中文/等号/空格（来自筛选条件），会破坏复制按钮 iframe 里的
        # CSS 选择器（#id），所以只取它的短哈希拼进 id。
        save_id = f"{q_no}_ai" + (f"_{hashlib.md5(filter_key.encode()).hexdigest()[:8]}" if filter_key else "")
        with st.container(key=f"qbar_ai_{save_id}"):
            header_col, copy_col, download_col = st.columns([10, 1, 1], gap=8)
            with header_col:
                st.markdown(f"**{t('AI 分类分布')}**")
            render_chart_save_controls(
                download_col, copy_col, save_id, "single", cat_stats, title, title_suffix=t("｜AI 分类分布")
            )
        render_chart(cat_chart_type, cat_config, key=f"ai_chart_{q_no}_{filter_key}")


def _chart_snapshot_png_for_save(q_no: str, chart_kind: str, stats_result: list[dict], title_zh: str) -> bytes:
    """"保存单张图表"按钮用的版本——把问题原文（中文版）画在图表最上面，这样单独
    存下来/发给别人的这张图，不用额外说明是哪道题。结果按内容指纹缓存在
    session_state 里，避免每次重跑脚本都要重新调一次 matplotlib（几百毫秒的 CPU
    工作，不缓存会让相关交互卡到看起来像坏的）。
    """

    fingerprint = (get_lang(), chart_kind, title_zh, tuple((row["option"], row["n"]) for row in stats_result))
    cache_key = f"chart_png_with_title_cache_{q_no}"
    cached = st.session_state.get(cache_key)
    if cached is not None and cached[0] == fingerprint:
        return cached[1]

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        export_word._render_chart_image(chart_kind, stats_result, tmp.name, title=title_zh, color_palette=_active_chart_palette())
        png_bytes = Path(tmp.name).read_bytes()

    st.session_state[cache_key] = (fingerprint, png_bytes)
    return png_bytes


def _grouped_bar_snapshot_png_for_save(key: str, categories: list[str], series: list[dict], title_zh: str) -> bytes:
    """按内容指纹缓存分组柱状图，避免每次 rerun 都重新画 matplotlib。"""

    palette = _active_chart_palette()
    fingerprint = (get_lang(), title_zh, tuple(categories), tuple((s["name"], tuple(s["data"])) for s in series), tuple(palette or []))
    cache_key = f"grouped_bar_png_cache_{key}"
    cached = st.session_state.get(cache_key)
    if cached is not None and cached[0] == fingerprint:
        return cached[1]
    with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
        export_word.render_grouped_bar_chart_image(categories, series, tmp.name, title=title_zh, color_palette=palette)
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
        <button id="{key}" title="{html_lib.escape(t('复制这张图表到剪贴板'), quote=True)}">
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
            status.textContent = {json.dumps(t("已复制"))};
            status.style.color = "#2E7D52";
        }} catch (err) {{
            status.textContent = {json.dumps(t("复制失败"))};
            status.style.color = "#B23B3B";
            console.error(err);
        }}
        setTimeout(() => {{ status.textContent = ""; }}, 1500);
    }});
    </script>
    """
    st.components.v1.html(html, height=42)


# "排版预览"里图片的基准高度／间距——真实反馈："别再让我自己调每张图的大小了，
# 干脆定死一个基准高度：饼图现在的高度（CHART_HEIGHT["pie"]）的 2/3"。用户自己选的
# 这个基准，理由是饼图旁边常常要摆照片，2/3 饼图高度看着协调，还顺带保证不会比图表
# 本身还醒目。用 CHART_HEIGHT 算出来而不是单独写死一个数字，饼图高度以后要是改了，
# 这个基准跟着自动变，不会出现"两个地方都存了一份高度、改了一个忘了改另一个"。
IMAGE_ROW_BASE_HEIGHT_PX = round(int(CHART_HEIGHT["pie"].removesuffix("px")) * 2 / 3)
IMAGE_ROW_BASE_GAP_PX = 16

# "排版预览"这一行实际有多宽——Streamlit 没给服务端 Python 提供"卡片容器实际渲染了
# 多宽"这个信息（跟着浏览器窗口变，不是写死的），这里用桌面浏览器正常宽度下真实
# 截图量出来的经验值。`_render_tiles_row` 靠这个值判断"每行放几张"设定的张数在当前
# 图片大小下放不放得下，放不下就把这一行统一缩小，保证张数优先于大小（真实反馈：
# 「每行放几张」原来不是硬约束，跟图片大小会打架）。
ROW_WIDTH_ASSUMPTION_PX = 940


def _image_mime(img: dict) -> str:
    """旧图片没有 MIME 时从文件名猜测，无法识别时按 PNG 处理。"""

    return img.get("mime") or mimetypes.guess_type(img.get("name", ""))[0] or "image/png"


def _images_payload(images: list[dict]) -> list[dict]:
    """即时保存与整份保存共用图片编码，避免后一次保存丢失字段。

    真实反馈：手动逐张调大小太麻烦，改成"统一按基准高度对齐，放不下才自动缩小"
    （见 `_render_tiles_row`），图片不再各自存一个可调的 zoom 了——旧数据里如果还有
    "zoom" 字段，读回来直接忽略，不会报错，也不会被这里重新写回去。
    """

    return [
        {
            "name": img["name"],
            "caption": img.get("caption", ""),
            "bytes_b64": base64.b64encode(img["bytes"]).decode("ascii"),
            "mime": _image_mime(img),
        }
        for img in images
    ]


def _persist_images(q_no: str) -> None:
    """把 session_state 里当前题目的图片写进这份文档的正式数据（不等手动保存）。

    跟 AI 分类结果一样，图片新增/编辑/删除后直接落库，重新打开不依赖自动保存草稿。
    文档还没有 saved_document_id 就什么都不做。
    """

    document_id = st.session_state.get("saved_document_id")
    if document_id is None:
        return
    images_payload = _images_payload(st.session_state.get(f"images_{q_no}", []))
    persistence.save_images(_get_db_conn(), document_id, q_no, images_payload)


def _crosstab_blocks_payload() -> list[dict]:
    """即时保存和整份保存共用编码，DataFrame 只在 session_state 内保留。"""

    payload = []
    for block in st.session_state.get("crosstab_blocks", [{"id": "1", "left": {"doc_id": None, "question_key": None}, "right": {"doc_id": None, "question_key": None}, "result": None}]):
        entry = {"id": block["id"], "left": dict(block["left"]), "right": dict(block["right"]), "result": None}
        if block.get("result") is not None:
            r = block["result"]
            table = r["table"]
            entry["result"] = {**r, "table": table.to_dict(orient="split"),
                               "table_index_name": table.index.name, "table_columns_name": table.columns.name}
        payload.append(entry)
    return payload


def _crosstab_state_payload() -> dict:
    """维度仍放在独立 key；保存分组和计数器，重新打开也不丢配置、不回收编号。"""

    groups = {}
    for block in st.session_state.get("crosstab_blocks", []):
        for side in ("left", "right"):
            q_key = block[side]["question_key"]
            key = f"xtb_{block['id']}_{side}_groups::{q_key}"
            if key in st.session_state:
                groups[key] = {"groups": st.session_state[key], "include_rest": st.session_state.get(f"{key}_rest", False)}
    return {"groups": groups, "next_block_id": st.session_state.get("crosstab_next_block_id", 2)}


def _persist_crosstab_blocks() -> None:
    """新增、删除、成功生成后直接保存正式 extras，不等手动保存或草稿。"""

    document_id = st.session_state.get("saved_document_id")
    if document_id is None:
        return
    persistence.save_crosstab_blocks(
        _get_db_conn(), document_id, _crosstab_blocks_payload(), state_payload=_crosstab_state_payload()
    )


def _render_zoomable_image(image_bytes: bytes, width_pct: int) -> None:
    """"插入图片"弹窗里管理列表／图库预览用的小缩略图，用 Streamlit 原生 `st.image`
    （不是拼 `<img>` 字符串）。这里只是给用户认一眼"这是哪张图"，不是最终排版效果——
    最终排版（等高对齐、放不下自动缩小）由 `_render_tiles_row` 决定，跟这份预览的
    大小无关，固定用一个看着舒服的缩略图比例就行，不需要能调。

    真实反馈"点图片跳到一个空白页"——第一版是把 base64 拼成 `data:` URI 放进
    `<a href target=_blank>`，现代 Chrome/Firefox 出于安全考虑不允许从链接点击直接
    整页跳转到 data: URI，点了只会打开一个空白页。第二版改成点击时用 `onclick` 里的
    JS 现场转成 blob: URL 再 `window.open`——结果 `st.markdown(unsafe_allow_html=True)`
    会把 `onclick` 这种事件属性直接过滤掉（真机确认过：渲染出来的 `<img>` 标签里
    `onclick` 整个不见了，样式类属性都还在，说明是选择性过滤事件属性，不是把整段
    HTML 都拦了），JS 根本没机会跑。

    现在这版放弃拼 HTML：用 `st.image` 原生渲染，缩略图大小靠"把图片放进一个按比例
    分栏的 `st.columns` 窄栏里 + `use_container_width=True`"实现（栏宽占整行的百分之几
    × 图片撑满这栏 = 视觉上等价的百分比缩放）。这样还顺带白拿 Streamlit 自带的悬浮
    工具栏（鼠标移上去右上角会出现一个全屏图标），点了在页面内弹出原始分辨率大图，
    不是导航到别的页面，不会撞上任何浏览器的跨页面安全限制。
    """

    width_pct = max(20, min(100, int(width_pct)))
    if width_pct >= 100:
        st.image(image_bytes, use_container_width=True)
    else:
        narrow_col, _ = st.columns([width_pct, 100 - width_pct])
        with narrow_col:
            st.image(image_bytes, use_container_width=True)


def _image_aspect_ratio(image_bytes: bytes) -> float:
    """原图的宽/高比——`_render_tiles_row` 算"等高排版时每张图该多宽"要用到。

    解码失败（理论上不会——上传时 `file_uploader` 已经限定了 png/jpg/jpeg，能存进
    去的字节都是真图片）就退回 1.0（当正方形处理），不能让一张图解码失败拖累
    整行都渲染不出来。
    """

    try:
        with PILImage.open(io.BytesIO(image_bytes)) as img:
            width, height = img.size
        return width / height if height else 1.0
    except Exception:  # noqa: BLE001
        return 1.0


def _render_tiles_row(row_tiles: list[dict], single_image_align: str = "center") -> None:
    """"排版预览"里一行图片按统一的基准高度对齐，宽度各自按原图比例走，且保证
    "每行放几张"这个数不被打破——这是用户自己定下来的规则，不再让每张图各自调大小：

    1. 基准高度固定为 `IMAGE_ROW_BASE_HEIGHT_PX`（饼图高度的 2/3，用户自己选的
       比例）。这一行的图片按各自真实长宽比、都用这个基准高度算出天然想要的宽度。
    2. 天然总宽度（含间距）放得下这一行假定的可用宽度，就按基准高度原样显示，
       不缩小。放不下，把这一行所有图片的高度和间距按同一个比例统一缩小，缩到
       刚好放得下——不裁切、不变形，只是整体缩小，"每行放几张"永远是真的（不会
       因为放不下而被迫换行/减少张数）。这套"放得下就不缩、放不下就统一缩"的算法
       跟上一版（每张图自己独立可调大小）一脉相承，只是现在所有图片的"基准高度"
       都相等，不再有各自独立的缩放值。
    3. 只有一张图（这一行没有别的图片一起排版）时，天然宽度不会超出可用宽度
       （单独一张不存在"排不下"的问题），这时按 `single_image_align` 居中或居左——
       真实反馈"只放一张图的时候，默认居中，也可以选居左"。多张图排一行的默认
       靠左对齐不受这个参数影响。

    ROW_WIDTH_ASSUMPTION_PX：这个工具的"纸张"卡片没有写死的像素宽度（能跟着浏览器
    宽度变），Streamlit 也没给服务端 Python 提供"这个容器实际渲染了多宽"这个信息，
    没法算出一个总是精确的数字。这里用一个基于真实截图量出来的经验值（桌面浏览器
    正常宽度下，卡片内容区大约这么宽）来做"放不放得下"的判断——比这个宽的浏览器
    窗口，图片可能比理论上能放的还稍微小一点；比这个窄的，可能会略微超出（有
    `overflow-x` 兜底，最多出现一条很少见的横向滚动条，不会整个布局崩掉）。
    """

    if not row_tiles:
        return

    ratios = [_image_aspect_ratio(tile["bytes"]) for tile in row_tiles]
    wanted_height = IMAGE_ROW_BASE_HEIGHT_PX
    wanted_gap_px = IMAGE_ROW_BASE_GAP_PX

    wanted_total_width = wanted_height * sum(ratios) + wanted_gap_px * (len(row_tiles) - 1)
    scale = 1.0
    if wanted_total_width > ROW_WIDTH_ASSUMPTION_PX:
        scale = ROW_WIDTH_ASSUMPTION_PX / wanted_total_width

    height_px = max(24, round(wanted_height * scale))
    gap_px = max(4, round(wanted_gap_px * scale))
    items_html = []
    for tile in row_tiles:
        b64 = base64.b64encode(tile["bytes"]).decode("ascii")
        caption_html = ""
        if tile.get("caption"):
            caption_html = (
                '<figcaption style="margin-top:0.3rem; font-size:0.8rem; color:#6B6B6B; '
                f'text-align:center; max-width:100%;">{html_lib.escape(tile["caption"])}</figcaption>'
            )
        items_html.append(
            '<figure style="margin:0; display:flex; flex-direction:column; align-items:center; flex:0 0 auto;">'
            f'<img src="data:{tile["mime"]};base64,{b64}" alt="" '
            f'style="height:{height_px}px; width:auto; display:block; border-radius:0;">'
            f'{caption_html}</figure>'
        )
    justify = "flex-start"
    if len(row_tiles) == 1:
        justify = "center" if single_image_align == "center" else "flex-start"
    st.markdown(
        # width:100% 不能漏——真实反馈"居中设置了但完全没居中"：这段 HTML 是 st.markdown
        # 拼出来的一个普通 <div>，没有显式 width 的话，浏览器会让它按内容宽度收缩
        # （shrink-to-fit），不会自动撑满卡片宽度。justify-content:center 是"在容器内部
        # 把内容居中"，容器本身如果已经缩到跟内容一样宽，就没有多余空间可以居中——
        # 两张图那一行看着没占满卡片宽度、单独一张图完全没居中，都是这同一个根因。
        f'<div style="display:flex; align-items:flex-end; justify-content:{justify}; '
        f'width:100%; flex-wrap:nowrap; overflow-x:auto; gap:{gap_px}px; margin-bottom:0.75rem;">'
        + "".join(items_html) + "</div>",
        unsafe_allow_html=True,
    )


def _collect_image_library(exclude_q_no: str) -> list[dict]:
    """收集其它题目的图片，按题号排序后去重，保留最早题号作为来源。"""

    sources = sorted(
        (key[len("images_"):], value)
        for key, value in st.session_state.items()
        if isinstance(key, str) and key.startswith("images_")
        and key != f"images_{exclude_q_no}" and isinstance(value, list)
    )
    library = []
    seen = set()
    for q_no, images in sources:
        for img in images:
            bytes_hash = img.get("bytes_hash") or hashlib.md5(img["bytes"]).hexdigest()
            if bytes_hash in seen:
                continue
            seen.add(bytes_hash)
            library.append({
                "bytes": img["bytes"], "name": img["name"], "mime": _image_mime(img),
                "bytes_hash": bytes_hash, "source_q_no": q_no,
            })
    return library


def render_image_attachments_trigger(q_no: str) -> None:
    state_key = f"images_{q_no}"
    images = st.session_state.setdefault(state_key, [])

    # 移动/删除后下标会换人；在下次创建控件前清理旧值，避免说明文字串到另一张图。
    reset_count = st.session_state.pop(f"img_reset_widgets_{q_no}", 0)
    for i in range(reset_count):
        st.session_state.pop(f"img_caption_{q_no}_{i}", None)

    with st.popover("", icon=":material/add_photo_alternate:", help=t("插入图片")):
        upload_tab, library_tab = st.tabs([t("上传新图片"), t("从其他题目复制")])
        with upload_tab:
            # file_uploader 有个坑：只要 key 不变，它会一直记得这次选过的文件、每次 rerun
            # 都原样交还给你，不是"只在你选文件的那一次"才返回——不是靠 key 换掉来复位的话，
            # 删除一张图片之后紧接着的那次 rerun，这里会看到"上传框里还有这个文件、但
            # images 里已经没有了"，判定成"新上传"又给加回去，delete 按钮等于白点了。
            # 换 key 强制这个控件复位，成功吃进一批文件之后就跟它没关系了。
            uploader_key_counter = st.session_state.setdefault(f"img_uploader_key_{q_no}", 0)
            uploaded_images = st.file_uploader(
                t("选择图片（可多选，可重复调用多次追加）"),
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
                                "mime": f.type or _image_mime({"name": f.name}),
                                "bytes_hash": hashlib.md5(content).hexdigest(),
                            }
                        )
                        added = True
                if added:
                    st.session_state[f"img_uploader_key_{q_no}"] += 1
                    _persist_images(q_no)
                    st.rerun()

        with library_tab:
            st.caption(t("同一张图要用在好几道题时，不用重新从电脑上传——点「添加到本题」直接复用这份分析里已经传过的图。"))
            library = _collect_image_library(q_no)
            if not library:
                st.caption(t("这份分析里其他题目还没有插入过图片。"))
            for source in library:
                preview_col, add_col = st.columns([3, 1])
                with preview_col:
                    _render_zoomable_image(source["bytes"], 30)
                    st.caption(t("来自 {source_q_no}：{name}", source_q_no=source["source_q_no"], name=source["name"]))
                with add_col:
                    if st.button(t("添加到本题"), key=f"img_copy_{q_no}_{source['bytes_hash']}"):
                        images.append({
                            "bytes": source["bytes"], "name": source["name"],
                            "mime": source["mime"], "bytes_hash": source["bytes_hash"],
                            "caption": "",
                        })
                        _persist_images(q_no)
                        st.rerun()

        if images:
            st.caption(t("图片会按统一的基准高度自动对齐，放不下时自动等比例缩小（不会裁切、不会变形）；"
                "用 ↑↓ 调整先后顺序。「每行放几张」和单张图片时靠左/居中，在这个弹窗关掉之后、"
                "图片正下方的排版预览里调。"))

        delete_index = None
        move_swap: tuple[int, int] | None = None
        edited = False
        for i, img in enumerate(images):
            image_col, action_col = st.columns([3, 1])
            with action_col:
                # 排版顺序用"上移/下移"调整，不是拖拽——排版里这张图排第几个，就是它在
                # images 这个列表里的位置，跟下面按"每行放几张"分组渲染时用的是同一个顺序。
                if st.button("↑", key=f"img_up_{q_no}_{i}", disabled=i == 0, help=t("上移这张图片")):
                    move_swap = (i, i - 1)
                if st.button("↓", key=f"img_down_{q_no}_{i}", disabled=i == len(images) - 1, help=t("下移这张图片")):
                    move_swap = (i, i + 1)
                if st.button(t("删除"), key=f"img_del_{q_no}_{i}", help=t("删除这张图片")):
                    delete_index = i
            with image_col:
                _render_zoomable_image(img["bytes"], 60)
            caption = st.text_input(
                t("图片描述"), value=img["caption"], key=f"img_caption_{q_no}_{i}", label_visibility="collapsed",
                placeholder=t("给这张图配一行文字描述"),
            )
            if caption != img.get("caption", ""):
                img["caption"] = caption
                edited = True
            st.divider()
        if move_swap is not None:
            a, b = move_swap
            images[a], images[b] = images[b], images[a]
            st.session_state[f"img_reset_widgets_{q_no}"] = len(images)
            _persist_images(q_no)
            st.rerun()
        if delete_index is not None:
            st.session_state[f"img_reset_widgets_{q_no}"] = len(images)
            images.pop(delete_index)
            _persist_images(q_no)
            st.rerun()
        if edited:
            _persist_images(q_no)


def render_image_attachments_grid(q_no: str) -> None:
    """插入图片 + 文字描述，单独排成一行/几行——真实反馈"插入的图片不能跟饼图/柱状图
    挤在同一行，应该在问题和分析图表之间单独成一行"：图表是算出来的分析结果，图片是
    用户自己找补充证据用的，两种性质不同的内容混排在一起容易分不清哪个是哪个。这个
    函数现在只管图片自己的排版，图表完全是另一条路径（调用方在这个函数和图表之间
    直接空开，图表永远走交互式 ECharts，不再有"要不要把图表也塞进排版"这道选择）。

    排版用的是"每行放几张"+ 上下移动调整顺序，不是自由拖拽——原来那版用
    streamlit-elements（react-grid-layout）做自由拖拽/调整大小，两轮下来都没能在真实
    浏览器里跑出预期效果（这个组件本身也确认过是个不算活跃维护的第三方库），排查成本
    已经不小；"上下移动"是最基础的按钮点击，不会有"这个事件到底有没有被真正触发"这种
    不确定性。一行内部的排版（每张图多高、彼此间距多少、单张时怎么对齐）交给
    `_render_tiles_row`——图片不再各自有可调的大小，统一按基准高度对齐，这是用户
    自己定的规则："别再让我一张一张调了，干脆定死一个基准高度，放不下再自动缩小"。
    """

    state_key = f"images_{q_no}"
    images = st.session_state.setdefault(state_key, [])

    if not images:
        return

    tiles = [
        {"bytes": img["bytes"], "mime": _image_mime(img), "caption": img.get("caption", "")}
        for img in images
    ]

    st.caption(t("图片先后顺序在上面「插入图片」弹窗里调；这里管下面排版分成几行、每行放几张、"
        "单张图片时靠左还是居中。"))

    per_row = st.number_input(
        t("每行放几张"),
        min_value=1,
        max_value=6,
        value=st.session_state.get(f"images_per_row_{q_no}", 1),
        key=f"images_per_row_{q_no}",
        help=t("这个数是硬约束——图片统一按基准高度（饼图高度的 2/3）显示，放得下就不缩小；"
            "这一行放不下设定的张数时，会把这一行所有图片按同一个比例统一缩小到刚好放得下"
            "（不会裁切、不会变形），不会因为放不下就换行或者减少这一行放几张。"),
    )
    align = st.radio(
        t("单张图片时的对齐方式"),
        options=["center", "left"],
        format_func=lambda v: t("居中") if v == "center" else t("居左"),
        horizontal=True,
        index=0 if st.session_state.get(f"images_align_{q_no}", "center") == "center" else 1,
        key=f"images_align_{q_no}",
        help=t("只在这一行只有一张图片时生效（比如「每行放几张」设成 1，或者最后一行只剩一张）；"
            "同一行有好几张图片时始终靠左，不受这个设置影响。"),
    )

    for row_start in range(0, len(tiles), per_row):
        _render_tiles_row(tiles[row_start : row_start + per_row], single_image_align=align)


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
    header_cells = "".join(f"<th>{html_lib.escape(t(c) if c == '原文' else str(c))}</th>" for c in columns)
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
    """按题型渲染一个"题目单元"（单选/多选/排序/开放/数值），section_df 已经是这一段该用的样本。

    sec_units/unit_index：开放题要在同一段里前后找候选关联题目才需要，其他题型用不上，
    默认 None 也不影响单选/多选/数值的渲染。
    """

    kind = unit["kind"]
    q_no = unit["display_no"]
    title = unit["title"]
    cols = unit["columns"]

    if kind == "single":
        col = cols[0]
        raw_result = stats.single_choice_stats(section_df[col])
        options = [r["option"] for r in raw_result]
        with st.container(key=f"qbar_{q_no}"):
            header_col, insert_col, edit_col, copy_col, download_col = st.columns([8.5, 1, 1, 1, 1], gap=8)
            with header_col:
                label_map, header_caption = render_question_header(q_no, title, t("单选题"), options)
            display_result = relabel(raw_result, label_map)
            with edit_col:
                display_result = render_label_override_editor(q_no, display_result)
            render_chart_save_controls(download_col, copy_col, q_no, "single", display_result, title)
            with insert_col:
                render_image_attachments_trigger(q_no)
        if header_caption:
            st.caption(header_caption)
        # 插入的图片单独成一行，放在问题标题和下面的分析图表之间——真实反馈"插入的图片
        # 不能和饼图/柱状图挤在同一行"，图表和图片本来就是两种不同性质的内容（图表是
        # 算出来的分析结果，图片是用户自己找补充证据用的），混排在一起容易搞不清哪个
        # 是哪个。图表因此也不用再在"交互图" vs "参与排版的静态截图"之间二选一了，
        # 图表固定走交互式 ECharts 这条路，跟插入的图片互不干扰。
        render_image_attachments_grid(q_no)
        chart_type = chart_spec.choose_chart_type("single", len(display_result))
        config = chart_spec.build_chart_config(chart_type, display_result, "", t("n = {n}", n=n_for_footer), color_palette=_active_chart_palette())
        render_chart(chart_type, config, key=f"chart_{q_no}")

    elif kind == "numeric":
        col = cols[0]
        with st.container(key=f"qbar_{q_no}"):
            header_col, insert_col = st.columns([11, 1])
            with header_col:
                _, header_caption = render_question_header(q_no, title, t("数值题"), [])
            with insert_col:
                render_image_attachments_trigger(q_no)
        if header_caption:
            st.caption(header_caption)
        render_image_attachments_grid(q_no)
        result = stats.numeric_stats(section_df[col])
        st.table(pd.DataFrame([result]))

    elif kind == "open":
        col = cols[0]
        series = section_df[col].dropna()

        with st.container(key=f"qbar_{q_no}"):
            header_col, insert_col, star_col = st.columns([9.5, 1, 2], gap=8)
            with header_col:
                _, header_caption = render_question_header(q_no, title, t("开放题"), [])
            with insert_col:
                render_image_attachments_trigger(q_no)
        if header_caption:
            st.caption(header_caption)
        render_image_attachments_grid(q_no)

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
            if st.button("", icon=toggle_icon, key=f"toggle_raw_{q_no}", help=t("展开/收起原始数据")):
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
                        t("按「{question}」筛选", question=ctx_label),
                        options,
                        key=f"context_filter_{q_no}_{ctx_label}",
                        format_func=lambda value: t(value) if value == "（全部）" else value,
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
            note = t("、").join(t("「{label}」＝{value}", label=label, value=value) for label, value in active_filters)
            st.write(t("当前只看 {filter} 这部分：{filtered} 人（这道题总共 {count} 人填写）。", filter=note, filtered=len(filtered_series), count=len(series)))
        else:
            st.write(t("{count}人填写了这题。", count=len(series)))

        render_open_ai_classify_results(q_no, filtered_series, filter_key=filter_key, title=title)

    elif kind == "multi":
        list_series = _multi_select_list_series(section_df, cols)
        raw_result = stats.multi_choice_stats(list_series)
        options = [r["option"] for r in raw_result]
        with st.container(key=f"qbar_{q_no}"):
            header_col, insert_col, edit_col, copy_col, download_col = st.columns([8.5, 1, 1, 1, 1], gap=8)
            with header_col:
                zh_map, header_caption = render_question_header(q_no, title, t("多选题"), options)
            display_result = relabel(raw_result, zh_map)
            with edit_col:
                display_result = render_label_override_editor(q_no, display_result)
            render_chart_save_controls(download_col, copy_col, q_no, "multi", display_result, title)
            with insert_col:
                render_image_attachments_trigger(q_no)
        if header_caption:
            st.caption(header_caption)
        render_image_attachments_grid(q_no)
        config = chart_spec.build_chart_config("bar_h", display_result, "", t("n = {n}", n=n_for_footer), color_palette=_active_chart_palette())
        render_chart("bar_h", config, key=f"chart_multi_{q_no}")

    elif kind == "ranking":
        max_rank = len(cols)
        option_labels_raw = clean.option_labels_for_group(cols)
        with st.container(key=f"qbar_{q_no}"):
            header_col, insert_col = st.columns([11, 1])
            with header_col:
                label_map, header_caption = render_question_header(
                    q_no, title, t("排序题"), list(option_labels_raw.values())
                )
            with insert_col:
                render_image_attachments_trigger(q_no)
        if header_caption:
            st.caption(header_caption)
        render_image_attachments_grid(q_no)

        option_labels_display = {c: label_map.get(v, v) for c, v in option_labels_raw.items()}
        for row_start in range(0, len(cols), 4):
            row_cols_names = cols[row_start:row_start + 4]
            row_st_cols = st.columns(len(row_cols_names))
            for st_col, orig_col in zip(row_st_cols, row_cols_names):
                option_label = option_labels_display[orig_col]
                rank_stats = stats.ranking_option_stats(section_df, orig_col, max_rank)
                rank_stats_display = [
                    {**row, "option": t("第{rank}名", rank=row["option"])}
                    for row in rank_stats
                ]
                config = chart_spec.build_chart_config(
                    "pie", rank_stats_display, option_label, "",
                    color_palette=_active_chart_palette(),
                )
                # 每个选项也要能一键复制/下载，跟单选/多选题图表一样——真实反馈"这几张
                # 饼图也需要 copy/download"。原始列名可能带中文/换行/连字符（比如见数
                # 那种"题干-选项"格式），直接拼进 st.container key 会破坏"st-key-..."
                # CSS 选择器，所以跟 AI 分类结果那个 mini qbar 一样，只取列名的短哈希
                # 拼一个安全的 id，不直接用原始列名。
                save_id = f"{q_no}_{hashlib.md5(orig_col.encode()).hexdigest()[:8]}"
                with st_col:
                    with st.container(key=f"qbar_rank_{save_id}"):
                        header_col, copy_col, download_col = st.columns([6, 1, 1], gap=8)
                        with header_col:
                            st.markdown(f"**{option_label}**")
                        render_chart_save_controls(
                            download_col, copy_col, save_id, "single", rank_stats_display, title,
                            title_suffix=t("｜{option}", option=option_label),
                        )
                    render_chart("pie", config, key=f"chart_rank_{q_no}_{orig_col}")

        st.table(stats.ranking_table(section_df, cols, option_labels_display, max_rank))


def build_units(mapping: pd.DataFrame) -> list[dict]:
    """把映射表拆成题目单元：多选/排序按同题型、同分类和同分组键合并，其余一行一个单元。"""

    units: list[dict] = []
    seen_group_keys: set[tuple[str, str, str]] = set()
    for _, row in mapping.iterrows():
        if row["q_type"] == "忽略":
            continue
        if row["q_type"] in ("multi", "ranking"):
            group_key = (row["q_type"], row["section"], row["q_no"])
            if group_key in seen_group_keys:
                continue
            seen_group_keys.add(group_key)
            cols = mapping[
                (mapping["q_type"] == row["q_type"])
                & (mapping["q_no"] == row["q_no"])
                & (mapping["section"] == row["section"])
            ]["column"].tolist()
            units.append(
                {"kind": row["q_type"], "section": row["section"], "title": row["title"], "columns": cols}
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
            # 旧数据（这次改动之前存的）可能还带着每张图各自的 "zoom" 字段——图片已经
            # 不再各自调大小了，统一按基准高度对齐，这个字段读回来也没地方用，不用理它。
            content = base64.b64decode(img["bytes_b64"])
            restored.append(
                {
                    "bytes": content,
                    "name": img["name"],
                    "caption": img.get("caption", ""),
                    "mime": _image_mime(img),
                    "bytes_hash": hashlib.md5(content).hexdigest(),
                }
            )
        st.session_state[f"images_{q_no}"] = restored

    for q_no, per_row in extras.get("images_per_row", {}).items():
        st.session_state[f"images_per_row_{q_no}"] = per_row

    for q_no, align in extras.get("images_align", {}).items():
        st.session_state[f"images_align_{q_no}"] = align

    # 旧数据（这次改动之前存的）可能还带着 "include_chart_in_grid" 这个字段——图表
    # 已经不再参与图片排版了，这个字段读回来也没地方用，不用管它，`extras.get(...)`
    # 直接不读这个 key 就行，字段留在旧记录里不会报错，也不影响其它内容加载。

    for q_no, overrides in extras.get("label_overrides", {}).items():
        st.session_state[f"label_overrides_{q_no}"] = dict(overrides)


    restored_blocks = []
    for entry in extras.get("crosstab_blocks", []):
        block = {"id": entry["id"], "left": dict(entry["left"]), "right": dict(entry["right"]), "result": None}
        if entry.get("result") is not None:
            r = entry["result"]
            table = pd.DataFrame(**r["table"])
            table.index.name = r.get("table_index_name")
            table.columns.name = r.get("table_columns_name")
            block["result"] = {"kind": r["kind"], "title": r["title"], "table": table,
                               "chart_config": r["chart_config"], "left_label": r["left_label"], "right_label": r["right_label"]}
        restored_blocks.append(block)
    # 老文档没有这个字段时也给一个空板块；明确删光的空列表则原样恢复。
    if "crosstab_blocks" in extras:
        st.session_state["crosstab_blocks"] = restored_blocks
    state = extras.get("crosstab_state", {})
    st.session_state["crosstab_next_block_id"] = max(
        max((int(b["id"]) for b in restored_blocks), default=0) + 1, state.get("next_block_id", 2)
    )
    for key, value in state.get("groups", {}).items():
        st.session_state[key] = value["groups"]
        st.session_state[f"{key}_rest"] = value["include_rest"]


# ---------------------------------------------------------------------------
# 1. 上传
# ---------------------------------------------------------------------------

# 上传/映射/生成分析这一整块——生成分析之前需要一直展开着方便配置，生成分析之后
# 默认收起来（不是删掉，折叠状态下这里面的控件照样能用、照样能改，只是视觉上先让位
# 给下面的分析结果，不用的话不用一直占着屏幕最上面的空间）。
with st.expander(t("原始数据"), expanded=not st.session_state.get("generated", False)):
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
            keep_keys = {"db_conn", "lang", "analysis_mode", "current_document_id", "current_project_id"}
            for key in list(st.session_state.keys()):
                if key not in keep_keys:
                    del st.session_state[key]

            document_id = requested_document_id
            if document_id is None:
                st.error(t("没有找到要加载的历史分析，请回到项目工作区重新选择。"))
                st.stop()
            try:
                loaded = persistence.load_analysis(_get_db_conn(), document_id)
            except Exception as exc:  # noqa: BLE001
                st.error(t("加载历史分析失败：{error}", error=exc))
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
        st.info(t("已从历史记录加载：{title}（{total} 人）", title=st.session_state.get('document_title', ''), total=len(df_all)))
    else:
        # 真实反馈的严重 bug："新建问卷分析"默认填的标题是上一份问卷的标题，点保存
        # 直接把上一份问卷覆盖掉了。根源和"load_existing"分支上面注释里说的是同一类
        # 问题：project_view.py 点"+ 新建问卷分析"时原来只手动清了 mapping/generated/
        # conclusions/test_method 这几个"记得住"的 key，document_title/saved_document_id
        # 不在这份清单里，上一份分析残留的这两个值会原样带进这次"新建"——下面第 2820/2838
        # 行两处判断都是"session_state 里已经有这个 key 就不当新的处理"，一旦
        # document_title/saved_document_id 是上一份的残留值，标题输入框显示的就是
        # 上一份的标题，保存逻辑也会误判成"这份文档已经存过一次了"走 update_analysis
        # 覆盖更新，而不是 save_analysis 新建一条。
        #
        # 用 st.session_state.pop("analysis_mode", None) 判断是不是"新建"这个一次性
        # 开关——第一次从项目工作区点"+新建问卷分析"跳转过来时它是 "new"，pop 出来
        # 是 "new" 就顺手把这个 key 也删掉，同一次"新建分析"过程中用户上传文件/填
        # 映射表触发的后续 rerun，这个 key 已经不在了，不会重复触发下面的清空（不然
        # 每次 rerun 都会把用户刚填的映射表/标题清空，没法正常操作）。清空策略跟
        # load_existing 分支一样，用白名单而不是列举"要清哪些"——不然又会重演这次
        # 同样的漏列问题。
        if st.session_state.pop("analysis_mode", None) == "new":
            keep_keys = {"db_conn", "lang", "current_document_id", "current_project_id"}
            for key in list(st.session_state.keys()):
                if key not in keep_keys:
                    del st.session_state[key]

        uploaded = st.file_uploader(t("上传问卷原始数据（CSV / xlsx）"), type=["csv", "xlsx"])

        if uploaded is None:
            st.info(t("上传一个文件开始。没有现成数据的话，随便导出一份 Qualtrics/问卷星/Google Forms 的 CSV 都行。"))
            st.stop()

        upload_dir = PROJECT_ROOT / "data" / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        save_path = upload_dir / uploaded.name
        save_path.write_bytes(uploaded.getvalue())

        try:
            raw_df = ingest.load_file(str(save_path))
        except Exception as exc:  # noqa: BLE001 - 展示给用户看，不静默
            st.error(t("解析失败：{error}", error=exc))
            st.stop()

        # 有些问卷平台（见数等）导出的 CSV 有两行表头：第一行是完整题目文本（已经被当列名用了），
        # 第二行是内部字段代码（"作答ID""Q1""Q5_1"这种）——不剔除的话会被当成第一个人的真实答案，
        # 表现出来就是某道题的分布里冒出一个奇怪的、n=1 的选项，值正好是字段代码或者一段 <img> 标签。
        raw_df, dropped_metadata_row = clean.drop_leading_metadata_row(raw_df)
        if dropped_metadata_row:
            st.info(t("检测到并自动剔除了第一行——它看起来是问卷平台的字段代码行，不是真实作答（比如「作答ID」「Q1」这种），不算进统计。"))

        st.success(t("读取成功：{rows} 行 × {columns} 列", rows=len(raw_df), columns=len(raw_df.columns)))
        with st.expander(t("预览原始数据（前 5 行）"), expanded=False):
            st.dataframe(raw_df.head())

        # ---------------------------------------------------------------------------
        # 2. 去重
        # ---------------------------------------------------------------------------

        id_col = st.selectbox(
            t("哪一列是受访者 ID？（用于去重，选'不去重'跳过）"),
            ["（不去重）"] + list(raw_df.columns),
            format_func=lambda value: t(value) if value == "（不去重）" else value,
        )
        df_all = raw_df
        if id_col != "（不去重）":
            before = len(df_all)
            df_all = clean.dedupe(df_all, id_col)
            dropped = before - len(df_all)
            if dropped:
                st.warning(t("去重剔除了 {count} 行重复 {column}。", count=dropped, column=id_col))

    # ---------------------------------------------------------------------------
    # 3. 数据映射：题型 + 分类（筛选/正式/基础信息）+ 分组键
    # ---------------------------------------------------------------------------

    st.subheader(t("数据映射"), anchor="mapping-table")
    st.caption(
        t("题型决定怎么统计和画图；「分类」决定这题算 3.筛选、4.正式问卷还是 5.基础信息——"
        "显示的题号（S1/Q1/C1…）由分类自动生成，不用手填。「分组键」只在多选题里有用："
        "同一分类下分组键相同的几列会被合并成一道多选题。")
    )
    st.caption(
        t("点了「生成分析」之后这张表还是可以改的，不用重新上传文件——比如自动识别的多选题"
        "分组不对、某道题类型判断错了，直接在下面这张表里改对应的行，改完页面会立刻按新的"
        "设置重新生成整份报告。侧边栏导航最上面「调整题型／分组」可以随时跳回这里。")
    )

    if "mapping" not in st.session_state or list(st.session_state["mapping"]["column"]) != list(df_all.columns):
        # 自动识别多选题拆分列（不管是见数"题干-选项"还是 Tally"题干 (选项)"这两种命名规律，
        # 只要取值以布尔值为主就认），同一组的列默认打成 multi + 同一个分组键；Tally 那种额外
        # 带的"选项逗号拼接"汇总列默认忽略，不然会被当成一道假开放题重复分析。
        multi_groups, multi_summary_columns = clean.detect_multi_select_groups(df_all)
        column_to_group: dict[str, tuple[str, str, str]] = {}  # column -> (分组键, 题干, 题型)
        for group_index, (prefix, option_columns) in enumerate(multi_groups.items(), start=1):
            group_key = f"auto_multi_{group_index}"
            for col in option_columns:
                column_to_group[col] = (group_key, prefix, "multi")

        ranking_groups = clean.detect_ranking_groups(df_all)
        ranking_groups = {
            prefix: option_columns
            for prefix, option_columns in ranking_groups.items()
            if not any(col in column_to_group or col in multi_summary_columns for col in option_columns)
        }
        for group_index, (prefix, option_columns) in enumerate(ranking_groups.items(), start=1):
            group_key = f"auto_rank_{group_index}"
            for col in option_columns:
                column_to_group[col] = (group_key, prefix, "ranking")

        default_rows = []
        for i, col in enumerate(df_all.columns):
            if col in multi_summary_columns:
                default_rows.append(
                    {"column": col, "q_type": "忽略", "section": "正式", "q_no": f"g{i + 1}", "title": col}
                )
                continue
            if col in column_to_group:
                group_key, prefix, group_type = column_to_group[col]
                default_rows.append(
                    {"column": col, "q_type": group_type, "section": "正式", "q_no": group_key, "title": prefix}
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
        st.session_state["mapping_auto"] = st.session_state["mapping"].copy(deep=True)
        st.session_state.pop("mapping_memory_report", None)
        previous_mapping = mapping_memory.latest_project_mapping(
            _get_db_conn(), st.session_state.get("current_project_id"),
            st.session_state.get("current_document_id"),
        )
        if previous_mapping is not None:
            remembered_mapping, report = mapping_memory.apply_template(
                st.session_state["mapping"], previous_mapping["rows"]
            )
            if report["matched_count"]:
                st.session_state["mapping"] = remembered_mapping
                st.session_state["mapping_memory_report"] = {**report, "name": previous_mapping["name"]}
                st.session_state.pop("mapping_editor", None)
        st.session_state["generated"] = False
        if multi_groups:
            st.info(
                t("自动识别出 {count} 道多选题（按选项列名规律+布尔取值判断），已经在下面的映射表里合并成 multi 类型，不用手动一个个改分组键了；不对的话可以在表格里直接调整。", count=len(multi_groups))
            )
        if ranking_groups:
            st.info(
                t("自动识别出 {count} 道排序题（按选项列名规律+名次取值判断），已经在下面的映射表里合并成 ranking 类型，不用手动一个个改分组键了；不对的话可以在表格里直接调整。", count=len(ranking_groups))
            )

    with st.expander(t("映射记忆"), expanded=False):
        saved_templates = mapping_memory.list_templates(_get_db_conn())
        if saved_templates:
            templates_by_id = {item["id"]: item for item in saved_templates}
            selected_template_id = st.selectbox(
                t("已存模板"), list(templates_by_id), key="mapping_template_selection",
                format_func=lambda template_id: f"{templates_by_id[template_id]['name']} (#{template_id})",
            )
            if st.button(t("套用模板"), key="mapping_template_apply"):
                template_rows = mapping_memory.load_template(_get_db_conn(), selected_template_id)
                if template_rows is not None:
                    st.session_state.setdefault("mapping_auto", st.session_state["mapping"].copy(deep=True))
                    st.session_state["mapping"], report = mapping_memory.apply_template(
                        st.session_state["mapping"], template_rows
                    )
                    st.session_state["mapping_memory_report"] = {
                        **report, "name": templates_by_id[selected_template_id]["name"],
                    }
                    st.session_state.pop("mapping_editor", None)
            if st.button(t("删除模板"), key="mapping_template_delete"):
                mapping_memory.delete_template(_get_db_conn(), selected_template_id)
                st.rerun()
        template_name = st.text_input(t("模板名称"), key="mapping_template_name")
        if st.button(t("把当前映射存为模板"), key="mapping_template_save", disabled=not template_name.strip()):
            mapping_memory.save_template(
                _get_db_conn(), template_name, st.session_state["mapping"].to_dict("records")
            )
            st.rerun()

    memory_report = st.session_state.get("mapping_memory_report")
    if memory_report:
        if st.button(t("撤销套用（恢复自动识别）"), key="mapping_template_undo"):
            st.session_state["mapping"] = st.session_state["mapping_auto"].copy(deep=True)
            st.session_state.pop("mapping_memory_report", None)
            st.session_state.pop("mapping_editor", None)
        else:
            st.info(t(
                "已按『{name}』套用 {matched}/{total} 列的映射，其余列为自动识别，可在下方修改",
                name=memory_report["name"], matched=memory_report["matched_count"], total=memory_report["total_count"],
            ))

    mapping = st.data_editor(
        st.session_state["mapping"],
        column_config={
            "column": st.column_config.TextColumn(t("原始列名"), disabled=True),
            "q_type": st.column_config.SelectboxColumn(
                t("题型"), options=["single", "multi", "ranking", "open", "numeric", "忽略"],
                format_func=lambda value: t(value) if value == "忽略" else value,
            ),
            "section": st.column_config.SelectboxColumn(t("分类"), options=ALL_SECTIONS),
            "q_no": st.column_config.TextColumn(t("分组键（多选题共享同一个值才会合并）")),
            "title": st.column_config.TextColumn(t("题目文本（英文原题，或已经是中文就直接填中文）")),
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
        st.subheader(t("筛选设置"))
        st.caption(t("选中的值 = 未通过筛选（screen out）；不选就当这道题不参与过滤，只在「3. 筛选问题」里展示分布。"))
        for _, row in screen_rows.iterrows():
            col = row["column"]
            unique_values = sorted(df_all[col].dropna().unique().tolist(), key=str)
            screen_fail_values[col] = st.multiselect(
                t("「{title}」——哪些取值算未通过？", title=row['title']), unique_values, key=f"screenfail_{col}"
            )

    other_screen_rows = mapping[(mapping["section"] == "筛选") & (mapping["q_type"] != "single")]
    if not other_screen_rows.empty:
        st.info(
            t("以下筛选题不是单选题，本 demo 暂不支持据此过滤样本，只会在「3. 筛选问题」里展示，不影响「4. 正式问卷」「5. 基础信息探测」的有效样本：")
            + t("、").join(other_screen_rows["title"].tolist())
        )

    if st.button(t("生成分析"), type="primary"):
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
    st.sidebar.markdown(f"[{t(label)}](#{anchor})")

# 有效样本：任一筛选题命中"未通过"取值，就整体剔除
df_valid = clean.filter_valid_samples(df_all, screen_fail_values)

if screen_fail_values and any(screen_fail_values.values()):
    st.info(t("筛选后：全量 {total} 人 → 有效样本 {valid} 人（剔除 {excluded} 人）。", total=len(df_all), valid=len(df_valid), excluded=len(df_all) - len(df_valid)))

has_screening = bool(screen_fail_values) and any(screen_fail_values.values())

# ---------------------------------------------------------------------------
# 5. ① 结论 + ② 测试方法——渲染顺序在③④⑤之前，对应整体页面框架的 1、2 两部分。
#    这两部分都是手填/自动统计，不需要 engine 的统计引擎，先用 session_state 存，
#    还没接 engine/db.py 的 conclusions/test_method 表——那张表已经在 Milestone 3a
#    建好了，等这个 demo 真的要"保存项目"的时候再接，现在每次刷新还是会清空。
# ---------------------------------------------------------------------------

with st.container(key="section_paper_1"):
    st.header(t("1. 结论"), anchor="sec1")
    st.caption(t("一句话最重要的结论，默认 1 条，带数字；可以再加。"))

    if "conclusions" not in st.session_state:
        st.session_state["conclusions"] = [""]

    for i in range(len(st.session_state["conclusions"])):
        col_num, col_text, col_del = st.columns([0.6, 9.4, 1])
        col_num.markdown(f"**{i + 1}.**")
        st.session_state["conclusions"][i] = col_text.text_input(
            t("结论 {number}", number=i + 1),
            value=st.session_state["conclusions"][i],
            key=f"conclusion_input_{i}",
            placeholder=t("例：179人中，选择最多的是「新西兰羊毛精工打造」，86人（48.0%）。"),
            label_visibility="collapsed",
        )
        if col_del.button(t("删除"), key=f"conclusion_del_{i}") and len(st.session_state["conclusions"]) > 1:
            st.session_state["conclusions"].pop(i)
            st.rerun()

    if st.button(t("+ 新增一条结论"), key="conclusion_add"):
        st.session_state["conclusions"].append("")
        st.rerun()

with st.container(key="section_paper_2"):
    st.header(t("2. 测试方法"), anchor="sec2")

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
        t("(a) 测试平台与样本来源（根据列名猜的，不准就自己改）"),
        value=tm["platform_source"],
        key="tm_platform_source",
        placeholder=t("如 Prolific + Tally / PickFu / Credamo 见数"),
    )
    tm["is_branched"] = st.checkbox(t("(b) 是否有分流设计"), value=tm["is_branched"], key="tm_is_branched")
    if tm["is_branched"]:
        tm["branch_count"] = st.number_input(
            t("分几份问卷"), min_value=1, step=1, value=tm["branch_count"] or 1, key="tm_branch_count"
        )
        st.caption(
            t("这版 demo 一次只处理一份上传文件，没法从单个 CSV 自动判断是不是分流问卷，"
            "这项只能你自己勾；分几份问卷各自的样本量需要分开上传后自己核对——"
            "跨文件合并统计留给正式版（`engine/db.py` 已经有 `documents.branch_label` 字段接这个）。")
        )
    else:
        tm["branch_count"] = None

    sample_line = t("**(c) 样本量**：全量 {total} 人", total=len(df_all))
    if has_screening:
        sample_line += t("，有效样本 {valid} 人", valid=len(df_valid))
    sample_line += t("（自动统计，不用手填）")
    st.markdown(sample_line)

    # (d) 筛选逻辑：不是一个可编辑输入框——直接从"筛选设置"步骤里你已经勾选的内容拼出来，
    # 全自动、不能手改（改的地方应该回"筛选设置"改，不是这里，两处不一致会更乱）。
    screen_rule_parts = []
    screen_rule_display_parts = []
    for col, fail_values in screen_fail_values.items():
        if fail_values:
            col_title = mapping.loc[mapping["column"] == col, "title"].iloc[0]
            screen_rule_parts.append(f"「{col_title}」选中 {fail_values} 视为未通过")
            screen_rule_display_parts.append(t("「{title}」选中 {values} 视为未通过", title=col_title, values=fail_values))
    tm["screen_out_rule"] = "；".join(screen_rule_parts) if screen_rule_parts else "无"
    st.markdown(t("**(d) 筛选逻辑**：{rule}（根据上面「筛选设置」自动生成，不用手填）", rule=t("；").join(screen_rule_display_parts) if screen_rule_display_parts else t("无")))

    # (e) 跳转逻辑没法从导出的平铺 CSV 里可靠推断（跳转是问卷设计时的分支规则，答题数据本身
    # 看不出"是因为跳转没看到题"还是"看到了但没填"），这项保留手填。
    tm["skip_logic_note"] = st.text_area(
        t("(e) 跳转逻辑（没法从数据自动判断，需要你回忆问卷设计手填）"),
        value=tm["skip_logic_note"],
        key="tm_skip_logic_note",
        placeholder=t("没有就填「无」"),
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
        st.header(t(SECTION_HEADER[section]), anchor=SECTION_ANCHOR[section])
        if section == "筛选":
            st.caption(t("筛选题看的是筛选前的全量样本，不是有效样本——这道题本来就是拿来筛人的。"))

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
    st.header(t("6. 完整数据表格"), anchor="sec6")
    st.caption(t("只展示通过筛选的有效样本；点一行，下面「7. 受访者个人视角」会展开这个人的完整作答。"))

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
        images_align: dict = {}
        label_overrides: dict = {}
        image_units = [{"display_no": f"crosstab_block_{b['id']}"} for b in st.session_state.get("crosstab_blocks", [])]
        for u in units + image_units:
            q_no = u["display_no"]
            ai_result_map = _collect_ai_results_for(q_no)
            if ai_result_map:
                ai_results[q_no] = ai_result_map
            imgs = st.session_state.get(f"images_{q_no}")
            if imgs:
                images[q_no] = _images_payload(imgs)
            per_row = st.session_state.get(f"images_per_row_{q_no}")
            if per_row is not None:
                images_per_row[q_no] = per_row
            align = st.session_state.get(f"images_align_{q_no}")
            if align is not None:
                images_align[q_no] = align
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
            "images_align": images_align,
            "label_overrides": label_overrides,
            "crosstab_blocks": _crosstab_blocks_payload(),
            "crosstab_state": _crosstab_state_payload(),
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
        align_fp = tuple(
            sorted(
                (u["display_no"], st.session_state[f"images_align_{u['display_no']}"])
                for u in units
                if st.session_state.get(f"images_align_{u['display_no']}") is not None
            )
        )
        label_override_fp = tuple(
            sorted(
                (u["display_no"], json.dumps(st.session_state[f"label_overrides_{u['display_no']}"], sort_keys=True, ensure_ascii=False))
                for u in units
                if st.session_state.get(f"label_overrides_{u['display_no']}")
            )
        )
        return (ai_fp, image_fp, per_row_fp, align_fp, label_override_fp)


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
            t("问卷标题"),
            value=st.session_state["document_title"],
            key="document_title_input",
            label_visibility="collapsed",
        )
        # 元信息条——客户翻开报告第一眼要确认的东西（样本量/来源/最近更新），之前完全没地方
        # 展示。放在标题正下方，跟标题共用同一个视觉分组；保存时间用真实墙钟时间，不是
        # _last_autosave_at 那个 monotonic 值（那个只用来算"距上次保存过了多久"，不能拿来显示）。
        saved_at = st.session_state.get("_last_saved_wallclock")
        saved_label = t("更新于 {time:%H:%M:%S}", time=saved_at) if saved_at else t("尚未保存")
        st.caption(t("N = {total}　·　{source}　·　{saved}", total=len(df_all), source=tm.get("platform_source") or t("未识别来源"), saved=saved_label))


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
            st.toast(t("已保存到数据库（document_id={document_id}）", document_id=document_id))
        except Exception as exc:  # noqa: BLE001 —— 保存失败不能挡住页面正常显示分析结果
            st.warning(t("保存失败，不影响当前页面查看：{error}", error=exc))
    else:
        document_id = st.session_state["saved_document_id"]
        project_id = st.session_state.get("current_project_id")

        with top_save_col:
            manual_save_clicked = st.button(t("保存"), key="manual_save_button", type="primary")

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
                st.toast(t("已手动保存（{time:%H:%M:%S}），并清掉了这份问卷的自动保存草稿。", time=datetime.now()))
            except Exception as exc:  # noqa: BLE001
                st.toast(t("手动保存失败：{error}", error=exc))
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
                    st.toast(t("已自动保存草稿（{time:%H:%M:%S}）——不会覆盖手动保存，点「保存」才会写入正式数据。", time=datetime.now()))
                except Exception as exc:  # noqa: BLE001
                    st.toast(t("自动保存草稿失败：{error}", error=exc))

    show_platform = False
    if raw_table_units["平台信息"]:
        show_platform = st.checkbox(t("显示平台信息列（10. 受访者信息，默认隐藏）"), value=False, key="show_platform_cols")

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
            {"headerName": t(SECTION_HEADER[section]), "headerClass": SECTION_HEADER_CLASS[section], "children": children}
        )

    use_set_filter = st.checkbox(
        t("按具体取值筛选（勾选框选答案，需要 ag-Grid 企业版 Set Filter，没有授权会在表格上出现"
        "「For Trial Use Only」水印——内部用可以接受就勾；不勾的话用免费版的文本筛选，"
        "点表头筛选图标、输入关键字也能缩小范围，只是不是勾选框）"),
        value=False,
        key="raw_grid_use_set_filter",
    )
    filter_type = "agSetColumnFilter" if use_set_filter else "agTextColumnFilter"

    gb = GridOptionsBuilder.from_dataframe(table_df)
    gb.configure_selection(selection_mode="single")
    gb.configure_default_column(filter=filter_type, floatingFilter=True, sortable=True, resizable=True)
    grid_options = gb.build()
    grid_options["columnDefs"] = [{"field": "受访者ID", "headerName": t("受访者ID"), "pinned": "left", "filter": filter_type}] + column_groups

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
    st.header(t("7. 受访者个人视角"), anchor="sec7")

    selected = grid_response.selected_rows
    has_selection = selected is not None and (
        (hasattr(selected, "empty") and not selected.empty) or (isinstance(selected, list) and len(selected) > 0)
    )

    if not has_selection:
        st.info(t("在上面表格里点一行，这里会展开这个人的完整作答。"))
    else:
        row = selected.iloc[0] if hasattr(selected, "iloc") else selected[0]
        respondent_id = row["受访者ID"]
        st.markdown(t("**受访者：{respondent_id}**", respondent_id=respondent_id))

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
                parts.append(t("{label}：{value}", label=u["title"], value=value if pd.notna(value) else "—"))
            st.caption("　".join(parts))

        # ⑦ 剩下的部分顺序是"筛选→基础信息→正式"，跟整体页面顺序（③④⑤=筛选→正式→基础信息）不一样——
        # 这是设计文档 v0.5 第 4 节原话定的，不是笔误。
        for section in ["筛选", "基础信息", "正式"]:
            sec_units = raw_table_units[section]
            if not sec_units:
                continue
            st.subheader(t(SECTION_HEADER[section]))
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
                st.write(value if pd.notna(value) and value != "" else t("（未作答/未看到这题）"))
                st.write("")

# ---------------------------------------------------------------------------
# 8. ⑧ 交叉分析——每个板块一套左右对称配置，生成后立即保存。
# ---------------------------------------------------------------------------

with st.container(key="section_paper_8"):
    st.header(t("8. 交叉分析"), anchor="sec8")
    st.caption(t("每个板块左右两栏分别选问卷、题目、维度，下方生成对比；同一份文档可以建好几个独立的交叉分析板块。"))
    st.session_state.setdefault("crosstab_blocks", [{"id": "1", "left": {"doc_id": None, "question_key": None}, "right": {"doc_id": None, "question_key": None}, "result": None}])
    st.session_state.setdefault("crosstab_next_block_id", 2)
    # 每次从现存板块重建导出历史，删除板块/更换题目重算后不残留旧结果。
    st.session_state["crosstab_history"] = {}
    delete_block_id = None
    for position, block in enumerate(st.session_state["crosstab_blocks"]):
        block_id = block["id"]
        with st.container(border=True, key=f"crosstab_block_{block_id}"):
            title_col, del_col = st.columns([6, 1])
            title_col.markdown(f"**{t('交叉分析板块 {n}', n=position + 1)}**")
            if del_col.button(t("删除这个板块"), key=f"xtb_{block_id}_delete_block"):
                delete_block_id = block_id
            left_col, right_col = st.columns(2)
            with left_col:
                left_ctx = render_crosstab_side(block_id, "left", block["left"], units, df_valid)
            with right_col:
                right_ctx = render_crosstab_side(block_id, "right", block["right"], units, df_valid)
            can_generate = left_ctx is not None and right_ctx is not None
            if st.button(t("生成交叉分析"), key=f"xtb_{block_id}_run", type="primary", disabled=not can_generate):
                block["result"] = _compute_crosstab_block_result(left_ctx, right_ctx)
                _persist_crosstab_blocks()
            result = block.get("result")
            if result is not None:
                st.markdown(f"**{result['title']}**")
                table = result["table"]
                st.dataframe(table.rename_axis(index=t("对比题答案"), columns=t("分组")) if result["kind"] == "same_doc" else table)
                if result["chart_config"] is not None:
                    config = result["chart_config"]
                    _, dl_col, cp_col = st.columns([8, 1, 1])
                    png = _grouped_bar_snapshot_png_for_save(f"xtb_{block_id}", config["yAxis"]["data"], config["series"], result["title"])
                    with dl_col:
                        st.download_button("", data=png, file_name=f"crosstab_{block_id}.png", mime="image/png",
                                           icon=":material/download:", key=f"xtb_{block_id}_download", help=t("下载这张图表"))
                    with cp_col:
                        _render_copy_image_button(png, key=f"xtb_{block_id}_copy")
                    # render_chart 会改标题并 pop footer，传副本，不能改掉已经保存的结果。
                    render_chart("bar_h", json.loads(json.dumps(config)), key=f"xtb_{block_id}_chart")
                st.session_state["crosstab_history"][result["title"]] = table
                q_no_for_images = f"crosstab_block_{block_id}"
                render_image_attachments_trigger(q_no_for_images)
                render_image_attachments_grid(q_no_for_images)
    if delete_block_id is not None:
        st.session_state["crosstab_blocks"] = [b for b in st.session_state["crosstab_blocks"] if b["id"] != delete_block_id]
        _persist_crosstab_blocks()
        st.rerun()
    if st.button(t("+ 新增交叉分析板块"), key="xtb_add_block"):
        new_id = str(st.session_state["crosstab_next_block_id"])
        st.session_state["crosstab_next_block_id"] += 1
        st.session_state["crosstab_blocks"].append({"id": new_id, "left": {"doc_id": None, "question_key": None}, "right": {"doc_id": None, "question_key": None}, "result": None})
        _persist_crosstab_blocks()
        st.rerun()

# ---------------------------------------------------------------------------
# 9. ⑨ AI 洞察——不自动展示，点按钮才生成；每条洞察引用的数字都要先在 Python 算好的
#    统计里核对过，核对不上的整条丢弃（engine/ai_insight.py 里做的）。
# ---------------------------------------------------------------------------

with st.container(key="section_paper_9"):
    st.header(t("9. AI 洞察"), anchor="sec9")
    st.caption(t("不自动生成。点下面按钮才会调用 AI；引用了编造数字的洞察会被整条丢弃，不会显示出来。"))

    if st.button(t("生成 AI 洞察"), key="run_insight"):
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
                with st.spinner(t("生成中…")):
                    insights = ai_insight.generate_insights(provider, bundle)
            except Exception as exc:  # noqa: BLE001
                st.error(t("AI 调用失败：{error}", error=exc))
            else:
                st.session_state["ai_insights"] = insights

    if "ai_insights" in st.session_state:
        if not st.session_state["ai_insights"]:
            st.info(t("这次没有生成出数字能对上的洞察（可能是模型输出没通过校验），可以重新点一次试试。"))
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
    st.header(t("10. 受访者信息"), anchor="sec10")

    platform_units_all = raw_table_units.get("平台信息", [])
    if not platform_units_all:
        st.info(t("没有列被标成「平台信息」——如果你的数据里有 ID/提交时间这类平台自动收录的字段，去上面「数据映射」表里把对应行的「分类」改成「平台信息」。"))
    else:
        platform_table = pd.DataFrame({"受访者ID": id_series.values}, index=df_valid.index)
        for u in platform_units_all:
            platform_table[f"{u['display_no']}｜{u['title']}"] = df_valid[u["columns"][0]].values
        st.caption(t("如实展示，不聚合、不加工。"))
        st.dataframe(platform_table, column_config={"受访者ID": t("受访者ID")}, use_container_width=True)

# ---------------------------------------------------------------------------
# 11. ⑪ 导出——把①②④⑤（正式问卷+基础信息，筛选题不导出，跟 export_word 模块的
#    既定规则一致）+⑨AI洞察 导出成一份 Word 文档。范围说明：
#    - 开放题的"中文翻译"是导出这一步现场调用 AI 逐条翻译的（按需触发，不是页面浏览时就
#      翻译好的——那是另一件事，是题目标题/选项的翻译，不是受访者原始作答的翻译）。
#    - ⑧交叉分析的结果这版不接入导出——交叉分析是你手动配置、点一次生成一次，没有存成
#      一个"要导出哪些交叉表"的列表，这个留给后面做。
# ---------------------------------------------------------------------------

with st.container(key="section_paper_11"):
    st.header(t("11. 导出"), anchor="sec11")
    st.caption(t("导出 1/2/4/5 + 9（筛选题、6/7/8/10 不导出——那些是网页交互功能，静态 Word 文档没有对应的东西）。"))

    if st.button(t("生成报告（Word / PDF / Markdown）"), type="primary", key="export_word_button"):
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
            elif kind == "ranking":
                max_rank = len(unit["columns"])
                option_labels_raw = clean.option_labels_for_group(unit["columns"])
                label_map, title_zh, _ = _compute_label_map(unit["title"], list(option_labels_raw.values()))
                option_labels_display = {c: label_map.get(v, v) for c, v in option_labels_raw.items()}
                stats_by_unit[display_no] = {
                    "table": stats.ranking_table(df_valid, unit["columns"], option_labels_display, max_rank),
                }
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
                        with st.spinner(t("翻译 {question} 的开放题原文中…", question=display_no)):
                            results = ai_translate.translate_verbatims(export_provider, items, protected_terms=[])
                        translations = {r["response_id"]: r["translation"] for r in results}
                    except Exception as exc:  # noqa: BLE001
                        st.warning(t("{question} 的开放题翻译失败（{error}），Word 里这道题的中文翻译列会留空。", question=display_no, error=exc))

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
                            t("{label}：{value}", label=label, value=cs.iloc[pos])
                            for label, cs in context_series_list
                            if pd.notna(cs.iloc[pos]) and cs.iloc[pos] != ""
                        ]
                        context_labels.append(t("；").join(parts) or None)
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

        project_name = "问卷分析"  # 文件名仍使用原始缺省值
        project_display_name = t("问卷分析")
        project_id = st.session_state.get("current_project_id")
        if project_id is not None:
            row = _get_db_conn().execute("SELECT name FROM projects WHERE id = ?", (project_id,)).fetchone()
            if row:
                project_name = row["name"]
                project_display_name = project_name

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
                project_name=project_display_name,
                conclusions=[c for c in st.session_state.get("conclusions", []) if c],
                test_method={
                    **tm,
                    "screen_out_rule": t("；").join(screen_rule_display_parts) if screen_rule_display_parts else t("无"),
                },
                units=export_units,
                stats_by_unit=stats_by_unit,
                n_by_unit=n_by_unit,
                ai_insights=st.session_state.get("ai_insights"),
                crosstabs=crosstabs,
                color_palette=_active_chart_palette(),
            )
        except Exception as exc:  # noqa: BLE001
            st.error(t("导出失败：{error}", error=exc))
        else:
            st.success(t("已生成：{filename}", filename=export_filename))
            pdf_path = markdown_path = None
            try:
                pdf_path = Path(export_pdf.convert_docx_to_pdf(str(export_path), str(export_dir)))
                pdf_data = pdf_path.read_bytes()
            except Exception as exc:  # noqa: BLE001
                pdf_path = None
                st.caption(t("未生成 PDF：{error}", error=exc))
            try:
                markdown_path = Path(export_markdown.convert_docx_to_markdown(str(export_path), str(export_dir)))
                markdown_data = markdown_path.read_bytes()
            except Exception as exc:  # noqa: BLE001
                markdown_path = None
                st.caption(t("未生成 Markdown：{error}", error=exc))

            word_col, pdf_col, markdown_col = st.columns(3)
            with word_col:
                st.download_button(
                    t("下载 Word 文件"),
                    export_path.read_bytes(),
                    file_name=export_filename,
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    on_click="ignore",
                )
            if pdf_path is not None:
                with pdf_col:
                    st.download_button(
                        t("下载 PDF 文件"), pdf_data,
                        file_name=pdf_path.name, mime="application/pdf", on_click="ignore",
                    )
            if markdown_path is not None:
                with markdown_col:
                    st.download_button(
                        t("下载 Markdown 文件（含图片，zip）"), markdown_data,
                        file_name=markdown_path.name, mime="application/zip", on_click="ignore",
                    )
