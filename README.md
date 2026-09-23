# Survey Visualization & Analysis Tool

[中文说明 → README.zh-CN.md](README.zh-CN.md)

Turn raw survey data (CSV / xlsx — exports from Tally, Prolific, Credamo and similar platforms
are supported) into an interactive web analysis report. AI is only used for things that
genuinely need semantic judgement — translation, open-ended answer classification, insights.
**Every number is computed by Python; the AI never touches or invents figures.**
The design history is in `设计文档-v0.*.md` (Chinese, oldest to newest).

The UI is **English by default**; use the **EN / 中文** switch at the top right (next to
"Deploy") to change language. Your choice is remembered.

Current version: see [`VERSION`](VERSION). What changed in each version is in
[`CHANGELOG.md`](CHANGELOG.md) (newest first).

## Requirements

- Python 3.11 (`requirements.txt` is a `pip freeze` from this version; other major versions
  are not guaranteed to work).
- An API key from one LLM provider — **optional**. Without one, everything except AI
  translation / classification / insights works (charts, statistics, Word/PDF/Markdown export).

## What it handles

Single-choice, multi-select, ranking, open-ended and numeric questions, each with the chart
type that fits it (ranking questions get one pie per option plus a rank × option summary
table). Uploading a new file into a project reuses the question types and titles from your
last saved analysis in it, so you don't re-configure the mapping table every time. Export
produces Word, PDF and Markdown in one click.

## Install & run

```bash
# 1. Clone
git clone https://github.com/JuranWang/QueryStats-Tool.git
cd QueryStats-Tool

# 2. Create a virtual environment and install dependencies
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 3. Run
.venv/bin/streamlit run app_streamlit/Home.py
```

Your browser opens `http://localhost:8501`. On first launch the database (`data/app.db`,
a single local SQLite file) and the upload/export folders are created automatically.

If something fails, paste the error together with this README into your own AI coding tool
(Claude Code, Codex, …) and let it debug — environment problems (wrong Python version,
missing system library) depend on your machine, not on this project.

### Optional: double-click launcher on macOS

After steps 1–2, the project folder contains `启动问卷分析工具.command`. Double-click it to
open the tool: it checks whether the local server is already running, starts it if not, and
opens the browser. Drag the file to your Desktop (or make an alias) to have a shortcut there.
The first time, macOS may warn about an "unidentified developer" — right-click the file,
choose "Open", and confirm once.

## Configure an AI provider (optional)

Open the home page → **API / Model settings**, pick a provider, choose a model from the
dropdown (or "Custom…" to type any model name), paste your API key, and save.

Supported: Anthropic (Claude), OpenAI, DeepSeek, Kimi (Moonshot), Qwen (Alibaba DashScope —
separate entries for **mainland-China** and **international/Singapore** accounts, since keys
are not interchangeable), Grok (xAI), OpenRouter (one key, most vendors' models), MiniMax, and
**Custom API** — any OpenAI-compatible endpoint: enter its base URL, model name and key.

Instead of the UI you can use environment variables (the UI value wins if both are set):

| Provider | Environment variable |
|---|---|
| Anthropic | `ANTHROPIC_API_KEY` |
| OpenAI | `OPENAI_API_KEY` |
| DeepSeek | `DEEPSEEK_API_KEY` |
| Kimi | `MOONSHOT_API_KEY` |
| Qwen (mainland) | `DASHSCOPE_API_KEY` |
| Qwen (international) | `DASHSCOPE_INTL_API_KEY` |
| Grok | `XAI_API_KEY` |
| OpenRouter | `OPENROUTER_API_KEY` |
| MiniMax | `MINIMAX_API_KEY` |
| Custom API | `CUSTOM_API_KEY` and `CUSTOM_BASE_URL` |

Per-item translation of open-ended answers uses a separate **translation provider**, which
you can set to a cheaper model on the same page (DeepSeek is suggested); if unset, it falls
back to the general provider.

## Two ways to use it

The tool has **no accounts and no per-user data isolation** — the database is one local
SQLite file. It is designed for one person (or a small, mutually-trusting team) running it on
a machine they control. It is not a multi-tenant service. Two setups follow from that:

### Option A: run it fully locally (recommended)

Everyone runs it on their own computer following "Install & run". Data stays in the local
`data/app.db`; nobody sees anyone else's data and nobody's actions affect anyone else.

**Pros**: data and API keys never leave your machine (a real plus for confidential client
data); zero operations work; users are independent.
**Cons**: you can't send a colleague a link to a specific analysis (share `data/app.db` or
export a Word report instead); each person updates their own copy (`git pull` and re-run
`pip install -r requirements.txt`).

### Option B: deploy to a server you control

For one shared URL, deploy to a server/VM **with persistent disk** (an always-on cloud VM, or
Docker with a persistent volume). It runs exactly like locally
(`streamlit run app_streamlit/Home.py`), just exposed to your team. Same code, same database
design — the only requirement is that `data/` survives restarts and redeploys.

**Not recommended**: free hosting with ephemeral storage (e.g. Streamlit Community Cloud).
Such platforms may wipe `data/app.db` on restart/redeploy, silently losing every project and
analysis. If you must use one, you need an external persistent database — beyond this
tool's current design.

## Data backup

Backups are **built in and automatic** for both options:

- On every new database connection the app checks whether a backup is due — at most one every
  6 hours. Backups go to `data/backups/` with timestamped names; the newest 30 are kept.
- The home page has a "Data backup" panel showing how many backups exist and when the latest
  was made, plus a "Back up now" button.
- Backups use SQLite's online backup API (not a file copy), so they are consistent and
  openable even while the database is in use.

**Important**: `data/backups/` lives on the same disk as `data/app.db`. It protects against
a corrupted or deleted database file, **not** against losing the whole disk/machine. Sync
`data/backups/` to cloud storage or an external drive yourself — the tool does not do this.

## Reporting problems

You don't need to learn GitHub: describe the problem to the AI coding tool you use with this
repo (Claude Code, Codex, … anything that can run terminal commands) and ask it to file an
Issue. Something like:

> I hit a problem using this survey analysis tool: [what you clicked, what you expected,
> what happened, and the exact error text]. Please create a GitHub issue in
> `https://github.com/JuranWang/QueryStats-Tool` (use `gh issue create`, short title, clear
> reproduction steps in the body). If you lack permission or aren't logged in to GitHub, tell
> me what to do.

The repo is public, so anyone can open an Issue (a GitHub account is needed). Issues are for
tracking — the maintainer checks them periodically; this is not a real-time support channel.
If your AI tool has no `gh` CLI, have it write the report and paste it into the GitHub website.

## Known limitations

- Single-machine SQLite; multi-user concurrent writes to one database file have not been
  stress-tested. It is designed for "one person, or several people each running their own copy".
- Multi-select questions loaded from history saved **before 2026-09** lose their original
  split columns, so "adjust group key" has no effect on them; analyses saved afterwards are fine.
- Some values in the data-mapping editor (section names like 正式/筛选/基础信息/平台信息) are
  stored as Chinese identifiers and are shown as-is in both languages.
- AI prompts stay in Chinese; the language of AI output follows the project's target language,
  not the UI language.
