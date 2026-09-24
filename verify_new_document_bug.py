"""真机验收："新建问卷分析"不能带着上一份问卷的标题/document_id，保存不能覆盖上一份。

复制代码到临时目录，只操作合成 CSV 和临时数据库，不碰真实数据。
运行：.venv/bin/python verify_new_document_bug.py
"""

from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

import requests
from playwright.sync_api import expect, sync_playwright

from engine import db

ROOT = Path(__file__).resolve().parent


def prepare_runtime(root: Path) -> None:
    for folder in ("app_streamlit", "engine", ".streamlit"):
        shutil.copytree(ROOT / folder, root / folder, ignore=shutil.ignore_patterns("__pycache__"))
    (root / "data").mkdir()
    (root / "data" / "uploads").mkdir()
    # main 分支默认界面语言是英文（internal 分支才默认中文）——脚本里的定位器都是
    # 中文文案，跟哪个分支的 DEFAULT_LANG 无关，直接在这份全新的临时数据库里把
    # 语言设置写成中文，两个分支跑这份脚本都一样可靠。
    conn = db.init_db(str(root / "data/app.db"))
    db.set_setting(conn, "ui_language", "zh")
    conn.close()
    (root / "doc_a.csv").write_text("Q1\nA\nB\nA\nC\n", encoding="utf-8")
    (root / "doc_b.csv").write_text("Q1\nX\nY\nX\nX\nY\n", encoding="utf-8")


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="newdoc-bug-"))
    print(f"验收目录（只含合成数据）：{root}", flush=True)
    prepare_runtime(root)
    port = 8531
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
                page.set_default_timeout(20000)
                page.on("pageerror", lambda e: (_ for _ in ()).throw(AssertionError(f"page error: {e}")))

                # 1. 新建项目 → 新建问卷分析 → 上传文档 A → 生成分析（触发首次自动保存）。
                page.goto(url)
                page.get_by_text("+ 新建项目", exact=True).click()
                page.get_by_label("项目名（对应客户/项目名称）").fill("__TEST__新建覆盖bug验收")
                page.get_by_role("button", name="创建", exact=True).click()
                page.wait_for_url("**/project_view**")

                page.get_by_role("button", name="+ 新建问卷分析", exact=True).click()
                page.wait_for_url("**/app**")
                page.set_input_files('input[type="file"]', str(root / "doc_a.csv"))
                page.get_by_role("button", name="生成分析", exact=True).click()
                page.wait_for_selector('text=已保存到数据库', timeout=15000)

                title_input_a = page.locator(".st-key-document_title_input input")
                expect(title_input_a).to_have_value("doc_a.csv")

                with sqlite3.connect(root / "data/app.db") as conn:
                    docs_after_a = conn.execute("SELECT id, title FROM documents").fetchall()
                assert len(docs_after_a) == 1, f"应该只有 1 份文档，实际：{docs_after_a}"
                doc_a_id, doc_a_title = docs_after_a[0]
                print(f"文档 A 已保存：id={doc_a_id}, title={doc_a_title!r}")

                # 2. 回项目工作区 → 再次点"+ 新建问卷分析" → 上传文档 B。
                page.get_by_role("button", name="← 返回项目工作区", exact=True).click()
                page.wait_for_url("**/project_view**")
                page.get_by_role("button", name="+ 新建问卷分析", exact=True).click()
                page.wait_for_url("**/app**")

                # 核心断言 1：这一刻页面上不应该还留着文档 A 的标题/任何痕迹——应该是
                # 全新的上传界面（还没有 document_title_input 这个控件，因为还没上传文件）。
                assert page.locator(".st-key-document_title_input").count() == 0, \
                    "bug 复现：新建分析页面在上传新文件之前就已经显示了标题输入框（说明带着上一份文档的状态）"

                page.set_input_files('input[type="file"]', str(root / "doc_b.csv"))
                page.get_by_role("button", name="生成分析", exact=True).click()
                page.wait_for_selector('text=已保存到数据库', timeout=15000)

                # 核心断言 2：标题必须是文档 B 的文件名，不能是文档 A 的标题。
                title_input_b = page.locator(".st-key-document_title_input input")
                expect(title_input_b).to_have_value("doc_b.csv")

                # 核心断言 3（最关键）：数据库里必须有两份独立的文档，文档 A 必须原样
                # 还在（标题没被文档 B 覆盖），不能变成只有一份被覆盖过的记录。
                with sqlite3.connect(root / "data/app.db") as conn:
                    docs_after_b = conn.execute("SELECT id, title FROM documents ORDER BY id").fetchall()
                assert len(docs_after_b) == 2, f"bug 复现：应该有 2 份独立文档，实际：{docs_after_b}"
                ids = [row[0] for row in docs_after_b]
                titles = {row[0]: row[1] for row in docs_after_b}
                assert doc_a_id in ids, f"文档 A（id={doc_a_id}）不见了：{docs_after_b}"
                assert titles[doc_a_id] == doc_a_title, \
                    f"bug 复现：文档 A 的标题被覆盖了，原来是 {doc_a_title!r}，现在是 {titles[doc_a_id]!r}"
                doc_b_id = [i for i in ids if i != doc_a_id][0]
                assert titles[doc_b_id] == "doc_b.csv"

                print(f"文档 B 已保存为独立的新文档：id={doc_b_id}, title={titles[doc_b_id]!r}")
                print(f"文档 A 原样保留：id={doc_a_id}, title={titles[doc_a_id]!r}")
                browser.close()

            print("Playwright 全流程通过：新建分析不再带上一份的标题，也不会覆盖上一份文档。", flush=True)
        finally:
            server.terminate()
            server.wait(timeout=10)


if __name__ == "__main__":
    main()
