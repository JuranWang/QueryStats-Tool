"""真机验收：账号登录 + 数据隔离 + 公开分享。

真实反馈："设计如下帐户，密码是帐户中文的拼音，并且在登录页提示。帐户：何昕，
李萍，暄浩，非凡，快刀，小丰，思言。然后每个账号的内容要进行隔离，但是设计一个
公开的功能，即某人可以公开某个问卷结果，所有人都可以访问"。

验收四件事：
1. 没登录看不到项目列表，只有登录表单。
2. 密码错会报错，不会放行。
3. 何昕建的项目，李萍登录后看不到（隔离生效）。
4. 何昕把项目设为公开之后，李萍登录能看到了（公开分享生效），且李萍自己的项目
   也还在（公开不会把隔离整个打开）。

复制代码到临时目录，只操作临时数据库。
运行：.venv/bin/python verify_account_isolation.py
"""

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

import requests
from playwright.sync_api import sync_playwright

from engine import db

ROOT = Path(__file__).resolve().parent


def prepare_runtime(root: Path) -> None:
    for folder in ("app_streamlit", "engine", ".streamlit"):
        shutil.copytree(ROOT / folder, root / folder, ignore=shutil.ignore_patterns("__pycache__"))
    (root / "data").mkdir()
    conn = db.init_db(str(root / "data/app.db"))
    db.set_setting(conn, "ui_language", "zh")
    conn.close()


def login(page, account: str, password: str) -> None:
    # st.selectbox 不是原生 <select>，不能用 select_option——跟项目里其它 verify
    # 脚本（见 verify_crosstab_browser.py 的 select_key）同一个套路：点开下拉，
    # 按文字定位选项再点。
    combo = page.locator(".st-key-login_account_select").get_by_role("combobox")
    combo.click()
    page.wait_for_timeout(400)
    page.locator(f"text={account}").last.click(timeout=5000)
    page.locator(".st-key-login_password_input input").fill(password)
    page.get_by_role("button", name="登录", exact=True).click()


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="account-isolation-"))
    print(f"验收目录（只含临时数据）：{root}", flush=True)
    prepare_runtime(root)
    port = 8603
    url = f"http://127.0.0.1:{port}"

    with (root / "server.log").open("w") as log:
        server = subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", str(root / "app_streamlit/Home.py"),
             "--server.port", str(port), "--server.headless", "true", "--browser.gatherUsageStats", "false"],
            cwd=root, stdout=log, stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 30
            while True:
                if server.poll() is not None:
                    raise RuntimeError((root / "server.log").read_text())
                try:
                    if requests.get(url, timeout=1).status_code == 200:
                        break
                except requests.RequestException:
                    pass
                if time.monotonic() >= deadline:
                    raise TimeoutError("server did not start in time")
                time.sleep(0.3)

            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1400, "height": 1000})
                page.set_default_timeout(20000)
                page_errors = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))

                # 1. 没登录 = 只看到登录表单，看不到项目列表。
                page.goto(url)
                page.wait_for_selector("text=登录", timeout=15000)
                assert "项目列表" not in page.content()
                assert not page_errors, f"登录页异常：{page_errors}"

                # 2. 密码错 -> 报错，不放行。
                login(page, "何昕", "wrongpassword")
                page.wait_for_selector("text=密码不对")
                assert "项目列表" not in page.content()

                # 3. 何昕登录成功，建一个项目。
                login(page, "何昕", "Hexin")
                page.wait_for_selector("text=项目列表", timeout=15000)
                page.get_by_text("+ 新建项目", exact=True).click()
                page.get_by_label("项目名（对应客户/项目名称）").fill("__TEST__何昕的私有项目")
                page.get_by_role("button", name="创建", exact=True).click()
                page.wait_for_url("**/project_view**")
                page.get_by_role("button", name="返回首页", exact=True).click()
                page.wait_for_selector("text=项目列表", timeout=15000)
                assert "__TEST__何昕的私有项目" in page.content()

                # 退出登录，换李萍登录 -> 看不到何昕的私有项目（隔离生效）。
                page.get_by_role("button", name="何昕 · 退出登录", exact=True).click()
                page.wait_for_selector("text=登录", timeout=15000)
                login(page, "李萍", "Liping")
                page.wait_for_selector("text=项目列表", timeout=15000)
                assert "__TEST__何昕的私有项目" not in page.content(), "隔离没生效：李萍看到了何昕的私有项目"

                # 李萍建一个自己的项目，退出登录。
                page.get_by_text("+ 新建项目", exact=True).click()
                page.get_by_label("项目名（对应客户/项目名称）").fill("__TEST__李萍的私有项目")
                page.get_by_role("button", name="创建", exact=True).click()
                page.wait_for_url("**/project_view**")
                # 用"返回首页"按钮做同页跳转，不用 page.goto(url) 硬刷新——这个 app
                # 硬刷新之后拿不回同一个 Streamlit session_state（见 CLAUDE.md 里
                # "page.reload() 不可靠"那条记录，这里是它的同一类表现）。
                page.get_by_role("button", name="返回首页", exact=True).click()
                page.wait_for_selector("text=项目列表", timeout=15000)
                page.get_by_role("button", name="李萍 · 退出登录", exact=True).click()

                # 何昕重新登录，把自己的项目设为公开。
                page.wait_for_selector("text=登录", timeout=15000)
                login(page, "何昕", "Hexin")
                page.wait_for_selector("text=项目列表", timeout=15000)
                page.get_by_role("button", name="设为公开", exact=True).first.click()
                page.wait_for_selector("text=已公开")
                page.get_by_role("button", name="何昕 · 退出登录", exact=True).click()

                # 李萍再登录 -> 现在应该能看到何昕公开的项目，自己的项目也还在。
                page.wait_for_selector("text=登录", timeout=15000)
                login(page, "李萍", "Liping")
                page.wait_for_selector("text=项目列表", timeout=15000)
                content = page.content()
                assert "__TEST__何昕的私有项目" in content, "公开没生效：李萍还是看不到何昕公开的项目"
                assert "__TEST__李萍的私有项目" in content, "公开开关误伤：李萍自己的项目不见了"

                page.screenshot(path=str(root / "account_isolation.png"), full_page=True)
                assert not page_errors, f"流程中出现异常：{page_errors}"

            print("Playwright 验收通过：登录门禁 + 密码校验 + 账号隔离 + 公开分享全部正常，"
                  f"截图见 {root / 'account_isolation.png'}。", flush=True)
        finally:
            server.terminate()
            server.wait(timeout=10)


if __name__ == "__main__":
    main()
