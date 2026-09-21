class FakeProvider:
    """测试用假 Provider：按调用顺序返回预先设定好的 dict 列表，不发任何网络请求。"""

    def __init__(self, responses: list[dict]):
        self._responses = list(responses)
        self.calls = []

    def complete_json(self, system: str, user: str) -> dict:
        self.calls.append((system, user))
        return self._responses.pop(0)
