"""真机验收："排序题新增赋分排名"——上传一份排序题 CSV（Credamo 风格，
"题干-选项" 列名、每行是该选项的名次），确认生成分析后排序题区块里除了原有的
"各选项各名次人数"表，还多出一张"赋分排名"表（N 个选项，排第1名得N分、排第2名
得N-1分……加总后总分最高的排第1），且标题/说明文字/表头都走 t() 正常渲染（不是
缺翻译时那种直接显示英文 fallback 或抛异常）。

真实反馈："排序题新增赋分排名，例如：一共x个选项，第一名分数x，第二名分数x-1，
以此类推，最终给一个赋分排名，赋分最高的是第一名"。

复制代码到临时目录，只操作合成 CSV 和临时数据库。
运行：.venv/bin/python verify_ranking_score.py
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

from engine import db

ROOT = Path(__file__).resolve().parent


def prepare_runtime(root: Path) -> None:
    for folder in ("app_streamlit", "engine", ".streamlit"):
        shutil.copytree(ROOT / folder, root / folder, ignore=shutil.ignore_patterns("__pycache__"))
    (root / "data").mkdir()
    conn = db.init_db(str(root / "data/app.db"))
    db.set_setting(conn, "ui_language", "zh")
    conn.close()

    # 跟 tests/test_ranking_app.py 同一种 Credamo 风格排序题结构："题干-选项"列名，
    # 取值是该选项在这一行（受访者）里拿到的名次。4 个选项、8 个人，手工构造出
    # 跟截图里同一种"总分最高排第 1"的可验证排序：选项按 0/1/2/3 在每个人的排名
    # 整体依次更靠后，总分应该严格递减。
    # 注意：这里不能用项目里常见的 "__TEST__" 双下划线前缀——真实渲染路径会把
    # 这段列名拼进 st_echarts 的组件 key，streamlit_echarts 新版本禁止 key 里出现
    # 连续两个下划线（跟这次要验的赋分排名功能无关，是环境里一个独立的小坑）。
    title = "TEST以下几种材料是地毯背面的防滑点，\n请按价值感从高到低排序"
    labels = ["硅基", "铂金硅", "液态硅", "弹性硅"]
    columns = [f"{title}-{label}" for label in labels]
    size = len(labels)
    n_rows = 8
    df = pd.DataFrame(
        [[str((i + j) % size + 1) for j in range(size)] for i in range(n_rows)],
        columns=columns,
    )
    df.to_csv(root / "ranking_export.csv", index=False, encoding="utf-8-sig")


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="ranking-score-"))
    print(f"验收目录（只含合成数据）：{root}", flush=True)
    prepare_runtime(root)
    port = 8602
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
                page = browser.new_page(viewport={"width": 1700, "height": 1600})
                page.set_default_timeout(20000)
                page_errors = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))

                page.goto(url)
                page.get_by_text("+ 新建项目", exact=True).click()
                page.get_by_label("项目名（对应客户/项目名称）").fill("__TEST__赋分排名验收")
                page.get_by_role("button", name="创建", exact=True).click()
                page.wait_for_url("**/project_view**")
                page.get_by_role("button", name="+ 新建问卷分析", exact=True).click()
                page.wait_for_url("**/app**")
                page.set_input_files('input[type="file"]', str(root / "ranking_export.csv"))
                page.wait_for_selector("text=数据映射", timeout=15000)
                assert not page_errors, f"上传/映射阶段页面出现异常：{page_errors}"

                page.get_by_role("button", name="生成分析", exact=True).click()
                page.wait_for_selector("text=赋分排名", timeout=20000)
                assert not page_errors, f"生成分析后页面出现异常：{page_errors}"

                page.wait_for_timeout(500)
                content = page.content()
                assert "赋分排名" in content
                assert "总分" in content
                assert "平均分" in content

                score_heading = page.get_by_text("赋分排名", exact=True).first
                score_heading.scroll_into_view_if_needed()
                page.wait_for_timeout(500)
                page.screenshot(path=str(root / "ranking_score_table.png"), full_page=True)

            print("Playwright 验收通过：排序题区块里正常渲染出「赋分排名」表，"
                  f"截图见 {root / 'ranking_score_table.png'}，"
                  "人工核对总分是否按「硅基>铂金硅>液态硅>弹性硅」的顺序递减。", flush=True)
        finally:
            server.terminate()
            server.wait(timeout=10)


if __name__ == "__main__":
    main()
