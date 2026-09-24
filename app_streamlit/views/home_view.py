"""首页内容：项目列表、新建项目、API/模型设置。由 Home.py 的 st.navigation 加载，不要单独跑。"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from engine import db
from engine.i18n import t
from app_streamlit.lang_ui import init_language
from engine.llm_provider import (
    PROVIDER_API_KEY_ENV,
    PROVIDER_DEFAULT_MODEL,
    PROVIDER_MODEL_PRESETS,
    TRANSLATION_RECOMMENDED_PROVIDER,
)

DB_PATH = PROJECT_ROOT / "data" / "app.db"


def get_conn():
    if "db_conn" not in st.session_state:
        st.session_state["db_conn"] = db.init_db(str(DB_PATH))
    return st.session_state["db_conn"]


conn = get_conn()
init_language(conn)

st.title(t('问卷可视化分析工具'))
st.caption(t('首页：管理项目（对应不同客户）、配置 AI 供应商。'))

# ---------------------------------------------------------------------------
# 数据备份——get_conn() 里的 db.init_db 已经顺手做过一次自动备份检查了，这里只是
# 让备份这件事"看得见"（有多少份、最近一份是什么时候）+ 给一个不用等自动节流的
# 手动入口。真正的备份逻辑（在线备份 API、节流、旧备份轮转）都在 engine/db.py。
# ---------------------------------------------------------------------------

with st.expander(t('数据备份'), expanded=False):
    st.caption(
        t('数据库会在每次打开这个 app 时自动检查要不要备份（默认最多 6 小时备份一次，备份文件存在 data/backups/ 目录，保留最近 30 份）。**这份备份和正式数据库在同一块硬盘上**——如果这台机器/这个服务器本身是临时性存储（比如某些云平台的免费额度，重启就清空），务必把 data/backups/ 目录也同步到云盘、移动硬盘之类的外部位置，只在本地多存一份救不了这种情况。')
    )

    backups_dir = PROJECT_ROOT / "data" / "backups"
    existing_backups = sorted(backups_dir.glob(f"{DB_PATH.stem}-*.db")) if backups_dir.exists() else []
    if existing_backups:
        import datetime as _datetime

        latest = existing_backups[-1]
        latest_time = _datetime.datetime.fromtimestamp(latest.stat().st_mtime)
        total_size_mb = sum(f.stat().st_size for f in existing_backups) / (1024 * 1024)
        st.caption(
            t('目前有 {backup_count} 份备份，最近一份：{latest_time:%Y-%m-%d %H:%M}，共占用 {total_size_mb:.1f} MB。', backup_count=len(existing_backups), latest_time=latest_time, total_size_mb=total_size_mb)
        )
    else:
        st.caption(t('还没有备份文件——点下面「立即备份」，或者正常用几次就会自动生成。'))

    if st.button(t('立即备份'), key="manual_backup_button"):
        backup_path = db.backup_database(conn, str(DB_PATH), force=True)
        if backup_path:
            st.toast(t('已备份到 {backup_path}', backup_path=backup_path))
        else:
            st.toast(t('备份失败——数据库文件不存在或写入出错。'))
        st.rerun()

# ---------------------------------------------------------------------------
# 项目列表
# ---------------------------------------------------------------------------

st.header(t('项目列表'))

# 分析页面没有项目上下文时会自动开一个项目（origin='auto'）才能保存，名字是按问卷题目
# 猜的/AI 总结的，不是你自己新建的——这里给个筛选，省得这些占位项目跟你手动建的项目
# 混在一起、列表越滚越长。默认只看"手动新建"，自动生成的一键切过去看，不是删掉了。
origin_filter = st.radio(
    t('显示哪些项目'),
    ["手动新建", "自动生成", "全部"],
    format_func=lambda value: t(value),
    horizontal=True,
    key="project_origin_filter",
)

all_projects = conn.execute(
    "SELECT id, name, source_lang, target_lang, created_at, origin FROM projects ORDER BY id DESC"
).fetchall()

if origin_filter == "手动新建":
    projects = [p for p in all_projects if p["origin"] == "manual"]
elif origin_filter == "自动生成":
    projects = [p for p in all_projects if p["origin"] == "auto"]
else:
    projects = all_projects

if not all_projects:
    st.info(t('还没有项目，在下面新建一个。'))
elif not projects:
    st.info(t('没有「{origin}」的项目——切到「全部」看看，或者去下面新建一个。', origin=t(origin_filter)))
else:
    for p in projects:
        col_name, col_lang, col_open, col_rename, col_delete = st.columns([3, 3, 1, 1, 1])
        # Translate the system placeholder without changing persisted or user-entered names.
        display_name = t("未命名项目") if p["origin"] == "auto" and p["name"] == "未命名项目" else p["name"]
        col_name.markdown(f"**{display_name}**")
        if p["origin"] == "auto":
            col_name.caption(t('自动生成 · 按问卷题目自动命名，不是手动新建的'))
        col_lang.caption(t('{source_lang} → {target_lang} · 建于 {created_at}', source_lang=p['source_lang'], target_lang=p['target_lang'], created_at=p['created_at']))
        if col_open.button(t('打开'), key=f"open_project_{p['id']}"):
            st.session_state["current_project_id"] = p["id"]
            st.switch_page("views/project_view.py")

        with col_rename.popover(t('重命名')):
            new_name = st.text_input(t('新项目名'), value=p["name"], key=f"rename_project_input_{p['id']}")
            if st.button(t('保存'), key=f"rename_project_save_{p['id']}"):
                if new_name.strip():
                    db.rename_project(conn, p["id"], new_name.strip())
                    st.rerun()
                else:
                    st.error(t('项目名不能为空。'))

        # 删除是不可逆操作（连带项目下所有问卷分析一起删）——popover 本身就是第一步确认，
        # 里面还要再点一次「确认删除」，不会一下手滑就删掉。
        with col_delete.popover(t('删除')):
            st.warning(t('确定删除项目「{project_name}」？连同它名下所有问卷分析一起删除，不可恢复。', project_name=display_name))
            if st.button(t('确认删除'), key=f"delete_project_confirm_{p['id']}", type="primary"):
                db.delete_project(conn, p["id"])
                if st.session_state.get("current_project_id") == p["id"]:
                    st.session_state["current_project_id"] = None
                st.rerun()

with st.expander(t('+ 新建项目')):
    with st.form("new_project_form"):
        name = st.text_input(t('项目名（对应客户/项目名称）'))
        col1, col2 = st.columns(2)
        source_lang = col1.text_input(t('问卷原始语言'), value="en")
        target_lang = col2.text_input(t('报告语言'), value="zh-CN")
        submitted = st.form_submit_button(t('创建'))
        if submitted:
            if not name.strip():
                st.error(t('项目名不能为空。'))
            else:
                new_id = db.create_project(conn, name.strip(), source_lang, target_lang)
                st.session_state["current_project_id"] = new_id
                st.success(t('项目「{name}」创建成功。', name=name))
                st.switch_page("views/project_view.py")

st.divider()

# ---------------------------------------------------------------------------
# API / 模型设置
# ---------------------------------------------------------------------------

st.header(t('API / 模型设置'))
st.warning(
    t('填的 API key 会明文存在本机 `data/app.db` 这个 SQLite 文件里，不加密——现在这个工具单机跑、单人用，这个风险可以接受；以后如果要多人共享或部署到服务器，这块必须重做（至少加密存储，理想是不落库、走系统 keychain 或环境变量）。不放心的话也可以不填这里，改用环境变量（下面每个供应商旁边写了对应的环境变量名），效果一样，只是每次开新终端要自己设。')
)

PROVIDER_LABELS = {
    "anthropic": "Claude（Anthropic）",
    "openai": "OpenAI",
    "deepseek": "DeepSeek",
    "kimi": "Kimi（Moonshot）",
    # 阿里云 DashScope 的 key 绑定"开号时选的控制台区域"，大陆账号和国际/新加坡账号
    # 互不通用，配错了会直接 401、看着完全不像是"账号区域配错了"——拆成两个选项，
    # 不确定自己是哪种账号的话，两个都试一下就知道了。
    "qwen": "Qwen（通义千问，大陆账号，直连 DashScope）",
    "qwen_intl": "Qwen（通义千问，国际/新加坡账号，DashScope International）",
    # "Coding Plan"（key 格式 sk-sp-xxx）是阿里云百炼跟 Token Plan/按量付费完全
    # 隔离的第三种套餐，必须配自己专属的域名，混用会 401/403——跟上面 qwen 那条
    # 是不一样的坑，不能靠"多试几个 Qwen 选项"碰出来，需要一眼就能看到这是个
    # 独立选项。
    "qwen_coding_plan": "Qwen（通义千问，百炼 Coding Plan 套餐，大陆，key 形如 sk-sp-xxx）",
    "qwen_coding_plan_intl": "Qwen（通义千问，百炼 Coding Plan 套餐，国际，key 形如 sk-sp-xxx）",
    "grok": "Grok（xAI）",
    "openrouter": "OpenRouter（聚合网关，模型名要带厂商前缀，比如 qwen/qwen-turbo）",
    # MiniMax 的大陆/国际账号是两个不同域名（api.minimaxi.com / api.minimax.io），
    # key 互不通用，跟上面 Qwen 大陆/国际是同一类坑，拆成两个选项。
    "minimax": "MiniMax（国际/全球账号，api.minimax.io）",
    "minimax_cn": "MiniMax（大陆账号，api.minimaxi.com）",
    "custom": "自定义 API（任何 OpenAI 兼容接口，自己填 base_url）",
}

CUSTOM_MODEL_SENTINEL = "自定义…"


def _pick_model(provider: str, current_model: str | None, key_prefix: str) -> str:
    """模型名选择器——真实反馈"能不能把模型变成下拉框选项+自定义两种，而不是手动
    输入"：有核实过命名规律的供应商（见 PROVIDER_MODEL_PRESETS）显示"下拉框 + 自定义"
    两级选择，不用自己去查、也不容易手滑打错模型名；没有预设的供应商（OpenAI/Kimi/
    Grok 命名规律没核实过，"自定义 API"更是连供应商是谁都不知道）直接退回手填文本框，
    比编几个自己也不确定对不对的型号名放进下拉框更负责任。key_prefix 保证同一个
    供应商在"通用"和"翻译专用"两个区块里的控件 key 不会互相冲突。
    """

    presets = PROVIDER_MODEL_PRESETS.get(provider)
    if not presets:
        return st.text_input(
            t('模型名（供应商的模型命名会变，这里可以随时改）'),
            value=current_model or PROVIDER_DEFAULT_MODEL.get(provider, ""),
            key=f"{key_prefix}_model_text_{provider}",
        )

    preset_slugs = [slug for slug, _ in presets]
    preset_labels = dict(presets)
    picker_options = preset_slugs + [CUSTOM_MODEL_SENTINEL]
    default_choice = (
        current_model
        if current_model in preset_slugs
        else (CUSTOM_MODEL_SENTINEL if current_model else preset_slugs[0])
    )
    picked = st.selectbox(
        t('模型名'),
        picker_options,
        format_func=lambda slug: t(preset_labels.get(slug, slug)),
        index=picker_options.index(default_choice),
        key=f"{key_prefix}_model_picker_{provider}",
    )
    if picked == CUSTOM_MODEL_SENTINEL:
        return st.text_input(
            t('自定义模型名'),
            value=current_model if current_model not in preset_slugs else "",
            key=f"{key_prefix}_model_custom_{provider}",
        )
    return picked


current_provider = db.get_setting(conn, "llm_provider", default="anthropic")
current_model = db.get_setting(conn, "llm_model", default=PROVIDER_DEFAULT_MODEL.get(current_provider, ""))

st.markdown(t('**当前使用**：{provider_label} · 模型 `{model}`', provider_label=t(PROVIDER_LABELS.get(current_provider, current_provider)), model=current_model))

# 加了 Qwen 国际版/MiniMax/自定义 API 之后这一行从 7 家变成 10 家，PROVIDER_LABELS
# 里那种"给下拉框看的"完整说明文字（比如"Qwen（通义千问，大陆账号，直连
# DashScope）"）塞进这么窄的一格会被截断，大陆/国际两个 Qwen 截出来的文字长得
# 一模一样，完全看不出区别。这里单独给这一行用一份简短标签，下拉框里还是用
# PROVIDER_LABELS 那份完整说明。
PROVIDER_SHORT_LABELS = {
    "anthropic": "Claude",
    "openai": "OpenAI",
    "deepseek": "DeepSeek",
    "kimi": "Kimi",
    "qwen": "Qwen(大陆)",
    "qwen_intl": "Qwen(国际)",
    "qwen_coding_plan": "Qwen(Coding Plan)",
    "qwen_coding_plan_intl": "Qwen(Coding Plan国际)",
    "grok": "Grok",
    "openrouter": "OpenRouter",
    "minimax": "MiniMax(国际)",
    "minimax_cn": "MiniMax(大陆)",
    "custom": "自定义",
}

st.markdown(t('**各供应商 key 配置状态**'))
status_cols = st.columns(len(PROVIDER_LABELS))
for col, (provider, label) in zip(status_cols, PROVIDER_LABELS.items()):
    has_key = bool(db.get_setting(conn, f"api_key::{provider}", default=None))
    col.metric(t(PROVIDER_SHORT_LABELS.get(provider, label)), t('已配置') if has_key else "—")

with st.container(border=True):
    # 不用 st.form——表单里的控件切换不会立刻重跑脚本，切供应商之后模型名默认值要等点了
    # 保存才会刷新，体验很怪（这个问题在翻译专用那块暴露得更明显，见下面 OpenRouter
    # 预设那段）。改成普通控件 + 手动保存按钮，选哪个供应商立刻就能看到对应的默认模型名。
    provider = st.selectbox(
        t('选用哪个供应商'),
        list(PROVIDER_LABELS.keys()),
        format_func=lambda p: t(PROVIDER_LABELS[p]),
        index=list(PROVIDER_LABELS.keys()).index(current_provider) if current_provider in PROVIDER_LABELS else 0,
        key="provider_select",
    )
    # key 按供应商区分：切换供应商时，每家自己上次填的（还没保存的）内容不会互相冲掉。
    model = _pick_model(
        provider,
        current_model if provider == current_provider else PROVIDER_DEFAULT_MODEL.get(provider, ""),
        key_prefix="provider",
    )
    base_url_input = ""
    if provider == "custom":
        # "自定义 API"——同事们各有各习惯用的供应商，不可能每一家都单独接一遍；只要
        # 对方提供 OpenAI 兼容的 chat completions 接口，填这里的 base_url + 上面的
        # 模型名 + 下面的 API key 就能用。
        base_url_input = st.text_input(
            t('base_url（对方文档里的 OpenAI 兼容接口地址，通常以 /v1 结尾）'),
            value=db.get_setting(conn, "custom_base_url", default=""),
            key="provider_custom_base_url",
        )
    api_key_input = st.text_input(
        t('API key（不填就留空——不会清空已经存的 key；环境变量兜底：{env_name}）', env_name=PROVIDER_API_KEY_ENV.get(provider, '')),
        type="password",
        key=f"provider_api_key_input_{provider}",
    )
    if st.button(t('保存'), key="provider_settings_save"):
        db.set_setting(conn, "llm_provider", provider)
        db.set_setting(conn, "llm_model", model)
        if provider == "custom" and base_url_input.strip():
            db.set_setting(conn, "custom_base_url", base_url_input.strip())
        if api_key_input.strip():
            db.set_setting(conn, f"api_key::{provider}", api_key_input.strip())
        st.success(t('已保存。'))
        st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# 翻译专用供应商——跟上面"通用"分开配，因为翻译这个用途文本量通常远大于分类/洞察
# （每道题的每个选项、每条开放题原文都要过一遍 AI），全用 Claude 这种旗舰模型价格
# 差距很大。不单独配的话自动退回复用上面的通用设置，不强制谁都得多填一次。
# ---------------------------------------------------------------------------

st.subheader(t('翻译专用供应商（省钱用，选填）'))
st.caption(
    t('题目/选项翻译、开放题原文翻译走的是这里配的供应商，不单独配就跟上面「通用」一致。翻译是短文本、大批量的活，用 DeepSeek / Qwen 这类按官方报价（2026-09 查证）单价只有 Claude Haiku 的十分之一左右，中文语感也不差，没必要用旗舰模型翻译选项名这种小活。推荐 DeepSeek：便宜、中文语料训练、翻译语感公认扎实；Qwen-Turbo 更便宜一档，短选项名够用。')
)

INHERIT_SENTINEL = "（跟通用一致）"
translation_provider_options = [INHERIT_SENTINEL, *PROVIDER_LABELS.keys()]

current_translation_provider = db.get_setting(conn, "llm_provider::translation", default=None)
current_translation_model = db.get_setting(conn, "llm_model::translation", default=None)

if current_translation_provider is None:
    st.caption(t('当前：跟通用一致。'))
else:
    st.markdown(
        t('**当前翻译专用**：{provider_label} · 模型 `{model}`', provider_label=t(PROVIDER_LABELS.get(current_translation_provider, current_translation_provider)), model=current_translation_model or PROVIDER_DEFAULT_MODEL.get(current_translation_provider, ''))
    )

with st.container(border=True):
    # 同样不用 st.form——切供应商要立刻切换对应的模型下拉框，表单里的控件切换不会
    # 马上重跑脚本，会看到刚选完供应商、模型名还是上一家供应商的默认值。
    default_index = (
        0
        if current_translation_provider is None
        else translation_provider_options.index(current_translation_provider)
        if current_translation_provider in translation_provider_options
        else 0
    )
    # 没配置过的话，下拉默认停在推荐供应商（DeepSeek）上，省得每个人都要自己去查该选哪个。
    if current_translation_provider is None:
        default_index = translation_provider_options.index(TRANSLATION_RECOMMENDED_PROVIDER)

    translation_provider = st.selectbox(
        t('翻译专用供应商'),
        translation_provider_options,
        format_func=lambda p: t(PROVIDER_LABELS.get(p, p)),
        index=default_index,
        key="translation_provider_select",
    )

    translation_model = None
    translation_api_key_input = ""
    translation_base_url_input = ""
    if translation_provider != INHERIT_SENTINEL:
        translation_model = _pick_model(
            translation_provider,
            current_translation_model
            if translation_provider == current_translation_provider
            else PROVIDER_DEFAULT_MODEL.get(translation_provider, ""),
            key_prefix="translation",
        )
        if translation_provider == "custom":
            translation_base_url_input = st.text_input(
                t('base_url（跟上面「通用」的自定义 API 共用同一个 base_url 设置）'),
                value=db.get_setting(conn, "custom_base_url", default=""),
                key="translation_custom_base_url",
            )
        translation_api_key_input = st.text_input(
            t('API key（跟上面通用供应商共用同一个 key 存储位置，同一家供应商不用重复填；环境变量兜底：{env_name}）', env_name=PROVIDER_API_KEY_ENV.get(translation_provider, '')),
            type="password",
            key=f"translation_api_key_input_{translation_provider}",
        )

    if st.button(t('保存'), key="translation_provider_settings_save"):
        if translation_provider == INHERIT_SENTINEL:
            db.delete_setting(conn, "llm_provider::translation")
            db.delete_setting(conn, "llm_model::translation")
        else:
            db.set_setting(conn, "llm_provider::translation", translation_provider)
            db.set_setting(conn, "llm_model::translation", translation_model)
            if translation_provider == "custom" and translation_base_url_input.strip():
                db.set_setting(conn, "custom_base_url", translation_base_url_input.strip())
            if translation_api_key_input.strip():
                db.set_setting(conn, f"api_key::{translation_provider}", translation_api_key_input.strip())
        st.success(t('已保存。'))
        st.rerun()
