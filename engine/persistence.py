"""Save and reload complete survey analyses from SQLite."""

from __future__ import annotations

import json
import sqlite3

import pandas as pd

from .clean import _is_truthy, option_labels_for_group
from .db import (
    add_document,
    add_questions,
    add_responses,
    delete_autosave,
    delete_questions_for_document,
    get_test_method,
    list_conclusions,
    read_document_extras,
    rename_document,
    replace_conclusions,
    set_test_method,
    touch_document,
    touch_project,
    write_document_extras,
)
from .ingest import Question


MULTI_VALUE_SEPARATOR = "␟"

SECTION_TO_DB = {
    "筛选": "screen_out",
    "正式": "official",
    "基础信息": "background",
    "平台信息": "platform_auto",
}
DB_TO_SECTION = {value: key for key, value in SECTION_TO_DB.items()}


def _translated_options(unit: dict, df_all, translation_cache: dict) -> dict:
    if unit["kind"] not in {"single", "multi", "ranking"}:
        return {}

    translated: dict = {}
    if unit["kind"] in {"multi", "ranking"}:
        option_labels = option_labels_for_group(unit["columns"])
        for label in dict.fromkeys(option_labels.values()):
            translation = translation_cache.get(label)
            if translation is not None:
                translated[label] = translation
        return translated

    for value in df_all[unit["columns"][0]].dropna().unique().tolist():
        try:
            translation = translation_cache.get(value)
        except TypeError:
            continue
        if translation is not None:
            translated[value] = translation
    return translated


def _write_questions_and_responses(
    conn: sqlite3.Connection,
    document_id: int,
    units: list[dict],
    df_all,
    screen_fail_values: dict,
    translation_cache: dict,
    original_columns: dict | None = None,
) -> None:
    """写一份问卷的全部 questions/responses——save_analysis（新建）和 update_analysis
    （手动保存覆盖已有的一份）共用同一套写入逻辑，唯一的区别是调用前要不要先清空旧数据。
    """

    respondent_ids = [str(index) for index in range(len(df_all))]
    for order_index, unit in enumerate(units):
        kind = unit["kind"]
        columns = unit["columns"]
        # Keep original column names for mapping memory; load_analysis retains its
        # existing single-column/display-number behavior.
        meta: dict = {"columns": columns}
        if kind not in {"multi", "ranking"} and columns == [unit["display_no"]] and original_columns:
            # Historical loading exposes display numbers as data columns. Keep
            # the previously saved source names when that analysis is resaved.
            meta["columns"] = original_columns.get(unit["display_no"], columns)
        if kind not in {"multi", "ranking"} and screen_fail_values.get(columns[0]):
            meta["fail_values"] = screen_fail_values[columns[0]]

        if unit["title"] in translation_cache:
            meta["title_zh"] = translation_cache[unit["title"]]
        options_zh = _translated_options(unit, df_all, translation_cache)
        if options_zh:
            meta["options_zh"] = options_zh

        question = Question(
            q_no=unit["display_no"],
            q_type=kind,
            source_text_en=unit["title"],
            order_index=order_index,
            section=SECTION_TO_DB[unit["section"]],
            meta=meta,
        )
        [question_id] = add_questions(conn, document_id, [question])

        if kind == "multi":
            # 存的是"每个原始拆分列的真假值"这份最原始的信息（一个 JSON 对象，key 是
            # 原始列名），不是合并好的"选中项列表"——只存合并结果的话，"打开历史分析"
            # 之后原始拆分列已经不在了，没法重新调整分组键（真实反馈过的问题：调整
            # 分组键改了没有实际效果）。存最原始的形状，加载回来才能重建出跟当初上传
            # 时一模一样的 N 个布尔列，"调整分组键"才有真正能重新分组的原始材料。
            raw_series = df_all[columns].apply(
                lambda row: json.dumps(
                    {col: _is_truthy(row[col]) for col in columns}, ensure_ascii=False
                ),
                axis=1,
            )
        elif kind == "ranking":
            # Preserve every option's rank and missing values for later regrouping.
            raw_series = df_all[columns].apply(
                lambda row: json.dumps(
                    {col: None if pd.isna(row[col]) else str(row[col]) for col in columns},
                    ensure_ascii=False,
                ),
                axis=1,
            )
        else:
            raw_series = df_all[columns[0]]
        response_df = pd.DataFrame(
            {
                "respondent_id": respondent_ids,
                "raw_value": raw_series.reset_index(drop=True),
            }
        )
        add_responses(conn, question_id, response_df)


def save_analysis(
    conn: sqlite3.Connection,
    project_id: int,
    units: list[dict],
    df_all,
    screen_fail_values: dict,
    translation_cache: dict,
    test_method: dict,
    conclusions: list[str],
    filename: str,
    research_type: str = "quant_survey",
    title: str | None = None,
    extras: dict | None = None,
) -> int:
    """Persist one complete analysis as a brand-new document and return its id.

    extras：AI 分类结果/图片/拖拽排版这些形状不适合拆表的内容，整份存进
    document_extras（跟 questions/responses 是同一次"正式保存"，只是落在不同的表）。
    不传或传 None 就写一个空 dict，不影响 questions/responses 这条主流程。
    """

    document_id = add_document(
        conn,
        project_id,
        filename,
        format="csv",
        research_type=research_type,
        title=title or filename,
    )
    _write_questions_and_responses(
        conn, document_id, units, df_all, screen_fail_values, translation_cache
    )
    # 真实反馈的严重 bug："手动保存"点了直接报错 set_test_method() got multiple
    # values for argument 'project_id'。根源：test_method 这个字典如果是从
    # load_analysis() 读回来的（get_test_method() 内部是 `SELECT * ... dict(row)`，
    # 会把 project_id 这个外键列也一起带进字典里），这里 **test_method 展开的时候
    # 会跟前面已经按位置传的 project_id 撞上，Python 判定成"同一个参数传了两次"
    # 直接抛异常。project_id 这个字段本来就跟"哪个项目"是同一件事，不是真正的
    # "测试方法"设置，调用方在这里已经显式传了一次，展开前先把它从字典里摘掉。
    set_test_method(conn, project_id, **{k: v for k, v in test_method.items() if k != "project_id"})
    replace_conclusions(conn, project_id, conclusions)
    write_document_extras(conn, document_id, extras or {})
    touch_project(conn, project_id)
    return document_id


def update_analysis(
    conn: sqlite3.Connection,
    document_id: int,
    project_id: int,
    units: list[dict],
    df_all,
    screen_fail_values: dict,
    translation_cache: dict,
    test_method: dict,
    conclusions: list[str],
    title: str | None = None,
    extras: dict | None = None,
) -> None:
    """手动保存：原地整份覆盖一份已经存在的问卷分析，不新建 document 行，结论也是整份
    替换（不会越存越多）。这是"正式"保存——跟自动保存草稿（engine.db 的 autosaves 表）
    完全是两套数据，写完之后顺手把这份问卷的自动保存草稿清掉（草稿已经不比这次新了）。

    extras：不传就整份清空（写一个空 dict）——手动保存本来就是"当前状态整份覆盖"的
    语义，如果调用方这次没有 AI 分类结果/图片/拖拽排版了（比如全删掉了），也应该覆盖
    掉旧的，而不是留着上一次保存的内容不清。
    """

    original_columns = {
        row["q_no"]: json.loads(row["meta_json"]).get("columns", [row["source_text_en"] or row["q_no"]])
        for row in conn.execute(
            "SELECT q_no, source_text_en, meta_json FROM questions WHERE document_id = ? AND q_type != 'multi'",
            (document_id,),
        )
    }
    delete_questions_for_document(conn, document_id)
    _write_questions_and_responses(
        conn, document_id, units, df_all, screen_fail_values, translation_cache, original_columns
    )
    if title is not None:
        rename_document(conn, document_id, title)
    # 同一个坑，见 save_analysis() 里的说明：test_method 如果是从 load_analysis()
    # 读回来的，字典里会带着 project_id 这个外键列，跟下面已经按位置传的 project_id
    # 撞上会直接抛 TypeError——"手动保存"真机测试复现过这个 bug（点保存直接弹出
    # "手动保存失败：set_test_method() got multiple values for argument
    # 'project_id'"，对已经从历史记录打开过的文档，点"保存"必现）。
    set_test_method(conn, project_id, **{k: v for k, v in test_method.items() if k != "project_id"})
    replace_conclusions(conn, project_id, conclusions)
    write_document_extras(conn, document_id, extras or {})
    touch_document(conn, document_id)
    touch_project(conn, project_id)
    delete_autosave(conn, document_id)


def save_ai_results(conn: sqlite3.Connection, document_id: int, ai_results: dict) -> None:
    """只把 AI 分类结果写进这份文档已有的"正式"extras，图片/排版这些其它内容原样保留。

    真实反馈"AI 开放题分析结果下次打开就没了"——原来 AI 结果只会跟着"手动保存"或者 20 秒
    一次的自动保存草稿走，而重新打开一份分析读的是正式数据、不读草稿，所以两次保存之间
    跑的 AI 分类，关掉页面就丢了。这里让 AI 分类一跑完就单独落库，不等手动保存。
    ai_results 的形状同 extras["ai_results"]：{题号: {筛选条件("" 代表没筛选): 结果}}，
    是"当前全部结果"的整份覆盖（重新生成/清除之后不再有的那份，也会跟着从库里消失）。
    """

    extras = read_document_extras(conn, document_id) or {}
    extras["ai_results"] = ai_results
    write_document_extras(conn, document_id, extras)
    touch_document(conn, document_id)


def save_images(conn: sqlite3.Connection, document_id: int, q_no: str, images_payload: list[dict]) -> None:
    """只把一道题的图片写进这份文档已有的"正式"extras，其它题目/AI 结果/排版原样保留。

    真实反馈"插入图片后下次打开还要重新上传"——原来图片只会跟着"手动保存"或者 20 秒
    一次的自动保存草稿走，而重新打开一份分析读的是正式数据、不读草稿，所以两次保存之间
    插入的图片，关掉页面就丢了。这里让图片一改完就单独落库，不等手动保存。
    images_payload 的形状同 extras["images"][q_no]：图片字典的列表（字节用 bytes_b64），
    只覆盖当前题目；空列表表示已经清空，从 extras["images"] 里删除这道题。
    """

    extras = read_document_extras(conn, document_id) or {}
    images = extras.setdefault("images", {})
    if images_payload:
        images[q_no] = images_payload
    else:
        images.pop(q_no, None)
    write_document_extras(conn, document_id, extras)
    touch_document(conn, document_id)


def save_crosstab_blocks(
    conn: sqlite3.Connection, document_id: int, blocks_payload: list[dict], *, state_payload: dict | None = None,
) -> None:
    """整份覆盖当前交叉分析板块，保留图片和 AI 结果；删除的板块也从正式库里消失。

    分组在 session_state 的独立 key 中，另存 crosstab_state 恢复配置和只增不减的编号。
    """

    extras = read_document_extras(conn, document_id) or {}
    extras["crosstab_blocks"] = blocks_payload
    if state_payload is not None:
        extras["crosstab_state"] = state_payload
    write_document_extras(conn, document_id, extras)
    touch_document(conn, document_id)


def _load_question_values(conn: sqlite3.Connection, question: sqlite3.Row) -> list:
    """单选/数值/开放题用——一道题只对应一列。多选题走 `_load_multi_question`，
    不用这个函数（多选题要重建出好几列，不是一列）。"""

    rows = conn.execute(
        """
        SELECT raw_value
        FROM responses
        WHERE question_id = ?
        ORDER BY order_index ASC
        """,
        (question["id"],),
    ).fetchall()
    values = [row["raw_value"] for row in rows]
    if question["q_type"] == "numeric":
        try:
            return pd.to_numeric(pd.Series(values), errors="raise").tolist()
        except (TypeError, ValueError):
            return values
    return values


def _parse_multi_raw_value(raw_value: str | None, columns: list[str]) -> dict[str, bool] | None:
    """新格式：`raw_value` 是一个 JSON 对象（{原始列名: true/false}）。返回 None
    表示这条解析不出新格式（八成是旧数据），交给调用方走旧格式兼容逻辑。"""

    if raw_value in (None, ""):
        return {col: False for col in columns}
    try:
        parsed = json.loads(raw_value)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _load_multi_question(
    conn: sqlite3.Connection, question: sqlite3.Row, meta: dict
) -> tuple[dict[str, pd.Series], list[str]]:
    """加载一道多选题，返回 ({原始列名: 这一列的 Series}, unit 要用的 columns 列表）。

    优先按新格式读（每个原始拆分列的真假值分开存的那种，见 `_write_questions_and_
    responses`）——能重建出跟当初上传时一模一样的 N 个布尔列，"调整分组键"才有原始
    材料可以重新分组（真实反馈过：调整分组键改了没有实际效果，根源就是原来只存了
    合并结果，原始列早就不在了）。

    读到的是这次改动之前存的旧数据（`raw_value` 是"选中项标签用 ␟ 拼起来的字符串"，
    不是 JSON）就退回旧的处理方式——只有一个合并列，没法重新分组，但至少能正常
    打开、不会因为存储格式换了就读不出来、甚至报错。
    """

    rows = conn.execute(
        "SELECT raw_value FROM responses WHERE question_id = ? ORDER BY order_index ASC",
        (question["id"],),
    ).fetchall()
    raw_values = [row["raw_value"] for row in rows]

    original_columns = meta.get("columns") or [question["q_no"]]
    parsed_rows: list[dict] = []
    is_new_format = True
    for raw_value in raw_values:
        parsed = _parse_multi_raw_value(raw_value, original_columns)
        if parsed is None:
            is_new_format = False
            break
        parsed_rows.append(parsed)

    if is_new_format and meta.get("columns"):
        columns_out = {
            col: pd.Series([bool(row.get(col, False)) for row in parsed_rows])
            for col in original_columns
        }
        return columns_out, original_columns

    # 旧格式兼容路径。
    merged = [
        [] if value in (None, "") else value.split(MULTI_VALUE_SEPARATOR)
        for value in raw_values
    ]
    return {question["q_no"]: pd.Series(merged)}, [question["q_no"]]


def load_analysis(conn: sqlite3.Connection, document_id: int) -> dict:
    """Reload a complete analysis in the engine's pandas-oriented shape."""

    document = conn.execute(
        """
        SELECT project_id, research_type, title
        FROM documents
        WHERE id = ?
        """,
        (document_id,),
    ).fetchone()
    if document is None:
        raise ValueError(f"Document not found: {document_id}")

    questions = conn.execute(
        """
        SELECT id, q_no, q_type, source_text_en, order_index, section, meta_json
        FROM questions
        WHERE document_id = ?
        ORDER BY order_index ASC
        """,
        (document_id,),
    ).fetchall()

    columns: dict[str, pd.Series] = {}
    units: list[dict] = []
    screen_fail_values: dict = {}
    translation_cache: dict = {}
    for question in questions:
        q_no = question["q_no"]
        meta = json.loads(question["meta_json"])

        if question["q_type"] == "multi":
            multi_columns, unit_columns = _load_multi_question(conn, question, meta)
            columns.update(multi_columns)
        elif question["q_type"] == "ranking":
            unit_columns = meta["columns"]
            rows = conn.execute(
                "SELECT raw_value FROM responses WHERE question_id = ? ORDER BY order_index ASC",
                (question["id"],),
            ).fetchall()
            ranks = [json.loads(row["raw_value"]) for row in rows]
            columns.update({
                col: pd.Series([row.get(col) for row in ranks])
                for col in unit_columns
            })
        else:
            columns[q_no] = pd.Series(_load_question_values(conn, question))
            unit_columns = [q_no]

        units.append(
            {
                "kind": question["q_type"],
                "section": DB_TO_SECTION[question["section"]],
                "title": question["source_text_en"],
                "display_no": q_no,
                "columns": unit_columns,
            }
        )

        if "fail_values" in meta:
            screen_fail_values[q_no] = meta["fail_values"]
        if "title_zh" in meta:
            translation_cache[question["source_text_en"]] = meta["title_zh"]
        translation_cache.update(meta.get("options_zh", {}))

    project_id = document["project_id"]
    return {
        "df_all": pd.DataFrame(columns),
        "units": units,
        "screen_fail_values": screen_fail_values,
        "translation_cache": translation_cache,
        "test_method": get_test_method(conn, project_id),
        "conclusions": [
            conclusion["text"] for conclusion in list_conclusions(conn, project_id)
        ],
        "research_type": document["research_type"],
        "title": document["title"],
        "extras": read_document_extras(conn, document_id) or {},
        "project_id": project_id,
    }
