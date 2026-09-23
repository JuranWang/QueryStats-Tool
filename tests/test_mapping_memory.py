import json
import sqlite3
import textwrap
from pathlib import Path

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from engine import db, mapping_memory as memory, persistence


@pytest.fixture
def conn(tmp_path):
    path = tmp_path / "__TEST__mapping.sqlite"
    connection = db.init_db(str(path))
    try:
        yield connection
    finally:
        connection.close()
        path.unlink(missing_ok=True)


def row(column, q_type="single", section="正式", q_no="__TEST__auto", title="__TEST__auto title"):
    return dict(column=column, q_type=q_type, section=section, q_no=q_no, title=title)


def test_exact_match_precedes_normalization_and_does_not_mutate():
    current = pd.DataFrame([row("__TEST__A")])
    before = current.copy(deep=True)
    templates = [row("__TEST__a", title="__TEST__normalized"), row("__TEST__A", "numeric", "基础信息", title="__TEST__exact")]
    original_templates = json.dumps(templates)
    result, report = memory.apply_template(current, templates)
    assert result.iloc[0]["title"] == "__TEST__exact"
    assert result.iloc[0]["q_type"] == "numeric"
    assert result.iloc[0]["section"] == "基础信息"
    assert result.iloc[0]["q_no"] == "__TEST__auto"
    assert report["matched_count"] == report["total_count"] == 1
    assert_frame_equal(current, before)
    assert json.dumps(templates) == original_templates


def test_normalization_unmatched_report_and_preserved_shape():
    current = pd.DataFrame([
        row("  __TEST__Q　（ A ）  "), row("__TEST__new"), row("__TEST__Z"),
    ], index=[7, 7, 2])[ ["title", "column", "section", "q_no", "q_type"] ]
    templates = [row("__test__q(a)", "open", title="__TEST__edited"), row("__TEST__missing")]
    result, report = memory.apply_template(current, templates)
    assert result.iloc[0]["title"] == "__TEST__edited"
    assert_frame_equal(result.iloc[1:], current.iloc[1:])
    assert result.index.equals(current.index)
    assert result.columns.equals(current.columns)
    assert result["column"].tolist() == current["column"].tolist()
    assert report == dict(matched_count=1, total_count=3,
                          unmatched_columns=["__TEST__new", "__TEST__Z"],
                          missing_columns=["__TEST__missing"])


@pytest.mark.parametrize("templates, expected_keys", [
    ([row("__TEST__a", "multi", q_no="__TEST__saved"), row("__TEST__b", "multi", q_no="__TEST__saved")], ["__TEST__saved"] * 2),
    ([row("__TEST__a", "multi", q_no="__TEST__saved")], ["__TEST__auto"] * 2),
    ([row("__TEST__a", "multi", q_no="__TEST__one"), row("__TEST__b", "multi", q_no="__TEST__two")], ["__TEST__auto"] * 2),
    ([row("__TEST__a", "multi", q_no="__TEST__same"), row("__TEST__b", "multi", section="基础信息", q_no="__TEST__same")], ["__TEST__auto"] * 2),
    ([row("__TEST__a", "multi", q_no="__TEST__saved"), row("__TEST__b", "single", q_no="__TEST__saved")], ["__TEST__auto"] * 2),
])
def test_multi_keys_require_whole_current_group(templates, expected_keys):
    current = pd.DataFrame([row("__TEST__a", "multi"), row("__TEST__b", "multi")])
    result, _ = memory.apply_template(current, templates)
    assert result["q_no"].tolist() == expected_keys


def test_template_option_absent_from_data_does_not_block_complete_current_group():
    current = pd.DataFrame([row("__TEST__a", "multi"), row("__TEST__b", "multi")])
    templates = [row(f"__TEST__{option}", "multi", q_no="__TEST__saved") for option in "abc"]
    result, report = memory.apply_template(current, templates)
    assert result["q_no"].tolist() == ["__TEST__saved"] * 2
    assert report["missing_columns"] == ["__TEST__c"]


def test_multi_groups_are_scoped_by_section_and_new_multi_can_merge():
    current = pd.DataFrame([row("__TEST__a", "multi"), row("__TEST__b", "multi", "基础信息"), row("__TEST__c")])
    templates = [row("__TEST__a", "multi", q_no="__TEST__saved"), row("__TEST__c", "multi", q_no="__TEST__saved")]
    result, _ = memory.apply_template(current, templates)
    assert result["q_no"].tolist() == ["__TEST__saved", "__TEST__auto", "__TEST__saved"]


def test_template_key_does_not_collide_with_retained_automatic_group():
    current = pd.DataFrame([row("__TEST__a", "multi", q_no="__TEST__first"), row("__TEST__b", "multi", q_no="__TEST__second")])
    result, _ = memory.apply_template(current, [row("__TEST__a", "multi", q_no="__TEST__second")])
    assert result["q_no"].tolist() == current["q_no"].tolist()


def test_ambiguous_normalized_match_is_not_guessed():
    current = pd.DataFrame([row("__TEST__a ")])
    result, report = memory.apply_template(current, [row("__TEST__A"), row("__TEST__a")])
    assert_frame_equal(result, current)
    assert report["matched_count"] == 0


def test_empty_template_and_empty_frame():
    current = pd.DataFrame([row("__TEST__a")])
    result, report = memory.apply_template(current, [])
    assert_frame_equal(result, current)
    assert result is not current
    assert report["unmatched_columns"] == ["__TEST__a"]
    result, report = memory.apply_template(current.iloc[:0], [row("__TEST__a")])
    assert_frame_equal(result, current.iloc[:0])
    assert report["total_count"] == 0
    assert report["missing_columns"] == ["__TEST__a"]


def test_template_storage_deletion_and_cross_project_scope(conn):
    rows = [row("__TEST__column", title="__TEST__题目")]
    first = memory.save_template(conn, "  __TEST__template  ", rows)
    second = memory.save_template(conn, "__TEST__template", rows)
    assert [item["id"] for item in memory.list_templates(conn)] == [second, first]
    assert memory.list_templates(conn)[0]["created_at"]
    assert memory.load_template(conn, first) == rows
    assert memory.list_templates(conn)[1]["name"] == "__TEST__template"
    with pytest.raises(ValueError):
        memory.save_template(conn, "  ", rows)
    for template_id in (first, second):
        memory.delete_template(conn, template_id)
        assert memory.load_template(conn, template_id) is None
    memory.delete_template(conn, first)
    assert memory.list_templates(conn) == []


def saved_document(conn, project, suffix="one"):
    frame = pd.DataFrame({"__TEST__single": ["__TEST__yes"], "__TEST__a": [True], "__TEST__b": [False]})
    units = [
        dict(kind="single", section="筛选", title="__TEST__edited title", display_no="__TEST__S1", columns=["__TEST__single"]),
        dict(kind="multi", section="正式", title="__TEST__options", display_no="__TEST__Q1", columns=["__TEST__a", "__TEST__b"]),
    ]
    document_id = persistence.save_analysis(conn, project, units, frame, {}, {}, {}, [], f"__TEST__{suffix}.csv")
    return document_id, units, frame


def test_restore_saved_document_original_columns_and_unchanged_load(conn):
    project = db.create_project(conn, "__TEST__project", "en", "zh")
    document, _, _ = saved_document(conn, project)
    remembered = memory.latest_project_mapping(conn, project)
    assert remembered["id"] == document
    assert remembered["name"] == "__TEST__one.csv"
    assert remembered["rows"] == [
        row("__TEST__single", "single", "筛选", "__TEST__S1", "__TEST__edited title"),
        row("__TEST__a", "multi", "正式", "__TEST__Q1", "__TEST__options"),
        row("__TEST__b", "multi", "正式", "__TEST__Q1", "__TEST__options"),
    ]
    # Preserve the established load_analysis interface.
    assert list(persistence.load_analysis(conn, document)["df_all"].columns) == ["__TEST__S1", "__TEST__a", "__TEST__b"]
    assert memory.latest_project_mapping(conn, project, document) is None


def test_latest_formal_save_excludes_drafts_current_document_and_other_projects(conn):
    project = db.create_project(conn, "__TEST__project", "en", "zh")
    other = db.create_project(conn, "__TEST__other", "en", "zh")
    first, units, frame = saved_document(conn, project, "first")
    second, _, _ = saved_document(conn, project, "second")
    saved_document(conn, other, "other")
    draft = db.add_document(conn, project, "__TEST__draft.csv", "csv")
    db.write_autosave(conn, draft, {"mapping": [row("__TEST__draft")]})
    db.write_autosave(conn, first, {"mapping": [row("__TEST__newer_draft")]})
    db.rename_document(conn, first, "__TEST__renamed")
    persistence.save_ai_results(conn, first, {"__TEST__ai": {}})
    assert memory.latest_project_mapping(conn, project)["id"] == second
    assert memory.latest_project_mapping(conn, project, second)["id"] == first
    persistence.update_analysis(conn, first, project, units, frame, {}, {}, {}, [])
    assert memory.latest_project_mapping(conn, project)["id"] == first
    assert memory.latest_project_mapping(conn, None) is None


def test_original_column_names_survive_loading_and_resaving(conn):
    project = db.create_project(conn, "__TEST__project", "en", "zh")
    document, _, _ = saved_document(conn, project)
    expected = memory.latest_project_mapping(conn, project)["rows"]
    loaded = persistence.load_analysis(conn, document)
    persistence.update_analysis(conn, document, project, loaded["units"], loaded["df_all"], {}, {}, {}, [])
    assert memory.latest_project_mapping(conn, project)["rows"] == expected


def test_legacy_question_fallback_is_pure():
    questions = [dict(q_no="__TEST__Q1", q_type="single", source_text_en="__TEST__original", section="official", meta_json="{}")]
    assert memory.mapping_from_questions(questions) == [row("__TEST__original", q_no="__TEST__Q1", title="__TEST__original")]


def test_legacy_database_adds_only_template_table_and_preserves_settings(tmp_path):
    path = tmp_path / "__TEST__legacy.sqlite"
    conn = sqlite3.connect(path)
    try:
        conn.executescript(db.SCHEMA.split("CREATE TABLE IF NOT EXISTS mapping_templates")[0])
        conn.execute("INSERT INTO settings VALUES (?, ?)", ("__TEST__setting", "__TEST__unchanged"))
        conn.commit()
        before = conn.execute("SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    finally:
        conn.close()
    conn = db.init_db(str(path))
    try:
        assert conn.execute("SELECT value FROM settings WHERE key='__TEST__setting'").fetchone()[0] == "__TEST__unchanged"
        after = [tuple(item) for item in conn.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name != 'mapping_templates' ORDER BY name")]
        assert before == after
        memory.save_template(conn, "__TEST__legacy", [row("__TEST__a")])
    finally:
        conn.close()
        path.unlink(missing_ok=True)


@pytest.fixture
def mapping_app(conn):
    """Run only the actual mapping section, with a temporary DB and no app startup."""
    from streamlit.testing.v1 import AppTest

    source = (Path(__file__).resolve().parents[1] / "app_streamlit/app.py").read_text()
    block = textwrap.dedent(source[
        source.index('    st.subheader(t("数据映射"), anchor="mapping-table")'):
        source.index('    # 4. 筛选设置')
    ])
    app = AppTest.from_string('''
import pandas as pd
import streamlit as st
from engine import clean, mapping_memory
from engine.i18n import t, set_lang
set_lang("zh")
ALL_SECTIONS = ["筛选", "正式", "基础信息", "平台信息"]
def _get_db_conn():
    return st.session_state["__TEST__conn"]
def guess_is_platform_column(column):
    return False
df_all = st.session_state["__TEST__data"]
''' + block)
    app.session_state["__TEST__conn"] = conn
    app.session_state["__TEST__data"] = pd.DataFrame({"__TEST__single": ["__TEST__yes"]})
    return app


def test_ui_auto_applies_once_preserves_edits_and_undoes(conn, mapping_app):
    app = mapping_app
    project = db.create_project(conn, "__TEST__project", "en", "zh")
    saved_document(conn, project)
    app.session_state["current_project_id"] = project
    app.run()
    assert not app.exception
    assert app.session_state["mapping"].iloc[0]["title"] == "__TEST__edited title"
    assert len(app.info) == 1
    assert app.session_state["generated"] is False

    app.session_state["mapping_editor"] = {"edited_rows": {0: {"title": "__TEST__manual"}}, "added_rows": [], "deleted_rows": []}
    app.run()
    app.session_state["generated"] = True
    app.run()
    assert app.session_state["mapping"].iloc[0]["title"] == "__TEST__manual"
    app.button(key="mapping_template_undo").click().run()
    assert not app.exception
    assert app.session_state["mapping"].iloc[0]["title"] == "__TEST__single"
    assert app.session_state["generated"] is True
    assert not app.info
    app.run()
    assert app.session_state["mapping"].iloc[0]["title"] == "__TEST__single"


def test_ui_no_history_template_crud_apply_and_new_mapping_reset(conn, mapping_app):
    app = mapping_app.run()
    assert not app.exception
    assert not app.info
    assert not app.selectbox
    assert len(app.button) == 1
    assert app.button(key="mapping_template_save").disabled
    app.session_state["mapping_editor"] = {"edited_rows": {0: {"title": "__TEST__manual"}}, "added_rows": [], "deleted_rows": []}
    app.run()
    app.text_input(key="mapping_template_name").set_value("__TEST__template").run()
    app.button(key="mapping_template_save").click().run()
    assert not app.exception
    [template] = memory.list_templates(conn)
    assert memory.load_template(conn, template["id"])[0]["title"] == "__TEST__manual"

    app.session_state["mapping_editor"] = {"edited_rows": {0: {"title": "__TEST__changed"}}, "added_rows": [], "deleted_rows": []}
    app.run()
    app.button(key="mapping_template_apply").click().run()
    assert not app.exception
    assert app.session_state["mapping"].iloc[0]["title"] == "__TEST__manual"
    app.run()
    assert app.session_state["mapping"].iloc[0]["title"] == "__TEST__manual"
    app.button(key="mapping_template_undo").click().run()
    assert app.session_state["mapping"].iloc[0]["title"] == "__TEST__single"
    app.button(key="mapping_template_delete").click().run()
    assert not app.exception
    assert memory.list_templates(conn) == []
    assert not app.selectbox

    app.session_state["__TEST__data"] = pd.DataFrame({"__TEST__different": [1]})
    app.run()
    assert not app.exception
    assert app.session_state["mapping"]["column"].tolist() == ["__TEST__different"]
    assert app.session_state["mapping_auto"]["column"].tolist() == ["__TEST__different"]
    assert "mapping_memory_report" not in app.session_state


def test_ranking_template_preserves_group_and_rejects_partial_group():
    current = pd.DataFrame([row(f"__TEST__Rank-{label}", "ranking") for label in ("A", "B")])
    template = [row(f"__TEST__Rank-{label}", "ranking", q_no="__TEST__saved") for label in ("A", "B")]
    restored, _ = memory.apply_template(current, template)
    assert restored["q_no"].tolist() == ["__TEST__saved"] * 2
    partial, _ = memory.apply_template(current, template[:1])
    assert partial["q_no"].tolist() == ["__TEST__auto"] * 2
