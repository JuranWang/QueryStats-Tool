import pytest

from engine.i18n import set_lang


@pytest.fixture(autouse=True)
def _chinese_ui_language_for_legacy_assertions():
    # 已有测试断言的都是中文输出；界面默认语言现在是英文，测试统一固定成中文，
    # 专门测英文的用例自己 set_lang("en")。
    set_lang("zh")
    yield
    set_lang("zh")
