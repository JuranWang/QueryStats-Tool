#!/bin/bash
# 双击这个文件就能打开"问卷可视化分析工具"——不用自己敲命令行。
# 逻辑：先看本地服务是不是已经在跑了，没在跑就启动一下，然后打开浏览器。
# 已经在跑的话（比如你之前开过、这次只是想再开一个标签页），直接打开浏览器，
# 不会重复启动、也不会打断你之前分析到一半的东西。
#
# 用相对路径定位项目目录（不写死具体用户名/文件夹位置）——这样这个文件本身
# 可以随项目一起放进 GitHub，同事本地 clone 下来之后也能直接双击用，不用
# 改里面任何内容。

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || {
    echo "找不到项目目录，请确认这个启动文件还在项目文件夹里。"
    read -n 1 -s -r -p "按任意键关闭这个窗口..."
    exit 1
}

if [ ! -x ".venv/bin/streamlit" ]; then
    echo "还没装好本地环境（找不到 .venv），请先按 README.md 里"
    echo "「安装 & 运行」的步骤把环境装好，再双击这个文件。"
    read -n 1 -s -r -p "按任意键关闭这个窗口..."
    exit 1
fi

if curl -s -o /dev/null http://localhost:8501; then
    echo "服务已经在跑了，直接打开浏览器。"
else
    echo "正在启动本地服务，第一次启动可能要等几秒……"
    nohup .venv/bin/streamlit run app_streamlit/Home.py --server.headless true > /tmp/questionnaire_tool.log 2>&1 &

    # 真实反馈"这个网页有时候能打开，有时候打不开"——原来这里固定等 4 秒就
    # 直接开浏览器，不管服务到底真的起来了没有；电脑慢一点、或者是今天第一次
    # 启动要多花时间做 import，经常 4 秒还没绑定好端口，浏览器打开就是空白/
    # 打不开，看起来像"坏了"，其实只是还没启动完，等一下重新刷新/再点一次
    # 就好了——这不是运气问题，是这个脚本本身没有真的等服务就绪。改成实际
    # 轮询端口是不是已经能访问，最多等 30 秒，服务随时就绪就立刻打开，不会再
    # 因为"刚好比 4 秒慢一点"就失败。
    ready=false
    for _ in $(seq 1 30); do
        if curl -s -o /dev/null http://localhost:8501; then
            ready=true
            break
        fi
        sleep 1
    done
    if [ "$ready" = false ]; then
        echo ""
        echo "等了 30 秒服务还是没启动起来，这次不是「碰巧慢一点」，大概率是真的"
        echo "出了问题——详细报错存在 /tmp/questionnaire_tool.log 这个文件里，"
        echo "把这个文件的内容发给负责人，或者丢给你自己的 AI 编程工具帮忙看一下。"
        read -n 1 -s -r -p "按任意键关闭这个窗口..."
        exit 1
    fi
fi

open http://localhost:8501
echo ""
echo "已经在浏览器里打开了。这个窗口关掉没关系，工具会继续在后台跑着；"
echo "下次还想用，再双击一次这个文件就行。"
sleep 2
