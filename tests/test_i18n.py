"""i18n 完整性检查——独立于翻译时的自检，防止漏翻、占位符对不上、翻译逻辑本身坏掉。"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from engine import i18n
from engine.i18n import get_lang, set_lang, t
from engine.i18n_catalog import EN
from engine.i18n_catalog_app import EN_APP, NOT_TRANSLATED_APP
from engine.i18n_catalog_misc import EN_MISC, NOT_TRANSLATED_MISC

ROOT = Path(__file__).resolve().parent.parent
HAN = re.compile(r"[一-鿿]")
PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")

APP_FILES = ["app_streamlit/app.py", "engine/export_pdf.py", "engine/export_markdown.py"]
MISC_FILES = [
    "app_streamlit/Home.py",
    "app_streamlit/lang_ui.py",
    "app_streamlit/views/home_view.py",
    "app_streamlit/views/project_view.py",
    "engine/export_word.py",
    "engine/stats.py",
    "engine/clean.py",
    "engine/db.py",
    "engine/persistence.py",
    "engine/project_naming.py",
    "engine/llm_provider.py",
    "engine/ai_classify.py",
    "engine/ai_insight.py",
    "engine/ai_translate.py",
]


def _docstring_node_ids(tree: ast.AST) -> set[int]:
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(
                body[0].value.value, str
            ):
                ids.add(id(body[0].value))
    return ids


def _t_first_arg_ids(tree: ast.AST) -> set[int]:
    ids = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "t"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            ids.add(id(node.args[0]))
    return ids


def _scan(path: str):
    """Return (t_literals, untranslated_han_literals) for one source file."""

    tree = ast.parse((ROOT / path).read_text())
    docs = _docstring_node_ids(tree)
    in_t = _t_first_arg_ids(tree)
    t_literals, leftovers = [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in in_t:
                t_literals.append(node.value)
            elif id(node) not in docs and HAN.search(node.value):
                leftovers.append(node.value)
    return t_literals, leftovers


def _placeholders(text: str) -> set[str]:
    return set(PLACEHOLDER.findall(text))


def test_language_defaults_to_english_and_switches():
    set_lang("en")
    assert get_lang() == "en"
    set_lang("bogus")
    assert get_lang() == i18n.DEFAULT_LANG
    set_lang("zh")


def test_t_returns_chinese_source_in_zh_and_formats():
    set_lang("zh")
    assert t("中文 {n}", n=3) == "中文 3"


def test_t_falls_back_to_source_when_untranslated():
    set_lang("en")
    assert t("这句话绝对不在翻译表里 {n}", n=1) == "这句话绝对不在翻译表里 1"


def test_catalog_placeholders_match_source():
    bad = [
        (zh, en)
        for zh, en in EN.items()
        if _placeholders(zh) != _placeholders(en)
    ]
    assert not bad, f"placeholder mismatch: {bad[:5]}"


def test_catalog_values_are_english_not_chinese():
    still_chinese = [zh for zh, en in EN.items() if HAN.search(en)]
    assert not still_chinese, f"English value contains Chinese: {still_chinese[:5]}"


def test_no_duplicate_key_between_fragments_with_different_translations():
    clash = [k for k in EN_APP.keys() & EN_MISC.keys() if EN_APP[k] != EN_MISC[k]]
    assert not clash, f"same source string translated two ways: {clash[:5]}"


@pytest.mark.parametrize("path", APP_FILES + MISC_FILES)
def test_every_t_literal_has_an_english_translation(path):
    t_literals, _ = _scan(path)
    missing = sorted({s for s in t_literals if HAN.search(s) and s not in EN})
    assert not missing, f"{path}: t() strings missing from catalog: {missing[:10]}"


@pytest.mark.parametrize(
    "path,allowed",
    [(f, NOT_TRANSLATED_APP) for f in APP_FILES] + [(f, NOT_TRANSLATED_MISC) for f in MISC_FILES],
)
def test_no_untranslated_chinese_string_left_in_code(path, allowed):
    _, leftovers = _scan(path)
    bad = sorted({s for s in leftovers if s not in allowed})
    assert not bad, f"{path}: Chinese literals neither wrapped in t() nor allow-listed: {bad[:10]}"
