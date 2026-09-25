"""SQLite schema and basic persistence for survey analysis projects."""

from __future__ import annotations

import json
import sqlite3
import time
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd

if TYPE_CHECKING:
    from .ingest import Question


SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    source_lang TEXT,
    target_lang TEXT,
    -- 'auto'：分析页面在没有项目上下文时自动建的占位项目（比如直接跑 app.py，或者
    -- 服务端重启后浏览器还停在分析页）；'manual'：用户自己在首页点"新建项目"建的，
    -- 或者已经被人手动重命名过、确认过的。首页用这个字段做"自动/手动"筛选，不然
    -- 自动占位项目会跟真正的项目混在一起，列表越滚越长。
    origin TEXT NOT NULL DEFAULT 'manual' CHECK (origin IN ('manual', 'auto')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    filename TEXT NOT NULL,
    format TEXT NOT NULL,
    branch_label TEXT,
    research_type TEXT NOT NULL DEFAULT 'quant_survey'
        CHECK (research_type IN ('quant_survey','qualitative','desk_research')),
    title TEXT,
    uploaded_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents(id),
    q_no TEXT NOT NULL,
    q_type TEXT NOT NULL CHECK (q_type IN ('single','multi','open','numeric','ranking')),
    source_text_en TEXT,
    order_index INTEGER NOT NULL,
    section TEXT NOT NULL DEFAULT 'official'
        CHECK (section IN ('screen_out','official','background','platform_auto')),
    meta_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS test_method (
    project_id INTEGER PRIMARY KEY REFERENCES projects(id),
    platform_source TEXT,
    is_branched INTEGER NOT NULL DEFAULT 0,
    branch_count INTEGER,
    screen_out_rule TEXT,
    skip_logic_note TEXT
);

CREATE TABLE IF NOT EXISTS conclusions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    text TEXT NOT NULL,
    order_index INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER NOT NULL REFERENCES questions(id),
    respondent_id TEXT NOT NULL,
    raw_value TEXT,
    translation TEXT,
    order_index INTEGER
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER NOT NULL REFERENCES questions(id),
    label TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('manual','ai_closed','ai_open_frozen'))
);

CREATE TABLE IF NOT EXISTS response_categories (
    response_id INTEGER NOT NULL REFERENCES responses(id),
    category_id INTEGER NOT NULL REFERENCES categories(id),
    PRIMARY KEY (response_id, category_id)
);

CREATE TABLE IF NOT EXISTS ai_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER NOT NULL REFERENCES questions(id),
    mode TEXT NOT NULL,
    prompt_version TEXT,
    raw_output TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS share_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    token TEXT NOT NULL UNIQUE,
    scope TEXT,
    expires_at TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- 自动保存只占一个位置：document_id 是主键，每次自动保存用 INSERT ... ON CONFLICT
-- 整个替换掉上一份草稿，不会越存越多；跟 questions/responses（手动保存写的"正式"数据）
-- 完全是两张表，结构上就不可能覆盖手动保存的内容。
CREATE TABLE IF NOT EXISTS autosaves (
    document_id INTEGER PRIMARY KEY REFERENCES documents(id),
    payload_json TEXT NOT NULL,
    saved_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- "正式保存"里那些形状差异太大、不适合拆成关系表的内容：AI 分类结果、插入的图片
-- （连同文字描述）、拖拽排版位置。跟 questions.meta_json 是同一个思路——一份 JSON blob，
-- 每份问卷只占一行（document_id 是主键），手动保存整份覆盖。这张表结构上就是"正式"
-- 数据的一部分（不是草稿），只是内容形状不一样，不跟 autosaves 混在一起。
CREATE TABLE IF NOT EXISTS document_extras (
    document_id INTEGER PRIMARY KEY REFERENCES documents(id),
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

SCHEMA += """
CREATE TABLE IF NOT EXISTS mapping_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    rows_json TEXT NOT NULL
);
"""


def init_db(db_path: str) -> sqlite3.Connection:
    """Open a database, enforce foreign keys, and idempotently create its schema.

    ``check_same_thread=False``: Streamlit can rerun a session's script on a different
    worker thread than the one that created the connection stashed in ``st.session_state``,
    which trips sqlite3's default same-thread check (`sqlite3.ProgrammingError`). Streamlit
    still serializes reruns for a given session — there is no genuine concurrent access to
    this connection from two threads at once — so relaxing the check is safe for this
    single-user, single-process tool.

    真实反馈的严重 bug：同事第一次 clone 下来跑，直接报
    `sqlite3.OperationalError: unable to open database file`。根源是 `data/`
    这整个目录从来没有被 git 追踪过（`.gitignore` 排除的是 `data/app.db` 这些
    具体文件，但从来没有哪个文件把 `data/` 这个目录本身带进 git 历史里），全新
    `git clone` 下来的仓库根本没有 `data/` 这个目录；sqlite3 不会自动创建数据库
    文件所在的父目录（只会创建文件本身），目录不存在就直接抛这个错。这个 bug
    之前一直没暴露，是因为开发机上 `data/` 目录很早就手动建过、一直留到现在，
    每次都当"已经存在"用——对任何全新 clone 的人都必现。别的几个子目录
    （uploads/exports/backups）各自的调用点已经有 `mkdir(parents=True,
    exist_ok=True)`，唯独这里（整个 app 最先被调用、最上游的入口）没有。
    """

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate_add_missing_columns(conn)
    _migrate_questions_allow_ranking_type(conn)
    conn.commit()

    # 每次真正建立数据库连接（大致是"每次开一个新的浏览器 session"）都顺手检查一下
    # 要不要备份——具体多久备份一次由 backup_database 自己的节流逻辑决定，这里不用
    # 关心。备份失败（比如硬盘满了）绝对不能把整个 app 搞挂，包一层 try/except。
    try:
        backup_database(conn, db_path)
    except Exception:  # noqa: BLE001 — 备份本身出问题不能挡住正常使用
        pass

    return conn


BACKUP_INTERVAL_SECONDS = 6 * 60 * 60  # 6 小时检查一次要不要备份，够及时也不会写盘太勤
BACKUP_KEEP_COUNT = 30  # 保留最近 30 份——按 6 小时一份算覆盖最近一周多，不会无限占硬盘


def backup_database(
    conn: sqlite3.Connection,
    db_path: str,
    backup_dir: str | None = None,
    *,
    keep: int = BACKUP_KEEP_COUNT,
    min_interval_seconds: int = BACKUP_INTERVAL_SECONDS,
    force: bool = False,
) -> str | None:
    """把当前数据库整个备份一份带时间戳的文件，超过 `keep` 份的旧备份自动清掉。

    这是防数据丢失的最后一道保险——SQLite 文件本身不会自动有第二份拷贝，硬盘坏了、
    不小心删了 data/app.db、或者以后哪次改动不小心把数据写坏了，只能靠这份独立在
    别的文件里的备份救回来，不能只指望正在用的这一份 db 文件永远完好无损。

    用 `sqlite3.Connection.backup()`（Python 内置的 SQLite 在线备份 API），不是简单
    `shutil.copy` 复制文件——如果这个连接当时正好有未提交的事务/WAL 还没写回主文件，
    直接复制文件字节可能复制到一份不完整、打不开的数据库；官方备份 API 是事务一致的，
    不管当时数据库在不在用都能备份出一份能正常打开的完整文件。

    `min_interval_seconds` 节流：不是每次调用都真的复制一份（数据库文件可能有几十
    上百 MB，没必要每次开一个页面就复制一遍）——用备份目录里最新一份文件的时间戳
    判断"距上次备份过了多久"，不用额外的进程内变量记状态（Streamlit 每个 session
    甚至每次脚本重跑都是独立的执行环境，只有磁盘上的文件本身能跨 session、跨重启
    地记住"上次是什么时候备份的"）。`force=True` 跳过这个节流，给"立即备份"按钮用。
    """

    db_file = Path(db_path)
    if not db_file.exists():
        return None

    backup_root = Path(backup_dir) if backup_dir else db_file.parent / "backups"
    backup_root.mkdir(parents=True, exist_ok=True)

    existing = sorted(backup_root.glob(f"{db_file.stem}-*.db"))
    if not force and existing:
        last_backup_time = existing[-1].stat().st_mtime
        if time.time() - last_backup_time < min_interval_seconds:
            return None

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    backup_path = backup_root / f"{db_file.stem}-{timestamp}.db"

    backup_conn = sqlite3.connect(str(backup_path))
    try:
        conn.backup(backup_conn)
    finally:
        backup_conn.close()

    all_backups = sorted(backup_root.glob(f"{db_file.stem}-*.db"))
    for stale in all_backups[:-keep]:
        stale.unlink(missing_ok=True)

    return str(backup_path)


def _migrate_add_missing_columns(conn: sqlite3.Connection) -> None:
    """给已经存在的旧数据库补齐新加的列——CREATE TABLE IF NOT EXISTS 对已经建好的表
    不会补列，SQLite 的 ALTER TABLE ADD COLUMN 也没有"IF NOT EXISTS"，不查一下就直接
    加会在列已存在时报错，所以先查 PRAGMA table_info 再决定要不要加。

    注意：这种迁移加出来的列，在旧数据库里的物理顺序是排在最后（ALTER TABLE ADD COLUMN
    的固有行为），跟全新建库时 SCHEMA 字符串里写的顺序不一样——不影响任何按列名取值的代码
    （sqlite3.Row/dict 都是按名字取），只是 `PRAGMA table_info` 看到的顺序在新旧库上不同。
    """

    project_columns = {row["name"] for row in conn.execute("PRAGMA table_info(projects)")}
    if "origin" not in project_columns:
        with conn:
            conn.execute(
                "ALTER TABLE projects ADD COLUMN origin TEXT NOT NULL DEFAULT 'manual'"
            )
            # 一次性回填：老数据库里名字精确等于"未命名项目"的，基本可以确定就是这次
            # 改动之前 app.py 自动建的占位项目（旧代码把这个名字写死了）——回填成
            # origin='auto'，首页的自动/手动筛选对老数据也立刻生效，不用手动一个个标记。
            conn.execute("UPDATE projects SET origin = 'auto' WHERE name = '未命名项目'")


def _migrate_questions_allow_ranking_type(conn: sqlite3.Connection) -> None:
    """给已经存在的旧数据库把 `questions.q_type` 的 CHECK 约束从
    ('single','multi','open','numeric') 放宽到多一个 'ranking'（排序题）。

    这跟 `_migrate_add_missing_columns` 那种"补列"不一样——CHECK 约束是 CREATE TABLE
    语句本身的一部分，存在 `sqlite_master` 里，SQLite 没有"ALTER TABLE ... 改 CHECK
    约束"这种命令（`ALTER TABLE ADD COLUMN` 有，改约束没有），唯一的办法是整个表
    重建：改名占位 → 用新约束重新建一张同名表 → 把数据原样搬过去（连 id 一起，
    不能用自动生成的新 id，不然 responses/categories/ai_runs 这些外键就全对不上了）→
    删掉占位表。

    真的测过 SQLite 在这种"手动指定 id 搬数据"的场景下会不会把 AUTOINCREMENT 计数器
    搞乱——不会：只要搬过去的 INSERT 语句带着显式 id，SQLite 自己会把 AUTOINCREMENT
    的内部计数跟着更新到"目前见过的最大 id"，后面正常插入（不指定 id）的新记录
    还是会接着从最大 id 往后编号，不会跟老数据的 id 撞车。

    外键要先关掉再做这一套改名/重建——`responses.question_id REFERENCES questions(id)`
    这种外键在原表被改名的瞬间会找不到目标表，不关掉外键检查会直接报错。`PRAGMA
    foreign_keys` 这个开关在一个事务内部改是不生效的（SQLite 的已知行为，改之前
    专门写小脚本验证过），所以最后重新打开外键检查那一句必须放在 `with conn:` 这个
    事务块结束、自动提交了之后再单独执行一次，不能塞在块里面。

    真机测出来的一个坑：SQLite 默认的 `ALTER TABLE RENAME` 是"智能"模式——把
    `questions` 改名成占位表的那一刻，会顺手把 `responses`/`categories`/`ai_runs`
    这些表里 `REFERENCES questions(id)` 的外键定义也跟着悄悄改写成
    `REFERENCES questions_pre_ranking_migration(id)`，等占位表最后被删掉，这些外键
    就指向一个不存在的表——外键检查会报"no such table"，哪怕这几张表本身一行都没动过。
    这是本机真实验证出来的（不是猜的）：迁移完之后往 responses 插入一条脏数据触发
    外键校验，报的错正是"no such table: main.questions_pre_ranking_migration"。
    解法是迁移这几步期间把 `PRAGMA legacy_alter_table` 打开——关掉这种"智能改写"，
    让 RENAME 只改 `questions` 自己的名字，不去动其它表里的外键定义（反正新表很快
    就会用回 `questions` 这个名字，其它表的 `REFERENCES questions(id)` 本来就不需要
    跟着变）。
    """

    current_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'questions'"
    ).fetchone()
    if current_sql is None or "ranking" in current_sql[0]:
        # 全新数据库（还没建表，交给上面 SCHEMA 里 CREATE TABLE IF NOT EXISTS 用新
        # 约束建）或者已经迁移过一次的旧数据库，都不用再做一遍。
        return

    with conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("PRAGMA legacy_alter_table = ON")
        conn.execute("ALTER TABLE questions RENAME TO questions_pre_ranking_migration")
        conn.execute(
            """
            CREATE TABLE questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL REFERENCES documents(id),
                q_no TEXT NOT NULL,
                q_type TEXT NOT NULL CHECK (q_type IN ('single','multi','open','numeric','ranking')),
                source_text_en TEXT,
                order_index INTEGER NOT NULL,
                section TEXT NOT NULL DEFAULT 'official'
                    CHECK (section IN ('screen_out','official','background','platform_auto')),
                meta_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO questions (id, document_id, q_no, q_type, source_text_en, order_index, section, meta_json)
            SELECT id, document_id, q_no, q_type, source_text_en, order_index, section, meta_json
            FROM questions_pre_ranking_migration
            """
        )
        conn.execute("DROP TABLE questions_pre_ranking_migration")
        conn.execute("PRAGMA legacy_alter_table = OFF")
    conn.execute("PRAGMA foreign_keys = ON")


def create_project(
    conn: sqlite3.Connection,
    name: str,
    source_lang: str,
    target_lang: str,
    origin: str = "manual",
) -> int:
    with conn:
        cursor = conn.execute(
            "INSERT INTO projects (name, source_lang, target_lang, origin) VALUES (?, ?, ?, ?)",
            (name, source_lang, target_lang, origin),
        )
    return int(cursor.lastrowid)


def add_document(
    conn: sqlite3.Connection,
    project_id: int,
    filename: str,
    format: str,
    branch_label: str | None = None,
    research_type: str = "quant_survey",
    title: str | None = None,
) -> int:
    """Insert a document, defaulting its display title to its filename."""

    with conn:
        cursor = conn.execute(
            """
            INSERT INTO documents
                (project_id, filename, format, branch_label, research_type, title)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                filename,
                format,
                branch_label,
                research_type,
                filename if title is None else title,
            ),
        )
    return int(cursor.lastrowid)


def list_documents(
    conn: sqlite3.Connection,
    project_id: int,
    research_type: str | None = None,
) -> list[dict]:
    """List project documents from most to least recently updated."""

    sql = "SELECT * FROM documents WHERE project_id = ?"
    params: list[Any] = [project_id]
    if research_type is not None:
        sql += " AND research_type = ?"
        params.append(research_type)
    sql += " ORDER BY updated_at DESC, id DESC"
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


# 真实反馈"这里需要显示问卷的发布时间，并且默认按照时间排序，获取时间很简单，问卷
# 收录的回复中都有答题者的回复时间，按照最晚填问卷的时间记录"——上传时列名命中
# 这批关键词的列会被 app.py 的 `guess_is_platform_column()` 自动归类成"平台信息"
# （section='platform_auto'）落库，这里从这些已经存好的列里找出"作答提交/结束时间"
# 那一列，不是"开始时间"（同一份问卷常常两列都有，含义不一样，不能选错）。
_RESPONSE_TIME_STRONG_KEYWORDS = (
    "结束时间", "提交时间", "完成时间", "作答结束",
    "end date", "end time", "submitted", "submission", "completion time", "finished",
)
_RESPONSE_TIME_EXCLUDE_KEYWORDS = ("开始时间", "start date", "start time")


def get_document_response_time(conn: sqlite3.Connection, document_id: int) -> str | None:
    """这份问卷"发布时间"的推算值：受访者里最晚一次提交问卷的时间。

    上传时列名命中"结束/提交/完成时间"这批关键词的列会被自动归到"平台信息"
    （section='platform_auto'）落库，这里从这些列里挑出最像"提交/结束时间"的
    一列（排除"开始时间"，两者常常同时存在、含义完全不同），把这一列所有受访者
    的值解析成时间，取最大值——即"最晚填问卷的那个人的时间"，就是这份问卷该显示
    的发布时间。找不到任何能解析成时间的平台信息列（比如很老的历史数据、或者
    这份问卷的导出压根没带这类字段）就返回 None，调用方应该退回显示"更新于"这个
    数据库时间戳，不能假装有一个发布时间。
    """

    candidates = conn.execute(
        """
        SELECT id, source_text_en FROM questions
        WHERE document_id = ? AND section = 'platform_auto'
        ORDER BY order_index
        """,
        (document_id,),
    ).fetchall()
    if not candidates:
        return None

    def _score(name: str | None) -> int:
        name = name or ""
        lowered = name.lower()
        if any(kw in name or kw in lowered for kw in _RESPONSE_TIME_EXCLUDE_KEYWORDS):
            return -1
        if any(kw in name or kw in lowered for kw in _RESPONSE_TIME_STRONG_KEYWORDS):
            return 2
        return 0

    ordered = sorted(candidates, key=lambda row: -_score(row["source_text_en"]))

    for row in ordered:
        if _score(row["source_text_en"]) < 0:
            continue
        raw_values = [
            r[0] for r in conn.execute(
                "SELECT raw_value FROM responses WHERE question_id = ?", (row["id"],)
            ).fetchall()
        ]
        if not raw_values:
            continue
        # 这里经常会真的拿一批根本不是日期的值来试解析（IP、设备型号……都会走到
        # 这条兜底路径），pandas 对"整列格式不统一/推断不出来"这种情况会主动打一条
        # UserWarning——这是预期之内、已经用下面的"至少一半解析成功"兜底处理掉的
        # 正常情况，不是真的出了问题，压掉这条警告，不要让日志被刷屏。
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            parsed = pd.to_datetime(pd.Series(raw_values), errors="coerce")
        parsed = parsed.dropna()
        # 至少要有一半的值能被解析成时间，才认为这一列真的是时间列——一列大多数
        # 值都解析失败（比如其实是 IP／设备型号这类平台信息，凑巧列名沾了个"time"
        # 之类的词），不该被当成"发布时间"的来源。
        if len(parsed) == 0 or len(parsed) < len(raw_values) / 2:
            continue
        return parsed.max().strftime("%Y-%m-%d %H:%M:%S")

    return None


def touch_project(conn: sqlite3.Connection, project_id: int) -> None:
    """Update a project's activity timestamp to the current time."""

    with conn:
        conn.execute(
            "UPDATE projects SET updated_at = datetime('now') WHERE id = ?",
            (project_id,),
        )


def touch_document(conn: sqlite3.Connection, document_id: int) -> None:
    """Update a document's activity timestamp to the current time."""

    with conn:
        conn.execute(
            "UPDATE documents SET updated_at = datetime('now') WHERE id = ?",
            (document_id,),
        )


def add_questions(
    conn: sqlite3.Connection, document_id: int, questions: list["Question"]
) -> list[int]:
    ids: list[int] = []
    with conn:
        for question in questions:
            cursor = conn.execute(
                """
                INSERT INTO questions
                    (document_id, q_no, q_type, source_text_en, order_index, section,
                     meta_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    question.q_no,
                    question.q_type,
                    question.source_text_en,
                    question.order_index,
                    question.section,
                    json.dumps(question.meta, ensure_ascii=False),
                ),
            )
            ids.append(int(cursor.lastrowid))
    return ids


def set_test_method(
    conn: sqlite3.Connection,
    project_id: int,
    platform_source: str | None = None,
    is_branched: bool = False,
    branch_count: int | None = None,
    screen_out_rule: str | None = None,
    skip_logic_note: str | None = None,
) -> None:
    """Create or fully replace one project's test-method settings."""

    with conn:
        conn.execute(
            """
            INSERT INTO test_method (
                project_id,
                platform_source,
                is_branched,
                branch_count,
                screen_out_rule,
                skip_logic_note
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id) DO UPDATE SET
                platform_source = excluded.platform_source,
                is_branched = excluded.is_branched,
                branch_count = excluded.branch_count,
                screen_out_rule = excluded.screen_out_rule,
                skip_logic_note = excluded.skip_logic_note
            """,
            (
                project_id,
                platform_source,
                int(is_branched),
                branch_count,
                screen_out_rule,
                skip_logic_note,
            ),
        )


def get_test_method(conn: sqlite3.Connection, project_id: int) -> dict | None:
    """Return one project's test-method settings as a plain dictionary."""

    row = conn.execute(
        "SELECT * FROM test_method WHERE project_id = ?", (project_id,)
    ).fetchone()
    return None if row is None else dict(row)


def add_conclusion(
    conn: sqlite3.Connection, project_id: int, text: str, order_index: int
) -> int:
    """Insert one conclusion and return its row id."""

    with conn:
        cursor = conn.execute(
            """
            INSERT INTO conclusions (project_id, text, order_index)
            VALUES (?, ?, ?)
            """,
            (project_id, text, order_index),
        )
    return int(cursor.lastrowid)


def list_conclusions(conn: sqlite3.Connection, project_id: int) -> list[dict]:
    """List a project's conclusions in ascending display order."""

    rows = conn.execute(
        """
        SELECT id, text, order_index
        FROM conclusions
        WHERE project_id = ?
        ORDER BY order_index ASC
        """,
        (project_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def update_conclusion(conn: sqlite3.Connection, conclusion_id: int, text: str) -> None:
    """Update a conclusion's text without changing its display order."""

    with conn:
        conn.execute(
            "UPDATE conclusions SET text = ? WHERE id = ?", (text, conclusion_id)
        )


def delete_conclusion(conn: sqlite3.Connection, conclusion_id: int) -> None:
    """Delete one conclusion."""

    with conn:
        conn.execute("DELETE FROM conclusions WHERE id = ?", (conclusion_id,))


def _sql_value(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value.item() if hasattr(value, "item") else value


def add_responses(conn: sqlite3.Connection, question_id: int, df) -> None:
    required = {"respondent_id", "raw_value"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Missing required response columns: {sorted(missing)}")

    has_translation = "translation" in df.columns
    rows = [
        (
            question_id,
            _sql_value(row["respondent_id"]),
            _sql_value(row["raw_value"]),
            _sql_value(row["translation"]) if has_translation else None,
            order_index,
        )
        for order_index, (_, row) in enumerate(df.iterrows())
    ]
    with conn:
        conn.executemany(
            """
            INSERT INTO responses
                (question_id, respondent_id, raw_value, translation, order_index)
            VALUES (?, ?, ?, ?, ?)
            """,
            rows,
        )


def get_setting(conn: sqlite3.Connection, key: str, default=None) -> Any:
    """Return a stored setting, or ``default`` when the key is absent."""

    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return default if row is None else row[0]


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Create or replace one application setting."""

    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )


def delete_setting(conn: sqlite3.Connection, key: str) -> None:
    """Remove one application setting, if present.

    用于"清空一个覆盖设置、退回默认值"这种场景（比如翻译专用供应商设成"跟通用一致"）——
    跟 set_setting 存空字符串不是一回事：空字符串仍然是"有配置"，get_setting 不会走 default。
    """

    with conn:
        conn.execute("DELETE FROM settings WHERE key = ?", (key,))


def log_ai_run(
    conn: sqlite3.Connection,
    question_id: int,
    mode: str,
    prompt_version: str,
    raw_output: str,
) -> int:
    """Store one uninterpreted AI output for audit purposes."""

    with conn:
        cursor = conn.execute(
            """
            INSERT INTO ai_runs (question_id, mode, prompt_version, raw_output)
            VALUES (?, ?, ?, ?)
            """,
            (question_id, mode, prompt_version, raw_output),
        )
    return int(cursor.lastrowid)


# ---------------------------------------------------------------------------
# 自动保存草稿——跟"手动保存"（questions/responses/conclusions 那几张表）完全分开存，
# 结构上就不可能互相覆盖。每份问卷只占一行（document_id 是主键），新草稿直接顶掉旧草稿。
# ---------------------------------------------------------------------------


def write_autosave(conn: sqlite3.Connection, document_id: int, payload: dict) -> None:
    """整份替换掉一份问卷的自动保存草稿——不追加、不保留历史版本，只留最新一份。"""

    with conn:
        conn.execute(
            """
            INSERT INTO autosaves (document_id, payload_json, saved_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(document_id) DO UPDATE SET
                payload_json = excluded.payload_json,
                saved_at = excluded.saved_at
            """,
            (document_id, json.dumps(payload, ensure_ascii=False)),
        )


def read_autosave(conn: sqlite3.Connection, document_id: int) -> dict | None:
    """读回一份问卷的自动保存草稿；没有草稿返回 None。"""

    row = conn.execute(
        "SELECT payload_json, saved_at FROM autosaves WHERE document_id = ?",
        (document_id,),
    ).fetchone()
    if row is None:
        return None
    return {"payload": json.loads(row["payload_json"]), "saved_at": row["saved_at"]}


def delete_autosave(conn: sqlite3.Connection, document_id: int) -> None:
    """手动保存成功后清掉对应的草稿——草稿已经不比正式保存新，留着容易在下次打开时
    被误当成"有更新的草稿"提示用户恢复。"""

    with conn:
        conn.execute("DELETE FROM autosaves WHERE document_id = ?", (document_id,))


def write_document_extras(conn: sqlite3.Connection, document_id: int, payload: dict) -> None:
    """整份替换掉一份问卷"正式保存"里非结构化的那部分内容（AI 分类结果/图片/拖拽排版）。
    跟 write_autosave 是同一种"单槽覆盖"写法，但这张表是正式数据，不是草稿。"""

    with conn:
        conn.execute(
            """
            INSERT INTO document_extras (document_id, payload_json, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(document_id) DO UPDATE SET
                payload_json = excluded.payload_json,
                updated_at = excluded.updated_at
            """,
            (document_id, json.dumps(payload, ensure_ascii=False)),
        )


def read_document_extras(conn: sqlite3.Connection, document_id: int) -> dict | None:
    """读回一份问卷的 AI 分类结果/图片/拖拽排版；没存过返回 None。"""

    row = conn.execute(
        "SELECT payload_json FROM document_extras WHERE document_id = ?", (document_id,)
    ).fetchone()
    return None if row is None else json.loads(row["payload_json"])


def rename_document(conn: sqlite3.Connection, document_id: int, title: str) -> None:
    with conn:
        conn.execute(
            "UPDATE documents SET title = ?, updated_at = datetime('now') WHERE id = ?",
            (title, document_id),
        )


def delete_questions_for_document(conn: sqlite3.Connection, document_id: int) -> None:
    """清掉一份问卷名下所有 questions，连带 responses/categories/response_categories/
    ai_runs 这几层依赖一起清——这几张表建表时没加 ON DELETE CASCADE，PRAGMA
    foreign_keys=ON 之下留着孤儿行会直接报外键错误。不删 documents 这一行本身，
    manual-save 覆盖式重存要保留 document_id 不变（历史列表里的这一条不能变成新的一条）。
    """

    with conn:
        question_ids = [
            row["id"]
            for row in conn.execute(
                "SELECT id FROM questions WHERE document_id = ?", (document_id,)
            ).fetchall()
        ]
        if not question_ids:
            return
        placeholders = ",".join("?" * len(question_ids))
        response_ids = [
            row["id"]
            for row in conn.execute(
                f"SELECT id FROM responses WHERE question_id IN ({placeholders})",
                question_ids,
            ).fetchall()
        ]
        if response_ids:
            r_placeholders = ",".join("?" * len(response_ids))
            conn.execute(
                f"DELETE FROM response_categories WHERE response_id IN ({r_placeholders})",
                response_ids,
            )
        conn.execute(
            f"DELETE FROM categories WHERE question_id IN ({placeholders})",
            question_ids,
        )
        conn.execute(
            f"DELETE FROM ai_runs WHERE question_id IN ({placeholders})", question_ids
        )
        conn.execute(
            f"DELETE FROM responses WHERE question_id IN ({placeholders})",
            question_ids,
        )
        conn.execute(f"DELETE FROM questions WHERE id IN ({placeholders})", question_ids)


def delete_document(conn: sqlite3.Connection, document_id: int) -> None:
    """删除一份问卷分析（连带 questions 往下的所有依赖数据、自动保存草稿、AI 分类结果/
    图片/拖拽排版这些"正式"的附加内容）。"""

    delete_questions_for_document(conn, document_id)
    with conn:
        conn.execute("DELETE FROM autosaves WHERE document_id = ?", (document_id,))
        conn.execute("DELETE FROM document_extras WHERE document_id = ?", (document_id,))
        conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))


def rename_project(conn: sqlite3.Connection, project_id: int, name: str) -> None:
    """重命名一个项目——只要是人手动改的名字，就把 origin 一起标成 'manual'：一个自动
    占位项目一旦被人确认/改过名字，就不该再被"自动生成"筛选一直当成待清理的噪音。"""

    with conn:
        conn.execute(
            "UPDATE projects SET name = ?, origin = 'manual', updated_at = datetime('now') WHERE id = ?",
            (name, project_id),
        )


def delete_project(conn: sqlite3.Connection, project_id: int) -> None:
    """删除一个项目——连带它名下所有问卷分析（含各自的 questions/responses 等）、
    结论、测试方法、分享链接一起清掉，不留孤儿行。"""

    with conn:
        document_ids = [
            row["id"]
            for row in conn.execute(
                "SELECT id FROM documents WHERE project_id = ?", (project_id,)
            ).fetchall()
        ]
    for document_id in document_ids:
        delete_document(conn, document_id)
    with conn:
        conn.execute("DELETE FROM conclusions WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM test_method WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM share_links WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))


def replace_conclusions(
    conn: sqlite3.Connection, project_id: int, conclusions: list[str]
) -> None:
    """把一个项目的结论整份替换掉——manual save 需要"覆盖"语义，跟 add_conclusion
    那种"追加一条"不是一回事，重复调用 add_conclusion 会让结论越存越多、越存越重复。"""

    with conn:
        conn.execute("DELETE FROM conclusions WHERE project_id = ?", (project_id,))
        for order_index, text in enumerate(conclusions):
            if text:
                conn.execute(
                    "INSERT INTO conclusions (project_id, text, order_index) VALUES (?, ?, ?)",
                    (project_id, text, order_index),
                )
