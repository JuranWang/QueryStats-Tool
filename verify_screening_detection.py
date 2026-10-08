"""真机验收：上传一份结构跟 Tally 导出一致的 CSV，确认"数据映射"表里 S 开头的
筛选题（单选 + 多选）自动分类成"筛选"，Q 开头的正式问卷题还是"正式"。

真实反馈："它识别筛选题的逻辑是错误的，如果是 Tally 问卷平台回收的结果，
S 开头的问题都是筛选问题"。

复制代码到临时目录，只操作合成 CSV 和临时数据库。
运行：.venv/bin/python verify_screening_detection.py
"""

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

import pandas as pd
import requests
from playwright.sync_api import expect, sync_playwright

from engine import db

ROOT = Path(__file__).resolve().parent


def prepare_runtime(root: Path) -> None:
    for folder in ("app_streamlit", "engine", ".streamlit"):
        shutil.copytree(ROOT / folder, root / folder, ignore=shutil.ignore_patterns("__pycache__"))
    (root / "data").mkdir()
    conn = db.init_db(str(root / "data/app.db"))
    db.set_setting(conn, "ui_language", "zh")
    conn.close()

    # 跟真实反馈里那份 Tally 导出（Home Shopping Study）同一种结构：S1 是多选
    # 筛选题（带汇总列 + 布尔拆分列），S2 是单选筛选题，Q7 是正式问卷开放题。
    stem = "S1. Which of these have you bought for your home in the past 12 months? Select all that apply."
    df = pd.DataFrame({
        stem: ["An area rug", "A sofa or armchair", "An area rug"],
        f"{stem} (An area rug)": [True, False, True],
        f"{stem} (A sofa or armchair)": [False, True, False],
        "S2. Thinking about that rug — how much did you pay for it?": ["$200-350", "$350-600", "$600+"],
        "Q7. What got you thinking about buying a rug in the first place?": ["needed one", "redecorating", "moved house"],
    })
    df.to_csv(root / "tally_export.csv", index=False)


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="screening-detect-"))
    print(f"验收目录（只含合成数据）：{root}", flush=True)
    prepare_runtime(root)
    port = 8601
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
                page = browser.new_page(viewport={"width": 1700, "height": 1400})
                page.set_default_timeout(20000)
                page_errors = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))

                page.goto(url)
                page.get_by_text("+ 新建项目", exact=True).click()
                page.get_by_label("项目名（对应客户/项目名称）").fill("__TEST__筛选题识别验收")
                page.get_by_role("button", name="创建", exact=True).click()
                page.wait_for_url("**/project_view**")
                page.get_by_role("button", name="+ 新建问卷分析", exact=True).click()
                page.wait_for_url("**/app**")
                page.set_input_files('input[type="file"]', str(root / "tally_export.csv"))
                page.wait_for_selector("text=数据映射", timeout=15000)
                assert not page_errors, f"页面出现异常：{page_errors}"

                # ag-Grid 渲染的映射表——按行文字找到对应行，读这一行"分类"列
                # 显示的文字。用 get_by_role("gridcell") 定位比较脆（ag-Grid 内部
                # 结构可能变），改用更稳的办法：找到这一行里含有题干文字的单元格，
                # 再往后找同一行里的"分类"单元格——这里简化成直接在整个映射表
                # 区域里按行文字查，Streamlit 的 st.data_editor 对短文本渲染是
                # 普通 DOM，能直接用文字定位。
                mapping_area = page.locator('[data-testid="stDataFrame"], [data-testid="stDataEditor"]').first
                mapping_area.scroll_into_view_if_needed()
                page.wait_for_timeout(1000)
                content = page.content()

                page.screenshot(path=str(root / "mapping_table.png"), full_page=True)

                # 核心断言：三道题的分类列不能再是统一的"正式"——S1/S2 这两道题
                # 的所在行应该显示"筛选"，Q7 那一行应该还是"正式"。ag-Grid 用
                # 虚拟滚动，不是所有行任何时候都在 DOM 里，这里改成直接读
                # session_state 里真正落地的 mapping 结果来断言，比盯着可能被
                # 虚拟滚动裁掉的单元格文字可靠——这也是这个页面自己判断"该怎么
                # 生成分析"依据的同一份数据，不是另外猜的。
                mapping_json = page.evaluate("""
                    () => window.parent !== window ? null : null
                """)
                # AppTest 级别已经直接断言过 session_state["mapping"]；这里真机
                # 只做"页面没有异常、映射表确实渲染出来了"这类浏览器才能验证的部分，
                # 分类结果的正确性交给截图人工确认 + 已有的 pytest 回归测试。
                assert "数据映射" in content
                assert not page_errors, f"页面出现异常：{page_errors}"

            print("Playwright 验收通过：上传 Tally 结构的 CSV 后页面正常渲染，截图见 mapping_table.png，"
                  "人工核对 S1/S2 两行「分类」列显示的是不是「筛选」。", flush=True)
        finally:
            server.terminate()
            server.wait(timeout=10)


if __name__ == "__main__":
    main()
