import pytest

from engine.i18n import set_lang


@pytest.fixture(autouse=True)
def _chinese_ui_language_for_legacy_assertions():
    # 已有测试断言的都是中文输出；界面默认语言现在是英文，测试统一固定成中文，
    # 专门测英文的用例自己 set_lang("en")。
    set_lang("zh")
    yield
    set_lang("zh")


@pytest.fixture(autouse=True)
def _no_live_internal_default_llm_calls(monkeypatch):
    """内部团队版（`internal` 分支）自带 `engine/internal_defaults.py` 里的真实共享
    API key——测试只要没显式配置供应商/mock 调用，`get_provider()` 就会兜底捡到这个
    真实 key，等于在跑测试的时候悄悄发真实网络请求：真的花钱，而且真的会因为模型
    响应慢而超时。公开仓库（这个分支）本来就没有这个文件，这条 fixture 在这里是
    无操作（`_internal_default_provider()` 本来就因为 ImportError 返回 None）——
    保留同一份 `conftest.py` 是为了让 internal 分支合并/cherry-pick 过来的改动不用
    每次单独处理这一个文件，两边保持一致。

    统一在测试环境屏蔽这个内部兜底——用的是 `tests/test_llm_provider.py` 里已有
    的同一招（往 `sys.modules` 塞 `None` 强制这个模块 import 失败），不是新发明
    一套机制。想专门测"内置默认值确实生效"的用例（比如
    `test_get_provider_uses_internal_default_key_when_present`），自己在测试函数
    里用同一个 `monkeypatch` 把 `sys.modules["engine.internal_defaults"]` 换成
    真正的假模块——同一个 `monkeypatch` 对象后设置的值会覆盖这里先设置的，测试
    结束时一并撤销，两边不冲突。
    """

    import sys

    monkeypatch.setitem(sys.modules, "engine.internal_defaults", None)
