"""真机验收：项目工作区问卷列表显示"发布时间"（取受访者最晚提交时间）并按它排序。

真实反馈："这里需要显示问卷的发布时间，并且默认按照时间排序。获取时间的时间很
简单，问卷收录的回复中都有答题者的回复时间，按照最晚填问卷的时间记录"。

复制代码到临时目录，只操作合成问卷和临时数据库。
运行：.venv/bin/python verify_publish_time.py
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

from engine import db, persistence

ROOT = Path(__file__).resolve().parent


def prepare_runtime(root: Path) -> None:
    for folder in ("app_streamlit", "engine", ".streamlit"):
        shutil.copytree(ROOT / folder, root / folder, ignore=shutil.ignore_patterns("__pycache__"))
    (root / "data").mkdir()
    conn = db.init_db(str(root / "data/app.db"))
    db.set_setting(conn, "ui_language", "zh")

    project_id = db.create_project(conn, "验收项目", "en", "zh")
    method = dict(platform_source=None, is_branched=False, branch_count=None, screen_out_rule=None, skip_logic_note=None)

    # 文档 A：先建（数据库 updated_at 更早），但问卷里的"结束时间"比文档 B 更晚——
    # 真实场景就是"先建好分析框架、后来又追加导入了一批新收的回复"，updated_at
    # 早不代表问卷发布/收尾更早，"发布时间"必须以数据本身的时间为准，不能用
    # updated_at 顶替。
    units_a = [
        dict(kind="single", title="偏好", display_no="Q1", columns=["Q1"], section="正式"),
        dict(kind="open", title="结束时间", display_no="P1", columns=["结束时间"], section="平台信息"),
    ]
    df_a = pd.DataFrame({
        "Q1": ["A", "B", "A"],
        "结束时间": ["2026-09-10 08:00:00", "2026-09-22 23:59:00", "2026-09-15 12:00:00"],
    })
    persistence.save_analysis(conn, project_id, units_a, df_a, {}, {}, method, [], "doc_a.csv", title="__TEST__文档A（发布更晚）")

    units_b = [
        dict(kind="single", title="偏好", display_no="Q1", columns=["Q1"], section="正式"),
        dict(kind="open", title="结束时间", display_no="P1", columns=["结束时间"], section="平台信息"),
    ]
    df_b = pd.DataFrame({
        "Q1": ["A", "B"],
        "结束时间": ["2026-09-01 08:00:00", "2026-09-02 09:00:00"],
    })
    persistence.save_analysis(conn, project_id, units_b, df_b, {}, {}, method, [], "doc_b.csv", title="__TEST__文档B（发布更早）")

    # 文档 C：没有任何"平台信息"字段的老数据——应该退回显示"更新于"，不能崩溃、
    # 也不能瞎编一个发布时间。
    units_c = [dict(kind="single", title="偏好", display_no="Q1", columns=["Q1"], section="正式")]
    df_c = pd.DataFrame({"Q1": ["A", "B"]})
    persistence.save_analysis(conn, project_id, units_c, df_c, {}, {}, method, [], "doc_c.csv", title="__TEST__文档C（无平台信息）")

    conn.close()


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="publish-time-"))
    print(f"验收目录（只含合成数据）：{root}", flush=True)
    prepare_runtime(root)
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
                page = browser.new_page(viewport={"width": 1600, "height": 1200})
                page.set_default_timeout(20000)
                page_errors = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))

                page.goto(url)
                page.get_by_role("button", name="打开", exact=True).first.click()
                page.wait_for_url("**/project_view**")
                page.wait_for_selector("text=__TEST__文档A（发布更晚）")

                assert not page_errors, f"页面出现异常：{page_errors}"

                # 排序断言：文档 A（发布时间最晚：2026-09-22）必须排在文档 B（发布时间
                # 2026-09-02）前面，即使文档 B 是"后建的"（数据库 updated_at 更晚）——
                # 这是这个功能真正要验证的核心行为："发布时间"要以数据本身为准，不能
                # 被 updated_at 顶替。文档 C 没有发布时间、退回显示 updated_at（一个
                # 真实的"刚刚"时间戳），它排在最前面是符合预期的正常结果（它确实是
                # 三份里最新落库的），不是这条测试要锁定的行为，不跟 A/B 比较相对顺序。
                titles_in_order = page.locator(".stMarkdown strong").all_inner_texts()
                titles_in_order = [t for t in titles_in_order if t.startswith("__TEST__")]
                print("列表实际顺序：", titles_in_order)
                assert titles_in_order.index("__TEST__文档A（发布更晚）") < titles_in_order.index("__TEST__文档B（发布更早）"), (
                    f"发布时间更晚的文档 A 应该排在文档 B 前面，实际顺序：{titles_in_order}"
                )

                # 文案断言：A/B 应该显示"发布于 ..."且时间是数据里算出来的最晚提交时间
                # （不是 updated_at）；C 没有平台信息字段，应该退回"更新于"。
                expect(page.get_by_text("发布于 2026-09-22 23:59:00")).to_be_visible()
                expect(page.get_by_text("发布于 2026-09-02 09:00:00")).to_be_visible()
                assert page.locator("text=/更新于 \\d{4}-\\d{2}-\\d{2}/").count() >= 1, \
                    "文档 C 没有平台信息字段，应该退回显示「更新于」，没有找到"

                page.screenshot(path=str(root / "publish_time_list.png"))
                assert not page_errors, f"页面出现异常：{page_errors}"

            print("Playwright 全流程通过：问卷列表按发布时间排序，显示的是数据里算出来的最晚提交时间。", flush=True)
        finally:
            server.terminate()
            server.wait(timeout=10)


if __name__ == "__main__":
    main()
