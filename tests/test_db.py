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
    get_document_response_time,
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
    "mapping_templates": ["id", "name", "created_at", "rows_json"],
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


def test_init_db_creates_missing_parent_directories(tmp_path):
    """真实反馈的严重 bug：同事第一次 clone 仓库跑起来，直接报
    sqlite3.OperationalError: unable to open database file。根源是 data/ 这个
    目录从来没被 git 追踪过，全新 clone 下来根本不存在这个目录，sqlite3 不会
    自动创建数据库文件的父目录。这里专门模拟"全新 clone、data/ 目录还不存在"
    这个场景（不是用 tmp_path 本身——那个目录 pytest 已经建好了，测不出这个 bug），
    确认 init_db 自己会把缺失的父目录建起来，不需要调用方提前手动建。
    """

    nested_db_path = tmp_path / "fresh_clone" / "data" / "app.db"
    assert not nested_db_path.parent.exists()

    conn = init_db(str(nested_db_path))

    assert nested_db_path.exists()
    conn.close()
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


def test_migration_allows_ranking_question_type_without_breaking_existing_data(tmp_path):
    """模拟"改动之前"的老数据库：手写一张只认 single/multi/open/numeric 的 questions
    表，塞一些真实数据（带外键指向它的 responses 行），再用现在的 init_db 打开——
    新的 q_type='ranking' 要能存进去，旧数据（id、内容、外键关系）要原样保留，
    外键约束本身也不能被这次"整表重建"式的迁移搞坏（真机测的时候真的复现过一次
    SQLite 的坑：ALTER TABLE RENAME 默认会把 responses 表里的外键定义也跟着悄悄
    改指向重命名后的占位表，占位表删掉后外键就指向一个不存在的表——这条测试断言
    外键在迁移后依然正常拒绝一条指向不存在题目的记录，同时依然放行合法记录）。
    """

    db_path = str(tmp_path / "legacy_questions.sqlite")
    legacy_conn = sqlite3.connect(db_path)
    legacy_conn.execute("PRAGMA foreign_keys = ON")
    legacy_conn.execute(
        """
        CREATE TABLE documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            format TEXT NOT NULL
        )
        """
    )
    legacy_conn.execute(
        """
        CREATE TABLE questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL REFERENCES documents(id),
            q_no TEXT NOT NULL,
            q_type TEXT NOT NULL CHECK (q_type IN ('single','multi','open','numeric')),
            source_text_en TEXT,
            order_index INTEGER NOT NULL,
            section TEXT NOT NULL DEFAULT 'official'
                CHECK (section IN ('screen_out','official','background','platform_auto')),
            meta_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    legacy_conn.execute(
        """
        CREATE TABLE responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER NOT NULL REFERENCES questions(id),
            respondent_id TEXT NOT NULL,
            raw_value TEXT,
            translation TEXT,
            order_index INTEGER
        )
        """
    )
    legacy_conn.execute("INSERT INTO documents (id, project_id, filename, format) VALUES (1, 1, 'f.csv', 'csv')")
    legacy_conn.execute(
        "INSERT INTO questions (id, document_id, q_no, q_type, order_index) VALUES (7, 1, 'Q1', 'single', 0)"
    )
    legacy_conn.execute(
        "INSERT INTO responses (question_id, respondent_id, raw_value) VALUES (7, 'r1', 'A')"
    )
    legacy_conn.commit()
    legacy_conn.close()

    conn = init_db(db_path)

    # 旧数据原样保留，id 也没变（responses 的外键还指着 id=7 这道题）。init_db 用
    # sqlite3.Row 做 row_factory，Row 不支持直接跟普通 tuple 比 == ，先转一下。
    assert [tuple(r) for r in conn.execute("SELECT id, q_type FROM questions")] == [(7, "single")]
    assert [tuple(r) for r in conn.execute("SELECT question_id, raw_value FROM responses")] == [(7, "A")]

    # 新约束真的放宽了——'ranking' 现在能存进去。
    conn.execute(
        "INSERT INTO questions (document_id, q_no, q_type, order_index) VALUES (1, 'Q2', 'ranking', 1)"
    )
    assert conn.execute("SELECT q_type FROM questions WHERE q_no = 'Q2'").fetchone()[0] == "ranking"

    # 无效题型依然被拒绝——CHECK 约束没有被误放宽成"什么都能存"。
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO questions (document_id, q_no, q_type, order_index) VALUES (1, 'Q3', 'bogus', 2)"
        )

    # 外键约束依然正常工作——这条锁住那次真机复现过的坑（RENAME 悄悄改写了 responses
    # 的外键定义，指向一个之后会被删掉的占位表，导致外键校验直接报"no such table"）。
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO responses (question_id, respondent_id, raw_value) VALUES (999999, 'r2', 'B')"
        )
    conn.execute("INSERT INTO responses (question_id, respondent_id, raw_value) VALUES (7, 'r3', 'C')")

    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.commit()

    # 再打开一次（模拟服务重启）——迁移是幂等的，不会重复执行、不会再报错。
    conn.close()
    conn2 = init_db(db_path)
    assert conn2.execute("SELECT COUNT(*) FROM questions").fetchone()[0] == 2
    conn2.close()


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


def _add_platform_auto_question(conn, document_id, q_no, source_text_en, order_index, values):
    [question_id] = add_questions(
        conn, document_id,
        [Question(q_no, "open", source_text_en, order_index, "platform_auto")],
    )
    add_responses(
        conn, question_id,
        pd.DataFrame({"respondent_id": [f"r{i}" for i in range(len(values))], "raw_value": values}),
    )
    return question_id


class TestGetDocumentResponseTime:
    """真实反馈"这里需要显示问卷的发布时间...按照最晚填问卷的时间记录"——这批
    测试锁定 get_document_response_time() 的挑选规则：优先"结束/提交时间"这类
    列名，明确排除"开始时间"，两者常常同时出现、含义完全相反，选错了"发布时间"
    会显示成"这份问卷第一个人开始填的时间"而不是"最后一个人填完的时间"。
    """

    def test_returns_the_latest_submission_time_among_respondents(self, tmp_path):
        conn = init_db(str(tmp_path / "survey.sqlite"))
        project_id = create_project(conn, "测试项目", "en", "zh-CN")
        document_id = add_document(conn, project_id, "responses.csv", "csv")
        _add_platform_auto_question(
            conn, document_id, "P1", "提交时间", 0,
            ["2026-09-17 09:00:00", "2026-09-17 13:06:58", "2026-09-16 08:00:00"],
        )

        assert get_document_response_time(conn, document_id) == "2026-09-17 13:06:58"
        conn.close()

    def test_prefers_end_time_column_over_start_time_column(self, tmp_path):
        conn = init_db(str(tmp_path / "survey.sqlite"))
        project_id = create_project(conn, "测试项目", "en", "zh-CN")
        document_id = add_document(conn, project_id, "responses.csv", "csv")
        # "开始时间"的最大值故意设得比"结束时间"更晚——如果实现选错了列，这条测试
        # 就能抓到（不是靠两列刚好同值蒙混过关）。
        _add_platform_auto_question(conn, document_id, "P1", "开始时间", 0, ["2026-09-18 23:00:00"])
        _add_platform_auto_question(conn, document_id, "P2", "结束时间", 1, ["2026-09-17 13:06:58"])

        assert get_document_response_time(conn, document_id) == "2026-09-17 13:06:58"
        conn.close()

    def test_falls_back_to_any_parseable_platform_column_when_no_keyword_matches(self, tmp_path):
        # 有些平台导出的时间列名不落在已知关键词里（比如"作答时间戳"这种）——
        # 只要值本身能被解析成时间，也应该被用上，不能因为列名没命中关键词就
        # 直接放弃、退化成 None。
        conn = init_db(str(tmp_path / "survey.sqlite"))
        project_id = create_project(conn, "测试项目", "en", "zh-CN")
        document_id = add_document(conn, project_id, "responses.csv", "csv")
        _add_platform_auto_question(
            conn, document_id, "P1", "作答时间戳", 0,
            ["2026-09-17 09:00:00", "2026-09-17 13:06:58"],
        )

        assert get_document_response_time(conn, document_id) == "2026-09-17 13:06:58"
        conn.close()

    def test_returns_none_when_there_are_no_platform_auto_questions(self, tmp_path):
        conn = init_db(str(tmp_path / "survey.sqlite"))
        project_id = create_project(conn, "测试项目", "en", "zh-CN")
        document_id = add_document(conn, project_id, "responses.csv", "csv")
        add_questions(conn, document_id, [Question("Q1", "single", "偏好", 0, "official")])

        assert get_document_response_time(conn, document_id) is None
        conn.close()

    def test_returns_none_when_platform_auto_values_are_not_dates(self, tmp_path):
        # 平台信息列不一定是时间（IP、设备型号……）——大多数值解析失败时不能瞎猜，
        # 应该退回 None，让调用方去用数据库自己的 updated_at。
        conn = init_db(str(tmp_path / "survey.sqlite"))
        project_id = create_project(conn, "测试项目", "en", "zh-CN")
        document_id = add_document(conn, project_id, "responses.csv", "csv")
        _add_platform_auto_question(
            conn, document_id, "P1", "IP", 0, ["192.168.1.1", "10.0.0.2", "8.8.8.8"],
        )

        assert get_document_response_time(conn, document_id) is None
        conn.close()
