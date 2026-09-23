"""Exercise image helpers and real Streamlit widgets without opening the full app or app.db."""

import ast
import base64
import hashlib
import html as html_lib
import io
import json
import mimetypes
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
from PIL import Image as PILImage
from streamlit.testing.v1 import AppTest


APP_PATH = Path(__file__).resolve().parents[1] / "app_streamlit" / "app.py"
APP_SOURCE = APP_PATH.read_text()
FUNCTIONS = {
    node.name: ast.get_source_segment(APP_SOURCE, node)
    for node in ast.walk(ast.parse(APP_SOURCE))
    if isinstance(node, ast.FunctionDef)
}
HELPERS = [
    "_image_mime", "_images_payload", "_persist_images", "_render_zoomable_image",
    "_image_aspect_ratio", "_render_tiles_row", "_collect_image_library",
    "_restore_extras", "_collect_ai_results_for", "_extras_payload",
    "_crosstab_blocks_payload", "_crosstab_state_payload",
    "_extras_fingerprint", "render_image_attachments_trigger",
]
# 模块级常量不是函数，AST 只扫了 FunctionDef，得单独从源码里挖出来注入命名空间——
# 硬编码在测试里会跟 app.py 改了数值却忘了同步这两处的坑一样，不如直接从源码执行。
# IMAGE_ROW_BASE_HEIGHT_PX 现在是从 CHART_HEIGHT["pie"] 算出来的表达式（不是字面量），
# 所以这几行按源码里出现的顺序原样 exec 一遍，而不是只挖字面量——CHART_HEIGHT 得先
# 存在，IMAGE_ROW_BASE_HEIGHT_PX 才能算对。
_CONSTANTS = {"CHART_HEIGHT", "IMAGE_ROW_BASE_HEIGHT_PX", "IMAGE_ROW_BASE_GAP_PX", "ROW_WIDTH_ASSUMPTION_PX"}
_constant_nodes = sorted(
    (
        node
        for node in ast.walk(ast.parse(APP_SOURCE))
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in _CONSTANTS
    ),
    key=lambda node: node.lineno,
)
CONSTANT_VALUES: dict = {}
exec("\n".join(ast.get_source_segment(APP_SOURCE, node) for node in _constant_nodes), CONSTANT_VALUES)
CONSTANT_VALUES = {k: v for k, v in CONSTANT_VALUES.items() if k in _CONSTANTS}


def _make_png(width: int, height: int) -> bytes:
    """真的 PNG 字节，尺寸精确可控——`_image_aspect_ratio` 现在会用 PIL 真的解码算
    长宽比，随便糊弄的占位字节（比如 b"abc"）会走进它的异常兜底分支，测不出真实的
    等高排版效果。"""

    buf = io.BytesIO()
    PILImage.new("RGB", (width, height), color=(120, 120, 120)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def helpers():
    namespace = {
        "base64": base64, "hashlib": hashlib, "html_lib": html_lib,
        "io": io, "json": json, "mimetypes": mimetypes, "PILImage": PILImage,
        "st": SimpleNamespace(
            session_state={}, markdown=Mock(), image=Mock(),
            columns=Mock(return_value=[MagicMock(), MagicMock()]),
        ),
        "t": lambda text, **kwargs: text.format(**kwargs),
        "persistence": SimpleNamespace(save_images=Mock()), "_get_db_conn": Mock(),
        "units": [{"display_no": "Q1"}],
        **CONSTANT_VALUES,
    }
    exec("\n\n".join(FUNCTIONS[name] for name in HELPERS), namespace)
    return namespace


def test_restore_save_roundtrip_and_caption_fingerprint(helpers):
    """旧数据（改动之前存的）可能还带着每张图各自的 "zoom" 字段——图片不再各自调
    大小了，这里确认恢复时直接忽略这个字段（不报错、也不出现在恢复后的 dict 里），
    指纹改用说明文字变没变来判断"这道题的图片有没有变"。"""

    extras = {"images": {"Q1": [
        {"name": "old.jpg", "bytes_b64": "YWJj"},
        {"name": "no_extension", "bytes_b64": "ZA==", "caption": "Long", "zoom": 125, "mime": "image/webp"},
        {"name": "unknown_extension", "bytes_b64": "ZQ=="},
    ]}}
    helpers["_restore_extras"](extras)
    imgs = helpers["st"].session_state["images_Q1"]
    assert [img["mime"] for img in imgs] == ["image/jpeg", "image/webp", "image/png"]
    assert all("zoom" not in img for img in imgs)
    fingerprint = helpers["_extras_fingerprint"]()
    imgs[0]["caption"] = "Changed"
    assert helpers["_extras_fingerprint"]() != fingerprint
    saved = helpers["_extras_payload"]()
    helpers["_restore_extras"](saved)
    assert helpers["st"].session_state["images_Q1"] == imgs


def test_library_excludes_current_question_and_deduplicates_sources(helpers):
    image = {"bytes": b"abc", "name": "old.jpg", "bytes_hash": hashlib.md5(b"abc").hexdigest()}
    helpers["st"].session_state.update({
        "images_Q3": [dict(image)], "images_Q1": [image],
        "images_Q2": [{"bytes": b"private", "name": "private.png"}],
        "images_per_row_Q1": 3,
    })
    library = helpers["_collect_image_library"]("Q2")
    assert len(library) == 1
    assert library[0]["source_q_no"] == "Q1"
    assert library[0]["mime"] == "image/jpeg"
    assert library[0] is not image


def test_persist_images_skips_unsaved_document_and_encodes_saved_document(helpers):
    helpers["_persist_images"]("Q1")
    helpers["_get_db_conn"].assert_not_called()
    helpers["persistence"].save_images.assert_not_called()
    helpers["st"].session_state.update({
        "saved_document_id": 42,
        "images_Q1": [{"bytes": b"abc", "name": "old.jpg", "caption": "Photo"}],
    })
    helpers["_persist_images"]("Q1")
    helpers["persistence"].save_images.assert_called_once_with(
        helpers["_get_db_conn"].return_value, 42, "Q1",
        [{"name": "old.jpg", "caption": "Photo", "mime": "image/jpeg", "bytes_b64": "YWJj"}],
    )


def test_zoomable_image_below_100_uses_a_proportioned_narrow_column(helpers):
    """两版失败的教训都不能再犯：`<a href="data:...">` 会被浏览器挡成空白页
    （真实反馈复现过），`onclick` 里现拼 JS 又会被 `st.markdown(unsafe_allow_html=True)`
    过滤掉事件属性（真机确认过：渲染出来的 `<img>` 标签里 onclick 整个不见了）。
    现在这版换成 Streamlit 原生 `st.image`（不拼 HTML 字符串），"缩放"靠塞进一个按
    比例分栏的窄栏实现——这条锁住这个实现方式，不被改回前两版任何一种。
    """

    helpers["_render_zoomable_image"](b"abc", 40)
    helpers["st"].markdown.assert_not_called()
    columns_args = helpers["st"].columns.call_args.args[0]
    assert columns_args == [40, 60]
    narrow_col = helpers["st"].columns.return_value[0]
    narrow_col.__enter__.assert_called_once()
    helpers["st"].image.assert_called_once_with(b"abc", use_container_width=True)


def test_zoomable_image_at_100_skips_the_column_split(helpers):
    helpers["_render_zoomable_image"](b"abc", 100)
    helpers["st"].columns.assert_not_called()
    helpers["st"].image.assert_called_once_with(b"abc", use_container_width=True)


def test_zoomable_image_clamps_out_of_range_zoom(helpers):
    helpers["_render_zoomable_image"](b"abc", 999)
    helpers["st"].columns.assert_not_called()  # 999 被夹到 100，走的是不分栏那条路
    helpers["_render_zoomable_image"](b"abc", 1)
    columns_args = helpers["st"].columns.call_args.args[0]
    assert columns_args == [20, 80]  # 1 被夹到下限 20


def test_image_aspect_ratio_reads_real_dimensions_and_falls_back_on_bad_bytes(helpers):
    assert helpers["_image_aspect_ratio"](_make_png(300, 100)) == pytest.approx(3.0)
    assert helpers["_image_aspect_ratio"](_make_png(100, 100)) == pytest.approx(1.0)
    assert helpers["_image_aspect_ratio"](b"not a real image") == 1.0  # 解码失败退回正方形


def test_tiles_row_aligns_by_shared_height_not_width(helpers):
    """核心诉求：图片不再各自调大小了，统一按同一个基准高度对齐，宽度交给浏览器
    自己按原图真实比例撑（用一张 3:1 的横图和一张正方形验证：两张高度相同，但
    <img> 标签里都没有写死宽度）。"""

    base = helpers["IMAGE_ROW_BASE_HEIGHT_PX"]
    # 两张都是正方形（长宽比 1:1）——两张加间距在基准高度下明显放得下
    # （2*307 + 16 = 630 < 940），用来测"放得下就不缩"这条分支；"放不下要缩"
    # 已经在 test_tiles_row_shrinks_uniformly_to_guarantee_per_row_fit_without_cropping
    # 里单独测过。
    helpers["_render_tiles_row"]([
        {"bytes": _make_png(100, 100), "mime": "image/png", "caption": ""},
        {"bytes": _make_png(100, 100), "mime": "image/jpeg", "caption": "Square"},
    ])
    markup = helpers["st"].markdown.call_args.args[0]
    assert "display:flex" in markup
    assert "flex-wrap:nowrap" in markup  # 不允许换行——每行放几张是硬约束
    assert markup.count(f"height:{base}px") == 2  # 两张图都在基准高度（放得下，不用缩）
    assert markup.count("width:auto") == 2  # 高度定死、宽度自动，不是等宽分栏
    assert "Square" in markup  # 说明文字原样出现在 figcaption 里


def test_tiles_row_left_aligned_when_multiple_even_if_align_is_center(helpers):
    """居中/居左只在"这一行只有一张图"时生效——好几张图排一行始终靠左，
    不受 single_image_align 影响（真实反馈明确要求两者分开）。"""

    square = _make_png(100, 100)
    helpers["_render_tiles_row"](
        [{"bytes": square, "mime": "image/png", "caption": ""} for _ in range(2)],
        single_image_align="center",
    )
    assert "justify-content:flex-start" in helpers["st"].markdown.call_args.args[0]


def test_tiles_row_single_image_respects_alignment_choice(helpers):
    square = _make_png(100, 100)
    helpers["_render_tiles_row"]([{"bytes": square, "mime": "image/png", "caption": ""}], single_image_align="center")
    markup = helpers["st"].markdown.call_args.args[0]
    assert "justify-content:center" in markup
    # 真实反馈"居中设置了但完全没居中"——根因是这个 flex 容器没有 width:100%，浏览器
    # 让它按内容宽度收缩，`justify-content:center` 在一个已经跟内容一样宽的容器里
    # 无事可做。这条锁住 width:100% 不会再被漏掉。
    assert "width:100%" in markup

    helpers["_render_tiles_row"]([{"bytes": square, "mime": "image/png", "caption": ""}], single_image_align="left")
    assert "justify-content:flex-start" in helpers["st"].markdown.call_args.args[0]


def test_tiles_row_shrinks_uniformly_to_guarantee_per_row_fit_without_cropping(helpers):
    """核心诉求："每行放几张"要是硬约束，图片放不下的时候整行统一缩小，不能因为
    放不下就少放几张（换行）——这条测试用 4 张很宽的图片（在基准高度下，4 张加起来
    远超一行假定的可用宽度）验证：4 张图片仍然全部出现在同一次 `st.markdown` 调用里
    （没有被拆到下一行/丢弃），高度和间距按同一个比例一起缩小到刚好放得下，没有
    裁切（宽度依然是 `width:auto`，不是固定宽度硬切）。"""

    base_h = helpers["IMAGE_ROW_BASE_HEIGHT_PX"]
    base_gap = helpers["IMAGE_ROW_BASE_GAP_PX"]
    row_width = helpers["ROW_WIDTH_ASSUMPTION_PX"]
    wide = _make_png(300, 100)  # 长宽比 3:1，四张摆一排在基准高度下明显放不下
    helpers["_render_tiles_row"]([
        {"bytes": wide, "mime": "image/png", "caption": ""} for _ in range(4)
    ])
    markup = helpers["st"].markdown.call_args.args[0]
    assert markup.count("<img") == 4  # 四张一张不少，没有因为放不下被拆走
    assert "flex-wrap:nowrap" in markup
    assert "width:auto" in markup and "object-fit" not in markup  # 没有裁切

    wanted_total = base_h * 3 * 4 + base_gap * 3
    scale = row_width / wanted_total
    expected_h = max(24, round(base_h * scale))
    expected_gap = max(4, round(base_gap * scale))
    assert f"height:{expected_h}px" in markup
    assert f"gap:{expected_gap}px" in markup
    assert f"height:{base_h}px" not in markup  # 确认真的缩小了，不是按基准高度硬塞


def test_tiles_row_escapes_caption_and_noop_on_empty(helpers):
    helpers["_render_tiles_row"]([])
    helpers["st"].markdown.assert_not_called()

    helpers["_render_tiles_row"]([
        {"bytes": _make_png(50, 50), "mime": "image/png", "caption": '<script>alert(1)</script>'},
    ])
    markup = helpers["st"].markdown.call_args.args[0]
    assert "<script>alert(1)</script>" not in markup
    assert "&lt;script&gt;" in markup


@pytest.fixture
def image_app():
    script = '''
import base64
import hashlib
import html as html_lib
import json
import mimetypes
import streamlit as st
from types import SimpleNamespace

def t(text, **kwargs):
    return text.format(**kwargs)

def record_save(conn, document_id, q_no, payload):
    st.session_state["writes"].append((q_no, payload))

persistence = SimpleNamespace(save_images=record_save)
def _get_db_conn():
    return None

# 真的 2x2 PNG 字节——`st.image` 是真家伙了（不再是 st.markdown 拼字符串），会用 PIL
# 校验图片能不能解码，随便糊弄的占位字节（比如 b"abc"）现在会直接抛
# `UnidentifiedImageError` 崩掉整个脚本。
_tiny_png = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEklEQVR4nGPkEpFjYGBgYgADAALmAEAUQs4PAAAAAElFTkSuQmCC"
)

st.session_state.setdefault("writes", [])
st.session_state.setdefault("saved_document_id", 1)
st.session_state.setdefault("images_Q1", [
    {"bytes": _tiny_png, "name": "a.png", "caption": "First", "bytes_hash": "a"},
    {"bytes": _tiny_png, "name": "b.jpg", "caption": "Second", "bytes_hash": "b"},
])
st.session_state.setdefault("images_Q2", [
    {"bytes": _tiny_png, "name": "c.jpg", "caption": "Source", "bytes_hash": "c"},
])
'''
    names = [name for name in HELPERS if name not in {
        "_restore_extras", "_collect_ai_results_for", "_extras_payload", "_extras_fingerprint",
    }]
    script += "\n\n".join(FUNCTIONS[name] for name in names)
    script += '\nrender_image_attachments_trigger("Q1")\n'
    app = AppTest.from_string(script).run()
    assert not app.exception
    return app


def test_caption_save_once_and_unrelated_rerun_does_not_write(image_app):
    app = image_app
    assert app.session_state["writes"] == []
    app.text_input(key="img_caption_Q1_0").set_value("Updated").run()
    assert not app.exception
    assert len(app.session_state["writes"]) == 1
    assert app.session_state["writes"][-1][1][0]["caption"] == "Updated"
    app.run()
    assert not app.exception
    assert len(app.session_state["writes"]) == 1  # 无关的 rerun 不会重复落库


@pytest.mark.parametrize("button", ["img_down_Q1_0", "img_up_Q1_1", "img_del_Q1_0"])
def test_move_delete_preserves_each_images_widget_values(image_app, button):
    app = image_app
    app.button(key=button).click().run()
    assert not app.exception
    assert len(app.session_state["writes"]) == 1
    assert app.text_input(key="img_caption_Q1_0").value == "Second"
    assert app.session_state["images_Q1"][0]["name"] == "b.jpg"
    app.run()
    assert len(app.session_state["writes"]) == 1


def test_copy_creates_independent_caption_and_saves(image_app):
    app = image_app
    app.button(key="img_copy_Q1_c").click().run()
    assert not app.exception
    assert len(app.session_state["writes"]) == 1
    copy = app.session_state["images_Q1"][-1]
    source = app.session_state["images_Q2"][0]
    assert copy is not source
    assert copy["caption"] == ""
    assert copy["bytes"] == source["bytes"] and copy["mime"] == "image/jpeg"
    app.text_input(key="img_caption_Q1_2").set_value("Independent").run()
    assert not app.exception
    assert source["caption"] == "Source"  # 复制出来的是独立副本，改说明不会串到原图
