"""Minimal UI internationalisation: Chinese source strings are the lookup keys.

用法：`from engine.i18n import t`，把界面上显示给人看的中文原文包一层 `t("中文原文")`；
带变量的写成 `t("共 {n} 人", n=count)`（不要用 f-string——f-string 在调用 t() 之前就已经
把变量拼进去了，查不到翻译）。当前语言是"线程本地"的：Streamlit 每个浏览器会话的脚本
在自己的线程里跑，每次重跑最开头由 `app_streamlit/lang_ui.py` 按该会话选的语言调一次
`set_lang()`，所以引擎层（图表、Word 导出）不用到处传 lang 参数也能拿到正确语言，
也不会在多个会话之间串语言。

英文翻译表在 `engine/i18n_catalog.py`（`EN` 字典）；查不到的中文原文原样返回（不会
崩，但界面上会漏出一句中文——`tests/test_i18n.py` 会扫描所有 `t()` 调用，保证没有漏翻）。
"""

from __future__ import annotations

import threading

DEFAULT_LANG = "en"
SUPPORTED_LANGS = ("en", "zh")

_local = threading.local()


def set_lang(lang: str) -> None:
    _local.lang = lang if lang in SUPPORTED_LANGS else DEFAULT_LANG


def get_lang() -> str:
    return getattr(_local, "lang", DEFAULT_LANG)


def t(text: str, **fmt) -> str:
    """Translate a Chinese source string into the current language."""

    if get_lang() == "zh":
        out = text
    else:
        from .i18n_catalog import EN

        out = EN.get(text, text)
    return out.format(**fmt) if fmt else out
