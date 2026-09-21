import json

import pytest

from engine import db
from engine.ai_classify import classify_closed, classify_custom, classify_open
from engine.ingest import Question
from tests.fakes import FakeProvider


RESPONSES = [
    {"response_id": 1, "text": "容易清洁"},
    {"response_id": 2, "text": "价格偏高"},
]
CATEGORIES = ["清洁", "价格"]


def _question_id(conn) -> int:
    project_id = db.create_project(conn, "测试项目", "en", "zh-CN")
    document_id = db.add_document(conn, project_id, "responses.csv", "csv")
    return db.add_questions(
        conn, document_id, [Question("Q1", "open", "Why?", 0)]
    )[0]


def test_classify_closed_assigns_every_response_to_given_categories():
    provider = FakeProvider(
        [
            {
                "assignments": [
                    {"response_id": 1, "category": "清洁"},
                    {"response_id": 2, "category": "价格"},
                ]
            }
        ]
    )

    result = classify_closed(provider, RESPONSES, CATEGORIES)

    assert result == [
        {"response_id": 1, "category": "清洁"},
        {"response_id": 2, "category": "价格"},
    ]
    assert "只能从给定类目里选择" in provider.calls[0][1]
    assert json.dumps(CATEGORIES, ensure_ascii=False) in provider.calls[0][1]


def test_classify_closed_replaces_invented_category_with_unclassified():
    provider = FakeProvider(
        [
            {
                "assignments": [
                    {"response_id": 1, "category": "外观"},
                    {"response_id": 2, "category": "价格"},
                ]
            }
        ]
    )

    result = classify_closed(provider, RESPONSES, CATEGORIES)

    assert result[0] == {"response_id": 1, "category": "__unclassified__"}


def test_classify_closed_fills_missing_response_id_with_unclassified():
    provider = FakeProvider(
        [{"assignments": [{"response_id": 1, "category": "清洁"}]}]
    )

    result = classify_closed(provider, RESPONSES, CATEGORIES)

    assert result == [
        {"response_id": 1, "category": "清洁"},
        {"response_id": 2, "category": "__unclassified__"},
    ]


def test_classify_closed_discards_unknown_response_id():
    provider = FakeProvider(
        [
            {
                "assignments": [
                    {"response_id": 1, "category": "清洁"},
                    {"response_id": 2, "category": "价格"},
                    {"response_id": 999, "category": "清洁"},
                ]
            }
        ]
    )

    result = classify_closed(provider, RESPONSES, CATEGORIES)

    assert [item["response_id"] for item in result] == [1, 2]


def test_classify_open_extracts_then_assigns_all_responses():
    provider = FakeProvider(
        [
            {"categories": ["清洁", "价格"]},
            {
                "assignments": [
                    {"response_id": 1, "category": "清洁"},
                    {"response_id": 2, "category": "价格"},
                ]
            },
        ]
    )

    result = classify_open(provider, RESPONSES, sample_size=1)

    assert result == {
        "categories": ["清洁", "价格"],
        "assignments": [
            {"response_id": 1, "category": "清洁"},
            {"response_id": 2, "category": "价格"},
        ],
    }
    assert len(provider.calls) == 2
    assert '"response_id": 2' not in provider.calls[0][1]
    assert '"response_id": 2' in provider.calls[1][1]
    assert json.dumps(["清洁", "价格"], ensure_ascii=False) in provider.calls[1][1]


def test_classification_with_connection_logs_each_ai_run(tmp_path):
    conn = db.init_db(str(tmp_path / "survey.sqlite"))
    question_id = _question_id(conn)
    provider = FakeProvider(
        [
            {"categories": ["清洁", "价格"]},
            {
                "assignments": [
                    {"response_id": 1, "category": "清洁"},
                    {"response_id": 2, "category": "价格"},
                ]
            },
        ]
    )

    classify_open(provider, RESPONSES, conn=conn, question_id=question_id)

    rows = conn.execute(
        "SELECT mode, prompt_version, raw_output FROM ai_runs ORDER BY id"
    ).fetchall()
    assert [(row["mode"], row["prompt_version"]) for row in rows] == [
        ("classify_open_extract", "v1"),
        ("classify_open_assign", "v1"),
    ]
    assert json.loads(rows[0]["raw_output"]) == {"categories": ["清洁", "价格"]}
    conn.close()


def test_classify_custom_embeds_instruction_and_reuses_extract_then_assign_flow():
    provider = FakeProvider(
        [
            {"categories": ["提到价格", "没提到价格"]},
            {
                "assignments": [
                    {"response_id": 1, "category": "没提到价格"},
                    {"response_id": 2, "category": "提到价格"},
                ]
            },
        ]
    )

    result = classify_custom(
        provider, RESPONSES, "判断每条回答有没有提到价格", sample_size=1
    )

    assert result == {
        "categories": ["提到价格", "没提到价格"],
        "assignments": [
            {"response_id": 1, "category": "没提到价格"},
            {"response_id": 2, "category": "提到价格"},
        ],
    }
    assert len(provider.calls) == 2
    assert "判断每条回答有没有提到价格" in provider.calls[0][1]
    # 分配那一步复用 _classify_closed，结果只会是提炼出来的类目之一——保证不管
    # instruction 多自由，最终形状始终是"每条回答对应一个类目"，能直接喂给
    # stats.single_choice_stats 画柱状图/饼图，不会退化成自由文本。
    assert json.dumps(["提到价格", "没提到价格"], ensure_ascii=False) in provider.calls[1][1]


def test_classify_custom_rejects_empty_instruction():
    provider = FakeProvider([])

    with pytest.raises(ValueError):
        classify_custom(provider, RESPONSES, "   ")

    assert provider.calls == []


def test_classify_custom_logs_extract_and_assign_with_distinct_modes():
    conn = db.init_db(":memory:")
    question_id = _question_id(conn)
    provider = FakeProvider(
        [
            {"categories": ["提到价格"]},
            {"assignments": [{"response_id": 1, "category": "提到价格"}, {"response_id": 2, "category": "提到价格"}]},
        ]
    )

    classify_custom(
        provider, RESPONSES, "判断有没有提到价格", conn=conn, question_id=question_id
    )

    rows = conn.execute(
        "SELECT mode, prompt_version FROM ai_runs ORDER BY id"
    ).fetchall()
    assert [(row["mode"], row["prompt_version"]) for row in rows] == [
        ("classify_custom_extract", "v1"),
        ("classify_custom_assign", "v1"),
    ]
    conn.close()
