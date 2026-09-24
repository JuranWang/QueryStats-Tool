# 更新记录

每次同步到 GitHub 都会在这里加一条，写清楚这次改了什么——不用会用 `git log` 也能
看懂这个工具最近有什么变化。新的写在最上面。

当前版本号记在仓库根目录的 `VERSION` 文件里（比如 `v1.0.0`），每次同步到 GitHub 都会
往上加一位：只是修 bug 加最后一位（v1.0.0 → v1.0.1），加了新功能加中间一位
（v1.0.1 → v1.1.0），大改动/不兼容旧数据才加第一位。

## 2026-09-24 — v1.4.1

- **修复：推理模型（如 MiniMax-M2）的 AI 功能必现解析失败** / **Fixed: AI features
  always failed to parse output from reasoning models (e.g. MiniMax-M2).**
  - 真实反馈：换用 MiniMax 之后 AI 功能报错，认证是通过的，但解析响应失败。
    查证发现 MiniMax-M2 这类"推理模型"会先输出一段 `<think>...</think>` 思维链，
    这段文字经常会提到"要输出的 JSON 是 `{...}`"这种话——原来"找第一个 `{` 到
    最后一个 `}`"的朴素解析算法会把思维链里提到的花括号也框进去，切出来的是一段
    混杂大量说明文字的非法 JSON，直接解析失败。
    Reported: after switching to MiniMax, AI features errored out — authentication
    succeeded but response parsing failed. Investigation found MiniMax-M2 (a
    "reasoning" model) emits a `<think>...</think>` chain-of-thought block before
    its real answer, and that block often mentions things like "the JSON to output
    is `{...}`" — the old naive "first `{` to last `}`" parser would grab braces
    mentioned inside the reasoning text too, producing an illegal JSON blob mixed
    with prose, which failed to parse.
  - 修复：解析前先把整段 `<think>...</think>` 去掉再做花括号匹配，普通模型的
    输出里本来就没有这个标签，去掉一个不存在的东西是无操作，不影响任何现有行为。
    真机验证：用真实 API 调用捕获到的原始响应文本作为回归测试，端到端重新跑通过。
    Fixed: strip any `<think>...</think>` block before brace-matching. Regular
    models never emit this tag, so removing something that isn't there is a no-op
    and doesn't change existing behavior. Verified live: added a regression test
    using the exact raw response text captured from a real API call, and re-ran
    the end-to-end call successfully after the fix.

## 2026-09-24 — v1.4.0

- **新增 Qwen 百炼 Coding Plan 套餐支持** / **Added support for Qwen's Bailian
  "Coding Plan" subscription tier.**
  - 真实反馈：内部团队共享的 Qwen key 配上之后，同事那边点 AI 功能报错
    `401 Incorrect API key provided`。查证发现这个 key 是阿里云百炼的
    "Coding Plan"套餐（key 格式 `sk-sp-xxx`），跟普通按量付费的 Qwen key
    是完全隔离的第三套计费/接入体系（各自独立的 base_url、模型名），混用
    官方文档明确写了会 401/403——之前"qwen"这个供应商配的是按量付费专用的
    域名，根本不认这种 key。
    Reported: after configuring the team's shared Qwen key, AI features failed
    with `401 Incorrect API key provided`. Investigation found the key belongs to
    Alibaba Bailian's "Coding Plan" subscription (`sk-sp-xxx` format) — a third
    billing/access tier, fully isolated from regular pay-as-you-go Qwen keys, with
    its own dedicated base URL and model names. Alibaba's own docs state mixing
    them causes exactly this 401/403. The existing "qwen" provider only pointed at
    the pay-as-you-go domain, which rejects this key type outright.
  - 新增两个独立的供应商选项（大陆/国际各一个），配上各自专属的 base_url 和
    Coding Plan 专用的版本化模型名（如 `qwen3.7-plus`，不是 `qwen-plus`）。
    内部团队版的共享 key 已经切换到正确的供应商配置。
    Added two new provider options (mainland and international), each pointing at
    its dedicated base URL with Coding Plan's own versioned model names (e.g.
    `qwen3.7-plus`, not `qwen-plus`). The internal team build's shared key has been
    switched to the correct provider configuration.

## 2026-09-24 — v1.3.1

- **紧急修复：全新 clone 下来第一次跑必现崩溃** / **Critical fix: every fresh clone
  crashed on first run.**
  - 真实反馈：同事第一次 clone 仓库、装好依赖跑起来，直接报
    `sqlite3.OperationalError: unable to open database file`。
    Reported: a teammate's very first run after cloning and installing
    dependencies crashed immediately with `sqlite3.OperationalError: unable to
    open database file`.
  - 根源：`data/` 这整个目录从来没有被 git 追踪过（`.gitignore` 排除的是
    `data/app.db` 这些具体文件，但目录本身也从没进过 git 历史），全新 clone 下来
    根本没有这个目录；`sqlite3.connect()` 不会自动创建数据库文件的父目录，只会
    创建文件本身，目录不存在就直接报错。这个 bug 之前一直没暴露，纯粹是因为
    所有人的开发机上 `data/` 目录很早就存在、一直当"理所当然"用，对任何全新
    clone 的人是 100% 必现。
    Root cause: `data/` had never been tracked by git at all (`.gitignore`
    excludes specific files under it, but nothing ever committed the directory
    itself), so a fresh clone simply has no `data/` folder. `sqlite3.connect()`
    creates the database *file* but never its parent directory, so this crashes
    every time the folder doesn't already exist. It went unnoticed only because
    every existing developer's machine already had a long-lived `data/` folder
    taken for granted — this was a 100% guaranteed crash for anyone cloning fresh.
  - 修复：`engine/db.py` 的 `init_db()`（全 app 最先被调用的入口）现在会在连接
    数据库之前先把父目录建好，新增回归测试专门模拟"目录还不存在"的场景复现过。
    Fixed: `init_db()` (the very first thing the whole app calls) now creates the
    parent directory before connecting. Added a regression test that specifically
    simulates the "directory doesn't exist yet" scenario to reproduce this.

## 2026-09-23 — v1.3.0

- **跨问卷对比：标题写清楚题干、颜色改用标准调色板、图例可编辑** /
  **Cross-survey comparison: titles now include the real question text, colors
  switched to the standard palette, and legends are now editable.**
  - 真实反馈三点：① 标题只有题号（如"Q24"），看不出对比的是哪道题；② 图表两个
    系列的颜色差异太小，用的不是报告里其它图表统一的调色板；③ 图例文字（默认是
    文档标题/文件名）需要能改。
    Reported: (1) titles only showed question numbers like "Q24", giving no clue
    what was being compared; (2) the two series' colors were too close together and
    didn't match the palette used everywhere else in the report; (3) the legend
    text (document titles by default) needed to be editable.
  - 标题现在带完整题干原文；分组对比图表默认颜色换成跟其它图表统一的十色调色板
    （之前用的是一套只有四种蓝色深浅的窄色板，从未在界面上真正验证过）；图例文字
    复用现成的"编辑图表上显示的文字"机制，改了同时更新表格表头和图表图例，并
    正常持久化。
    Titles now include the full question text. Grouped comparison charts default
    to the same ten-color palette used elsewhere (previously a narrow four-shade
    blue-only scale that had never actually been validated on screen). Legend text
    reuses the existing "edit chart labels" mechanism — editing it updates both the
    table header and the chart legend, and persists correctly.
- **紧急修复：手动保存对"已经打开过的历史文档"必现报错** / **Critical fix: manual
  save crashed every time for a previously-opened document.**
  - 真机验证这次改动时意外发现（不是这次改动引入的，是已经存在的 bug）：点
    "保存"报错"set_test_method() got multiple values for argument 'project_id'"。
    根源是读取测试方法设置的 `get_test_method()` 用 `SELECT * ... dict(row)`，
    返回的字典里天生带着 `project_id` 这一列；再拿这份字典去调用保存函数时，
    跟已经单独传的 `project_id` 参数撞上，直接抛异常——对任何"先从项目工作区
    打开一份历史分析、再点保存"的操作都会必现。
    Discovered incidentally while real-browser-verifying this update (a
    pre-existing bug, not introduced by it): clicking "Save" failed with
    `set_test_method() got multiple values for argument 'project_id'`.
    `get_test_method()` reads the row via `SELECT * ... dict(row)`, so the
    returned dict already contains a `project_id` key; passing that dict on to the
    save function collided with the `project_id` already passed separately —
    reproducible every time for any document opened from the project workspace
    and then saved.
  - 已在 `engine/persistence.py` 修复并补充回归测试，用真实调用链路（`get_test_method`
    的实际返回值，不是手写的干净字典）复现过。
    Fixed in `engine/persistence.py` with a regression test that reproduces the
    real call path (using `get_test_method`'s actual return value, not a
    hand-written clean dict).

## 2026-09-23 — v1.2.2

- **修复：同一道多选题在问卷里循环问了好几遍时，第 2/3 轮会被误判成独立单选题**
  / **Fixed: a multi-select question asked multiple times in a loop (e.g. once per
  product-grade framing) had its 2nd/3rd occurrence misdetected as separate
  single-choice questions.**
  - 真实反馈：一份问卷里"以下这些东西，你会把哪些算作'胶'？"这道多选题按"医用级/
    母婴级/食用级硅胶"分别问了三遍，原始表头逐字重复；pandas 读取时会给第 2、3 次
    出现的列名自动追加 ".1"/".2" 去重后缀，这个后缀被现有的"排除整句标点"规则误判
    成"看起来像一句话"，导致第 2、3 轮的选项列整组从多选题分组里掉出去，退化成
    9×2 道独立单选题（取值显示成未翻译的原始 0/1）。
    Reported bug: a survey asked the same multi-select question three times (once
    per product-grade framing), producing identical raw headers. pandas
    auto-appends ".1"/".2" dedup suffixes to the 2nd/3rd occurrences, which the
    existing "looks like a full sentence" exclusion rule misfired on (it treats any
    period as sentence-ending punctuation), dropping those columns out of grouping
    entirely and degrading them into raw, untranslated 0/1 single-choice questions.
  - 修好之后，三轮循环各自正确合并成一道独立的多选题，选项名干净、不带技术性
    后缀；已用真实数据验证（Python 函数级 + 新增回归测试 + 完整真机浏览器复现）。
    Each loop iteration now correctly merges into its own independent multi-select
    question with clean option labels. Verified against the real data at the
    function level, with a new regression test, and end-to-end in a real browser.

## 2026-09-23 — v1.2.1

- **紧急修复：新建问卷分析会覆盖上一份问卷** / **Critical fix: creating a new survey analysis could overwrite the previous one.**
  - 真实反馈：点"+ 新建问卷分析"，标题输入框默认显示的是上一份问卷的标题，点
    "保存"会把上一份问卷直接覆盖掉，不是新建一条记录。
    Reported bug: clicking "+ New survey analysis" showed the *previous* document's
    title by default, and saving overwrote that previous document instead of creating
    a new one.
  - 根源：`session_state` 里 `document_title`/`saved_document_id` 这些上一份分析
    残留的值，"新建"这个动作原来只清了 `mapping`/`generated`/`conclusions`/
    `test_method` 几个"记得住"的 key，这两个不在清单里，跟着带进了下一次"新建"。
    Root cause: `document_title`/`saved_document_id` from the previous analysis
    lingered in `session_state` — the "new analysis" action only cleared a
    hand-maintained list of keys (`mapping`/`generated`/`conclusions`/`test_method`)
    that didn't include these two.
  - 修复：改成跟"打开历史分析"共用同一套"白名单保留、其余全部清空"策略，不再
    靠手动列举要清哪些 key（这类清单以后加新功能大概率会再漏）。已用真实浏览器
    复现过修复前后的行为差异，并新增自动化回归测试。
    Fixed by reusing the same "keep an allowlist, clear everything else" strategy
    already used when reopening a saved analysis, instead of a hand-maintained list
    of keys to clear (which is exactly the kind of list that tends to miss new keys
    as features are added). Verified the before/after behavior difference in a real
    browser and added an automated regression test.

## 2026-09-22 — v1.2.0

- **新增 MiniMax 大陆账号支持** / **Added MiniMax mainland-China account support.**
  - 之前 MiniMax 只接了国际/全球账号的域名（api.minimax.io），大陆账号的兼容域名
    当时没能从官方文档确认下来，一直是已知空缺。这次重新查证（MiniMax 官方文档
    及其大陆镜像 platform.minimaxi.com）确认大陆账号走的是 api.minimaxi.com
    （注意域名比国际版多一个"i"，是完全不同的地址，不是同一个域名换路径），两边
    key 互不通用——现在两个账号类型都是独立的供应商选项，跟 Qwen 大陆/国际的
    拆分方式一致，选错了不会再套用错误的默认域名。
    MiniMax previously only supported the international account domain
    (api.minimax.io); the mainland-China compatible domain was an unconfirmed gap.
    Re-verified against MiniMax's official docs (and its mainland mirror
    platform.minimaxi.com): mainland accounts use api.minimaxi.com (note the extra
    "i" — a genuinely different domain, not the same one with a different path), and
    the two account types' keys are not interchangeable. Both are now separate
    provider options, mirroring how Qwen's mainland/international split already works.

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
