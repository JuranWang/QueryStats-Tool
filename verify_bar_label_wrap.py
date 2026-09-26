"""真机验收：横条图（bar_h）选项文字很长、需要换行时，类目标签不能叠在一起。

真实反馈（真实截图复现）："文字多了以后排版异常"——长的中英双语选项换行后，
每个类目分到的高度还是按"一行文字"算的固定值，换行后的文字会溢出到相邻类目，
看起来叠成一团。

复制代码到临时目录，只操作合成问卷和临时数据库。
运行：.venv/bin/python verify_bar_label_wrap.py
"""

from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import time

import pandas as pd
import requests
from playwright.sync_api import sync_playwright

from engine import db, persistence

ROOT = Path(__file__).resolve().parent

# 真实反馈复现用的选项文字——直接照抄真实截图里那道"图案或设计"单选题最长的
# 几个选项，不编造，这样这条回归测试锁定的就是真实出过问题的那批文字长度。
LONG_OPTIONS = [
    "- 其他 / - Other",
    "- 儿童/趣味 / - Kids / playful",
    "- 我不知道 / - I don't know",
    "- 有纹理，几乎没有或没有可见图案 / - Textured with little or no visible pattern",
    "- 纯色，一种主导颜色，几乎没有或没有可见图案 / - Solid color, one dominant color with little or no visible pattern",
    "- 传统，如波斯、东方、复古风格、花卉、华丽 / - Traditional, such as Persian, Oriental, vintage-inspired, floral, ornate",
]


def prepare_runtime(root: Path) -> None:
    for folder in ("app_streamlit", "engine", ".streamlit"):
        shutil.copytree(ROOT / folder, root / folder, ignore=shutil.ignore_patterns("__pycache__"))
    (root / "data").mkdir()
    conn = db.init_db(str(root / "data/app.db"))
    db.set_setting(conn, "ui_language", "zh")

    project_id = db.create_project(conn, "验收项目", "en", "zh")
    method = dict(platform_source=None, is_branched=False, branch_count=None, screen_out_rule=None, skip_logic_note=None)
    # 单选题选项超过 5 个会走 bar_h（见 chart_spec.choose_chart_type），凑够 6 个
    # 选项，人数按真实截图大致的分布给（不需要精确，只是不要全一样方便肉眼确认）。
    counts = [97, 72, 28, 14, 1, 1]
    values = []
    for option, count in zip(LONG_OPTIONS, counts):
        values.extend([option] * count)
    units = [dict(kind="single", title="以下哪项最能描述这块地毯的图案或设计？", display_no="Q1", columns=["Q1"], section="正式")]
    df = pd.DataFrame({"Q1": values})
    persistence.save_analysis(conn, project_id, units, df, {}, {}, method, [], "test.csv", title="__TEST__长选项换行验收")
    conn.close()


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="bar-label-wrap-"))
    print(f"验收目录（只含合成数据）：{root}", flush=True)
    prepare_runtime(root)
    port = 8561
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
                page = browser.new_page(viewport={"width": 1600, "height": 1400})
                page.set_default_timeout(20000)
                page_errors = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))

                page.goto(url)
                page.get_by_role("button", name="打开", exact=True).first.click()
                page.wait_for_url("**/project_view**")
                page.get_by_role("button", name="打开", exact=True).first.click()
                page.wait_for_url("**/app**")
                page.get_by_role("button", name="生成分析", exact=True).click()
                page.wait_for_timeout(3000)
                page.wait_for_selector(".st-key-qbar_Q1", timeout=10000)
                assert not page_errors, f"页面出现异常：{page_errors}"

                page.locator(".st-key-chart_Q1 .echarts-container").scroll_into_view_if_needed()
                page.wait_for_timeout(500)
                page.screenshot(path=str(root / "bar_label_wrap.png"), full_page=False)

                # 核心断言：每个类目的 y 轴标签整体高度（跟相邻类目标签）不能有
                # 垂直方向的重叠——这是真实反馈"叠在一起"的直接、可量化定义。
                #
                # 真机 dump 出来的 SVG 结构确认过：ECharts 给每个类目标签配了一个
                # 不可见的命中区域 <path d="M-170 {-半高}l170 0l0 {全高}l-170 0Z"
                # transform="translate(x centerY)">——"170"正是我们自己传给
                # axisLabel 的 width，宽度精确匹配不是巧合，这就是 ECharts 自己算出来
                # 的"这个类目标签实际占的完整包围盒"（换行几行都已经算在"全高"里面），
                # 比我自己去猜页面里哪几个 <text> 属于同一个类目更可靠——直接读
                # ECharts 自己算的结果，不是重新发明一遍它的布局逻辑。
                boxes = page.eval_on_selector_all(
                    ".st-key-chart_Q1 .echarts-container svg path",
                    """els => els
                        .map(el => {
                            const d = el.getAttribute("d") || "";
                            const m = d.match(/^M-170 (-?[\\d.]+)l170 0l0 ([\\d.]+)l-170 0Z$/);
                            if (!m) return null;
                            const t = (el.getAttribute("transform") || "").match(/translate\\(([\\d.-]+) ([\\d.-]+)\\)/);
                            if (!t) return null;
                            const centerY = parseFloat(t[2]);
                            const halfHeight = -parseFloat(m[1]);
                            return {top: centerY - halfHeight, bottom: centerY + halfHeight};
                        })
                        .filter(b => b !== null)
                    """,
                )
                assert len(boxes) == len(LONG_OPTIONS), (
                    f"没能量到全部 {len(LONG_OPTIONS)} 个类目标签的命中区域，量到 {len(boxes)} 个——"
                    "可能是 ECharts 内部实现变了，这条断言的 selector 需要跟着更新，不能当成通过"
                )
                boxes = sorted(boxes, key=lambda b: b["top"])
                overlaps = []
                for a, b in zip(boxes, boxes[1:]):
                    if a["bottom"] > b["top"] + 0.5:  # 留半像素误差余量，避免浮点误差误报
                        overlaps.append((a, b))

                print(f"量到 {len(boxes)} 个标签分组，重叠数：{len(overlaps)}")
                if overlaps:
                    print("重叠详情：", overlaps)
                assert not overlaps, f"y 轴标签仍然有重叠：{overlaps}"

                assert not page_errors, f"页面出现异常：{page_errors}"

            print("Playwright 验收通过：长选项换行后，y 轴标签之间不再重叠。", flush=True)
        finally:
            server.terminate()
            server.wait(timeout=10)


if __name__ == "__main__":
    main()
