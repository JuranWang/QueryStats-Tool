"""真机验收：横条图（bar_h）选项文字很长、需要换行时，类目标签不能叠在一起，
也不能因为高估换行行数而把整张图撑得比例失调（大片空白、短标签的行也被迫
跟最长的那条一样高）。

真实反馈（真实截图复现）：
1. "文字多了以后排版异常"——长的中英双语选项换行后，每个类目分到的高度还是
   按"一行文字"算的固定值，换行后的文字会溢出到相邻类目，看起来叠成一团。
2. 修好①之后又反馈"第一张图为什么比例失调了"——换行行数的估算比例是从
   matplotlib 导出图那套抄来的，跟浏览器 SVG 实际渲染的字符宽度不是一回事，
   系统性地高估了换行行数（尤其是英文占比高的标签），而 ECharts 类目轴是把
   总高度平均分给每一个类目，只要有一条标签的行数被高估，全部类目都会跟着
   多出一截没用的空白。

复制代码到临时目录，只操作合成问卷和临时数据库。
运行：.venv/bin/python verify_bar_label_wrap.py
"""

from pathlib import Path
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

# 场景一：真实反馈复现用的选项文字——直接照抄真实截图里那道"图案或设计"单选题
# 最长的几个选项，不编造，这样这条回归测试锁定的就是真实出过问题的那批文字长度。
PATTERN_OPTIONS = [
    "- 其他 / - Other",
    "- 儿童/趣味 / - Kids / playful",
    "- 我不知道 / - I don't know",
    "- 有纹理，几乎没有或没有可见图案 / - Textured with little or no visible pattern",
    "- 纯色，一种主导颜色，几乎没有或没有可见图案 / - Solid color, one dominant color with little or no visible pattern",
    "- 传统，如波斯、东方、复古风格、花卉、华丽 / - Traditional, such as Persian, Oriental, vintage-inspired, floral, ornate",
]
PATTERN_COUNTS = [97, 72, 28, 14, 1, 1]

# 场景二："比例失调"反馈用的原始选项文字（"质地或构造"题）——短标签（1 行）
# 和长标签（真机确认最长要换 4 行）混在同一张图里，专门用来抓"某一条标签的
# 换行行数被高估，连带把所有短标签的行也撑得一样高"这类问题。真机量出来的
# 每条标签实际换行行数（ECharts 渲染结果，不是估算值）：1/1/2/2/1/3/4/2。
TEXTURE_OPTIONS = [
    "- 编织的 / - Braided",
    "- 不确定 / - Not sure",
    "- 长绒 / 非常蓬松 / - Shag / very fluffy",
    "- 不同质地或高度的混合 / - A mix of different textures or heights",
    "- 厚实且柔软 / - Thick and plush",
    "- 柔软的纤维在表面直立 / - Soft fibers that stand upright across the surface",
    "- 平坦且看起来像编织的，几乎没有或完全没有可见的绒面 / - Flat and woven-looking, with little or no visible pile",
    "- 表面纤维短而均匀 / - Short and even fibers across the surface",
]
TEXTURE_COUNTS = [1, 5, 14, 18, 19, 35, 46, 76]
TEXTURE_REAL_MAX_LINES = 4  # 真机确认过的最长标签实际换行数，见上面注释


def prepare_runtime(root: Path, options: list[str], counts: list[int], title: str) -> None:
    for folder in ("app_streamlit", "engine", ".streamlit"):
        shutil.copytree(ROOT / folder, root / folder, ignore=shutil.ignore_patterns("__pycache__"))
    (root / "data").mkdir()
    conn = db.init_db(str(root / "data/app.db"))
    db.set_setting(conn, "ui_language", "zh")

    project_id = db.create_project(conn, "验收项目", "en", "zh")
    method = dict(platform_source=None, is_branched=False, branch_count=None, screen_out_rule=None, skip_logic_note=None)
    values = []
    for option, count in zip(options, counts):
        values.extend([option] * count)
    units = [dict(kind="single", title=title, display_no="Q1", columns=["Q1"], section="正式")]
    df = pd.DataFrame({"Q1": values})
    persistence.save_analysis(conn, project_id, units, df, {}, {}, method, [], "test.csv", title=f"__TEST__{title}")
    conn.close()


def run_scenario(
    scenario_name: str, port: int, options: list[str], counts: list[int], title: str,
    max_box_height: float | None = None,
) -> None:
    root = Path(tempfile.mkdtemp(prefix=f"bar-label-wrap-{scenario_name}-"))
    print(f"[{scenario_name}] 验收目录（只含合成数据）：{root}", flush=True)
    prepare_runtime(root, options, counts, title)
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
                page.wait_for_selector(".st-key-qbar_Q1", timeout=15000)
                assert not page_errors, f"[{scenario_name}] 页面出现异常：{page_errors}"

                page.locator(".st-key-chart_Q1 .echarts-container").scroll_into_view_if_needed()
                page.wait_for_timeout(500)
                page.screenshot(path=str(root / "bar_label_wrap.png"), full_page=False)

                # 核心断言 1：每个类目的 y 轴标签整体高度（跟相邻类目标签）不能有
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
                            return {top: centerY - halfHeight, bottom: centerY + halfHeight, height: halfHeight * 2};
                        })
                        .filter(b => b !== null)
                    """,
                )
                assert len(boxes) == len(options), (
                    f"[{scenario_name}] 没能量到全部 {len(options)} 个类目标签的命中区域，量到 {len(boxes)} 个——"
                    "可能是 ECharts 内部实现变了，这条断言的 selector 需要跟着更新，不能当成通过"
                )
                sorted_boxes = sorted(boxes, key=lambda b: b["top"])
                overlaps = []
                for a, b in zip(sorted_boxes, sorted_boxes[1:]):
                    if a["bottom"] > b["top"] + 0.5:  # 留半像素误差余量，避免浮点误差误报
                        overlaps.append((a, b))

                print(f"[{scenario_name}] 量到 {len(boxes)} 个标签分组，重叠数：{len(overlaps)}")
                if overlaps:
                    print(f"[{scenario_name}] 重叠详情：", overlaps)
                assert not overlaps, f"[{scenario_name}] y 轴标签仍然有重叠：{overlaps}"

                # 核心断言 2（"比例失调"回归锁定）：真机确认过 ECharts 类目轴给每个
                # 类目分配的"带宽"（相邻类目中心点 centerY 的间距）是完全一致的
                # （这是 ECharts 自己的行为，符合预期），但每条标签自己的命中区域
                # 高度是按它实际渲染了几行文字来定的，不会被拉伸到跟带宽一样高——
                # 短标签只占一行，长标签占几行，各自居中放在这个统一带宽里。所以
                # "比例失调"真正能量化的地方不是"每条标签的高度是否相等"（本来就
                # 不该相等），而是这个统一带宽本身**不该比这批标签里最长的那一条
                # 实际需要的高度多出太多**——带宽跟最长标签高度贴得越近，图表就
                # 越紧凑，短标签周围的"没用上的空白"也越少。
                center_ys = sorted(b["top"] + b["height"] / 2 for b in boxes)
                band_gaps = {round(b - a, 1) for a, b in zip(center_ys, center_ys[1:])}
                assert len(band_gaps) == 1, (
                    f"[{scenario_name}] 各类目之间的带宽间距不一致（ECharts 类目轴应该是平分总高度的）：{band_gaps}"
                )
                band_gap = band_gaps.pop()
                tallest_label_height = max(b["height"] for b in boxes)
                assert band_gap >= tallest_label_height - 0.5, (
                    f"[{scenario_name}] 带宽间距 {band_gap}px 比最长标签实际需要的 {tallest_label_height}px 还小——"
                    "这本该是不可能出现的（跟断言 1 的重叠检查矛盾），selector 或算法可能哪里错了。"
                )
                if max_box_height is not None:
                    assert band_gap <= max_box_height, (
                        f"[{scenario_name}] 带宽间距是 {band_gap}px（最长标签实际只需要 {tallest_label_height}px），"
                        f"超过了按真机确认的最长标签算出来的上限 {max_box_height}px——"
                        "换行行数估算可能又开始系统性高估了，图表会比实际需要的更空旷、比例失调。"
                    )
                print(f"[{scenario_name}] 带宽间距：{band_gap}px，最长标签实际高度：{tallest_label_height}px")

                assert not page_errors, f"[{scenario_name}] 页面出现异常：{page_errors}"

            print(f"[{scenario_name}] Playwright 验收通过。", flush=True)
        finally:
            server.terminate()
            server.wait(timeout=10)


def main() -> None:
    run_scenario("pattern", 8561, PATTERN_OPTIONS, PATTERN_COUNTS, "以下哪项最能描述这块地毯的图案或设计？")
    # 每个类目分到的高度 = max(46, 真实最长行数*16+14)，留 1 行的估算误差余量
    # （比如真的变成 5 行也不算失败，但不能离谱地估成 7、8 行）。
    max_height = (TEXTURE_REAL_MAX_LINES + 1) * 16 + 14
    run_scenario("texture", 8562, TEXTURE_OPTIONS, TEXTURE_COUNTS, "你会如何描述这块地毯的质地或构造？", max_box_height=max_height)


if __name__ == "__main__":
    main()
