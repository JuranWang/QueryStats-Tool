import pandas as pd
import pytest

from engine.ingest import Question, detect_encoding, load_csv, load_file, load_xlsx


def test_question_defaults():
    question = Question("Q1", "single", "Choose one", 0)
    assert question.section == "official"
    assert question.meta == {}

    other_question = Question("Q2", "open", "Why?", 1)
    question.meta["title_zh"] = "选择一个"
    assert other_question.meta == {}


def test_detect_encoding_and_load_csv_preserve_data(tmp_path):
    path = tmp_path / "responses.csv"
    path.write_text("编号,答案\n1,是\n2,否\n", encoding="utf-8-sig")

    assert isinstance(detect_encoding(str(path)), str)
    result = load_csv(str(path))

    assert result.columns.tolist() == ["编号", "答案"]
    assert result.to_dict("records") == [
        {"编号": 1, "答案": "是"},
        {"编号": 2, "答案": "否"},
    ]


def test_load_xlsx_and_file_dispatch(tmp_path):
    path = tmp_path / "responses.xlsx"
    expected = pd.DataFrame({"respondent_id": ["r1", "r2"], "score": [3, 5]})
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        expected.to_excel(writer, sheet_name="data", index=False)

    pd.testing.assert_frame_equal(load_xlsx(str(path), "data"), expected)
    pd.testing.assert_frame_equal(load_file(str(path)), expected)


def test_load_file_rejects_unsupported_suffix(tmp_path):
    path = tmp_path / "responses.txt"
    path.write_text("not a supported survey export", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported file format"):
        load_file(str(path))
