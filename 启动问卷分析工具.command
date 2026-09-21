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
    sleep 4
fi

open http://localhost:8501
echo ""
echo "已经在浏览器里打开了。这个窗口关掉没关系，工具会继续在后台跑着；"
echo "下次还想用，再双击一次这个文件就行。"
sleep 2
