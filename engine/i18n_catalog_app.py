"""English translations and intentional data literals for app_streamlit/app.py."""

from __future__ import annotations

EN_APP: dict[str, str] = {
    '本份问卷': 'This survey',
    '1. 选择问卷': '1. Choose a survey',
    '2. 选择题目': '2. Choose a question',
    '3. 选择选项（分组）': '3. Group answer options',
    '这份问卷没有可用的单选/多选题。': 'This survey has no available single-choice or multi-choice questions.',
    '其余未覆盖的人另算一组': 'Include unmatched respondents as a separate group',
    '维度{n}': 'Dimension {n}',
    '维度名称不能重复，请修改后再生成。': 'Dimension names must be unique. Rename them before generating.',
    '交叉分析板块 {n}': 'Cross-analysis block {n}',
    '删除这个板块': 'Delete this block',
    '+ 新增交叉分析板块': '+ Add cross-analysis block',
    '每个板块左右两栏分别选问卷、题目、维度，下方生成对比；同一份文档可以建好几个独立的交叉分析板块。': 'Choose a survey, question, and dimensions on each side, then generate the comparison below. Each document can contain multiple independent cross-analysis blocks.',
    '{source} 按 {count} 个维度分组，对比 {target} 上的分布': '{source}, grouped into {count} dimensions, compared with the distribution of {target}',
    '{label}（左侧）': '{label} (left)',
    '{label}（右侧）': '{label} (right)',

    "本问卷内交叉分析": "Within-survey cross-analysis",
    "跨问卷对比": "Cross-survey comparison",
    "挑另一份已经分析过的问卷，对比对应题目在两次测试里的结果，适合同一批素材或问卷跨版本、跨轮次迭代时使用。":
        "Choose another analyzed survey to compare corresponding questions across tests, versions, or rounds of the same materials or questionnaire.",
    "暂无可用于对比的项目。": "No projects are available for comparison.",
    "对比问卷所在项目": "Comparison survey project",
    "这个项目下没有其它可对比的问卷分析，请选择其它项目。":
        "This project has no other survey analyses to compare. Choose another project.",
    "对比问卷": "Comparison survey",
    "本问卷没有可对比的单选、多选或数值题。":
        "This survey has no single-choice, multi-choice, or numeric questions to compare.",
    "本问卷题目": "Current survey question",
    "对比问卷没有同类型的题目，请选择其它问卷或本问卷题目。":
        "The comparison survey has no questions of the same type. Choose another survey or current question.",
    "对比问卷题目（按标题相似度排序）": "Comparison question (ordered by title similarity)",
    "差值 = {label_b} − {label_a}；选择题以百分点（pp）表示。":
        "Difference = {label_b} − {label_a}; choice questions use percentage points (pp).",
    "生成对比": "Generate comparison",
    "跨问卷对比｜{label_a}·{question_a} vs {label_b}·{question_b}":
        "Cross-survey comparison | {label_a}·{question_a} vs {label_b}·{question_b}",
    "有效样本：{label_a} N={n_a}；{label_b} N={n_b}":
        "Valid samples: {label_a} N={n_a}; {label_b} N={n_b}",
    "差值": "Difference",
    "自动识别出 {count} 道排序题（按选项列名规律+名次取值判断），已经在下面的映射表里合并成 ranking 类型，不用手动一个个改分组键了；不对的话可以在表格里直接调整。":
        "Automatically detected {count} ranking questions from option column names and rank values, "
        "and grouped them as ranking in the mapping table below. You don't need to edit each group key "
        "manually; adjust them in the table if needed.",
    "上传新图片": "Upload new images",
    "从其他题目复制": "Copy from other questions",
    "同一张图要用在好几道题时，不用重新从电脑上传——点「添加到本题」直接复用这份分析里已经传过的图。":
        "If the same image is used in several questions, you don't need to re-upload it — click "
        "\"Add to this question\" to reuse an image already uploaded elsewhere in this analysis.",
    "这份分析里其他题目还没有插入过图片。": "No other questions in this analysis have images yet.",
    "来自 {source_q_no}：{name}": "From {source_q_no}: {name}",
    "添加到本题": "Add to this question",
    "图片会按统一的基准高度自动对齐，放不下时自动等比例缩小（不会裁切、不会变形）；用 ↑↓ 调整先后顺序。「每行放几张」和单张图片时靠左/居中，在这个弹窗关掉之后、图片正下方的排版预览里调。":
        "Images align to a shared baseline height and shrink proportionally if they don't fit "
        "(never cropped or distorted). Use ↑↓ to reorder. \"Images per row\" and left/center "
        "alignment for a single image are set below the images, once this popup is closed.",
    "图片先后顺序在上面「插入图片」弹窗里调；这里管下面排版分成几行、每行放几张、单张图片时靠左还是居中。":
        "Image order is set in the \"Insert images\" popup above; this controls how many rows the "
        "layout below is split into, how many images per row, and left/center alignment for a "
        "single image.",
    "这个数是硬约束——图片统一按基准高度（饼图高度的 2/3）显示，放得下就不缩小；这一行放不下设定的张数时，会把这一行所有图片按同一个比例统一缩小到刚好放得下（不会裁切、不会变形），不会因为放不下就换行或者减少这一行放几张。":
        "This number is a hard constraint. Images render at a shared baseline height (2/3 of the "
        "pie chart's height) and stay that size if they fit; if this row's count doesn't fit, all "
        "images in it are scaled down together to fit exactly (never cropped or distorted, never "
        "wrapped to the next row or reduced in count).",
    "单张图片时的对齐方式": "Alignment for a single image",
    "居中": "Center",
    "居左": "Left",
    "只在这一行只有一张图片时生效（比如「每行放几张」设成 1，或者最后一行只剩一张）；同一行有好几张图片时始终靠左，不受这个设置影响。":
        "Only applies when a row has exactly one image (e.g. \"Images per row\" is 1, or a "
        "trailing row has one left over). Rows with several images are always left-aligned, "
        "regardless of this setting.",
    "下载 PDF 文件": "Download PDF file",
    "下载 Markdown 文件（含图片，zip）": "Download Markdown file (with images, ZIP)",
    "未生成 PDF：{error}": "PDF was not generated: {error}",
    "未生成 Markdown：{error}": "Markdown was not generated: {error}",
    "未检测到 LibreOffice（soffice），请下载安装：https://www.libreoffice.org/download/download-libreoffice/": "LibreOffice (soffice) was not found. Download and install it from https://www.libreoffice.org/download/download-libreoffice/",
    "未检测到 Pandoc（pandoc），请下载安装：https://pandoc.org/installing.html": "Pandoc (pandoc) was not found. Download and install it from https://pandoc.org/installing.html",
    "{tool} 转换超时（{timeout} 秒）：{error}": "{tool} conversion timed out ({timeout} seconds): {error}",
    "{tool} 转换失败（退出码 {code}）：{error}": "{tool} conversion failed (exit code {code}): {error}",
    "{tool} 未生成非空文件：{error}": "{tool} did not generate a nonempty file: {error}",
    "映射记忆": "Mapping memory",
    "已存模板": "Saved templates",
    "套用模板": "Apply template",
    "删除模板": "Delete template",
    "模板名称": "Template name",
    "把当前映射存为模板": "Save current mapping as a template",
    "撤销套用（恢复自动识别）": "Undo template (restore automatic detection)",
    "已按『{name}』套用 {matched}/{total} 列的映射，其余列为自动识别，可在下方修改": "Applied mapping from “{name}” to {matched}/{total} columns. Remaining columns use automatic detection. You can edit them below.",
    '这道题已经有一份 AI 分析结果，已自动保存。重新生成会先清除上一次的结果。': 'This question already has an AI analysis result, saved automatically. Regenerating will clear the previous result first.',
    '清除已有结果': 'Clear existing result',
    '重新生成（清除上一次结果）': 'Regenerate (clears previous result)',
    'AI 分析结果已自动保存。': 'AI analysis result saved automatically.',
    '｜AI 分类分布': ' | AI classification distribution',
    # 不含中文字符，tests/test_i18n.py 的"漏翻扫描"扫不到这一条（它只找带汉字的
    # t() 调用），但不补的话英文界面下载/复制的文件名会看到中文全角竖线"｜"跟在
    # 英文选项名后面，观感不对——手动补上，保持跟"｜AI 分类分布"同一个约定
    # （中文用全角"｜"不带空格，英文换成带空格的普通竖线"|"）。
    '｜{option}': ' | {option}',
    "问卷分析": "Survey analysis",
    "设计文档最新版本 1～10 全部框架的真实调用演示。": "Live demo of all 10 sections in the latest design specification.",
    "**(c) 样本量**：全量 {total} 人": "**(c) Sample size**: Total N = {total}",
    "（自动统计，不用手填）": " (calculated automatically)",
    "← 返回首页": "← Back to home",
    "界面风格": "Visual theme",
    "没有配置可用的 AI 供应商，去首页「API/模型设置」填一下。": "No AI provider is configured. Open API / model settings on the home page to set one up.",
    "拓展其他问题回答": "Show answers to related questions",
    "每行放几张": "Images per row",
    "原始数据": "Raw data",
    "数据映射": "Data mapping",
    "题型决定怎么统计和画图；「分类」决定这题算 3.筛选、4.正式问卷还是 5.基础信息——显示的题号（S1/Q1/C1…）由分类自动生成，不用手填。「分组键」只在多选题里有用：同一分类下分组键相同的几列会被合并成一道多选题。": "Question type determines the analysis and chart. Category assigns each question to 3. Screening, 4. Main questionnaire, or 5. Background information. Question numbers (S1/Q1/C1…) are generated automatically. The group key applies only to multi-select questions: columns in the same category with the same group key are combined into one question.",
    "点了「生成分析」之后这张表还是可以改的，不用重新上传文件——比如自动识别的多选题分组不对、某道题类型判断错了，直接在下面这张表里改对应的行，改完页面会立刻按新的设置重新生成整份报告。侧边栏导航最上面「调整题型／分组」可以随时跳回这里。": "You can edit this table after generating the analysis without uploading again. Correct question types or multi-select groupings here, and the report will update immediately. Use “Edit question types / groups” in the sidebar to return here.",
    "生成分析": "Generate analysis",
    "筛选后：全量 {total} 人 → 有效样本 {valid} 人（剔除 {excluded} 人）。": "After screening: Total N = {total} → Valid N = {valid} (excluded N = {excluded}).",
    "1. 结论": "1. Conclusions",
    "一句话最重要的结论，默认 1 条，带数字；可以再加。": "Start with one key conclusion backed by numbers. Add more as needed.",
    "+ 新增一条结论": "+ Add conclusion",
    "2. 测试方法": "2. Methodology",
    "(a) 测试平台与样本来源（根据列名猜的，不准就自己改）": "(a) Survey platform and sample source (inferred from column names; edit if needed)",
    "(b) 是否有分流设计": "(b) Split survey design",
    "，有效样本 {valid} 人": ", Valid N = {valid}",
    "**(d) 筛选逻辑**：{rule}（根据上面「筛选设置」自动生成，不用手填）": "**(d) Screening logic**: {rule} (generated automatically from Screening settings above)",
    "(e) 跳转逻辑（没法从数据自动判断，需要你回忆问卷设计手填）": "(e) Skip logic (enter from the questionnaire design; cannot be inferred from the data)",
    "6. 完整数据表格": "6. Full data table",
    "只展示通过筛选的有效样本；点一行，下面「7. 受访者个人视角」会展开这个人的完整作答。": "Only valid responses are shown. Select a row to view that person's complete answers in 7. Individual responses.",
    "按具体取值筛选（勾选框选答案，需要 ag-Grid 企业版 Set Filter，没有授权会在表格上出现「For Trial Use Only」水印——内部用可以接受就勾；不勾的话用免费版的文本筛选，点表头筛选图标、输入关键字也能缩小范围，只是不是勾选框）": "Filter by selecting values (requires ag-Grid Enterprise Set Filter; without a license, a “For Trial Use Only” watermark appears). Leave unchecked to use free text filters: click a column's filter icon and enter a keyword.",
    "7. 受访者个人视角": "7. Individual responses",
    "8. 交叉分析": "8. Crosstab analysis",
    "手动配置，不预设。维度数量不限——默认每个选项各自一组，可以合并/改名/增删。「对比到哪道题」单选、多选题都支持。": "Configure as many comparison groups as needed. Each option starts as a separate group; you can combine, rename, add, or remove groups. Both single-choice and multi-select questions can be used for comparison.",
    "9. AI 洞察": "9. AI insights",
    "不自动生成。点下面按钮才会调用 AI；引用了编造数字的洞察会被整条丢弃，不会显示出来。": "Insights are generated only when you click the button. Any insight containing unverified numbers is discarded.",
    "生成 AI 洞察": "Generate AI insights",
    "10. 受访者信息": "10. Respondent information",
    "11. 导出": "11. Export",
    "导出 1/2/4/5 + 9（筛选题、6/7/8/10 不导出——那些是网页交互功能，静态 Word 文档没有对应的东西）。": "Export sections 1/2/4/5 + 9. Screening questions and sections 6/7/8/10 are excluded because they are interactive features without an equivalent in the static Word report.",
    "生成报告（Word / PDF / Markdown）": "Generate report (Word / PDF / Markdown)",
    "← 返回项目工作区": "← Back to project workspace",
    "切换标题字体／题目外框／结论字号；Streamlit 原生控件（按钮/勾选框/下拉框）固定跟随「蓝调报告」，这是已知限制，不是没切换生效。": "Changes heading fonts, question borders, and conclusion text size. Streamlit's native buttons, checkboxes, and dropdowns retain the Blue report styling.",
    "{error}，暂时显示英文原文": "{error}. Showing the original English text for now.",
    "有 {count} 条翻译没通过校验，暂时显示英文原文，建议人工核对": "Translations failing validation: {count}. Showing the original English text; please review manually.",
    "留空就用自动生成的文字；改了这里，下面的图表和排版截图会跟着变。": "Leave blank to use the generated text. Changes update both the chart and the layout snapshot.",
    "AI 分类": "AI classification",
    "选择分类方式": "Classification method",
    "运行": "Run",
    "n = {n}": "n = {n}",
    "AI 分类分布": "AI classification distribution",
    "选择图片（可多选，可重复调用多次追加）": "Select images (select multiple files or upload again to add more)",
    "已从历史记录加载：{title}（{total} 人）": "Loaded from history: {title} (N = {total})",
    "上传问卷原始数据（CSV / xlsx）": "Upload survey data (CSV / xlsx)",
    "读取成功：{rows} 行 × {columns} 列": "Loaded successfully: Rows = {rows} × Columns = {columns}",
    "哪一列是受访者 ID？（用于去重，选'不去重'跳过）": "Which column contains respondent IDs? (Select “No deduplication” to skip)",
    "筛选设置": "Screening settings",
    "选中的值 = 未通过筛选（screen out）；不选就当这道题不参与过滤，只在「3. 筛选问题」里展示分布。": "Selected values screen respondents out. Leave empty to show the distribution in 3. Screening questions without filtering responses.",
    "结论 {number}": "Conclusion {number}",
    "如 Prolific + Tally / PickFu / Credamo 见数": "For example, Prolific + Tally / PickFu / Credamo",
    "分几份问卷": "Number of survey versions",
    "这版 demo 一次只处理一份上传文件，没法从单个 CSV 自动判断是不是分流问卷，这项只能你自己勾；分几份问卷各自的样本量需要分开上传后自己核对——跨文件合并统计留给正式版（`engine/db.py` 已经有 `documents.branch_label` 字段接这个）。": "This demo handles one uploaded file at a time and cannot infer a split survey design from a single CSV. Select this manually and upload each version separately to check its sample size. Cross-file analysis is planned for the full version (`engine/db.py` already includes `documents.branch_label`).",
    "没有就填「无」": "Enter “None” if not applicable",
    "问卷标题": "Survey title",
    "更新于 {time:%H:%M:%S}": "Updated at {time:%H:%M:%S}",
    "尚未保存": "Not saved yet",
    "N = {total}　·　{source}　·　{saved}": "N = {total} · {source} · {saved}",
    "显示平台信息列（10. 受访者信息，默认隐藏）": "Show platform metadata columns (10. Respondent information; hidden by default)",
    "在上面表格里点一行，这里会展开这个人的完整作答。": "Select a row in the table above to view that person's complete answers.",
    "**受访者：{respondent_id}**": "**Respondent: {respondent_id}**",
    "至少需要两道单选/多选题（一道用来圈人群，一道用来对比），才能配置交叉分析。": "At least two single-choice or multi-select questions are needed: one to define groups and one to compare.",
    "1. 从哪道题圈人群": "1. Question used to define groups",
    "2. 配置对比维度": "2. Configure comparison groups",
    "维度名称": "Group name",
    "包含哪些取值": "Included values",
    "+ 新增维度": "+ Add group",
    "按选项重置": "Reset to one group per option",
    "排序方式": "Sort by",
    "默认顺序": "Default order",
    "占比从高到低": "Share: high to low",
    "占比从低到高": "Share: low to high",
    "上移这个维度": "Move this group up",
    "下移这个维度": "Move this group down",
    "把没被任何维度覆盖的人另算一个「其余」维度": "Include respondents outside all defined groups in a “Rest” group",
    "3. 对比到哪道题": "3. Question to compare",
    "没有列被标成「平台信息」——如果你的数据里有 ID/提交时间这类平台自动收录的字段，去上面「数据映射」表里把对应行的「分类」改成「平台信息」。": "No columns are assigned to platform metadata. If your data includes fields such as IDs or submission times, set their category to Platform metadata in the Data mapping table above.",
    "如实展示，不聚合、不加工。": "Shown as recorded, without aggregation or processing.",
    "自动翻译失败（{error}），暂时显示英文原文": "Automatic translation failed ({error}). Showing the original English text for now.",
    "编辑图表上显示的文字": "Edit chart labels",
    "下载这张图表": "Download this chart",
    "当前只分析筛选出来的 {count} 人（{filter}），不是全部受访者。": "Analyzing only the filtered sample: N = {count} ({filter}).",
    "候选类目（逗号分隔）": "Categories (comma-separated)",
    "复制这张图表到剪贴板": "Copy this chart to the clipboard",
    "已复制": "Copied",
    "复制失败": "Copy failed",
    "插入图片": "Insert images",
    "图片描述": "Image caption",
    "上传一个文件开始。没有现成数据的话，随便导出一份 Qualtrics/问卷星/Google Forms 的 CSV 都行。": "Upload a file to get started. You can use a CSV export from Qualtrics, Wenjuanxing, or Google Forms.",
    "检测到并自动剔除了第一行——它看起来是问卷平台的字段代码行，不是真实作答（比如「作答ID」「Q1」这种），不算进统计。": "The first row was detected as survey platform field codes (such as response ID or Q1) and removed. It is excluded from all statistics.",
    "预览原始数据（前 5 行）": "Preview raw data (first 5 rows)",
    "自动识别出 {count} 道多选题（按选项列名规律+布尔取值判断），已经在下面的映射表里合并成 multi 类型，不用手动一个个改分组键了；不对的话可以在表格里直接调整。": "Multi-select questions detected: {count}, based on column names and boolean values. Their columns have been grouped as multi in the mapping table. Adjust the groupings there if needed.",
    "「{title}」——哪些取值算未通过？": "“{title}” — which values screen respondents out?",
    "以下筛选题不是单选题，本 demo 暂不支持据此过滤样本，只会在「3. 筛选问题」里展示，不影响「4. 正式问卷」「5. 基础信息探测」的有效样本：": "These screening questions are not single-choice. This demo displays them in 3. Screening questions but does not use them to filter the valid sample in 4. Main questionnaire or 5. Background information:",
    "例：179人中，选择最多的是「新西兰羊毛精工打造」，86人（48.0%）。": "Example: Of 179 respondents, 86 (48.0%) selected “Expertly crafted from New Zealand wool”, the most popular option.",
    "删除": "Delete",
    "「{title}」选中 {values} 视为未通过": "“{title}”: selecting {values} screens the respondent out",
    "筛选题看的是筛选前的全量样本，不是有效样本——这道题本来就是拿来筛人的。": "Screening questions use the full sample before screening, since their purpose is to filter respondents.",
    "已保存到数据库（document_id={document_id}）": "Saved to database (document_id={document_id})",
    "保存": "Save",
    "受访者ID": "Respondent ID",
    "维度名 {index}": "Group name {index}",
    "包含取值 {index}": "Included values {index}",
    "生成交叉分析": "Generate crosstab",
    "**{source} 按 {count} 个维度分组，对比 {target} 上的分布**": "**{source}: comparison groups = {count}; distribution of {target}**",
    "这次没有生成出数字能对上的洞察（可能是模型输出没通过校验），可以重新点一次试试。": "No insights passed numerical validation this time. Try generating them again.",
    "已生成：{filename}": "Generated: {filename}",
    "分析要求（比如「判断每条回答有没有提到价格敏感」）": "Analysis instructions (for example, identify responses mentioning price sensitivity)",
    "原文": "Original response",
    "给这张图配一行文字描述": "Add a one-line caption for this image",
    "↑ {question} 的图表": "↑ Chart for {question}",
    "单选题": "Single-choice",
    "没有找到要加载的历史分析，请回到项目工作区重新选择。": "The saved analysis could not be found. Return to the project workspace and select it again.",
    "解析失败：{error}": "Could not parse the file: {error}",
    "去重剔除了 {count} 行重复 {column}。": "Duplicate rows removed: {count} (ID column: {column}).",
    "原始列名": "Original column name",
    "题型": "Question type",
    "分类": "Category",
    "分组键（多选题共享同一个值才会合并）": "Group key (multi-select columns must share a value to be combined)",
    "题目文本（英文原题，或已经是中文就直接填中文）": "Question text (original English, or Chinese if already in Chinese)",
    "无": "None",
    "保存失败，不影响当前页面查看：{error}": "Save failed; you can still view this page: {error}",
    "已手动保存（{time:%H:%M:%S}），并清掉了这份问卷的自动保存草稿。": "Saved at {time:%H:%M:%S}. The autosaved draft for this survey has been cleared.",
    "分组": "Group",
    "对比题答案": "Comparison question answer",
    "导出失败：{error}": "Export failed: {error}",
    "下载 Word 文件": "Download Word file",
    "用自己的话描述想从这些开放题回答里提炼出什么——AI 会先按这个要求总结出几个类目，再把每条回答分到对应类目里，出来的还是图表能直接画的分类结果。": "Describe what you want to learn from these open-ended responses. AI will derive categories from your instructions and assign each response to a category, producing results that can be charted.",
    "上移这张图片": "Move image up",
    "下移这张图片": "Move image down",
    "删除这张图片": "Delete image",
    "数值题": "Numeric",
    "当前只看 {filter} 这部分：{filtered} 人（这道题总共 {count} 人填写）。": "Filtered sample ({filter}): N = {filtered}; total responses to this question: N = {count}.",
    "{count}人填写了这题。": "Responses to this question: N = {count}.",
    "加载历史分析失败：{error}": "Could not load the saved analysis: {error}",
    "未识别来源": "Unknown source",
    "手动保存失败：{error}": "Manual save failed: {error}",
    "已自动保存草稿（{time:%H:%M:%S}）——不会覆盖手动保存，点「保存」才会写入正式数据。": "Draft autosaved at {time:%H:%M:%S}. It does not overwrite your saved analysis; click Save to update it.",
    "（未作答/未看到这题）": "(No answer / question not shown)",
    "生成中…": "Generating…",
    "AI 调用失败：{error}": "AI request failed: {error}",
    "调用 AI 中…": "Calling AI…",
    "开放题": "Open-ended",
    "展开/收起原始数据": "Expand / collapse raw data",
    "；": "; ",
    "自动保存草稿失败：{error}": "Could not autosave the draft: {error}",
    "其余": "Rest",
    "按「{question}」筛选": "Filter by “{question}”",
    "多选题": "Multi-select",
    "请先填至少一个候选类目。": "Enter at least one category first.",
    "请先填写分析要求。": "Enter analysis instructions first.",
    "翻译 {question} 的开放题原文中…": "Translating open-ended responses for {question}…",
    "{question} 的开放题翻译失败（{error}），Word 里这道题的中文翻译列会留空。": "Open-ended translation failed for {question} ({error}). Its Chinese translation column will be blank in the Word report.",
    "蓝调报告": "Blue report",
    "极简": "Minimalist",
    "调整题型／分组": "Edit question types / groups",
    "3. 筛选问题": "3. Screening questions",
    "4. 正式问卷": "4. Main questionnaire",
    "5. 基础信息探测": "5. Background information",
    "封闭分类（自己填类目）": "Closed coding (enter your own categories)",
    "开放聚类（AI 自动提炼类目）": "Open coding (AI derives categories)",
    "自定义分析（自己写分析要求）": "Custom analysis (enter your own instructions)",
    "（不去重）": "(No deduplication)",
    "（全部）": "(All)",
    "筛选": "Screening",
    "正式": "Main survey",
    "基础信息": "Background information",
    "平台信息": "Platform metadata",
    "忽略": "Ignore",
    "**{prefix}{title}【{question_type}】**": "**{prefix}{title} [{question_type}]**",
    "　（{note}）": " ({note})",
    "、": ", ",
    "「{label}」＝{value}": "“{label}” = {value}",
    "{label}：{value}": "{label}: {value}",
}

# Retain data identifiers; translate their labels only at rendering boundaries.
NOT_TRANSLATED_APP: set[str] = {
    " 上的分布",  # 交叉表历史记录标题键片段，保持缓存标识稳定，界面另行翻译
    " 个维度分组，对比 ",  # 交叉表历史记录标题键片段，保持缓存标识稳定，界面另行翻译
    " 按 ",  # 交叉表历史记录标题键片段，保持缓存标识稳定，界面另行翻译
    " 视为未通过",  # 持久化筛选规则的原文片段，界面使用独立翻译模板
    "1. 结论",  # 模块级显示常量，在使用处翻译以支持语言切换
    "10. 受访者信息",  # 模块级显示常量，在使用处翻译以支持语言切换
    "11. 导出",  # 模块级显示常量，在使用处翻译以支持语言切换
    "2. 测试方法",  # 模块级显示常量，在使用处翻译以支持语言切换
    "3. 筛选问题",  # 模块级显示常量，在使用处翻译以支持语言切换
    "4. 正式问卷",  # 模块级显示常量，在使用处翻译以支持语言切换
    "5. 基础信息探测",  # 模块级显示常量，在使用处翻译以支持语言切换
    "6. 完整数据表格",  # 模块级显示常量，在使用处翻译以支持语言切换
    "7. 受访者个人视角",  # 模块级显示常量，在使用处翻译以支持语言切换
    "8. 交叉分析",  # 模块级显示常量，在使用处翻译以支持语言切换
    "9. AI 洞察",  # 模块级显示常量，在使用处翻译以支持语言切换
    "AI 分类",  # DataFrame 内部列名，保持数据键不变，仅在显示处翻译
    "Credamo 见数",  # 自动推断的平台来源数据，会存入方法设置；保持原值
    "[一-鿿]",  # 汉字检测正则表达式
    "」选中 ",  # 持久化筛选规则的原文片段，界面使用独立翻译模板
    "作答ID",  # 平台原始列名，用于精确匹配元数据，不能翻译
    "作答总时长(秒)",  # 平台原始列名，用于精确匹配元数据，不能翻译
    "作答渠道",  # 平台原始列名，用于精确匹配元数据，不能翻译
    "其余",  # 数据哨兵值，参与比较或统计；显示处翻译
    "分组",  # DataFrame 内部列名，保持数据键不变，仅在显示处翻译
    "原文",  # DataFrame 内部列名，保持数据键不变，仅在显示处翻译
    "发布ID",  # 平台原始列名，用于精确匹配元数据，不能翻译
    "受访者ID",  # DataFrame 内部列名，保持数据键不变，仅在显示处翻译
    "城市",  # 平台原始列名，用于精确匹配元数据，不能翻译
    "基础信息",  # 分类数据值，用于映射、分组及数据库；映射表取值按要求保留原文
    "对比题答案",  # DataFrame 内部列名，保持数据键不变，仅在显示处翻译
    "封闭",  # 分类模式前缀，用于 startswith 分支判断
    "封闭分类（自己填类目）",  # 分类模式数据值，显示处通过 format_func 翻译
    "屏幕分辨率",  # 平台原始列名，用于精确匹配元数据，不能翻译
    "平台信息",  # 分类数据值，用于映射、分组及数据库；映射表取值按要求保留原文
    "开始时间",  # 平台原始列名，用于精确匹配元数据，不能翻译
    "开放聚类（AI 自动提炼类目）",  # 分类模式数据值，显示处通过 format_func 翻译
    "忽略",  # 数据哨兵值，参与比较或统计；显示处翻译
    "操作系统类型",  # 平台原始列名，用于精确匹配元数据，不能翻译
    "无",  # 持久化筛选规则默认数据值，显示处翻译
    "极简",  # 模块级显示常量，在使用处翻译以支持语言切换
    "正式",  # 分类数据值，用于映射、分组及数据库；映射表取值按要求保留原文
    "浏览器类型",  # 平台原始列名，用于精确匹配元数据，不能翻译
    "用户ID",  # 平台原始列名，用于精确匹配元数据，不能翻译
    "省份",  # 平台原始列名，用于精确匹配元数据，不能翻译
    "筛选",  # 分类数据值，用于映射、分组及数据库；映射表取值按要求保留原文
    "纬度",  # 平台原始列名，用于精确匹配元数据，不能翻译
    "经度",  # 平台原始列名，用于精确匹配元数据，不能翻译
    "结束时间",  # 平台原始列名，用于精确匹配元数据，不能翻译
    "维度",  # 新增分组的默认可编辑名称，存入 session_state 并参与分组，保持数据值
    "自定义",  # 分类模式前缀，用于 startswith 分支判断
    "自定义分析（自己写分析要求）",  # 分类模式数据值，显示处通过 format_func 翻译
    "蓝调报告",  # 模块级显示常量，在使用处翻译以支持语言切换
    "见数",  # 平台来源识别关键词，不能翻译
    "设备类型",  # 平台原始列名，用于精确匹配元数据，不能翻译
    "调整题型／分组",  # 模块级显示常量，在使用处翻译以支持语言切换
    "问卷分析",  # 缺省项目名称也用于导出文件名，保持文件名不变
    "问卷发布名称",  # 平台原始列名，用于精确匹配元数据，不能翻译
    "（不去重）",  # 数据哨兵值，参与比较或统计；显示处翻译
    "（全部）",  # 数据哨兵值，参与比较或统计；显示处翻译
}
