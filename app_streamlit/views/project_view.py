"""项目工作区：定量问卷调研 / 定性访谈 / 案头研究 三个分区。由 Home.py 的 st.navigation 加载。"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from engine import db
from engine.i18n import t
from app_streamlit.lang_ui import init_language

DB_PATH = PROJECT_ROOT / "data" / "app.db"


def get_conn():
    if "db_conn" not in st.session_state:
        st.session_state["db_conn"] = db.init_db(str(DB_PATH))
    return st.session_state["db_conn"]


conn = get_conn()
init_language(conn)

project_id = st.session_state.get("current_project_id")
if project_id is None:
    st.info(t('还没选中项目，回首页打开一个。'))
    if st.button(t('返回首页')):
        st.switch_page("views/home_view.py")
    st.stop()

project = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
if project is None:
    st.error(t('这个项目不存在了（可能被删了）。'))
    st.session_state["current_project_id"] = None
    if st.button(t('返回首页')):
        st.switch_page("views/home_view.py")
    st.stop()

if st.button(t('返回首页')):
    st.switch_page("views/home_view.py")

# The legacy placeholder is a persisted value used by database migrations.
display_name = t("未命名项目") if project["origin"] == "auto" and project["name"] == "未命名项目" else project["name"]
st.title(display_name)
st.caption(t('{source_lang} → {target_lang} · 建于 {created_at}', source_lang=project['source_lang'], target_lang=project['target_lang'], created_at=project['created_at']))

tab_quant, tab_qual, tab_desk = st.tabs([t('定量问卷调研'), t('定性访谈'), t('案头研究')])

with tab_quant:
    st.caption(t('这个项目历史上分析过的每份问卷，按最近更新排在最前面。'))

    documents = db.list_documents(conn, project_id, research_type="quant_survey")

    if not documents:
        st.info(t('这个项目下还没有问卷分析。'))
    else:
        for doc in documents:
            col_title, col_meta, col_open, col_rename, col_delete = st.columns([3, 2, 1, 1, 1])
            col_title.markdown(f"**{doc['title']}**")
            col_meta.caption(t('更新于 {updated_at}', updated_at=doc['updated_at']))
            if col_open.button(t('打开'), key=f"open_doc_{doc['id']}"):
                st.session_state["current_document_id"] = doc["id"]
                st.session_state["analysis_mode"] = "load_existing"
                st.switch_page("app.py")

            with col_rename.popover(t('重命名')):
                new_title = st.text_input(t('新标题'), value=doc["title"], key=f"rename_doc_input_{doc['id']}")
                if st.button(t('保存'), key=f"rename_doc_save_{doc['id']}"):
                    if new_title.strip():
                        db.rename_document(conn, doc["id"], new_title.strip())
                        st.rerun()
                    else:
                        st.error(t('标题不能为空。'))

            # 删除是不可逆操作——popover 本身是第一步确认，里面还要再点一次「确认删除」。
            with col_delete.popover(t('删除')):
                st.warning(t('确定删除「{title}」这份问卷分析？不可恢复。', title=doc['title']))
                if st.button(t('确认删除'), key=f"delete_doc_confirm_{doc['id']}", type="primary"):
                    db.delete_document(conn, doc["id"])
                    st.rerun()

    st.divider()
    if st.button(t('+ 新建问卷分析'), type="primary"):
        st.session_state["current_document_id"] = None
        st.session_state["analysis_mode"] = "new"
        # 切页面前把跟"上一次分析"相关的 session_state 清掉，避免带着旧数据进新分析。
        for key in ("mapping", "generated", "conclusions", "test_method"):
            st.session_state.pop(key, None)
        st.switch_page("app.py")

with tab_qual:
    st.info(
        t('定性访谈还没接进这个工具——已经有独立的 interview-crosstab skill（自包含 HTML，不需要这个工具的后端），架构完全不同，这里先占个分类位置，不强行合并。')
    )

with tab_desk:
    st.info(t('案头研究还没做，先占个分类位置。'))
