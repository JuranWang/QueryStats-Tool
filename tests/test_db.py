import sqlite3

import pandas as pd
import pytest

from engine.db import (
    add_conclusion,
    add_document,
    add_questions,
    add_responses,
    backup_database,
    create_project,
    delete_conclusion,
    delete_document,
    delete_project,
    get_test_method,
    init_db,
    list_conclusions,
    list_documents,
    read_autosave,
    read_document_extras,
    rename_document,
    rename_project,
    replace_conclusions,
    set_test_method,
    update_conclusion,
    write_autosave,
    write_document_extras,
)
from engine.ingest import Question


EXPECTED_COLUMNS = {
    "projects": ["id", "name", "source_lang", "target_lang", "origin", "created_at", "updated_at"],
    "documents": [
        "id",
        "project_id",
        "filename",
        "format",
        "branch_label",
        "research_type",
        "title",
        "uploaded_at",
        "updated_at",
    ],
    "questions": [
        "id",
        "document_id",
        "q_no",
        "q_type",
        "source_text_en",
        "order_index",
        "section",
        "meta_json",
    ],
    "responses": [
        "id",
        "question_id",
        "respondent_id",
        "raw_value",
        "translation",
        "order_index",
    ],
    "categories": ["id", "question_id", "label", "source"],
    "response_categories": ["response_id", "category_id"],
    "ai_runs": [
        "id",
        "question_id",
        "mode",
        "prompt_version",
        "raw_output",
        "created_at",
    ],
    "share_links": ["id", "project_id", "token", "scope", "expires_at"],
    "settings": ["key", "value"],
    "test_method": [
        "project_id",
        "platform_source",
        "is_branched",
        "branch_count",
        "screen_out_rule",
        "skip_logic_note",
    ],
    "conclusions": ["id", "project_id", "text", "order_index"],
    "autosaves": ["document_id", "payload_json", "saved_at"],
    "document_extras": ["document_id", "payload_json", "updated_at"],
}


def test_init_db_creates_all_ddl_tables_and_exact_columns(tmp_path):
    conn = init_db(str(tmp_path / "survey.sqlite"))

    assert conn.row_factory is sqlite3.Row
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    table_names = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    assert table_names == set(EXPECTED_COLUMNS)

    for table, expected_columns in EXPECTED_COLUMNS.items():
        actual_columns = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})")]
        assert actual_columns == expected_columns

    # IF NOT EXISTS makes repeat initialization safe.
    second_conn = init_db(str(tmp_path / "survey.sqlite"))
    second_conn.close()
    conn.close()


def test_basic_writes_preserve_input_order_and_optional_translation(tmp_path):
    conn = init_db(str(tmp_path / "survey.sqlite"))
    project_id = create_project(conn, "测试项目", "en", "zh-CN")
    document_id = add_document(conn, project_id, "responses.csv", "csv")
    question_ids = add_questions(
        conn,
        document_id,
        [
            Question("S1", "single", "Qualified?", 0, "screen_out"),
            Question("Q1", "open", "Why?", 1),
        ],
    )

    assert len(question_ids) == 2
    assert [row["q_no"] for row in conn.execute("SELECT q_no FROM questions ORDER BY id")] == [
        "S1",
        "Q1",
    ]

    responses = pd.DataFrame(
        {
            "respondent_id": ["r1", "r2"],
            "raw_value": ["Good", "Fast"],
            "translation": ["好", "快"],
        },
        index=[10, 20],
    )
    add_responses(conn, question_ids[1], responses)

    stored = conn.execute(
        "SELECT respondent_id, raw_value, translation, order_index FROM responses ORDER BY id"
    ).fetchall()
    assert [tuple(row) for row in stored] == [
        ("r1", "Good", "好", 0),
        ("r2", "Fast", "快", 1),
    ]
    conn.close()


def test_foreign_keys_and_question_type_check_are_enforced(tmp_path):
    conn = init_db(str(tmp_path / "survey.sqlite"))

    with pytest.raises(sqlite3.IntegrityError):
        add_document(conn, 999, "missing.csv", "csv")

    project_id = create_project(conn, "测试项目", "en", "zh-CN")
    document_id = add_document(conn, project_id, "responses.csv", "csv")
    with pytest.raises(sqlite3.IntegrityError):
        add_questions(conn, document_id, [Question("Q1", "invalid", "Bad type", 0)])
    conn.close()


def test_question_section_check_is_enforced(tmp_path):
    conn = init_db(str(tmp_path / "survey.sqlite"))
    project_id = create_project(conn, "测试项目", "en", "zh-CN")
    document_id = add_document(conn, project_id, "responses.csv", "csv")

    with pytest.raises(sqlite3.IntegrityError):
        add_questions(
            conn,
            document_id,
            [Question("Q1", "single", "Bad section", 0, "invalid")],
        )
    conn.close()


def test_add_document_stores_optional_branch_label(tmp_path):
    conn = init_db(str(tmp_path / "survey.sqlite"))
    project_id = create_project(conn, "测试项目", "en", "zh-CN")

    unlabeled_id = add_document(conn, project_id, "all.csv", "csv")
    labeled_id = add_document(conn, project_id, "group-1.csv", "csv", "组1")

    rows = conn.execute(
        "SELECT id, branch_label FROM documents ORDER BY id"
    ).fetchall()
    assert [dict(row) for row in rows] == [
        {"id": unlabeled_id, "branch_label": None},
        {"id": labeled_id, "branch_label": "组1"},
    ]
    conn.close()


def test_set_and_get_test_method_upserts_full_row_and_handles_missing(tmp_path):
    conn = init_db(str(tmp_path / "survey.sqlite"))
    project_id = create_project(conn, "测试项目", "en", "zh-CN")

    assert get_test_method(conn, project_id) is None

    set_test_method(
        conn,
        project_id,
        platform_source="Prolific + Tally",
        is_branched=True,
        branch_count=2,
        screen_out_rule="未成年筛出",
        skip_logic_note="Q2 跳至 Q5",
    )
    assert get_test_method(conn, project_id) == {
        "project_id": project_id,
        "platform_source": "Prolific + Tally",
        "is_branched": 1,
        "branch_count": 2,
        "screen_out_rule": "未成年筛出",
        "skip_logic_note": "Q2 跳至 Q5",
    }

    set_test_method(
        conn,
        project_id,
        platform_source="Tally",
        is_branched=False,
        branch_count=None,
        screen_out_rule="无",
        skip_logic_note=None,
    )
    assert get_test_method(conn, project_id) == {
        "project_id": project_id,
        "platform_source": "Tally",
        "is_branched": 0,
        "branch_count": None,
        "screen_out_rule": "无",
        "skip_logic_note": None,
    }
    assert conn.execute(
        "SELECT COUNT(*) FROM test_method WHERE project_id = ?", (project_id,)
    ).fetchone()[0] == 1
    conn.close()


def test_create_project_defaults_to_manual_origin(tmp_path):
    conn = init_db(str(tmp_path / "survey.sqlite"))
    manual_id = create_project(conn, "手动建的项目", "en", "zh-CN")
    auto_id = create_project(conn, "自动建的项目", "en", "zh-CN", origin="auto")

    assert conn.execute("SELECT origin FROM projects WHERE id = ?", (manual_id,)).fetchone()[0] == "manual"
    assert conn.execute("SELECT origin FROM projects WHERE id = ?", (auto_id,)).fetchone()[0] == "auto"
    conn.close()


def test_rename_project_flips_origin_to_manual(tmp_path):
    # 一个自动占位项目一旦被人手动改过名字，就该算"手动"了，不该继续被"自动生成"
    # 筛选一直当成待清理的噪音。
    conn = init_db(str(tmp_path / "survey.sqlite"))
    project_id = create_project(conn, "未命名项目", "en", "zh-CN", origin="auto")

    rename_project(conn, project_id, "改过的项目名")

    row = conn.execute("SELECT name, origin FROM projects WHERE id = ?", (project_id,)).fetchone()
    assert row["name"] == "改过的项目名"
    assert row["origin"] == "manual"
    conn.close()


def test_migration_backfills_origin_for_old_databases(tmp_path):
    # 模拟"改动之前"的老数据库：手写一个没有 origin 列的 projects 表，再用现在的
    # init_db 打开它——新列要能补上，而且名字精确是"未命名项目"的老占位项目要能被
    # 自动回填成 origin='auto'，不用用户自己一个个标记。
    db_path = str(tmp_path / "legacy.sqlite")
    legacy_conn = sqlite3.connect(db_path)
    legacy_conn.execute(
        """
        CREATE TABLE projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            source_lang TEXT,
            target_lang TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    legacy_conn.execute("INSERT INTO projects (name) VALUES ('未命名项目')")
    legacy_conn.execute("INSERT INTO projects (name) VALUES ('客户委托的品牌调研')")
    legacy_conn.commit()
    legacy_conn.close()

    conn = init_db(db_path)
    rows = {row["name"]: row["origin"] for row in conn.execute("SELECT name, origin FROM projects")}
    assert rows["未命名项目"] == "auto"
    assert rows["客户委托的品牌调研"] == "manual"
    conn.close()


def test_conclusion_crud_orders_updates_and_deletes(tmp_path):
    conn = init_db(str(tmp_path / "survey.sqlite"))
    project_id = create_project(conn, "测试项目", "en", "zh-CN")

    third_id = add_conclusion(conn, project_id, "第三条", 30)
    first_id = add_conclusion(conn, project_id, "第一条", 10)
    second_id = add_conclusion(conn, project_id, "第二条", 20)

    assert list_conclusions(conn, project_id) == [
        {"id": first_id, "text": "第一条", "order_index": 10},
        {"id": second_id, "text": "第二条", "order_index": 20},
        {"id": third_id, "text": "第三条", "order_index": 30},
    ]

    update_conclusion(conn, second_id, "更新后的第二条")
    assert list_conclusions(conn, project_id)[1] == {
        "id": second_id,
        "text": "更新后的第二条",
        "order_index": 20,
    }

    delete_conclusion(conn, first_id)
    assert list_conclusions(conn, project_id) == [
        {"id": second_id, "text": "更新后的第二条", "order_index": 20},
        {"id": third_id, "text": "第三条", "order_index": 30},
    ]
    conn.close()


def test_replace_conclusions_overwrites_instead_of_accumulating(tmp_path):
    # 手动保存要能反复调用而不是每次都往 conclusions 表里堆——这也是 update_analysis
    # 用 replace_conclusions 而不是 add_conclusion 循环的原因。
    conn = init_db(str(tmp_path / "survey.sqlite"))
    project_id = create_project(conn, "测试项目", "en", "zh-CN")

    replace_conclusions(conn, project_id, ["第一版结论A", "第一版结论B"])
    replace_conclusions(conn, project_id, ["第二版结论"])

    texts = [c["text"] for c in list_conclusions(conn, project_id)]
    assert texts == ["第二版结论"]
    conn.close()


def test_write_autosave_occupies_a_single_slot_per_document(tmp_path):
    # "自动保存只占一个位置"——同一个 document_id 反复写，只留最新一份，不越存越多。
    conn = init_db(str(tmp_path / "survey.sqlite"))
    project_id = create_project(conn, "测试项目", "en", "zh-CN")
    document_id = add_document(conn, project_id, "responses.csv", "csv")

    write_autosave(conn, document_id, {"mapping": [{"column": "v1"}]})
    write_autosave(conn, document_id, {"mapping": [{"column": "v2"}]})

    assert read_autosave(conn, document_id)["payload"] == {"mapping": [{"column": "v2"}]}
    row_count = conn.execute(
        "SELECT COUNT(*) FROM autosaves WHERE document_id = ?", (document_id,)
    ).fetchone()[0]
    assert row_count == 1
    conn.close()


def test_read_autosave_returns_none_when_no_draft_exists(tmp_path):
    conn = init_db(str(tmp_path / "survey.sqlite"))
    project_id = create_project(conn, "测试项目", "en", "zh-CN")
    document_id = add_document(conn, project_id, "responses.csv", "csv")

    assert read_autosave(conn, document_id) is None
    conn.close()


def test_write_document_extras_occupies_a_single_slot_per_document(tmp_path):
    conn = init_db(str(tmp_path / "survey.sqlite"))
    project_id = create_project(conn, "测试项目", "en", "zh-CN")
    document_id = add_document(conn, project_id, "responses.csv", "csv")

    write_document_extras(conn, document_id, {"images": {"Q1": [{"name": "a.png"}]}})
    write_document_extras(conn, document_id, {"images": {"Q1": [{"name": "b.png"}]}})

    assert read_document_extras(conn, document_id) == {"images": {"Q1": [{"name": "b.png"}]}}
    row_count = conn.execute(
        "SELECT COUNT(*) FROM document_extras WHERE document_id = ?", (document_id,)
    ).fetchone()[0]
    assert row_count == 1
    conn.close()


def test_read_document_extras_returns_none_when_nothing_saved(tmp_path):
    conn = init_db(str(tmp_path / "survey.sqlite"))
    project_id = create_project(conn, "测试项目", "en", "zh-CN")
    document_id = add_document(conn, project_id, "responses.csv", "csv")

    assert read_document_extras(conn, document_id) is None
    conn.close()


def test_rename_and_delete_document_cascades_dependent_rows(tmp_path):
    conn = init_db(str(tmp_path / "survey.sqlite"))
    project_id = create_project(conn, "测试项目", "en", "zh-CN")
    document_id = add_document(conn, project_id, "responses.csv", "csv", title="旧标题")
    [question_id] = add_questions(
        conn,
        document_id,
        [Question(q_no="Q1", q_type="single", source_text_en="q", order_index=0)],
    )
    add_responses(
        conn, question_id, pd.DataFrame({"respondent_id": ["r1"], "raw_value": ["a"]})
    )
    write_autosave(conn, document_id, {"mapping": []})
    write_document_extras(conn, document_id, {"images": {}})

    rename_document(conn, document_id, "新标题")
    assert list_documents(conn, project_id)[0]["title"] == "新标题"

    delete_document(conn, document_id)

    assert list_documents(conn, project_id) == []
    assert conn.execute(
        "SELECT COUNT(*) FROM questions WHERE document_id = ?", (document_id,)
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM responses WHERE question_id = ?", (question_id,)
    ).fetchone()[0] == 0
    assert read_document_extras(conn, document_id) is None
    assert read_autosave(conn, document_id) is None
    conn.close()


def test_rename_and_delete_project_cascades_documents_and_conclusions(tmp_path):
    conn = init_db(str(tmp_path / "survey.sqlite"))
    project_id = create_project(conn, "旧项目名", "en", "zh-CN")
    document_id = add_document(conn, project_id, "responses.csv", "csv")
    add_conclusion(conn, project_id, "一条结论", 0)

    rename_project(conn, project_id, "新项目名")
    assert conn.execute(
        "SELECT name FROM projects WHERE id = ?", (project_id,)
    ).fetchone()["name"] == "新项目名"

    delete_project(conn, project_id)

    assert conn.execute(
        "SELECT COUNT(*) FROM projects WHERE id = ?", (project_id,)
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM documents WHERE id = ?", (document_id,)
    ).fetchone()[0] == 0
    assert list_conclusions(conn, project_id) == []
    conn.close()


def test_init_db_creates_an_initial_backup(tmp_path):
    # init_db 内部会顺手调用一次 backup_database——数据库一建好、连接一开，
    # 备份目录和第一份备份文件就该出现，不用等用户手动做什么。
    db_path = tmp_path / "survey.sqlite"
    conn = init_db(str(db_path))
    backups = sorted((tmp_path / "backups").glob("survey-*.db"))
    assert len(backups) == 1
    conn.close()


def test_backup_database_produces_an_openable_copy_with_the_same_data(tmp_path):
    db_path = tmp_path / "survey.sqlite"
    conn = init_db(str(db_path))
    project_id = create_project(conn, "备份测试项目", "en", "zh-CN")

    backup_path = backup_database(conn, str(db_path), force=True)
    assert backup_path is not None

    backup_conn = sqlite3.connect(backup_path)
    backup_conn.row_factory = sqlite3.Row
    row = backup_conn.execute(
        "SELECT name FROM projects WHERE id = ?", (project_id,)
    ).fetchone()
    assert row["name"] == "备份测试项目"
    backup_conn.close()
    conn.close()


def test_backup_database_is_throttled_unless_forced(tmp_path):
    db_path = tmp_path / "survey.sqlite"
    conn = init_db(str(db_path))  # 这一步已经产出了第一份备份

    # 节流生效：紧接着再调一次（不传 force），不足 min_interval_seconds，应该是 no-op。
    result = backup_database(conn, str(db_path), min_interval_seconds=3600)
    assert result is None
    backups = sorted((tmp_path / "backups").glob("survey-*.db"))
    assert len(backups) == 1

    # force=True 跳过节流，一定会再产出一份新的（用不同的时间戳文件名区分）。
    import time as _time
    _time.sleep(1.1)  # 时间戳精确到秒，隔开一点避免文件名撞在一起
    result = backup_database(conn, str(db_path), min_interval_seconds=3600, force=True)
    assert result is not None
    backups = sorted((tmp_path / "backups").glob("survey-*.db"))
    assert len(backups) == 2
    conn.close()


def test_backup_database_rotates_old_backups_beyond_keep_count(tmp_path):
    db_path = tmp_path / "survey.sqlite"
    conn = init_db(str(db_path))

    import time as _time
    for _ in range(4):
        _time.sleep(1.1)
        backup_database(conn, str(db_path), keep=3, min_interval_seconds=0, force=True)

    backups = sorted((tmp_path / "backups").glob("survey-*.db"))
    # init_db 建库时已经产出 1 份，加上循环里 4 份，一共 5 份——超过 keep=3 的部分
    # 应该被自动清掉，只留最近 3 份。
    assert len(backups) == 3
    conn.close()
