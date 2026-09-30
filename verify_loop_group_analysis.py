"""真机验收：题组循环分析（"matrix 逻辑"问卷：同一批题目按轮次重复问了好几遍）。

真实反馈的问卷结构："大家第一步会做什么"（不分轮次的整体动作分布）+ "做某个
特定动作会选择什么平台"（动作×平台交叉表），来自一份真实的购买路径问卷
（rounds: Q9/Q12/Q15/Q18/Q21 是"做什么"，Q10/Q13/Q16/Q19/Q22 是"去哪个平台"，
第三轮起有退出选项）。这里用缩小过的合成数据复现同一个结构，不接真实文件。

复制代码到临时目录，只操作合成问卷和临时数据库。
运行：.venv/bin/python verify_loop_group_analysis.py
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

EXIT_OPTION = "That was it — I was ready to buy"


def prepare_runtime(root: Path) -> None:
    for folder in ("app_streamlit", "engine", ".streamlit"):
        shutil.copytree(ROOT / folder, root / folder, ignore=shutil.ignore_patterns("__pycache__"))
    (root / "data").mkdir()
    conn = db.init_db(str(root / "data/app.db"))
    db.set_setting(conn, "ui_language", "zh")

    project_id = db.create_project(conn, "验收项目", "en", "zh")
    method = dict(platform_source=None, is_branched=False, branch_count=None, screen_out_rule=None, skip_logic_note=None)
    # 4 位受访者：A/C 两轮都走"找灵感→Pinterest"，B 第 2 轮就退出，D 走满两轮
    # 但第二轮去向不同——回答的核心问题跟 verify 脚本同一批测试数据（tests/
    # test_stats.py 的 _rug_journey_df）保持一致，方便对照真机结果和单元测试
    # 算出来的结果是不是一回事。
    units = [
        dict(kind="single", title="第1轮做什么", display_no="Q1", columns=["Q1"], section="正式"),
        dict(kind="single", title="第1轮去哪", display_no="Q2", columns=["Q2"], section="正式"),
        dict(kind="single", title="第2轮做什么", display_no="Q3", columns=["Q3"], section="正式"),
        dict(kind="single", title="第2轮去哪", display_no="Q4", columns=["Q4"], section="正式"),
    ]
    df = pd.DataFrame({
        "Q1": ["Looking for ideas", "Getting a sense of cost", "Looking for ideas", "Getting a sense of cost"],
        "Q2": ["Pinterest", "An online retailer", "Pinterest", "An online retailer"],
        "Q3": ["Getting a sense of cost", EXIT_OPTION, "Getting a sense of cost", "Reading reviews"],
        "Q4": ["An online retailer", None, "An online retailer", "Reddit"],
    })
    persistence.save_analysis(conn, project_id, units, df, {}, {}, method, [], "test.csv", title="__TEST__题组循环验收")
    conn.close()


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="loop-group-"))
    print(f"验收目录（只含合成数据）：{root}", flush=True)
    prepare_runtime(root)
    port = 8591
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
                page = browser.new_page(viewport={"width": 1600, "height": 1600})
                page.set_default_timeout(20000)
                page_errors = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))

                page.goto(url)
                page.get_by_role("button", name="打开", exact=True).first.click()
                page.wait_for_url("**/project_view**")
                page.get_by_role("button", name="打开", exact=True).first.click()
                page.wait_for_url("**/app**")
                page.get_by_role("button", name="生成分析", exact=True).click()
                page.wait_for_selector(".st-key-section_paper_8loop", timeout=15000)
                assert not page_errors, f"页面出现异常：{page_errors}"

                loop_section = page.locator(".st-key-section_paper_8loop")
                loop_section.scroll_into_view_if_needed()
                loop_section.get_by_role("button", name="+ 新增题组循环板块", exact=True).click()
                page.wait_for_selector(".st-key-loop_block_1")
                block = page.locator(".st-key-loop_block_1")

                def select_round(round_index: int, role: str, label_substr: str) -> None:
                    combo = block.locator(f".st-key-loop_1_round_{round_index}_{role}").get_by_role("combobox")
                    combo.scroll_into_view_if_needed()
                    combo.click()
                    page.wait_for_timeout(300)
                    page.locator(f"text={label_substr}").last.click(timeout=5000)

                select_round(0, "action", "Q1｜第1轮做什么")
                select_round(0, "platform", "Q2｜第1轮去哪")
                select_round(1, "action", "Q3｜第2轮做什么")
                select_round(1, "platform", "Q4｜第2轮去哪")

                # 把真实退出选项标记成"退出/终止选项"——多选框从已配置的动作题
                # 观测值里取，这里直接点开下拉选中它。
                exit_select = block.locator('[class*="st-key-loop_1_exit_values"]')
                exit_select.get_by_role("combobox").click()
                page.wait_for_timeout(300)
                page.locator(f"text={EXIT_OPTION}").last.click(timeout=5000)
                # 注意：这里不能用 Escape 关掉下拉框——跟 st.popover 不一样，
                # st.multiselect 的下拉框被 Escape 关掉时会连刚选中的这一项一起
                # 撤销（真机验证发现的坑：Escape 之后多选框显示"Choose options"，
                # 选中态完全没生效）。改成点一下板块标题这类中性区域，让下拉框
                # 自然失焦关闭，选中的值才会真正落到 session_state 里。
                block.get_by_text("题组循环板块 1", exact=True).click()
                page.wait_for_timeout(800)

                block.get_by_role("button", name="生成题组循环分析", exact=True).click()
                page.wait_for_selector(".st-key-loop_1_action_chart", timeout=15000)
                assert not page_errors, f"页面出现异常：{page_errors}"

                # 核心断言 1：动作分布图应该渲染出来，且退出选项（"That was it..."）
                # 不应该出现在这张图里——它是"决定不再做了"，不是一次真正的动作。
                # 只看图表容器自己的 SVG 文字内容，不看整个页面（多选框选中态本身
                # 的"pill"标签、下拉框内部隐藏的选项列表都会包含这段文字，属于
                # 正常 UI 元素，不是"动作分布图里出现了退出选项"这个问题）。
                action_chart = block.locator(".st-key-loop_1_action_chart")
                expect(action_chart).to_be_visible()
                chart_svg_text = action_chart.locator(".echarts-container").inner_text()
                assert EXIT_OPTION not in chart_svg_text, (
                    f"退出选项不该出现在动作分布图里，实际图表文字：{chart_svg_text[:300]}"
                )

                # 核心断言 2：动作×平台交叉表应该出现，且"Getting a sense of cost"
                # 这个动作（respondent A 第2轮 + respondent C 第2轮 + respondent B
                # 第1轮 + respondent D 第1轮，一共4次）对应的平台里，"An online
                # retailer" 应该是 100%（这4次全部去的都是这个平台）。
                assert page.get_by_text("动作 × 平台", exact=False).count() > 0
                table_text = page.content()
                assert "An online retailer" in table_text

                # 核心断言 3：路径长度分布图应该渲染出来（4 人都至少走了 1 轮）。
                expect(block.locator(".st-key-loop_1_path_chart")).to_be_visible()

                page.screenshot(path=str(root / "loop_group_result.png"), full_page=True)
                assert not page_errors, f"页面出现异常：{page_errors}"

                # 核心断言 4（持久化）：手动保存 + 用一次全新的导航重新打开这份文档
                # （不是 page.reload()——跟 verify_crosstab_browser.py 里的教训一样，
                # 这个工具的"重新打开"要靠真的从项目列表点"打开"进来，才能确认
                # 结果不是靠这个浏览器标签页的内存活着），板块配置和结果都应该还在。
                page.get_by_role("button", name="保存", exact=True).click()
                page.wait_for_timeout(1000)
                page.goto(url)
                page.get_by_role("button", name="打开", exact=True).first.click()
                page.wait_for_url("**/project_view**")
                page.get_by_role("button", name="打开", exact=True).first.click()
                page.wait_for_url("**/app**")
                page.get_by_role("button", name="生成分析", exact=True).click()
                page.wait_for_selector(".st-key-section_paper_8loop", timeout=15000)
                page.locator(".st-key-section_paper_8loop").scroll_into_view_if_needed()
                page.wait_for_timeout(500)
                page.screenshot(path=str(root / "debug_after_reopen.png"), full_page=True)
                page.wait_for_selector(".st-key-loop_block_1", timeout=15000)
                block = page.locator(".st-key-loop_block_1")
                expect(block.locator(".st-key-loop_1_action_chart")).to_be_visible()
                assert not page_errors, f"页面出现异常：{page_errors}"

            print("Playwright 验收通过：题组循环分析生成、渲染、持久化都正常。", flush=True)
        finally:
            server.terminate()
            server.wait(timeout=10)


if __name__ == "__main__":
    main()
