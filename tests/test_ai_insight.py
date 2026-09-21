from engine import ai_insight, db
from engine.ingest import Question
from tests.fakes import FakeProvider


def _stats_bundle():
    return {
        "Q1": [
            {"option": "A", "n": 86, "pct": 48.0, "count_pct_label": "86人（48.0%）"},
            {"option": "B", "n": 93, "pct": 52.0, "count_pct_label": "93人（52.0%）"},
        ]
    }


def test_generate_insights_keeps_insight_whose_numbers_are_all_verifiable():
    provider = FakeProvider(
        [{"insights": ["选择 A 的有 86 人（48.0%）。"]}]
    )

    result = ai_insight.generate_insights(provider, _stats_bundle())

    assert result == [{"text": "选择 A 的有 86 人（48.0%）。"}]


def test_generate_insights_drops_insight_with_fabricated_number():
    # 93 是真实的，123 是模型编的——整条丢弃，不是只删掉编造的那个数字。
    provider = FakeProvider(
        [{"insights": ["选择 B 的有 93 人，占比 123%（编的）。"]}]
    )

    result = ai_insight.generate_insights(provider, _stats_bundle())

    assert result == []


def test_generate_insights_does_not_treat_substring_numbers_as_verifiable():
    # 数据里有 86 和 48.0，但 "8" 和 "6" 单独都不是真实出现过的数字，不能靠子串匹配蒙混过关。
    provider = FakeProvider([{"insights": ["有 8 人和 6 人。"]}])

    result = ai_insight.generate_insights(provider, _stats_bundle())

    assert result == []


def test_generate_insights_keeps_valid_and_drops_invalid_independently():
    provider = FakeProvider(
        [
            {
                "insights": [
                    "A 有 86 人（48.0%）。",
                    "B 有 999 人（编的）。",
                ]
            }
        ]
    )

    result = ai_insight.generate_insights(provider, _stats_bundle())

    assert result == [{"text": "A 有 86 人（48.0%）。"}]


def test_generate_insights_handles_non_list_and_non_string_items_gracefully():
    provider = FakeProvider([{"insights": "不是列表"}])
    assert ai_insight.generate_insights(provider, _stats_bundle()) == []

    provider2 = FakeProvider([{"insights": [123, None, ""]}])
    assert ai_insight.generate_insights(provider2, _stats_bundle()) == []


def test_generate_insights_logs_ai_run_when_connection_and_question_id_given(tmp_path):
    conn = db.init_db(str(tmp_path / "survey.sqlite"))
    project_id = db.create_project(conn, "测试项目", "en", "zh-CN")
    document_id = db.add_document(conn, project_id, "data.csv", "csv")
    [question_id] = db.add_questions(conn, document_id, [Question("Q1", "single", "Choose one", 0)])

    provider = FakeProvider([{"insights": ["A 有 86 人（48.0%）。"]}])
    ai_insight.generate_insights(provider, _stats_bundle(), conn=conn, question_id=question_id)

    row = conn.execute("SELECT mode, prompt_version FROM ai_runs WHERE question_id = ?", (question_id,)).fetchone()
    assert row["mode"] == "insight"
    assert row["prompt_version"] == "v1"
    conn.close()
