"""真机验收：循环问了好几遍的多选题（pandas 去重后缀 .1/.2）不能被误判成单选题。

复制代码 + 真实反馈用的那份文件到临时目录，不碰真实的 data/app.db。
运行：.venv/bin/python verify_multi_dedup_bug.py
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
REAL_FILE = ROOT / "data" / "uploads" / "硅胶专利测试.csv"


def prepare_runtime(root: Path) -> None:
    for folder in ("app_streamlit", "engine", ".streamlit"):
        shutil.copytree(ROOT / folder, root / folder, ignore=shutil.ignore_patterns("__pycache__"))
    (root / "data").mkdir()
    conn = db.init_db(str(root / "data/app.db"))
    db.set_setting(conn, "ui_language", "zh")
    conn.close()


def main() -> None:
    if not REAL_FILE.exists():
        raise SystemExit(f"找不到真实反馈用的文件：{REAL_FILE}")
    root = Path(tempfile.mkdtemp(prefix="multi-dedup-bug-"))
    print(f"验收目录：{root}", flush=True)
    prepare_runtime(root)
    port = 8541
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
                context = browser.new_context(viewport={"width": 1600, "height": 1200})
                page = context.new_page()
                page.set_default_timeout(30000)
                page_errors = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))

                page.goto(url)
                page.get_by_text("+ 新建项目", exact=True).click()
                page.get_by_label("项目名（对应客户/项目名称）").fill("__TEST__多选去重bug验收")
                page.get_by_role("button", name="创建", exact=True).click()
                page.wait_for_url("**/project_view**")
                page.get_by_role("button", name="+ 新建问卷分析", exact=True).click()
                page.wait_for_url("**/app**")
                page.set_input_files('input[type="file"]', str(REAL_FILE))
                page.wait_for_selector("text=读取成功", timeout=15000)

                # 这份文件列很多（27 个多选选项列 + 平台信息等），自动识别多选/排序题
                # 分组要跑一遍全部列，映射表渲染完成前会有好几轮 rerun——真机验证过
                # 的坑（交叉分析板块也踩过一次）：点击click落在两次 rerun 中间，按钮
                # 节点正在被替换，点击可能悄悄没有任何效果（现象是后面什么都没发生，
                # 不报错也不产出结果，误以为是别的地方的 bug）。等页面稳定下来再点。
                page.wait_for_timeout(5000)

                # 真机验证过程中发现："11. 导出"这个文字在侧边栏导航链接里会提前
                # 出现（生成开始后侧栏立刻列出全部章节标题），跟正文里真正的
                # "11. 导出"小标题不是同一个东西——用它当"生成完成"的判据会在正文
                # 其实还没跑完的时候就提前通过。改成等"生成分析"这个按钮本身消失
                # （生成完之后这个按钮所在的整个上传区域仍在，但按钮点击后会立刻
                # 重新渲染成"已生成"状态，配合固定的保险等待时间，比赌一个可能被
                # 侧栏抢先匹配到的文字更可靠）。
                page.get_by_role("button", name="生成分析", exact=True).click()
                page.wait_for_timeout(2000)
                if page.get_by_role("button", name="生成分析", exact=True).count() > 0:
                    # 有真实反馈过的"生成交叉分析"按钮点击落空的先例——点了但没生效，
                    # 这里探测一次按钮是否还在（还在说明可能没点中），补点一次。
                    page.get_by_role("button", name="生成分析", exact=True).click()
                # 这份文件列多、行也多（300 人），文字类的"等到了没到"判据在这份大文件
                # 上试过好几种都不可靠（侧边栏导航提前列出章节标题、映射表是 canvas
                # 画的网格会误命中同名文字）——直接给一个对 300 行数据够用的固定
                # 等待时间，比赌一个不稳定的文字判据更可预期。
                page.wait_for_timeout(25000)
                print("exceptions:", page.locator('[data-testid="stException"]').count())
                if page.locator('[data-testid="stException"]').count():
                    print(page.locator('[data-testid="stException"]').first.inner_text()[:2000])

                # 图表是 ECharts 组件，渲染在独立的 iframe（about:srcdoc）里，选项名
                # 文字在图表的 SVG <text> 节点里——两个坑都踩过：(1) 主文档的
                # page.content() 不会递归进子 iframe 的文档；(2) SVG 里的文字，
                # Playwright/Chromium 的 innerText 计算不会把它算进去（innerText 是
                # 按 CSS 渲染盒模型算的，SVG <text> 没有走那套盒模型），inner_text()
                # 会得到"看起来完全没有这段文字"的假象。改用 .content()（原始 HTML
                # 源码）而不是 inner_text()，且要把主文档 + 每个 iframe 各自的
                # .content() 都拼起来查，两个问题都绕开。
                all_text_parts = [page.content()]
                for frame in page.frames:
                    try:
                        all_text_parts.append(frame.content())
                    except Exception:
                        pass
                all_text = "\n".join(all_text_parts)
                print("拼起来的总文字长度（含所有 iframe）:", len(all_text))
                if "保存失败" in all_text:
                    idx = all_text.find("保存失败")
                    print("!!! 发现保存失败提示:", all_text[idx:idx+300])

                # 核心断言 2：报告正文里不能出现"可多选-热熔胶.1【单选题】"这种
                # 退化成单选题的标题（这是 bug 复现时的真实标题文字，直接按子串找，
                # 原始 HTML 源码不像渲染出来的文字那样天然按行分隔）。
                assert "可多选-热熔胶.1" not in all_text, "bug 复现：第 2 轮的热熔胶列退化成了独立列"
                assert "可多选-热熔胶.2" not in all_text, "bug 复现：第 3 轮的热熔胶列退化成了独立列"
                assert "热熔胶.1【单选题】" not in all_text
                assert "热熔胶.2【单选题】" not in all_text

                # 核心断言 3（最终、最可靠的判据）：直接查这次自动保存进临时数据库
                # 的实际结果，绕开图表异步渲染、SVG 换行这些跟"分组对不对"本身无关
                # 的干扰。落库时 questions 表是"每个最终合并后的题目单元存一行"（不是
                # 每个原始拆分列一行——那 9 个选项已经在 build_units 那步合并成了一个
                # 单元），分组正确的话，"算作胶"这道题应该存成 3 行、q_type 都是
                # 'multi'、q_no 各不相同（三轮循环各自是一道独立的题）；如果退化成
                # 独立单选题，会看到 q_type='single' 的行（而且数量会远多于 3）。
                import sqlite3
                with sqlite3.connect(root / "data/app.db") as db_conn:
                    rows = db_conn.execute(
                        "SELECT q_type, q_no FROM questions WHERE source_text_en LIKE ?",
                        ("%以下这些东西，你会把哪些算作%",),
                    ).fetchall()
                print("数据库里这道题相关的记录（共 {} 行）:".format(len(rows)), rows)
                single_rows = [r for r in rows if r[0] == "single"]
                multi_rows = [r for r in rows if r[0] == "multi"]
                assert not single_rows, \
                    f"bug 复现：这道多选题的循环轮次退化成了 {len(single_rows)} 条独立单选题记录：{single_rows}"
                assert len(multi_rows) == 3, \
                    f"应该是 3 道独立的多选题（三轮循环各一道），实际 {len(multi_rows)} 道：{multi_rows}"
                q_nos = {q_no for _, q_no in multi_rows}
                assert len(q_nos) == 3, f"3 道题的 q_no 应该互不相同，实际：{q_nos}"

                assert not page_errors, page_errors
                expect(page.locator('[data-testid="stException"]')).to_have_count(0)
                page.screenshot(path=str(root / "final.png"), full_page=True)
                browser.close()

            print("Playwright 全流程通过：循环问的多选题三轮都正确合并、选项名干净，没有退化成单选题。", flush=True)
        finally:
            server.terminate()
            server.wait(timeout=10)


if __name__ == "__main__":
    main()
