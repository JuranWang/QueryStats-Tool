"""真机验收：插入图片和图表的排版 + 复制/下载合成图。

真实反馈：
1. "只有一张图片的时候，图片和图表可以放在同一行：图左、图表右"。
2. "复制/下载的时候，应该把我传的图片和图表合成一张图，不能只有图表自己"。

复制代码到临时目录，只操作合成问卷和临时数据库。
运行：.venv/bin/python verify_image_chart_merge.py
"""

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

import pandas as pd
import requests
from PIL import Image
from playwright.sync_api import sync_playwright

from engine import db, persistence

ROOT = Path(__file__).resolve().parent


def prepare_runtime(root: Path) -> None:
    for folder in ("app_streamlit", "engine", ".streamlit"):
        shutil.copytree(ROOT / folder, root / folder, ignore=shutil.ignore_patterns("__pycache__"))
    (root / "data").mkdir()
    conn = db.init_db(str(root / "data/app.db"))
    db.set_setting(conn, "ui_language", "zh")

    units = [dict(kind="single", title="偏好", display_no="Q1", columns=["Q1"], section="正式")]
    method = dict(platform_source=None, is_branched=False, branch_count=None, screen_out_rule=None, skip_logic_note=None)
    df = pd.DataFrame({"Q1": ["A"] * 5 + ["B"] * 3 + ["C"] * 2})
    project = db.create_project(conn, "验收项目", "en", "zh")
    persistence.save_analysis(conn, project, units, df, {}, {}, method, [], "test.csv", title="验收问卷")
    conn.close()

    Image.new("RGB", (300, 200), "#245785").save(root / "photo1.png")
    Image.new("RGB", (200, 350), "#8A2E5C").save(root / "photo2.png")


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="image-chart-merge-"))
    print(f"验收目录（只含合成数据）：{root}", flush=True)
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
                context = browser.new_context(viewport={"width": 1600, "height": 1200}, accept_downloads=True)
                page = context.new_page()
                page.set_default_timeout(20000)
                page_errors = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))

                page.goto(url)
                page.get_by_role("button", name="打开", exact=True).first.click()
                page.wait_for_url("**/project_view**")
                page.get_by_role("button", name="打开", exact=True).first.click()
                page.wait_for_url("**/app**")
                page.get_by_role("button", name="生成分析", exact=True).click()
                page.wait_for_selector(".st-key-qbar_Q1")

                qbar = page.locator(".st-key-qbar_Q1")

                # 1. 还没插入图片：下载按钮走"只有图表"的旧路径，先存一份基准图，
                #    后面拿来跟"插入一张图之后"的合成图比宽度。
                with page.expect_download() as download:
                    page.locator(".st-key-chart_download_Q1 button:visible").click()
                download.value.save_as(root / "chart_only.png")
                with Image.open(root / "chart_only.png") as chart_only:
                    chart_only.verify()
                with Image.open(root / "chart_only.png") as chart_only:
                    chart_only_size = chart_only.size
                print(f"没插图片时，下载出来的图表本身大小：{chart_only_size}")

                # 2. 插入一张图片——真实反馈"只有一张图片时，图片和图表可以放在同一行：
                #    图左、图表右"。qbar_Q1 里有两个 popover（插入图片是第一个，视觉上
                #    排在"编辑图表文字"左边），每个 popover 内部 Streamlit 会渲染 2 个
                #    <button> 节点（一个没有布局，只有另一个真正可见可点，见
                #    verify_crosstab_browser.py 里 click_key() 记录的同一个坑）——
                #    用 :visible 过滤，不要直接 get_by_role("button").first（那样选到的
                #    可能是第一个 popover 里那个不可见的按钮，点了没反应）。
                insert_image_popover = qbar.get_by_test_id("stPopover").nth(0)
                insert_image_popover.locator("button:visible").click()
                page.locator('[class*="st-key-img_upload_Q1_"] input[type="file"]').set_input_files(str(root / "photo1.png"))
                page.wait_for_timeout(800)
                page.keyboard.press("Escape")
                page.wait_for_timeout(500)

                assert not page_errors, f"页面出现异常：{page_errors}"

                # 排版断言：只有一张图时，图片和图表应该在同一行（并排的两个 st.columns，
                # 而不是图片单独占一整行、图表在下面）——用 bounding box 判断"图片"跟
                # "图表 iframe"是不是左右并排（顶部 y 坐标接近，图片的右边界大致在
                # 图表左边界附近或更靠左）。注意：图片/图表是在 qbar_Q1 这个标题横条
                # 容器关闭之后才渲染的（跟原来的代码结构一样，插入的图片和图表本来就
                # 不在标题横条这个 st.container 里面），所以要在整个页面里找，不能
                # 把定位范围收窄到 qbar 容器内部。
                # 这台装的 Streamlit 版本，st_echarts 是通过新的"bidi component"机制
                # 直接渲染在主文档里的一段 <div class="echarts-container">（内部是原生
                # SVG），不是旧版本那种独立 iframe——用图表自己的 key（chart_{q_no}）
                # 对应的 CSS class 精确定位，不用去猜 iframe 的 title。
                image_box = page.locator("[data-testid='stImage'] img").first.bounding_box()
                chart_box = page.locator(".st-key-chart_Q1 .echarts-container").first.bounding_box()
                assert image_box is not None and chart_box is not None, "图片或图表没有渲染出来"
                assert abs(image_box["y"] - chart_box["y"]) < 40, (
                    f"图片和图表看起来不在同一行（y 差太多）：image={image_box}, chart={chart_box}"
                )
                assert image_box["x"] < chart_box["x"], (
                    f"图片应该在图表左边：image={image_box}, chart={chart_box}"
                )
                print("排版确认：只有一张图片时，图片在左、图表在右，同一行。")
                page.screenshot(path=str(root / "single_image_side_by_side.png"))

                # 3. 复制/下载现在应该是"图片+图表"合成的一张图——真实反馈"不能只有
                #    图表自己"。合成图应该比只有图表时明显更宽（图左图表右并排）。
                with page.expect_download() as download:
                    page.locator(".st-key-chart_download_Q1 button:visible").click()
                download.value.save_as(root / "merged_one_image.png")
                with Image.open(root / "merged_one_image.png") as merged:
                    merged.verify()
                with Image.open(root / "merged_one_image.png") as merged:
                    merged_size = merged.size
                print(f"插入一张图片后，下载出来的合成图大小：{merged_size}")
                assert merged_size[0] > chart_only_size[0], (
                    f"合成图应该比单独的图表更宽（图片+图表并排），实际：合成图{merged_size} vs 图表{chart_only_size}"
                )

                # 4. 再插入第二张图片——两张图及以上应该退回"图片单独排版、图表在下面"
                #    （不再是并排一行），下载应该变成"图片行 + 图表"上下堆叠、更高。
                insert_image_popover.locator("button:visible").click()
                page.locator('[class*="st-key-img_upload_Q1_"] input[type="file"]').last.set_input_files(str(root / "photo2.png"))
                page.wait_for_timeout(800)
                page.keyboard.press("Escape")
                page.wait_for_timeout(500)
                assert not page_errors, f"页面出现异常：{page_errors}"

                assert page.get_by_text("每行放几张").count() > 0, (
                    "两张图片时应该出现「每行放几张」这个排版设置——现在这个设置不见了，"
                    "说明没有退回到网格排版模式"
                )

                with page.expect_download() as download:
                    page.locator(".st-key-chart_download_Q1 button:visible").click()
                download.value.save_as(root / "merged_two_images.png")
                with Image.open(root / "merged_two_images.png") as merged2:
                    merged2.verify()
                with Image.open(root / "merged_two_images.png") as merged2:
                    merged2_size = merged2.size
                print(f"插入两张图片后，下载出来的合成图大小：{merged2_size}")
                assert merged2_size[1] > merged_size[1], (
                    f"两张图片应该堆在图表上面（更高），不是并排（应该比一张图片时的合成图更高）："
                    f"两张图{merged2_size} vs 一张图{merged_size}"
                )

                page.screenshot(path=str(root / "two_images_stacked.png"))
                assert not page_errors, f"页面出现异常：{page_errors}"

            print("Playwright 全流程通过：单张图片跟图表并排显示，复制/下载合成了图片+图表。", flush=True)
        finally:
            server.terminate()
            server.wait(timeout=10)


if __name__ == "__main__":
    main()
