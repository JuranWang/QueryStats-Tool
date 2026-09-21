from engine.project_naming import guess_project_name_from_questions, summarize_project_name


def _unit(section, title):
    return {"section": section, "title": title}


def test_guess_project_name_prefers_first_official_question():
    units = [
        _unit("平台信息", "作答ID"),
        _unit("正式", "以下几种空调，你认为哪些同时具备制冷和制热功能？"),
        _unit("正式", "冬天用来制热，你认为以下哪一种最省电费？"),
    ]

    assert guess_project_name_from_questions(units) == "以下几种空调，你认为哪些同时具备制冷和制热功能？"


def test_guess_project_name_truncates_long_titles():
    long_title = "这是一道非常非常非常非常非常非常非常非常非常长的问卷题目标题文本"
    units = [_unit("正式", long_title)]

    name = guess_project_name_from_questions(units)

    assert name.endswith("…")
    assert len(name) == 25  # 24 个字符 + 省略号


def test_guess_project_name_falls_back_to_any_titled_question():
    units = [_unit("平台信息", "作答ID"), _unit("基础信息", "您的年龄")]

    assert guess_project_name_from_questions(units) == "您的年龄"


def test_guess_project_name_returns_placeholder_when_nothing_usable():
    assert guess_project_name_from_questions([]) == "未命名项目"


class _StubProvider:
    def __init__(self, response=None, exc=None):
        self._response = response
        self._exc = exc

    def complete_json(self, system, user):
        if self._exc:
            raise self._exc
        return self._response


def test_summarize_project_name_uses_validated_ai_output():
    units = [_unit("正式", "冬天用来制热，你认为以下哪一种最省电费？")]
    provider = _StubProvider(response={"name": "空调制热省电认知"})

    assert summarize_project_name(provider, units) == "空调制热省电认知"


def test_summarize_project_name_falls_back_when_ai_output_too_long():
    units = [_unit("正式", "冬天用来制热，你认为以下哪一种最省电费？")]
    provider = _StubProvider(response={"name": "一个长度超过二十四个字符的离谱又啰嗦的项目名称示例文本"})

    assert summarize_project_name(provider, units) == guess_project_name_from_questions(units)


def test_summarize_project_name_falls_back_when_ai_call_fails():
    units = [_unit("正式", "冬天用来制热，你认为以下哪一种最省电费？")]
    provider = _StubProvider(exc=RuntimeError("API 挂了"))

    assert summarize_project_name(provider, units) == guess_project_name_from_questions(units)


def test_summarize_project_name_falls_back_when_no_official_questions():
    units = [_unit("平台信息", "作答ID")]
    provider = _StubProvider(response={"name": "不应该被调用"})

    assert summarize_project_name(provider, units) == "未命名项目"
