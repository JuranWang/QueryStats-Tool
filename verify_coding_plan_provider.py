"""真机验收：首页 API/模型设置能正常显示新增的 Qwen Coding Plan 供应商选项。

运行：.venv/bin/python verify_coding_plan_provider.py
"""

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

import requests
from playwright.sync_api import expect, sync_playwright

from engine import db

ROOT = Path(__file__).resolve().parent


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="coding-plan-"))
    print(f"验收目录：{root}", flush=True)
    for folder in ("app_streamlit", "engine", ".streamlit"):
        shutil.copytree(ROOT / folder, root / folder, ignore=shutil.ignore_patterns("__pycache__"))
    (root / "data").mkdir()
    conn = db.init_db(str(root / "data/app.db"))
    db.set_setting(conn, "ui_language", "zh")
    conn.close()

    port = 8551
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
                page = browser.new_page()
                page.set_default_timeout(20000)
                page_errors = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.goto(url)
                page.wait_for_selector("text=API / 模型设置", timeout=15000)
                page.locator("text=API / 模型设置").scroll_into_view_if_needed()

                # 打开"选用哪个供应商"下拉框（key="provider_select"），确认新选项在
                # 列表里——直接用 key 对应的 CSS class 定位，比猜 DOM 结构位置关系更稳。
                combo = page.locator(".st-key-provider_select").get_by_role("combobox")
                combo.scroll_into_view_if_needed()
                combo.click()
                page.wait_for_timeout(400)
                expect(page.get_by_text("百炼 Coding Plan", exact=False).first).to_be_visible()
                page.screenshot(path=str(root / "provider_dropdown.png"), full_page=False)
                page.keyboard.press("Escape")

                assert not page_errors, page_errors
                expect(page.locator('[data-testid="stException"]')).to_have_count(0)

            print("Playwright 验收通过：Coding Plan 选项正常显示在下拉框里，没有报错。", flush=True)
        finally:
            server.terminate()
            server.wait(timeout=10)


if __name__ == "__main__":
    main()
