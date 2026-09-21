"""给自动建的占位项目起一个比"未命名项目"更有用的名字。

用在分析页面没有项目上下文、需要临时建一个项目才能保存分析结果的场景（比如直接跑
app.py，或者服务端重启后浏览器还停在分析页）——这种项目是系统代劳建的，不是用户主动
新建的（对应 db.create_project 的 origin="auto"），起名这件事没有人参与，所以：

- 没配 AI 供应商：纯 Python 挑一道"正式"问卷里的代表性问题当名字，不调用任何 API。
- 配了 AI 供应商：让 AI 从题目列表里总结一个更有区分度的名字（同一类问卷题目相似的话，
  直接摘一道题当名字容易撞名；AI 总结能带出"这份问卷测的是什么"）。AI 输出只信任经过
  校验的部分——非空字符串、长度不离谱，校验不过直接退回纯 Python 的猜测，不会让一个
  奇怪的名字污染项目列表。
"""

from __future__ import annotations

MAX_NAME_LEN = 24


def guess_project_name_from_questions(units: list[dict]) -> str:
    """挑"正式"问卷里第一道有实际文本的题目当项目名；没有"正式"题就退而求其次挑任意
    一道有文本的题；什么都挑不到就还是叫"未命名项目"。"""

    candidates = [u for u in units if u.get("section") == "正式" and u.get("title")]
    if not candidates:
        # 没有"正式"题就退而求其次，挑任意非"平台信息"的题目（比如基础信息/筛选题）——
        # 平台自动收录的字段（作答ID之类）不该被当成项目名，宁可最后落到"未命名项目"。
        candidates = [u for u in units if u.get("section") != "平台信息" and u.get("title")]
    if not candidates:
        return "未命名项目"

    title = candidates[0]["title"].strip()
    if len(title) > MAX_NAME_LEN:
        title = title[:MAX_NAME_LEN].rstrip() + "…"
    return title or "未命名项目"


def summarize_project_name(provider, units: list[dict], sample_size: int = 12) -> str:
    """用 AI 从题目列表总结一个简洁、有区分度的项目名；任何一步不满意就退回纯 Python
    的 guess_project_name_from_questions，绝不把校验不过的 AI 输出当项目名用。"""

    fallback = guess_project_name_from_questions(units)
    titles = [u["title"] for u in units if u.get("section") == "正式" and u.get("title")][:sample_size]
    if not titles:
        return fallback

    system = "你负责给一份问卷调研项目起一个简洁的中文名称。"
    user = (
        "根据下面这些问卷题目，用不超过12个汉字总结一个简洁、有区分度的项目名称"
        "（不要写“问卷”“调研”这类通用词，直接概括这份问卷在测什么）。"
        '只返回 JSON 对象，格式为：{"name": "名称"}。\n'
        f"题目列表：{titles}"
    )
    try:
        output = provider.complete_json(system, user)
        name = output.get("name")
    except Exception:  # noqa: BLE001 —— AI 调用失败不能挡住项目照常创建，退回纯 Python 方案
        return fallback

    if not isinstance(name, str):
        return fallback
    name = name.strip()
    if not name or len(name) > MAX_NAME_LEN:
        return fallback
    return name
