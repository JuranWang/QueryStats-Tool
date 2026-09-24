"""English translations for views/*.py and engine/*.py display strings."""

from __future__ import annotations

EN_MISC: dict[str, str] = {
    '排序题': 'Ranking',
    '第{rank}名': 'Rank {rank}',
    '首页': 'Home',
    '项目工作区': 'Project workspace',
    '问卷分析': 'Survey analysis',
    '问卷可视化分析工具': 'Survey Analysis Studio',
    '首页：管理项目（对应不同客户）、配置 AI 供应商。': 'Manage client projects and configure AI providers.',
    '项目列表': 'Projects',
    '显示哪些项目': 'Show projects',
    '手动新建': 'Manually created',
    '自动生成': 'Auto-generated',
    '全部': 'All',
    '拖拽排版试验（临时入口，测试用）': 'Drag-and-drop layout demo (temporary test page)',
    'API / 模型设置': 'API / model settings',
    '**当前使用**：{provider_label} · 模型 `{model}`': '**Current provider**: {provider_label} · Model `{model}`',
    '**各供应商 key 配置状态**': '**API key status by provider**',
    '翻译专用供应商（省钱用，选填）': 'Translation provider (optional, for lower costs)',
    '数据备份': 'Data backups',
    '立即备份': 'Back up now',
    '还没有项目，在下面新建一个。': 'No projects yet. Create one below.',
    '+ 新建项目': '+ New project',
    '模型名': 'Model name',
    '选用哪个供应商': 'Provider',
    'API key（不填就留空——不会清空已经存的 key；环境变量兜底：{env_name}）': 'API key (leave blank to keep the saved key; environment fallback: {env_name})',
    '保存': 'Save',
    '当前：跟通用一致。': 'Current: use general settings.',
    '**当前翻译专用**：{provider_label} · 模型 `{model}`': '**Current translation provider**: {provider_label} · Model `{model}`',
    '翻译专用供应商': 'Translation provider',
    '目前有 {backup_count} 份备份，最近一份：{latest_time:%Y-%m-%d %H:%M}，共占用 {total_size_mb:.1f} MB。': 'Backups: {backup_count} · Latest: {latest_time:%Y-%m-%d %H:%M} · Total size: {total_size_mb:.1f} MB.',
    '还没有备份文件——点下面「立即备份」，或者正常用几次就会自动生成。': 'No backups yet. Click “Back up now” below, or backups will be created automatically as you use the app.',
    '没有「{origin}」的项目——切到「全部」看看，或者去下面新建一个。': 'No projects under “{origin}”. Select “All” or create a project below.',
    '项目名（对应客户/项目名称）': 'Project name (client or project)',
    '问卷原始语言': 'Survey source language',
    '报告语言': 'Report language',
    '创建': 'Create',
    '模型名（供应商的模型命名会变，这里可以随时改）': 'Model name (you can update it when the provider changes model names)',
    '自定义模型名': 'Custom model name',
    '已配置': 'Set',
    'base_url（对方文档里的 OpenAI 兼容接口地址，通常以 /v1 结尾）': 'base_url (OpenAI-compatible endpoint from the provider’s docs, usually ending in /v1)',
    '已保存。': 'Saved.',
    'API key（跟上面通用供应商共用同一个 key 存储位置，同一家供应商不用重复填；环境变量兜底：{env_name}）': 'API key (shared with general settings for this provider; no need to enter it twice; environment fallback: {env_name})',
    '已备份到 {backup_path}': 'Backup saved to {backup_path}',
    '备份失败——数据库文件不存在或写入出错。': 'Backup failed: the database file is missing or could not be written.',
    '{source_lang} → {target_lang} · 建于 {created_at}': '{source_lang} → {target_lang} · Created {created_at}',
    '打开': 'Open',
    'base_url（跟上面「通用」的自定义 API 共用同一个 base_url 设置）': 'base_url (shared with the custom API in general settings)',
    '自动生成 · 按问卷题目自动命名，不是手动新建的': 'Auto-generated · Named from survey questions',
    '重命名': 'Rename',
    '新项目名': 'New project name',
    '删除': 'Delete',
    '确定删除项目「{project_name}」？连同它名下所有问卷分析一起删除，不可恢复。': 'Delete project “{project_name}” and all its survey analyses? This cannot be undone.',
    '确认删除': 'Confirm deletion',
    '项目名不能为空。': 'Project name cannot be empty.',
    '项目「{name}」创建成功。': 'Project “{name}” created.',
    '返回首页': 'Back to home',
    '还没选中项目，回首页打开一个。': 'No project selected. Open one from the home page.',
    '这个项目不存在了（可能被删了）。': 'This project no longer exists. It may have been deleted.',
    '定量问卷调研': 'Quantitative surveys',
    '定性访谈': 'Qualitative interviews',
    '案头研究': 'Desk research',
    '这个项目历史上分析过的每份问卷，按最近更新排在最前面。': 'Survey analyses for this project, most recently updated first.',
    '+ 新建问卷分析': '+ New survey analysis',
    '案头研究还没做，先占个分类位置。': 'Desk research is not available yet. This tab is a placeholder.',
    '这个项目下还没有问卷分析。': 'No survey analyses in this project yet.',
    '更新于 {updated_at}': 'Updated {updated_at}',
    '新标题': 'New title',
    '确定删除「{title}」这份问卷分析？不可恢复。': 'Delete the survey analysis “{title}”? This cannot be undone.',
    '标题不能为空。': 'Title cannot be empty.',
    '拖拽排版试验': 'Drag-and-drop layout demo',
    '返回项目工作区': 'Back to project workspace',
    'streamlit-elements 加载失败：{error}': 'Failed to load streamlit-elements: {error}',
    '图片 A（占位）': 'Image A (placeholder)',
    '图片 B（占位）': 'Image B (placeholder)',
    '图片 C（占位，更宽）': 'Image C (wide placeholder)',
    '未填写': 'Not provided',
    '是': 'Yes',
    '否': 'No',
    '{project_name} 问卷分析报告': '{project_name} Survey Analysis Report',
    '测试方法': 'Methodology',
    '人数': 'Respondent count',
    '是（{count}份）': 'Yes (versions: {count})',
    '是（份数未填写）': 'Yes (number of versions not provided)',
    '平台来源': 'Survey platform',
    '是否分流': 'Split survey',
    '筛选剔除规则': 'Screen-out criteria',
    '跳转逻辑说明': 'Skip logic notes',
    '核心结论': 'Key conclusions',
    '项目': 'Item',
    '说明': 'Description',
    '暂无数据': 'No data available',
    '{display_no}. {title}【{question_type}】': '{display_no}. {title} [{question_type}]',
    '交叉分析': 'Crosstab analysis',
    'AI 洞察': 'AI insights',
    '均值': 'Mean',
    '中位数': 'Median',
    '最小': 'Minimum',
    '最大': 'Maximum',
    '对应选择': 'Associated choice',
    '原文': 'Original response',
    '中文翻译': 'Chinese translation',
    '{count}人（{percentage}）': '{count} ({percentage})',
    '三组合计': 'Total (3 groups)',
    '合计': 'Total',
    'custom 供应商必须通过 get_provider() 构造（需要额外传 base_url），不能直接从注册表实例化': 'The custom provider must be created through get_provider() with a base_url, not directly from the registry.',
    '未知的 LLM 供应商: {name}': 'Unknown LLM provider: {name}',
    '缺少 {name} 的 API key：请在设置里填写，或设置环境变量 {env_name}（缺少环境变量 {env_name}）': 'Missing API key for {name}: enter it in settings or set the {env_name} environment variable (missing environment variable: {env_name}).',
    '选用了「自定义 API」但没有填 base_url：请在设置里填写，或设置环境变量 CUSTOM_BASE_URL': 'Custom API selected without a base_url. Enter it in settings or set the CUSTOM_BASE_URL environment variable.',
    '选用了「自定义 API」但没有填模型名：请在设置里填写': 'Custom API selected without a model name. Enter it in settings.',
    'Qwen（通义千问，大陆账号，直连 DashScope）': 'Qwen (mainland China account, direct DashScope)',
    'Qwen（通义千问，国际/新加坡账号，DashScope International）': 'Qwen (international/Singapore account, DashScope International)',
    'Qwen（通义千问，百炼 Coding Plan 套餐，大陆，key 形如 sk-sp-xxx）': 'Qwen (Bailian Coding Plan, mainland China, key looks like sk-sp-xxx)',
    'Qwen（通义千问，百炼 Coding Plan 套餐，国际，key 形如 sk-sp-xxx）': 'Qwen (Bailian Coding Plan, international, key looks like sk-sp-xxx)',
    'Qwen(Coding Plan)': 'Qwen (Coding Plan)',
    'Qwen(Coding Plan国际)': 'Qwen (Coding Plan Intl)',
    'OpenRouter（聚合网关，模型名要带厂商前缀，比如 qwen/qwen-turbo）': 'OpenRouter (gateway; use a provider prefix, e.g. qwen/qwen-turbo)',
    'MiniMax（国际/全球账号）': 'MiniMax (international/global account)',
    'MiniMax（国际/全球账号，api.minimax.io）': 'MiniMax (international/global account, api.minimax.io)',
    'MiniMax（大陆账号，api.minimaxi.com）': 'MiniMax (mainland China account, api.minimaxi.com)',
    'MiniMax(国际)': 'MiniMax (Intl)',
    'MiniMax(大陆)': 'MiniMax (China)',
    '自定义 API（任何 OpenAI 兼容接口，自己填 base_url）': 'Custom API (any OpenAI-compatible endpoint; enter a base_url)',
    'Qwen(大陆)': 'Qwen (China)',
    'Qwen(国际)': 'Qwen (Intl)',
    '自定义': 'Custom',
    '自定义…': 'Custom…',
    '（跟通用一致）': '(Use general settings)',
    '单选题': 'Single-choice',
    '多选题': 'Multi-select',
    '开放题': 'Open-ended',
    '数值题': 'Numeric',
    '未命名项目': 'Untitled project',
    '筛选': 'Screening',
    '正式': 'Main survey',
    '基础信息': 'Background information',
    '平台信息': 'Platform metadata',
    'Claude（Anthropic）': 'Claude (Anthropic)',
    'Kimi（Moonshot）': 'Kimi (Moonshot)',
    'Grok（xAI）': 'Grok (xAI)',
    'Gemini 3.1 Flash Lite —— $0.25／$1.50': 'Gemini 3.1 Flash Lite — $0.25/$1.50',
    'Mistral Small —— $0.15／$0.60': 'Mistral Small — $0.15/$0.60',
    '填的 API key 会明文存在本机 `data/app.db` 这个 SQLite 文件里，不加密——现在这个工具单机跑、单人用，这个风险可以接受；以后如果要多人共享或部署到服务器，这块必须重做（至少加密存储，理想是不落库、走系统 keychain 或环境变量）。不放心的话也可以不填这里，改用环境变量（下面每个供应商旁边写了对应的环境变量名），效果一样，只是每次开新终端要自己设。': 'API keys entered here are stored in plain text in the local SQLite file `data/app.db`, without encryption. This is acceptable for the current single-user, local setup; shared or server deployments require a different approach (at least encrypted storage, ideally a system keychain or environment variables with no database storage). You can also leave these fields blank and use the environment variables listed for each provider. They work the same way, but you must set them in each new terminal session.',
    '题目/选项翻译、开放题原文翻译走的是这里配的供应商，不单独配就跟上面「通用」一致。翻译是短文本、大批量的活，用 DeepSeek / Qwen 这类按官方报价（2026-09 查证）单价只有 Claude Haiku 的十分之一左右，中文语感也不差，没必要用旗舰模型翻译选项名这种小活。推荐 DeepSeek：便宜、中文语料训练、翻译语感公认扎实；Qwen-Turbo 更便宜一档，短选项名够用。': 'This provider handles question, option, and open-ended response translation. Leave it unset to use general settings. Translation involves many short texts. According to official pricing checked in September 2026, DeepSeek / Qwen cost about one-tenth as much as Claude Haiku and handle Chinese well; a flagship model is unnecessary for short option labels. DeepSeek is recommended for its low cost, Chinese training data, and translation quality. Qwen-Turbo is cheaper still and suitable for short option labels.',
    '数据库会在每次打开这个 app 时自动检查要不要备份（默认最多 6 小时备份一次，备份文件存在 data/backups/ 目录，保留最近 30 份）。**这份备份和正式数据库在同一块硬盘上**——如果这台机器/这个服务器本身是临时性存储（比如某些云平台的免费额度，重启就清空），务必把 data/backups/ 目录也同步到云盘、移动硬盘之类的外部位置，只在本地多存一份救不了这种情况。': 'Each time you open the app, it checks whether a backup is due (at most once every 6 hours by default). Backups are stored in data/backups/, keeping the latest 30. **Backups and the live database are on the same disk**. If this machine or server uses temporary storage (such as a free cloud instance that resets on restart), also sync data/backups/ to cloud storage or an external drive. Another copy on the same disk will not protect against that loss.',
    '定性访谈还没接进这个工具——已经有独立的 interview-crosstab skill（自包含 HTML，不需要这个工具的后端），架构完全不同，这里先占个分类位置，不强行合并。': 'Qualitative interviews are not integrated yet. The separate interview-crosstab skill produces standalone HTML without this app’s backend and uses a different architecture. This tab is a placeholder.',
    '试着拖动下面三个色块调整位置、拖右下角小三角调整大小——参考飞书文档里拖图片调整并排展示的手感。如果完全拖不动、报错、卡死，或者手感很差（卡顿/跳动），把具体现象告诉我。': 'Drag the three colored blocks to reposition them, or drag the small triangle at the bottom right to resize them, similar to arranging images side by side in Feishu documents. Report any inability to drag, errors, freezes, lag, or jumping.',
    'Claude Haiku 4.5 —— 最快最便宜': 'Claude Haiku 4.5 — Fastest and cheapest',
    'Claude Sonnet 5 —— 质量成本均衡（推荐）': 'Claude Sonnet 5 — Balanced quality and cost (recommended)',
    'Claude Opus 5 —— 最强，也最贵': 'Claude Opus 5 — Most capable and most expensive',
    'DeepSeek Chat —— 常规对话/分类任务（推荐）': 'DeepSeek Chat — General chat and classification (recommended)',
    'DeepSeek Reasoner —— 带推理链，更慢更贵': 'DeepSeek Reasoner — Reasoning model; slower and more expensive',
    'Qwen Flash —— ¥0.15/¥1.5 每百万 token，最便宜，简单任务/大批量首选': 'Qwen Flash — ¥0.15/¥1.5 per million tokens; cheapest, ideal for simple or bulk tasks',
    'Qwen Plus —— ¥0.8/¥2 每百万 token，性价比均衡（推荐）': 'Qwen Plus — ¥0.8/¥2 per million tokens; balanced value (recommended)',
    'Qwen Long —— ¥0.5/¥2，超长文本/长上下文任务专用': 'Qwen Long — ¥0.5/¥2; for long documents and long-context tasks',
    'Qwen MT Turbo —— 专用翻译模型，比通用聊天模型翻译更准（翻译场景推荐）': 'Qwen MT Turbo — Dedicated translation model; more accurate than general chat models (recommended for translation)',
    'Qwen3.7-Plus —— 新一代 Plus，质量比 qwen-plus 更高': 'Qwen3.7-Plus — New-generation Plus; higher quality than qwen-plus',
    'Qwen3.7-Plus —— 官方推荐档位之一，支持图片理解': 'Qwen3.7-Plus — One of the officially recommended tiers; supports image understanding',
    'Qwen3.6-Plus —— 官方推荐档位之一，支持图片理解': 'Qwen3.6-Plus — One of the officially recommended tiers; supports image understanding',
    'Qwen3-Max（2026-01-23 版本）': 'Qwen3-Max (2026-01-23 build)',
    'Qwen3-Coder-Plus —— 代码场景': 'Qwen3-Coder-Plus — coding tasks',
    'Qwen3-Coder-Next —— 代码场景': 'Qwen3-Coder-Next — coding tasks',
    'Kimi K2.5 —— 官方推荐档位之一，支持图片理解': 'Kimi K2.5 — One of the officially recommended tiers; supports image understanding',
    'GLM-5 —— 官方推荐档位之一': 'GLM-5 — One of the officially recommended tiers',
    'MiniMax-M2.5 —— 官方推荐档位之一': 'MiniMax-M2.5 — One of the officially recommended tiers',
    'Qwen3-Max —— 上一代旗舰': 'Qwen3-Max — Previous-generation flagship',
    'Qwen3.8-Max —— 当前旗舰': 'Qwen3.8-Max — Current flagship',
    'MiniMax-M2 —— 性价比最高（推荐）': 'MiniMax-M2 — Best value (recommended)',
    'MiniMax-M2.5 —— 编程/工具调用更强': 'MiniMax-M2.5 — Stronger coding and tool use',
    'MiniMax-M3 —— 当前旗舰，百万级上下文，支持图片/视频输入': 'MiniMax-M3 — Current flagship; million-token context, image and video input',
    'Qwen Flash —— 最便宜，简单任务/大批量首选': 'Qwen Flash — Cheapest; ideal for simple or bulk tasks',
    'Qwen Plus —— 性价比均衡（推荐）': 'Qwen Plus — Balanced value (recommended)',
    'Qwen Long —— 超长文本/长上下文任务专用': 'Qwen Long — For long documents and long-context tasks',
    'DeepSeek V4.1 Flash —— $0.15／$0.60，便宜好用': 'DeepSeek V4.1 Flash — $0.15/$0.60; affordable and capable',
    'Qwen3.8 Flash —— $0.15／$0.47，最便宜': 'Qwen3.8 Flash — $0.15/$0.47; cheapest',
    'Llama 4 Maverick —— $0.20／$0.80，开源模型': 'Llama 4 Maverick — $0.20/$0.80; open-source model',
    'GPT-5.6 Luna —— $0.20／$1.20，OpenAI 便宜/快速档': 'GPT-5.6 Luna — $0.20/$1.20; OpenAI’s affordable, fast tier',
    'Claude Haiku 4.5 —— $1／$5，最快最便宜的 Claude': 'Claude Haiku 4.5 — $1/$5; fastest and cheapest Claude',
    'DeepSeek V4 Pro —— $0.66／$1.98，当前旗舰（推荐）': 'DeepSeek V4 Pro — $0.66/$1.98; current flagship (recommended)',
    'Gemini 3.8 Flash —— $0.75／$3.75，当前 Flash 旗舰': 'Gemini 3.8 Flash — $0.75/$3.75; current Flash flagship',
    'Qwen3.8 Max —— $2／$6，当前旗舰': 'Qwen3.8 Max — $2/$6; current flagship',
    'Claude Sonnet 5 —— $2／$10，质量成本均衡': 'Claude Sonnet 5 — $2/$10; balanced quality and cost',
    'Mistral Medium 3.5 —— $1.50／$7.50，当前旗舰': 'Mistral Medium 3.5 — $1.50/$7.50; current flagship',
    'GPT-5.6 Sol —— $2／$10，OpenAI 当前旗舰': 'GPT-5.6 Sol — $2/$10; OpenAI’s current flagship',
    'Grok 4.6 —— $2／$6，当前旗舰': 'Grok 4.6 — $2/$6; current flagship',
    'Gemini 3.1 Pro —— $2／$12，仍是 preview 阶段': 'Gemini 3.1 Pro — $2/$12; still in preview',
    'Claude Opus 5 —— $5／$25，最强最贵': 'Claude Opus 5 — $5/$25; most capable and most expensive',
}

# Keep data identifiers and LLM prompts independent of the interface language.
NOT_TRANSLATED_MISC: set[str] = {
    '排序题',  # 模块级常量/数据值，显示处翻译
    '中文',  # 语言切换按钮的母语名称，始终显示中文以便识别
    '自定义…',  # 模块级常量/数据值，显示处翻译
    '（跟通用一致）',  # 模块级常量/数据值，显示处翻译
    '手动新建',  # 筛选数据值，显示处翻译
    'Qwen（通义千问，大陆账号，直连 DashScope）',  # 模块级常量/数据值，显示处翻译
    'Qwen（通义千问，国际/新加坡账号，DashScope International）',  # 模块级常量/数据值，显示处翻译
    'Qwen（通义千问，百炼 Coding Plan 套餐，大陆，key 形如 sk-sp-xxx）',  # 模块级常量/数据值，显示处翻译
    'Qwen（通义千问，百炼 Coding Plan 套餐，国际，key 形如 sk-sp-xxx）',  # 模块级常量/数据值，显示处翻译
    'Qwen(Coding Plan)',  # 模块级常量/数据值，显示处翻译
    'Qwen(Coding Plan国际)',  # 模块级常量/数据值，显示处翻译
    'OpenRouter（聚合网关，模型名要带厂商前缀，比如 qwen/qwen-turbo）',  # 模块级常量/数据值，显示处翻译
    'MiniMax（国际/全球账号）',  # 模块级常量/数据值，显示处翻译
    'MiniMax（国际/全球账号，api.minimax.io）',  # 模块级常量/数据值，显示处翻译
    'MiniMax（大陆账号，api.minimaxi.com）',  # 模块级常量/数据值，显示处翻译
    'MiniMax(国际)',  # 模块级常量/数据值，显示处翻译
    'MiniMax(大陆)',  # 模块级常量/数据值，显示处翻译
    '自定义 API（任何 OpenAI 兼容接口，自己填 base_url）',  # 模块级常量/数据值，显示处翻译
    'Qwen(大陆)',  # 模块级常量/数据值，显示处翻译
    'Qwen(国际)',  # 模块级常量/数据值，显示处翻译
    '自定义',  # 模块级常量/数据值，显示处翻译
    '自动生成',  # 筛选数据值，显示处翻译
    '全部',  # 筛选数据值，显示处翻译
    '单选题',  # 模块级常量/数据值，显示处翻译
    '多选题',  # 模块级常量/数据值，显示处翻译
    '开放题',  # 模块级常量/数据值，显示处翻译
    '数值题',  # 模块级常量/数据值，显示处翻译
    '正式',  # 板块数据值，用于筛选导出题目
    '基础信息',  # 板块数据值，用于筛选导出题目
    '是',  # 原始数据识别词表，不随界面语言改变
    '否',  # 原始数据识别词表，不随界面语言改变
    '为什么',  # 原始数据识别词表，不随界面语言改变
    '为何',  # 原始数据识别词表，不随界面语言改变
    '原因',  # 原始数据识别词表，不随界面语言改变
    '理由',  # 原始数据识别词表，不随界面语言改变
    '\nCREATE TABLE IF NOT EXISTS projects (\n    id INTEGER PRIMARY KEY AUTOINCREMENT,\n    name TEXT NOT NULL,\n    source_lang TEXT,\n    target_lang TEXT,\n    -- \'auto\'：分析页面在没有项目上下文时自动建的占位项目（比如直接跑 app.py，或者\n    -- 服务端重启后浏览器还停在分析页）；\'manual\'：用户自己在首页点"新建项目"建的，\n    -- 或者已经被人手动重命名过、确认过的。首页用这个字段做"自动/手动"筛选，不然\n    -- 自动占位项目会跟真正的项目混在一起，列表越滚越长。\n    origin TEXT NOT NULL DEFAULT \'manual\' CHECK (origin IN (\'manual\', \'auto\')),\n    created_at TEXT NOT NULL DEFAULT (datetime(\'now\')),\n    updated_at TEXT NOT NULL DEFAULT (datetime(\'now\'))\n);\n\nCREATE TABLE IF NOT EXISTS documents (\n    id INTEGER PRIMARY KEY AUTOINCREMENT,\n    project_id INTEGER NOT NULL REFERENCES projects(id),\n    filename TEXT NOT NULL,\n    format TEXT NOT NULL,\n    branch_label TEXT,\n    research_type TEXT NOT NULL DEFAULT \'quant_survey\'\n        CHECK (research_type IN (\'quant_survey\',\'qualitative\',\'desk_research\')),\n    title TEXT,\n    uploaded_at TEXT NOT NULL DEFAULT (datetime(\'now\')),\n    updated_at TEXT NOT NULL DEFAULT (datetime(\'now\'))\n);\n\nCREATE TABLE IF NOT EXISTS questions (\n    id INTEGER PRIMARY KEY AUTOINCREMENT,\n    document_id INTEGER NOT NULL REFERENCES documents(id),\n    q_no TEXT NOT NULL,\n    q_type TEXT NOT NULL CHECK (q_type IN (\'single\',\'multi\',\'open\',\'numeric\',\'ranking\')),\n    source_text_en TEXT,\n    order_index INTEGER NOT NULL,\n    section TEXT NOT NULL DEFAULT \'official\'\n        CHECK (section IN (\'screen_out\',\'official\',\'background\',\'platform_auto\')),\n    meta_json TEXT NOT NULL DEFAULT \'{}\'\n);\n\nCREATE TABLE IF NOT EXISTS test_method (\n    project_id INTEGER PRIMARY KEY REFERENCES projects(id),\n    platform_source TEXT,\n    is_branched INTEGER NOT NULL DEFAULT 0,\n    branch_count INTEGER,\n    screen_out_rule TEXT,\n    skip_logic_note TEXT\n);\n\nCREATE TABLE IF NOT EXISTS conclusions (\n    id INTEGER PRIMARY KEY AUTOINCREMENT,\n    project_id INTEGER NOT NULL REFERENCES projects(id),\n    text TEXT NOT NULL,\n    order_index INTEGER NOT NULL\n);\n\nCREATE TABLE IF NOT EXISTS responses (\n    id INTEGER PRIMARY KEY AUTOINCREMENT,\n    question_id INTEGER NOT NULL REFERENCES questions(id),\n    respondent_id TEXT NOT NULL,\n    raw_value TEXT,\n    translation TEXT,\n    order_index INTEGER\n);\n\nCREATE TABLE IF NOT EXISTS categories (\n    id INTEGER PRIMARY KEY AUTOINCREMENT,\n    question_id INTEGER NOT NULL REFERENCES questions(id),\n    label TEXT NOT NULL,\n    source TEXT NOT NULL CHECK (source IN (\'manual\',\'ai_closed\',\'ai_open_frozen\'))\n);\n\nCREATE TABLE IF NOT EXISTS response_categories (\n    response_id INTEGER NOT NULL REFERENCES responses(id),\n    category_id INTEGER NOT NULL REFERENCES categories(id),\n    PRIMARY KEY (response_id, category_id)\n);\n\nCREATE TABLE IF NOT EXISTS ai_runs (\n    id INTEGER PRIMARY KEY AUTOINCREMENT,\n    question_id INTEGER NOT NULL REFERENCES questions(id),\n    mode TEXT NOT NULL,\n    prompt_version TEXT,\n    raw_output TEXT,\n    created_at TEXT NOT NULL DEFAULT (datetime(\'now\'))\n);\n\nCREATE TABLE IF NOT EXISTS share_links (\n    id INTEGER PRIMARY KEY AUTOINCREMENT,\n    project_id INTEGER NOT NULL REFERENCES projects(id),\n    token TEXT NOT NULL UNIQUE,\n    scope TEXT,\n    expires_at TEXT\n);\n\nCREATE TABLE IF NOT EXISTS settings (\n    key TEXT PRIMARY KEY,\n    value TEXT\n);\n\n-- 自动保存只占一个位置：document_id 是主键，每次自动保存用 INSERT ... ON CONFLICT\n-- 整个替换掉上一份草稿，不会越存越多；跟 questions/responses（手动保存写的"正式"数据）\n-- 完全是两张表，结构上就不可能覆盖手动保存的内容。\nCREATE TABLE IF NOT EXISTS autosaves (\n    document_id INTEGER PRIMARY KEY REFERENCES documents(id),\n    payload_json TEXT NOT NULL,\n    saved_at TEXT NOT NULL DEFAULT (datetime(\'now\'))\n);\n\n-- "正式保存"里那些形状差异太大、不适合拆成关系表的内容：AI 分类结果、插入的图片\n-- （连同文字描述）、拖拽排版位置。跟 questions.meta_json 是同一个思路——一份 JSON blob，\n-- 每份问卷只占一行（document_id 是主键），手动保存整份覆盖。这张表结构上就是"正式"\n-- 数据的一部分（不是草稿），只是内容形状不一样，不跟 autosaves 混在一起。\nCREATE TABLE IF NOT EXISTS document_extras (\n    document_id INTEGER PRIMARY KEY REFERENCES documents(id),\n    payload_json TEXT NOT NULL,\n    updated_at TEXT NOT NULL DEFAULT (datetime(\'now\'))\n);\n',  # SQL（含中文注释或历史项目名迁移条件），不可翻译
    "UPDATE projects SET origin = 'auto' WHERE name = '未命名项目'",  # SQL（含中文注释或历史项目名迁移条件），不可翻译
    '筛选',  # 数据库板块映射键，保持持久化数据值
    '平台信息',  # 数据库板块映射键，保持持久化数据值
    '你负责给一份问卷调研项目起一个简洁的中文名称。',  # LLM prompt，输出语言由项目目标语言决定，不跟界面语言走
    '未命名项目',  # 持久化的默认项目名，数据库历史迁移按此值匹配；显示处翻译
    '根据下面这些问卷题目，用不超过12个汉字总结一个简洁、有区分度的项目名称（不要写“问卷”“调研”这类通用词，直接概括这份问卷在测什么）。只返回 JSON 对象，格式为：{"name": "名称"}。\n题目列表：',  # LLM prompt，输出语言由项目目标语言决定，不跟界面语言走
    'Qwen Flash —— 最便宜，简单任务/大批量首选',  # 模块级常量/数据值，显示处翻译
    'Qwen Plus —— 性价比均衡（推荐）',  # 模块级常量/数据值，显示处翻译
    'Qwen Long —— 超长文本/长上下文任务专用',  # 模块级常量/数据值，显示处翻译
    'Qwen MT Turbo —— 专用翻译模型，比通用聊天模型翻译更准（翻译场景推荐）',  # 模块级常量/数据值，显示处翻译
    'Qwen3.7-Plus —— 新一代 Plus，质量比 qwen-plus 更高',  # 模块级常量/数据值，显示处翻译
    'Qwen3.7-Plus —— 官方推荐档位之一，支持图片理解',  # 模块级常量/数据值，显示处翻译
    'Qwen3.6-Plus —— 官方推荐档位之一，支持图片理解',  # 模块级常量/数据值，显示处翻译
    'Qwen3-Max（2026-01-23 版本）',  # 模块级常量/数据值，显示处翻译
    'Qwen3-Coder-Plus —— 代码场景',  # 模块级常量/数据值，显示处翻译
    'Qwen3-Coder-Next —— 代码场景',  # 模块级常量/数据值，显示处翻译
    'Kimi K2.5 —— 官方推荐档位之一，支持图片理解',  # 模块级常量/数据值，显示处翻译
    'GLM-5 —— 官方推荐档位之一',  # 模块级常量/数据值，显示处翻译
    'MiniMax-M2.5 —— 官方推荐档位之一',  # 模块级常量/数据值，显示处翻译
    'Qwen3-Max —— 上一代旗舰',  # 模块级常量/数据值，显示处翻译
    'Qwen3.8-Max —— 当前旗舰',  # 模块级常量/数据值，显示处翻译
    'DeepSeek V4.1 Flash —— $0.15／$0.60，便宜好用',  # 模块级常量/数据值，显示处翻译
    'Qwen3.8 Flash —— $0.15／$0.47，最便宜',  # 模块级常量/数据值，显示处翻译
    'Llama 4 Maverick —— $0.20／$0.80，开源模型',  # 模块级常量/数据值，显示处翻译
    'GPT-5.6 Luna —— $0.20／$1.20，OpenAI 便宜/快速档',  # 模块级常量/数据值，显示处翻译
    'Claude Haiku 4.5 —— $1／$5，最快最便宜的 Claude',  # 模块级常量/数据值，显示处翻译
    'DeepSeek V4 Pro —— $0.66／$1.98，当前旗舰（推荐）',  # 模块级常量/数据值，显示处翻译
    'Gemini 3.8 Flash —— $0.75／$3.75，当前 Flash 旗舰',  # 模块级常量/数据值，显示处翻译
    'Qwen3.8 Max —— $2／$6，当前旗舰',  # 模块级常量/数据值，显示处翻译
    'Claude Sonnet 5 —— $2／$10，质量成本均衡',  # 模块级常量/数据值，显示处翻译
    'Mistral Medium 3.5 —— $1.50／$7.50，当前旗舰',  # 模块级常量/数据值，显示处翻译
    'GPT-5.6 Sol —— $2／$10，OpenAI 当前旗舰',  # 模块级常量/数据值，显示处翻译
    'Grok 4.6 —— $2／$6，当前旗舰',  # 模块级常量/数据值，显示处翻译
    'Gemini 3.1 Pro —— $2／$12，仍是 preview 阶段',  # 模块级常量/数据值，显示处翻译
    'Claude Opus 5 —— $5／$25，最强最贵',  # 模块级常量/数据值，显示处翻译
    'Claude Haiku 4.5 —— 最快最便宜',  # 模块级常量/数据值，显示处翻译
    'Claude Sonnet 5 —— 质量成本均衡（推荐）',  # 模块级常量/数据值，显示处翻译
    'Claude Opus 5 —— 最强，也最贵',  # 模块级常量/数据值，显示处翻译
    'DeepSeek Chat —— 常规对话/分类任务（推荐）',  # 模块级常量/数据值，显示处翻译
    'DeepSeek Reasoner —— 带推理链，更慢更贵',  # 模块级常量/数据值，显示处翻译
    'Qwen Flash —— ¥0.15/¥1.5 每百万 token，最便宜，简单任务/大批量首选',  # 模块级常量/数据值，显示处翻译
    'Qwen Plus —— ¥0.8/¥2 每百万 token，性价比均衡（推荐）',  # 模块级常量/数据值，显示处翻译
    'Qwen Long —— ¥0.5/¥2，超长文本/长上下文任务专用',  # 模块级常量/数据值，显示处翻译
    'MiniMax-M2 —— 性价比最高（推荐）',  # 模块级常量/数据值，显示处翻译
    'MiniMax-M2.5 —— 编程/工具调用更强',  # 模块级常量/数据值，显示处翻译
    'MiniMax-M3 —— 当前旗舰，百万级上下文，支持图片/视频输入',  # 模块级常量/数据值，显示处翻译
    '\n\n上次输出：\n',  # LLM prompt，输出语言由项目目标语言决定，不跟界面语言走
    '\n\n上次输出不是合法 JSON，请只输出一个 JSON 对象，不要有任何其他文字',  # LLM prompt，输出语言由项目目标语言决定，不跟界面语言走
    '你负责从当前开放题的实际回答中提炼封闭分类标签。',  # LLM prompt，输出语言由项目目标语言决定，不跟界面语言走
    '你负责按用户给定的分析要求，从开放题回答中提炼分类标签。',  # LLM prompt，输出语言由项目目标语言决定，不跟界面语言走
    '你负责将开放题回答分配到一组已经确定的封闭类目。',  # LLM prompt，输出语言由项目目标语言决定，不跟界面语言走
    '阅读这些开放题回答，总结出 5-8 个能覆盖这些回答的分类标签，使用中文短语。请只返回 JSON 对象，格式为：{"categories": ["类目一", "类目二"]}。\n回答样本：',  # LLM prompt，输出语言由项目目标语言决定，不跟界面语言走
    '分析要求：',  # LLM prompt，输出语言由项目目标语言决定，不跟界面语言走
    '\n阅读这些开放题回答，根据上面的分析要求总结出 2-8 个能覆盖这些回答的分类标签，使用中文短语。请只返回 JSON 对象，格式为：{"categories": ["类目一", "类目二"]}。\n回答样本：',  # LLM prompt，输出语言由项目目标语言决定，不跟界面语言走
    '只能从给定类目里选择，不许自造新类目。每条 response_id 必须出现且只出现一次。\n请只返回 JSON 对象，格式为：{"assignments": [{"response_id": 1, "category": "类目"}]}。\n给定类目：',  # LLM prompt，输出语言由项目目标语言决定，不跟界面语言走
    '\n待分类回答：',  # LLM prompt，输出语言由项目目标语言决定，不跟界面语言走
    '你是问卷数据分析助手。只做现象判断，不做商业判断。',  # LLM prompt，输出语言由项目目标语言决定，不跟界面语言走
    '下面是已经算好的问卷统计数据（JSON）。请从中挑 2 到 4 条值得说的现象级洞察，每条一两句话，必须带具体数字，数字必须和下面数据完全一致——不能自己计算、四舍五入、合并或编造新数字。不要给出商业建议（不要说「应该主打什么」「该定什么价」这类话，只描述现象）。\n请只返回一个 JSON 对象，格式为：{"insights": ["第一条……", "第二条……"]}。\n统计数据：',  # LLM prompt，输出语言由项目目标语言决定，不跟界面语言走
    '你负责忠实翻译问卷开放题原话。',  # LLM prompt，输出语言由项目目标语言决定，不跟界面语言走
    '逐句直译，不概括、不总结主题；阿拉伯数字原样保留；下面这些专有名词原样保留不翻译：',  # LLM prompt，输出语言由项目目标语言决定，不跟界面语言走
    '。\n每条 response_id 必须出现且只出现一次。请只返回 JSON 对象，格式为：{"translations": [{"response_id": 1, "translation": "译文"}]}。\n待翻译回答：',  # LLM prompt，输出语言由项目目标语言决定，不跟界面语言走
    'Claude（Anthropic）',  # 模块级说明常量，显示处翻译（含中文标点）
    'Kimi（Moonshot）',  # 模块级说明常量，显示处翻译（含中文标点）
    'Grok（xAI）',  # 模块级说明常量，显示处翻译（含中文标点）
    'Gemini 3.1 Flash Lite —— $0.25／$1.50',  # 模块级说明常量，显示处翻译（含中文标点）
    'Mistral Small —— $0.15／$0.60',  # 模块级说明常量，显示处翻译（含中文标点）
}
