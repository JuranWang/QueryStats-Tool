"""内部团队账号：每个账号的密码是账号中文名的拼音，登录页直接提示——这不是
面向公网的安全边界（真正挡外人进来的是 Cloudflare Access/Tunnel 那一层），这里只是
给"每个人自己的项目列表互相不干扰 + 谁能把问卷结果公开给大家看"这两件事一个简单
的身份标识，图的是内部团队用起来省事，不是要做强密码/加密存储。

真实反馈："设计如下帐户，密码是帐户中文的拼音，并且在登录页提示。帐户：何昕，
李萍，暄浩，非凡，快刀，小丰，思言。然后每个账号的内容要进行隔离，但是设计一个
公开的功能，即某人可以公开某个问卷结果，所有人都可以访问"。

真实账号名单+密码跟 `engine/internal_defaults.py`（共享 API key）是同一个道理，
不放在这份代码本身里——哪怕密码只是拼音、本来就打算给同事看，一旦明文写进这个
文件，就会随这份代码一起进 GitHub 的公开仓库 `JuranWang/QueryStats-Tool` 的提交
历史，变成任何人都能在网上搜到、永久留底的东西，这就不是"内部团队内部提示"的
范围了，而是把登录名单公开给全世界。真实名单只存在于私有仓库
`QueryStats-Tool-Internal` 的 `internal` 分支上的 `engine/internal_accounts.py`
（这个仓库的 `.gitignore` 专门排除了这个文件名，见文件头注释）。公开仓库里没有
这个文件，下面的 `try/except ImportError` 会退回一个占位账号，本地单机跑照样能用，
只是不是真正内部团队那几个账号。
"""

from __future__ import annotations

try:
    from engine.internal_accounts import INTERNAL_ACCOUNTS as ACCOUNTS
except ImportError:
    ACCOUNTS: dict[str, str] = {"demo": "demo"}


def check_password(account: str, password: str) -> bool:
    return ACCOUNTS.get(account) == password
