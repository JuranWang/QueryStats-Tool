# 更新记录

每次同步到 GitHub 都会在这里加一条，写清楚这次改了什么——不用会用 `git log` 也能
看懂这个工具最近有什么变化。新的写在最上面。

当前版本号记在仓库根目录的 `VERSION` 文件里（比如 `v1.0.0`），每次同步到 GitHub 都会
往上加一位：只是修 bug 加最后一位（v1.0.0 → v1.0.1），加了新功能加中间一位
（v1.0.1 → v1.1.0），大改动/不兼容旧数据才加第一位。

## 2026-09-22 — v1.1.0

- **交叉分析改版：左右对称布局 + 多板块** / **Cross-analysis redesigned: symmetric layout + multiple blocks.**
  - 「8. 交叉分析」不再是"本问卷内/跨问卷对比"两个 tab，改成左右两栏对称结构：
    每栏各自「1. 选择问卷（默认本份，也可选其他已保存的问卷）→ 2. 选择题目 →
    3. 选择选项（分组）」，两栏是不是同一份文档，决定用联合交叉表还是独立占比对比。
    The two old tabs ("within-survey" / "cross-survey") are merged into one symmetric
    layout: each side independently picks "1. Survey (defaults to this document, or
    any other saved one) → 2. Question → 3. Grouped options." Whether the two sides
    point at the same document decides a joint crosstab vs. an independent-share
    comparison.
  - 支持在同一份文档里新增好几个独立的交叉分析板块（不是加选项，是加整块），
    每个板块可以单独删除。
    One document can now hold several independent cross-analysis blocks (not more
    options within one — whole additional blocks), each deletable on its own.
  - 生成结果立刻落库，不依赖手动保存或 20 秒自动草稿（草稿表本来就不会在正常
    重新打开时被读回来）；每个板块下方支持插入图片，跨问卷对比的图表支持一键
    复制/下载。
    Results are saved immediately on generation — not dependent on manual save or
    the 20-second draft table (which was never read back on a normal reopen anyway).
    Each block supports inserting images below it, and cross-survey comparison charts
    support one-click copy/download.
  - 维度分组列表新增排序方式（默认顺序/占比从高到低/占比从低到高）和手动上下
    调整，方便结果表格里选项的呈现顺序。
    The dimension-grouping list now has a sort control (default / share high-to-low /
    share low-to-high) plus manual up/down reordering, for controlling how options
    appear in the result table.
  - 修复一个真机截图发现的问题："选择问卷"下拉框选中"本份问卷"时显示成占位提示
    文字而不是"本份问卷"三个字（原因是选项值直接用了 Python 的 None，跟控件自己
    "没有选中项"的内部表示撞了）。
    Fixed a real-browser-caught bug: the "Survey" dropdown showed a placeholder
    instead of "This document" when that option was selected (the option's value was
    Python's `None`, which collided with the widget's own "nothing selected" sentinel).

## 2026-09-22 — v1.0.0

- **新增排序题支持** / **Ranking questions are now supported.**
  - 见数/Credamo 这类"每个选项一列、值是名次"的排序题导出，原来会被误判成好几道
    独立单选题；现在会自动识别成一道排序题（数据映射表里也能手动改）。
    Credamo-style ranking exports (one column per option, values are ranks) used to be
    misread as several separate single-choice questions. They are now auto-detected as
    one ranking question (and can be adjusted by hand in the data-mapping table).
  - 每个选项一张饼图（展示这个选项被打各个名次的占比），加一张汇总表格（横轴选项、
    纵轴名次），都支持一键复制/下载，Word 导出里也有这张表格。
    Each option gets its own pie chart (its rank distribution) plus a summary table
    (options × ranks). Both support one-click copy/download, and the table is included
    in the Word export.
  - 数据库结构小改动：已有数据库会在下次打开时自动、安全地升级（已用真实数据验证过
    不丢数据、外键约束保持正常）。
    Small database schema change: existing databases upgrade automatically and safely
    on next launch (verified against real data — no data loss, foreign keys intact).

## 2026-09-21（4）

- **数据映射记忆**：同一个项目里新上传一份数据，会自动套用上一次保存时调好的题型/
  分类/题目文本，不用每次都重新配置；也可以把映射存成模板，跨项目复用。
  **Mapping memory**: uploading a new file into the same project now reuses the
  question types, categories and titles from the last saved analysis automatically.
  Mappings can also be saved as reusable templates across projects.
- **导出改成"导出"，一次生成 Word / PDF / Markdown 三种格式**（原来只有 Word）。
  **Export now produces Word, PDF and Markdown in one click** (previously Word only).
- **插入图片功能重新设计**：
  Reworked the "insert images" feature:
  - 图片统一按一个基准高度对齐（饼图高度的 2/3），不用再一张一张手动调大小；
    "每行放几张"是硬约束，放不下时整行图片按同一个比例缩小，不会裁切/变形，也不会
    因为放不下就换行或减少张数。
    Images render at a shared baseline height (2/3 of the pie-chart height) instead of
    needing per-image manual sizing. "Images per row" is a hard constraint — if a row
    doesn't fit, everything in it scales down together (never cropped, never wrapped).
  - 图片不再和图表挤在同一行，改成单独一行、位于问题标题和分析图表之间。
    Inserted images no longer share a row with the chart; they get their own row
    between the question title and the chart.
  - 同一张图可以在别的题目里一键复用，不用重新从电脑上传。
    The same image can be reused on another question with one click, no re-upload.
- 修了一个真实反馈的 bug：切换"界面风格"这个设置偶尔会导致整页崩溃（跟 Streamlit
  热重载时的一个已知行为有关），现在读到异常值会自动退回默认风格，不会再崩页。
  Fixed a bug where the "visual theme" setting could occasionally crash the whole page;
  it now falls back to the default theme instead.

## 2026-09-21（3）

- **AI 开放题分析结果现在自动保存** / **AI open-ended analysis results are now saved automatically.**
  - 之前：结果只跟"手动保存"或 20 秒一次的草稿走，重新打开问卷读的是正式数据，所以关掉页面结果就没了。
    现在：AI 分类一跑完就直接写进这份分析的正式数据，下次打开还在。
    Before: results only followed manual saves / 20-second drafts, so closing the page lost them. Now they are written to the analysis as soon as classification finishes.
  - 新增"重新生成（清除上一次结果）"和"清除已有结果"两个选项。
    New "Regenerate (clears previous result)" and "Clear existing result" options.
- **AI 分类结果的图也能一键复制/下载了**，跟单选题图表一样。/ The AI classification chart now has one-click copy and download like other charts.
- 语言切换开关往左挪了一点，不再跟 Streamlit 右上角的 Running / Stop 图标重叠。/ The language switch moved left so it no longer overlaps Streamlit's Running / Stop indicator.

## 2026-09-21（2）

- **界面默认改为英文，右上角（Deploy 旁边）新增 EN／中文 切换开关** / **UI is now English by default, with an EN / 中文 switch at the top right (next to Deploy).**
  - 首页、项目工作区、分析页（全部 11 个部分）、Word 导出的固定文字、图表上的"人数"等都跟着语言走；选择会记住。
    All pages, Word-export labels and chart captions follow the language; your choice is remembered.
  - 问卷数据本身（题目、选项、你输入的项目名）不会被翻译，原样显示。
    Survey data itself (question titles, options, project names) is shown as-is.
  - 已知限制：数据映射表里的板块名（正式／筛选／基础信息／平台信息）是存库的中文标识，两种语言下都原样显示；
    AI 的 prompt 仍是中文，AI 输出语言跟项目的目标语言走，不跟界面语言走。
- README 改成英文为主（`README.md`），中文版在 `README.zh-CN.md`；README 里过时的"私有仓库"说法已更正，供应商列表补全。

## 2026-09-21

- **交叉分析支持多选题**："对比到哪道题"原来只能选单选题，现在多选题也能选了——
  比如"按性别分组，对比 Q5 各种取暖能源被使用的比例"这种分析现在能直接做。多选题
  按"这个分组里有百分之多少的人选了这个选项"算，不会因为一个人同时选了好几个选项
  就把分母算错。
- **API / 模型设置大幅扩充**：
  - 新增 Qwen 国际/新加坡账号、MiniMax、"自定义 API"（任何 OpenAI 兼容接口，自己
    填 base_url 就能用）三个供应商选项。
  - 模型名从纯手输改成"下拉框 + 自定义"——Claude、DeepSeek、Qwen（两种账号）、
    MiniMax、OpenRouter 这几家现在下拉框里能直接选（附带价格/定位说明），选
    "自定义…"才需要手打。
  - Qwen 和 OpenRouter 的模型列表大幅扩充，价格和型号名直接从官方接口查证：
    Qwen 补到 7 个档位（含专用翻译模型 Qwen MT Turbo），OpenRouter 补到 16 个
    档位，覆盖 OpenAI/Anthropic/Google/Meta/Mistral/DeepSeek/Qwen/xAI 八家主流
    厂商。
- **桌面双击启动**（可选）：项目目录里的 `启动问卷分析工具.command`，双击就能打开
  工具，不用敲命令行；详见 README「可选：Mac 上双击启动」一节。
- 修了一个真实测试中发现的 bug：交叉分析多选题数据展开后送进计算函数会因为
  "索引重复"报错，已修复。

## 2026-09-16（首次同步到 GitHub）

- 项目正式开源到 `JuranWang/QueryStats-Tool`（公开仓库）。
- README 补全：安装步骤、AI 供应商配置、本地运行 vs 自己部署两种方案、自动备份
  说明、给同事的反馈渠道（跟自己的 AI 工具描述问题、提交 GitHub Issue）。
