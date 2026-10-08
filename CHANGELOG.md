# 更新记录

每次同步到 GitHub 都会在这里加一条，写清楚这次改了什么——不用会用 `git log` 也能
看懂这个工具最近有什么变化。新的写在最上面。

当前版本号记在仓库根目录的 `VERSION` 文件里（比如 `v1.0.0`），每次同步到 GitHub 都会
往上加一位：只是修 bug 加最后一位（v1.0.0 → v1.0.1），加了新功能加中间一位
（v1.0.1 → v1.1.0），大改动/不兼容旧数据才加第一位。

**更新时的重要提醒**：装新版本时，默认应该把电脑上旧的那份代码文件夹删掉（或者在
同一个文件夹里 `git pull`，不要每次都重新 `git clone` 到一个新文件夹）——同一台电脑
上留着好几份不同版本的代码，自己也会搞混到底在用哪一份、改的东西有没有生效。

## 2026-10-07 — v1.6.3

- **修复：v1.6.1 修好"等不够就打开"之后，又冒出"网页有时候打不开"的新花样**
  / **Fixed: new failure modes surfaced after the v1.6.1 startup-wait fix.**
  - 真实反馈（真实截图复现）：双击启动之后，浏览器里固定/收藏的标签页打开的是
    `localhost:8502`，报"无法连接服务器"。
    Reported (reproduced from a real screenshot): the pinned/bookmarked browser
    tab opened `localhost:8502` and failed with "can't connect to the server".
  - 根源 1——**端口漂移**：启动脚本一直没有显式固定端口，Streamlit 发现 8501
    被占用时会自己悄悄换到下一个空闲端口（8502、8503……）。如果电脑上曾经有
    一个旧进程占着 8501（比如上次关闭方式不对、或者还留着另一份旧代码目录在
    跑），新启动的服务就会被挤到别的端口；等那个旧进程自己也不在了，之前收藏
    的标签页却停在了那个再也不会有东西响应的端口号上，看起来和"打不开"一模
    一样，其实是网址本身就错了。
    Root cause 1 — **port drift**: the launcher never pinned a port, so Streamlit
    silently moved to the next free one whenever 8501 was occupied by a leftover
    process. Once that old process was gone, a tab bookmarked to the drifted port
    would fail forever, looking identical to "can't open" but actually pointing
    at the wrong address.
  - 根源 2——**改之前自己又踩了新坑**：给这次修复做真机验证时，连带测出另外
    两个之前不存在的真实 bug：① 脚本里原来写的是没加花括号的 `$URL`/`$PORT`，
    在 Mac 自带的这个 bash 版本上，只要变量后面紧跟着别的字符（哪怕是中文标点）
    就会被解析器错误地吞掉、展开成空值——改成统一加花括号的 `${URL}`/`${PORT}`。
    ② 新增的"检测端口是否被占用"逻辑一开始不小心把同一个端口上的普通浏览器
    客户端连接（比如开着的 Chrome 标签页）也当成"占用者"，必须额外加
    `-sTCP:LISTEN` 只认真正在监听的那个进程；③ 检测到的旧进程如果已经完全卡死
    （不响应任何信号），原来只发一次"礼貌关闭"信号就不管了，端口可能永远释放
    不出来——改成等 3 秒没反应就强制结束；④ 检查服务是否就绪用的 curl 原来没加
    超时，遇到"端口还在但进程完全卡死不回应"这种情况会直接无限等下去，整个
    脚本跟着一起卡死——加上超时。四个问题都是写代码时凭经验判断"应该没问题"、
    真机测试才会暴露出来的真实坑，不是凭空想象的边界情况。
    Root cause 2 — **new bugs introduced while fixing root cause 1**, all found
    through live testing, not theoretical: ① unbraced `$URL`/`$PORT` get silently
    swallowed into an empty expansion on this bash build whenever immediately
    followed by another character (even CJK punctuation) — fixed by always using
    `${URL}`/`${PORT}`; ② the new "is the port occupied" check initially also
    matched an ordinary browser tab's client connection to that port (e.g. an
    open Chrome tab), not just the actual listener — fixed with `-sTCP:LISTEN`;
    ③ a genuinely wedged old process that never responds to a polite kill could
    hold the port forever — escalates to a forced kill after a 3-second grace
    period; ④ the readiness-check `curl` had no timeout, so a port held open by a
    completely unresponsive process would hang it (and the whole script)
    indefinitely — a timeout was added.
  - 真机验证过全部四条路径：正常冷启动、服务已在跑直接打开、旧进程卡死自动
    清理重启、端口被不认识的程序占用时安全拒绝不误杀。
    Verified live across all four paths: normal cold start, already-running fast
    path, automatic cleanup and restart when the old process is wedged, and a
    safe refusal (no accidental kill) when the port is held by an unrelated
    program.

## 2026-10-03 — v1.6.2

- **设置页暂时下架 Qwen 百炼 Coding Plan 这个供应商选项** / **Temporarily removed
  the Qwen Bailian "Coding Plan" option from the provider settings page.**
  - 真实反馈：内部团队共享的这把 Coding Plan key 测了好几次都是
    `invalid access token or token expired`，账号侧的问题一直没恢复，现在没有一把
    能用的 key 配这个选项，放在下拉框里同事选了也用不了。
    Reported: the team's shared Coding Plan key keeps failing with `invalid access
    token or token expired` — an account-side issue that hasn't resolved. With no
    working key, leaving this option visible just lets people pick something that
    won't work.
  - 从"API / 模型设置"页的供应商下拉框、状态栏、翻译专用供应商下拉框里暂时移除
    （`app_streamlit/views/home_view.py` 的 `PROVIDER_LABELS`/`PROVIDER_SHORT_LABELS`），
    底层的供应商实现（`engine/llm_provider.py` 里 `qwen_coding_plan`/
    `qwen_coding_plan_intl` 两个注册条目）**没有删**——以后想清楚要怎么重新配置
    这个套餐，把这两行标签加回来就行，不用再碰 engine 那边的代码。内部共享的那把
    已确认报废的 key 也一并从 `engine/internal_defaults.py`（私有仓库专属文件）
    里删掉了。
    Temporarily removed from the provider dropdown, the status row, and the
    translation-specific provider dropdown on the "API / Model settings" page. The
    underlying provider implementation is untouched — re-adding the two label
    entries is enough to bring the option back once there's a working key. The
    confirmed-dead shared key was also removed from `engine/internal_defaults.py`
    (the private-repo-only file).

## 2026-10-03 — v1.6.1

- **修复：双击启动工具"有时候能打开，有时候打不开"** / **Fixed: the double-click
  launcher sometimes failed to open the app.**
  - 真实反馈：同事反映这个网页有时候能打开，有时候打不开。
    Reported: a teammate said the page sometimes opens and sometimes doesn't.
  - 根源：`启动问卷分析工具.command` 启动本地服务之后，固定 `sleep 4` 秒就直接
    打开浏览器，完全不检查服务到底有没有真的起来——电脑慢一点、或者是今天
    第一次启动要多花时间做 import，经常 4 秒还没绑定好端口，浏览器打开看到的
    就是空白/打不开，看起来像"坏了"，其实只是还没启动完。这不是偶发的运气
    问题，是脚本本身没有真的等服务就绪就抢先开浏览器。
    Root cause: after launching the local server, the `.command` launcher waited
    a fixed 4 seconds and then opened the browser unconditionally, never checking
    whether the server had actually finished starting. On a slower machine, or on
    the first run of the day (extra import overhead), 4 seconds often wasn't
    enough — the browser would open before the port was ready, looking like the
    app was broken when it just hadn't finished starting.
  - 修复：改成真的轮询端口是否就绪（最多等 30 秒，就绪就立刻打开，不用等满），
    真的等满 30 秒还没起来才提示"大概率是真的出了问题"并给出日志文件路径，
    不再用一个固定、可能不够用的等待时间赌运气。真机测试过：正常启动（几秒内
    轮询成功）和真的起不来（30 秒后给出明确报错指引）两条路径都验证过。
    Fixed: the launcher now actually polls until the port responds (up to 30
    seconds, opening as soon as it's ready rather than always waiting the full
    time), and only reports a likely real failure — with the log file path — if
    it's still not up after the full 30 seconds. No longer gambles on a fixed
    wait that may or may not be long enough. Verified live: both the normal
    startup path (ready within a few seconds) and the genuine-failure path
    (clear error message after 30 seconds) were tested end-to-end.

## 2026-09-29 — v1.6.0

- **新增「题组循环分析」，支持"matrix 逻辑"问卷（同一批题目按轮次重复问了好几
  遍）** / **New "repeated round analysis": support for "matrix" style
  questionnaires where the same block of questions repeats across several
  rounds.**
  - 真实反馈：一份消费者购买路径问卷，每一轮三道题——这一步做什么（动作）、
    去哪个平台、为什么去那儿，最少两轮最多五轮。用户想知道两件事："不分第
    几轮，大家整体会做什么"，以及"做某个具体动作的人主要去了哪个平台"。
    现有的⑧交叉分析只能对比两道互相独立的题，没法把 5 轮"折叠"到一起统计——
    Q9/Q12/Q15/Q18/Q21（5 轮"做什么"）本质是同一个逻辑维度的 5 次重复，不是
    5 道独立的题。
    Reported: a consumer purchase-journey survey asks the same three questions
    (what did you do, where did you go, why) for 2 to 5 repeating rounds. The
    user wanted two things: the pooled action distribution regardless of which
    round it happened in, and which platform people used for a specific action.
    The existing crosstab feature can only compare two independent questions, so
    it couldn't fold 5 repeated rounds into one analysis.
  - 新增 `engine/stats.py` 的 `reshape_repeated_rounds()`（把 N 轮"动作题+平台题"
    展开成一张"每人每轮一行"的长表）和 `loop_path_length_stats()`（路径长度/
    退出点：这个人真正走了几轮、在哪一轮主动选择"到这里就结束了"）。长表建好
    之后，动作分布复用现成的 `single_choice_stats()`，动作×平台交叉表直接复用
    现成的 `crosstab_counts()`——不是重新发明一套统计逻辑。
    Added `reshape_repeated_rounds()` (folds N rounds of action+platform columns
    into a long table, one row per respondent per round) and
    `loop_path_length_stats()` (path length and exit point: how many rounds a
    respondent really went through, and at which round they chose to stop) to
    `engine/stats.py`. Once reshaped, the action distribution reuses the existing
    `single_choice_stats()` and the action×platform crosstab reuses the existing
    `crosstab_counts()` — no new statistics logic was invented.
  - 新增「8+. 题组循环分析」板块（在⑧交叉分析下面）：挑每一轮对应的"动作题"+
    "平台题"（都是这份文档已经正常导入的单选题，不需要改上传/映射步骤），标记
    哪些选项算"退出/终止"，一键生成整体动作分布、动作×平台交叉表、路径长度
    分布三张结果，跟交叉分析板块一样支持多个板块、即时落库。
    Added a new "8+. Repeated round analysis" section (below section 8): pick
    each round's action and platform question (both are ordinary single-choice
    questions already imported normally), mark which options mean "exit", and
    generate the pooled action distribution, the action×platform crosstab, and
    the path-length distribution in one click. Supports multiple named blocks and
    saves immediately, same as the crosstab blocks.

## 2026-09-26 — v1.5.2

- **修复：v1.5.1 修好重叠之后，又把图表撑得比例失调** / **Fixed: the v1.5.1
  overlap fix over-corrected, making charts disproportionately tall.**
  - 真实反馈（真实截图复现）："第一张图为什么比例失调了"——v1.5.1 为了不让长
    选项换行后压线，按"这批标签最多要换成几行"统一分配每个类目的高度，但那份
    换行行数的估算比例是从 `engine/export_word.py` 给 matplotlib 导出图用的
    那套抄来的（中文按整字号宽、英文按约一半字号宽），跟浏览器 SVG 实际渲染
    完全是两回事，系统性地高估了换行行数——真机确认"厚实且柔软 / - Thick and
    plush"这种英文占比高的标签实际不换行，旧比例却算成要换 2 行。ECharts 类目轴
    是把这个"统一高度"平分给每一个类目，只要有一条被高估，全部类目（包括本来
    只需要一行的短标签）都会跟着多出一截没用的空白，图表因此显得又高又空旷。
    Reported (reproduced from a real screenshot): v1.5.1's overlap fix sized every
    category's slot to the tallest wrapped label, but the wrap-estimate ratios were
    copied from the matplotlib-based export estimator, not calibrated to actual
    browser SVG text rendering — it systematically overestimated line counts
    (verified live: a label like "Thick and plush", mostly English, didn't wrap at
    all in the browser but the old ratios predicted 2 lines). Since every category
    shares that one estimated height, any overestimate padded out every row,
    including short single-line labels, making the whole chart look bloated.
  - 修复：重新测出两个更准的字符宽度比例（中文约 2/3 字号宽、英文/数字/空格约
    0.425 倍字号宽，不是之前抄来的 1 倍/0.55 倍）——起一个临时页面，把两批完全
    独立的真实反馈标签（这次"质地或构造"题的 8 个选项、上一版"图案或设计"题的
    6 个选项）一起渲染，直接读 ECharts 输出的 SVG 量出真实换行行数校准出来的，
    在两批数据上都精确匹配，不是只拟合了一批。回归测试也从"不重叠"加了一条
    "每个类目的带宽不能比这批标签里最长的那条实际需要的高度多太多"，以后再
    有类似的估算失准会直接测出来，不用等人眼看出"图表看着很空"。
    Fixed: recalibrated the character-width ratios (CJK ≈ 2/3 of font size, ASCII/
    digits/spaces ≈ 0.425×, not the borrowed 1×/0.55×) by rendering two
    independent real-world label sets side by side and reading the actual wrapped
    line counts straight from ECharts' own SVG output — the new ratios matched
    exactly on both sets. The regression test now also asserts each category's
    allocated band isn't padded far beyond what the tallest real label needs, so a
    future miscalibration shows up as a test failure instead of a visual complaint.

## 2026-09-26 — v1.5.1

- **修复：横条图选项文字长、需要换行时，相邻类目标签会叠在一起** / **Fixed:
  long option labels that wrap to multiple lines overlapped the adjacent category
  on horizontal bar charts.**
  - 真实反馈（真机截图复现）：多选题/单选题选项超过 5 个时走横条图，选项文字是
    中英双语拼接的长文本，换行后文字直接压在上一行/下一行的标签上，看起来叠成
    一团；个别情况下最长的一条标签整个从图上消失。
    Reported (reproduced from a real screenshot): once a question has enough
    options to switch to a horizontal bar chart, long bilingual option labels wrap
    onto multiple lines and visually collide with the neighboring category's
    label; in some cases the longest label disappeared from the chart entirely.
  - 根源：横条图给每个类目分配的高度是写死的一份定值（46px，只够放一行字），
    ECharts 的类目轴是把总高度平均分给每个类目，不会按"这条标签换了几行"单独
    多给空间——只要有一条标签换行，它实际画出来的高度就会超出这 46px，溢出到
    相邻类目的位置。
    Root cause: every category was given a fixed 46px slot (enough for one line),
    but ECharts divides the axis height equally across categories rather than
    per-label — once any label wraps, it overflows past its 46px slot into the
    neighboring category.
  - 修复：新增 `_estimate_wrapped_line_count()`，跟标题/图例换行用的是同一套
    字符宽度估算（中文按整字号宽，英文/数字/空格按约一半字号宽），算出这批标签
    里最多要换成几行，每个类目的高度按这个最大行数分配，不再是固定的一行高度。
    真机验收：用真实反馈里那道题的原始选项文字复现过 bug（换行后标签互相压线、
    最长的一条整个消失），确认修复后不再重叠。
    Fixed: added `_estimate_wrapped_line_count()`, using the same character-width
    heuristic already used for chart titles/legends, to compute the maximum line
    count needed across all labels and size every category's slot accordingly
    instead of a fixed one-line height. Verified live using the exact option text
    from the real report (reproduced the overlap and the vanishing label first,
    confirmed both are gone after the fix).

## 2026-09-25 — v1.5.0

- **问卷列表显示"发布时间"，默认按它排序** / **Survey list now shows a "published"
  time and sorts by it.**
  - 真实反馈：项目工作区的问卷列表只显示"更新于"（数据库落库时间），看不出这份
    问卷实际是什么时候收上来的；应该用受访者里最晚一次提交问卷的时间。
    Reported: the survey list only showed "updated" (the database save time), not
    when the survey was actually fielded; it should use the latest respondent
    submission time instead.
  - 新增 `engine/db.py` 的 `get_document_response_time()`：从上传时自动识别出的
    "平台信息"字段（结束/提交时间，明确排除"开始时间"，两者常同时出现、含义相反）
    里取受访者最晚一次提交的时间。查不到（老数据、或者这份问卷压根没带这类字段）
    就退回原来的"更新于"，不会崩溃也不会编一个假的发布时间。
    Added `get_document_response_time()`, which reads the auto-detected "platform
    info" fields (submission/end time, explicitly excluding "start time" — the two
    are often both present with opposite meanings) and returns the latest
    respondent's submission time. Falls back to the old "updated" timestamp when
    none is found (older data, or a survey export with no such field) — never
    crashes, never fabricates a publish time.

- **插入图片跟图表的排版和复制/下载合并成一张图** / **Inserted images now share a
  layout with the chart, and copy/download merges them into one image.**
  - 真实反馈：只有一张图片时，图片和图表应该放在同一行（图左、图表右），不用像
    多张图片那样单独占一整行；复制/下载出来的应该是插入的图片和图表合成一张图，
    不能只有图表自己。
    Reported: with exactly one inserted image, it should share a row with the
    chart (image on the left, chart on the right) instead of taking a full row to
    itself like multiple images do; copying/downloading should produce one merged
    image containing both the inserted image and the chart, not the chart alone.
  - 新增 `engine/export_word.py` 的 `compose_question_snapshot_image()`：只有一张
    图时图左图表右并排（两边按图表高度对齐）；两张图及以上时图片沿用原来的
    "每行放几张"网格排版，图表整行放在下面。单选/多选题正文图表的复制/下载按钮
    接了这个合成逻辑，排序题/AI 分类分布这些跟 q_no 不是一一对应的图表不受影响。
    Added `compose_question_snapshot_image()`: with exactly one image, it sits
    beside the chart (both aligned to the chart's height); with two or more, images
    keep the existing per-row grid layout with the chart placed below. The
    copy/download controls on single- and multi-choice question charts now use
    this; per-option ranking charts and the AI-classification chart are unaffected
    since their images aren't a 1:1 match to a single q_no.

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
