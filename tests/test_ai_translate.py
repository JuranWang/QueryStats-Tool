import json

from engine import db
from engine.ai_translate import translate_verbatims
from engine.ingest import Question
from tests.fakes import FakeProvider


def _translate(text_en: str, translation: str, protected_terms=None):
    provider = FakeProvider(
        [
            {
                "translations": [
                    {"response_id": 1, "translation": translation},
                ]
            }
        ]
    )
    result = translate_verbatims(
        provider,
        [{"response_id": 1, "text_en": text_en}],
        protected_terms or [],
    )
    return result[0], provider


def _question_id(conn) -> int:
    project_id = db.create_project(conn, "测试项目", "en", "zh-CN")
    document_id = db.add_document(conn, project_id, "responses.csv", "csv")
    return db.add_questions(
        conn, document_id, [Question("Q1", "open", "Why?", 0)]
    )[0]


def test_translate_verbatims_accepts_translation_preserving_number_and_term():
    result, provider = _translate(
        "I bought 2 Ruggable rugs.", "我买了 2 张 Ruggable 地毯。", ["Ruggable"]
    )

    assert result == {
        "response_id": 1,
        "translation": "我买了 2 张 Ruggable 地毯。",
        "valid": True,
        "issues": [],
    }
    prompt = provider.calls[0][1]
    assert "逐句直译，不概括、不总结主题" in prompt
    assert "Ruggable" in prompt


def test_translate_verbatims_flags_missing_number():
    result, _ = _translate("I bought 2 rugs.", "我买了地毯。")

    assert result["valid"] is False
    assert "missing_number:2" in result["issues"]


def test_translate_verbatims_flags_missing_protected_term():
    result, _ = _translate(
        "Ruggable is easy to clean.", "这种地毯容易清洁。", ["Ruggable"]
    )

    assert "missing_term:Ruggable" in result["issues"]


def test_translate_verbatims_flags_empty_translation():
    result, _ = _translate("It is soft.", "")

    assert "empty_translation" in result["issues"]


def test_translate_verbatims_flags_unchanged_translatable_text():
    result, _ = _translate("This rug is soft.", "This rug is soft.")

    assert "untranslated" in result["issues"]


def test_translate_verbatims_keeps_invalid_model_output_unchanged():
    result, _ = _translate("It costs 200 dollars.", "价格不详。")

    assert result["valid"] is False
    assert result["translation"] == "价格不详。"
    assert result["issues"] == ["missing_number:200"]


def test_translate_verbatims_logs_raw_output(tmp_path):
    conn = db.init_db(str(tmp_path / "survey.sqlite"))
    question_id = _question_id(conn)
    raw_output = {
        "translations": [{"response_id": 1, "translation": "这很柔软。"}]
    }
    provider = FakeProvider([raw_output])

    translate_verbatims(
        provider,
        [{"response_id": 1, "text_en": "It is soft."}],
        [],
        conn=conn,
        question_id=question_id,
    )

    row = conn.execute(
        "SELECT mode, prompt_version, raw_output FROM ai_runs"
    ).fetchone()
    assert (row["mode"], row["prompt_version"]) == ("translate", "v1")
    assert json.loads(row["raw_output"]) == raw_output
    conn.close()
