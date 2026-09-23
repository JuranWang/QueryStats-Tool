"""Playwright 全流程验收：复制代码到临时目录，只操作合成问卷和临时数据库。

运行：.venv/bin/python verify_crosstab_browser.py
需要允许启动本地服务与 Chromium 的环境；截图/下载/日志保留在打印的临时目录。
"""

from pathlib import Path
import argparse
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import requests

import pandas as pd
from PIL import Image
from playwright.sync_api import expect, sync_playwright

from engine import db, persistence


ROOT = Path(__file__).resolve().parent


def prepare_runtime(root):
    for folder in ("app_streamlit", "engine", ".streamlit"):
        shutil.copytree(ROOT / folder, root / folder, ignore=shutil.ignore_patterns("__pycache__"))
    (root / "data").mkdir()
    conn = db.init_db(str(root / "data/app.db"))
    db.set_setting(conn, "ui_language", "zh")
    units = [
        dict(kind="single", title="偏好", display_no="Q1", columns=["Q1"], section="正式"),
        dict(kind="multi", title="选择", display_no="Q2", columns=["选择 (A)", "选择 (B)"], section="正式"),
    ]
    method = dict(platform_source=None, is_branched=False, branch_count=None, screen_out_rule=None, skip_logic_note=None)
    for number in (1, 2):
        project = db.create_project(conn, f"验收项目{number}", "en", "zh")
        df = pd.DataFrame({"Q1": ["A", "A", "B", "C"], "选择 (A)": [True, True, False, False], "选择 (B)": [True, False, True, False]})
        persistence.save_analysis(conn, project, units, df, {}, {}, method, [], f"test{number}.csv", title=f"验收问卷{number}")
    conn.close()
    Image.new("RGB", (240, 120), "#245785").save(root / "evidence.png")


def run_browser(root, url):
    def extras():
        with sqlite3.connect(root / "data/app.db") as conn:
            row = conn.execute("SELECT payload_json FROM document_extras WHERE document_id=1").fetchone()
        return json.loads(row[0])

    def wait_saved(check):
        # 真机验证发现的坑：点完按钮到 Streamlit 服务端真正跑完这次 rerun、把
        # 结果写进 document_extras 之间有一小段异步延迟——点击本身不会阻塞到
        # 落库完成。这段时间里 extras() 读到的可能是"还没有这个字段"的旧数据，
        # check(data) 直接按下标/键名取值会抛 KeyError/IndexError，这个异常原来
        # 没有被下面的循环接住，第一次轮询没赶上就直接整个函数崩溃退出，等于
        # 完全没有真正"轮询等待"，只是显得像在等。改成把 check(data) 包一层
        # try/except，取不到就当"还没落库"处理，继续下一轮，而不是让异常
        # 直接从这里往外冒。
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            data = extras()
            try:
                if check(data):
                    return data
            except (KeyError, IndexError, TypeError):
                pass
            time.sleep(0.2)
        raise AssertionError(f"Expected saved state was not observed: {extras()}")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1600, "height": 1200}, permissions=["clipboard-read", "clipboard-write"], accept_downloads=True)
        page = context.new_page()
        page.set_default_timeout(30000)
        page_errors = []
        page.on("pageerror", lambda error: page_errors.append(str(error)))

        def css_key(key):
            # 真机验证发现：st.xxx(key=...) 生成的 "st-key-<key>" class，凡是
            # [A-Za-z0-9_] 以外的字符（中文、"｜"、"::" 里的冒号……）都会被逐字符
            # 替换成 "-"（不是整体去掉、也不是合并成一个 "-"）——"xtb_1_left_groups
            # ::Q1｜偏好_name_0" 会变成 "xtb_1_left_groups--Q1---_name_0"。凡是 key
            # 本身拼了题目原文（中文）的控件，都得按这个规则转换一遍才能定位到，
            # 不能直接拿原始 key 当 CSS class 用。
            return "st-key-" + re.sub(r"[^A-Za-z0-9_]", "-", key)

        def click_key(key):
            # 真机验证发现：像下载按钮这类控件，Streamlit 内部会同时渲染 2 个
            # <button> 节点，其中一个没有布局（bounding box 是 None，即
            # display:none 之类），只有另一个是真正可见可点的——不是页面重复
            # 渲染了两份内容（读 app.py 源码确认这个按钮只有一处调用），是这个
            # 控件自己内部的实现细节（怀疑是"准备中/就绪"两态之间用可见性切换、
            # 不是整个换掉节点）。严格模式下 Playwright 遇到多个匹配会直接报错，
            # 用 :visible 只挑真正可见的那个，不要用 .first/.last 猜位置——两次
            # 实测发现"可见的是第几个"并不固定。
            btn = page.locator(f".{css_key(key)} button:visible")
            btn.scroll_into_view_if_needed()
            btn.click()

        def select_key(key, label):
            # 真机验证发现：这台装的 Streamlit 版本，下拉选项渲染出来的是普通
            # <div>，不带 role="option"（不是所有 Streamlit/BaseWeb 版本都这样），
            # get_by_role("option", ...) 在这个版本上永远等不到匹配，改成按文字
            # 精确匹配定位，跟版本无关，更稳。
            combo = page.locator(f".{css_key(key)}").get_by_role("combobox")
            combo.scroll_into_view_if_needed()
            combo.click()
            page.wait_for_timeout(400)  # 下拉弹层是异步渲染的，给一点缓冲再找选项
            # exact=True 在这个版本上反而经常匹配不上（怀疑是 BaseWeb 渲染的选项
            # 文字节点前后带了不可见空白/嵌套 span，"精确相等"判断不通过而"包含"
            # 判断没问题）——用 text= 子串定位，跟前面调试脚本里验证过能点中的
            # 写法保持一致。
            page.locator(f"text={label}").last.click(timeout=5000)

        def open_document():
            page.goto(url)
            click_key("open_project_1")
            click_key("open_doc_1")
            # 真机验证发现：从项目工作区"打开"一份历史分析，进来之后"原始数据"
            # 步骤默认还是展开的、需要手动点一次"生成分析"才会渲染下面 1~11 全部
            # 正文（包括第 8 节交叉分析）——这不是这次交叉分析改动引入的行为，是
            # 这个工具本来就有的设计（st.session_state["generated"] 这个开关，
            # 历史记录加载不会自动置真），验收脚本这一步之前漏掉了。
            page.get_by_role("button", name="生成分析", exact=True).click()
            expect(page.locator(".st-key-crosstab_block_1")).to_be_visible()

        open_document()
        block1 = page.locator(".st-key-crosstab_block_1")
        expect(block1.get_by_text("1. 选择问卷", exact=True)).to_have_count(2)
        select_key("xtb_1_right_question", "Q2｜选择")
        # 真机验证发现：block1.get_by_role("textbox") 数出来是 0——这个 Streamlit
        # 版本里 st.text_input 的实际可见输入框并不总能被当成隐式 role="textbox"
        # 命中（怀疑跟内部包装结构有关），靠"数第几个 textbox"来定位这道题的第
        # 一个维度名称输入框不可靠。改成用 css_key() 精确定位这个字段自己的 key
        # 对应的 CSS class，不依赖数量/顺序假设。
        left_group_key = "xtb_1_left_groups::Q1｜偏好"
        left_name_0 = page.locator(f".{css_key(left_group_key)}_name_0").locator("input")
        left_name_0.fill("自定义 A")
        left_name_0.press("Enter")
        # 真机验证发现：text_input 的 Enter 会触发一次异步 rerun，Streamlit 会把
        # 下面这些按钮对应的 DOM 节点卸载重挂载；这次 rerun 还没跑完就紧接着点
        # "生成交叉分析"，点击有一定概率落在正在被替换掉的旧节点上、悄悄没有
        # 任何效果（现象：extras 里完全没有 crosstab_blocks 这个字段，看起来像是
        # 这个按钮点击整个没生效，而不是生成逻辑本身有问题）。等这次 rerun 稳定
        # 下来再点，等同于真实用户手速不会快到卡在两次 rerun 中间这一下。
        page.wait_for_timeout(500)
        click_key("xtb_1_run")
        wait_saved(lambda x: x["crosstab_blocks"][0]["result"] is not None)
        assert extras()["crosstab_blocks"][0]["result"]["kind"] == "same_doc"
        # 真机验证发现：直接对 block1（st.container(border=True) 生成的
        # stVerticalBlock）这个 locator 调用 .screenshot() 会一直卡到超时——这个
        # 容器的布局方式（direction: column 的 flex 容器）让 Playwright 量不出
        # 一个正常的可截图边界（"waiting for fonts to load" 卡死），不是内容
        # 没渲染出来（前面用整页截图已经确认这块内容是正常显示的）。截图只是
        # 留证据用，不是功能断言，改成滚动到这块区域后截整个视口，效果一样。
        block1.scroll_into_view_if_needed()
        page.screenshot(path=str(root / "same_doc.png"))

        click_key("xtb_add_block")
        block2 = page.locator(".st-key-crosstab_block_2")
        select_key("xtb_2_right_doc", "验收项目2 · 验收问卷2 · #2")
        click_key("xtb_2_run")
        saved = wait_saved(lambda x: len(x["crosstab_blocks"]) == 2 and x["crosstab_blocks"][1]["result"] is not None)
        assert saved["crosstab_blocks"][1]["result"]["kind"] == "cross_doc"
        with page.expect_download() as download:
            click_key("xtb_2_download")
        download.value.save_as(root / "download.png")
        with Image.open(root / "download.png") as image:
            assert image.format == "PNG"
            image.verify()
        copy_frame = next(frame for frame in page.frames if frame.locator("#xtb_2_copy").count())
        copy_frame.locator("#xtb_2_copy").click()
        expect(copy_frame.locator("#xtb_2_copy_status")).to_have_text("已复制")
        assert page.evaluate("async () => (await navigator.clipboard.read()).some(item => item.types.includes('image/png'))")
        block2.scroll_into_view_if_needed()
        page.screenshot(path=str(root / "cross_doc.png"))

        block2.get_by_test_id("stPopover").get_by_role("button").first.click()
        page.locator('[class*="st-key-img_upload_crosstab_block_2_"] input[type="file"]').set_input_files(root / "evidence.png")
        wait_saved(lambda x: bool(x.get("images", {}).get("crosstab_block_2")))
        page.keyboard.press("Escape")
        click_key("manual_save_button")
        page.reload()
        # 新 session 从项目列表重新打开，证明结果不是靠旧页面内存存活。
        open_document()
        expect(page.locator(".st-key-crosstab_block_2")).to_be_visible()
        restored = extras()
        assert [b["result"] for b in restored["crosstab_blocks"]] == [b["result"] for b in saved["crosstab_blocks"]]
        assert restored["images"]["crosstab_block_2"]
        expect(page.locator(f".{css_key(left_group_key)}_name_0").locator("input")).to_have_value("自定义 A")
        click_key("xtb_1_delete_block")
        expect(page.locator(".st-key-crosstab_block_1")).to_have_count(0)
        click_key("xtb_2_delete_block")
        wait_saved(lambda x: x["crosstab_blocks"] == [])
        click_key("xtb_add_block")
        expect(page.locator(".st-key-crosstab_block_3")).to_be_visible()
        assert not page_errors, page_errors
        expect(page.locator('[data-testid="stException"]')).to_have_count(0)
        page.screenshot(path=str(root / "final.png"))
        browser.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8502)
    args = parser.parse_args()
    root = Path(tempfile.mkdtemp(prefix="crosstab-browser-"))
    print(f"验收目录（只含合成数据）：{root}", flush=True)
    prepare_runtime(root)
    url = f"http://127.0.0.1:{args.port}"
    with (root / "server.log").open("w") as log:
        server = subprocess.Popen([sys.executable, "-m", "streamlit", "run", str(root / "app_streamlit/Home.py"),
                                   "--server.port", str(args.port), "--server.headless", "true", "--browser.gatherUsageStats", "false"],
                                  cwd=root, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 30
            while True:
                if server.poll() is not None:
                    raise RuntimeError((root / "server.log").read_text())
                try:
                    # 这台机器上装的 Streamlit 版本内部跑的是 Uvicorn（不是老版本的
                    # Tornado）——urllib.request.urlopen 发出的请求会被 Uvicorn 判成
                    # "Invalid HTTP request"、返回 400（curl 打同一个地址是正常 200，
                    # 确认是 urlopen 这个客户端库本身的兼容性问题，不是服务本身的
                    # bug），换成 requests 库发请求，行为跟 curl 一致。
                    response = requests.get(url, timeout=1)
                    assert response.status_code == 200
                    break
                except (requests.RequestException, AssertionError):
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.2)
            run_browser(root, url)
            print("Playwright 全流程通过。", flush=True)
        finally:
            server.terminate()
            server.wait(timeout=10)


if __name__ == "__main__":
    main()
