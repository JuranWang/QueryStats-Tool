from __future__ import annotations

import pandas as pd
import pytest
from docx import Document

from PIL import Image

from engine.export_word import _render_chart_image, export_analysis_to_docx


DEFAULT_METHOD = {
    "platform_source": "问卷平台",
    "is_branched": False,
    "branch_count": None,
    "screen_out_rule": "不符合条件者剔除",
    "skip_logic_note": "无跳转",
}


def _export(tmp_path, **overrides):
    output = tmp_path / "report.docx"
    arguments = {
        "output_path": str(output),
        "project_name": "测试项目",
        "conclusions": [],
        "test_method": DEFAULT_METHOD,
        "units": [],
        "stats_by_unit": {},
        "n_by_unit": {},
        "ai_insights": None,
        "crosstabs": None,
    }
    arguments.update(overrides)
    export_analysis_to_docx(**arguments)
    return Document(output)


def _single_unit(display_no="Q1", section="正式", title="最喜欢的选项"):
    return {
        "kind": "single",
        "section": section,
        "title": title,
        "display_no": display_no,
    }


def _single_stats():
    return [
        {"option": "选项A", "n": 6, "pct": 60.0, "count_pct_label": "6人（60.0%）"},
        {"option": "选项B", "n": 4, "pct": 40.0, "count_pct_label": "4人（40.0%）"},
    ]


def _paragraph_texts(document):
    return [paragraph.text for paragraph in document.paragraphs]


def _table_with_header(document, expected_header):
    for table in document.tables:
        header = [cell.text for cell in table.rows[0].cells]
        if header == expected_header:
            return table
    raise AssertionError(f"Table header not found: {expected_header}")


def test_basic_structure_includes_title_conclusion_and_chart(tmp_path):
    document = _export(
        tmp_path,
        project_name="猫粮概念测试",
        conclusions=["选项A获得6人（60.0%）选择。"],
        units=[_single_unit()],
        stats_by_unit={"Q1": _single_stats()},
        n_by_unit={"Q1": 10},
    )
    texts = _paragraph_texts(document)
    assert "猫粮概念测试" in texts[0]
    assert any("核心结论" in text for text in texts)
    assert any("选项A获得6人（60.0%）选择。" in text for text in texts)
    assert len(document.inline_shapes) >= 1


def test_empty_conclusions_omit_section_heading(tmp_path):
    document = _export(tmp_path, conclusions=[])
    assert "核心结论" not in _paragraph_texts(document)


def test_screening_unit_is_not_exported(tmp_path):
    screening = _single_unit("S1", "筛选", "筛选题标题")
    official = _single_unit("Q1", "正式", "正式题标题")
    document = _export(
        tmp_path,
        units=[screening, official],
        stats_by_unit={"S1": _single_stats(), "Q1": _single_stats()},
        n_by_unit={"S1": 10, "Q1": 10},
    )
    all_text = "\n".join(_paragraph_texts(document))
    assert "正式题标题" in all_text
    assert "筛选题标题" not in all_text


@pytest.mark.parametrize(
    ("rows", "expected_header"),
    [
        (
            [{"raw": "Because A", "translation": "因为A", "corresponding_choice": "A"}],
            ["对应选择", "原文", "中文翻译"],
        ),
        (
            [{"raw": "Because A", "translation": "因为A", "corresponding_choice": None}],
            ["原文", "中文翻译"],
        ),
        (
            # 关联的那道题不是每个人都填了（跳题/选填）——只要有人有对应选择，这一列就该
            # 显示出来，不能因为部分受访者缺这个字段就把整列都藏起来。
            [
                {"raw": "Because A", "translation": "因为A", "corresponding_choice": "A"},
                {"raw": "No idea", "translation": "不知道", "corresponding_choice": None},
            ],
            ["对应选择", "原文", "中文翻译"],
        ),
    ],
)
def test_open_question_headers_follow_corresponding_choice(tmp_path, rows, expected_header):
    unit = {"kind": "open", "section": "正式", "title": "选择原因", "display_no": "Q2"}
    document = _export(
        tmp_path,
        units=[unit],
        stats_by_unit={"Q2": rows},
        n_by_unit={"Q2": len(rows)},
    )
    _table_with_header(document, expected_header)


def test_render_chart_image_with_title_adds_space_without_error(tmp_path):
    # "保存单张图表"功能用的就是带 title 的这个调用——标题要真的占出空间（图片变高），
    # 不能只是传了参数但其实没生效；也不能因为加了标题就直接报错或者产出空文件。
    stats_result = [
        {"option": "选项A", "n": 10, "count_pct_label": "10人（100.0%）"},
        {"option": "选项B", "n": 5, "count_pct_label": "5人（50.0%）"},
    ]
    no_title_path = tmp_path / "no_title.png"
    with_title_path = tmp_path / "with_title.png"

    _render_chart_image("single", stats_result, str(no_title_path))
    _render_chart_image(
        "single", stats_result, str(with_title_path),
        title="这是一道很长的问卷题目标题，用来确认标题会自动换行、不会跟图表内容重叠",
    )

    assert no_title_path.exists() and with_title_path.exists()
    no_title_height = Image.open(no_title_path).height
    with_title_height = Image.open(with_title_path).height
    assert with_title_height > no_title_height


def test_render_pie_chart_image_handles_many_long_options_without_error(tmp_path):
    # 真实反馈过的场景：饼图选项文字很长（中英双语拼接）、其中一个选项占比很小（容易
    # 把标签推到画布边缘）——这版把标签挪到独立的图例区域，不再直接标在扇区上，
    # 这里验证这种真实场景不会报错、能正常出图（图例本身的视觉排版没法用像素断言，
    # 只能靠人工看图确认，这里锁住"至少能正常跑完、产出一张图"这个底线）。
    stats_result = [
        {
            "option": "新品牌／The new brand focuses on EV",
            "n": 51,
            "count_pct_label": "51人（42.5%）",
        },
        {
            "option": "像GM或Ford这样历史悠久的汽车制造商／A long-established carmaker like GM or Ford",
            "n": 41,
            "count_pct_label": "41人（34.2%）",
        },
        {
            "option": "不确定，我需要了解更多／Not sure, I'd need to know more",
            "n": 28,
            "count_pct_label": "28人（23.3%）",
        },
    ]
    output_path = tmp_path / "pie_legend.png"

    _render_chart_image("single", stats_result, str(output_path), title="Q11. 测试问题")

    assert output_path.exists()
    assert Image.open(output_path).width > 0


def test_numeric_question_table_contains_all_summary_values(tmp_path):
    unit = {"kind": "numeric", "section": "正式", "title": "可接受价格", "display_no": "Q3"}
    stats = {"n": 8, "mean": 12.5, "median": 11.0, "min": 5.0, "max": 30.0}
    document = _export(
        tmp_path,
        units=[unit],
        stats_by_unit={"Q3": stats},
        n_by_unit={"Q3": 8},
    )
    table = _table_with_header(document, ["项目", "N", "均值", "中位数", "最小", "最大"])
    body = "|".join(cell.text for cell in table.rows[1].cells)
    for expected in ("12.5", "11.0", "5.0", "30.0"):
        assert expected in body


@pytest.mark.parametrize("ai_insights", [None, []])
def test_empty_ai_insights_omit_section_heading(tmp_path, ai_insights):
    document = _export(tmp_path, ai_insights=ai_insights)
    assert "AI 洞察" not in _paragraph_texts(document)


def test_crosstab_dimensions_match_dataframe(tmp_path):
    dataframe = pd.DataFrame(
        {"男": ["2人（20.0%）", "8人（80.0%）"], "合计": ["3人（15.0%）", "17人（85.0%）"]},
        index=pd.Index(["A", "B"], name="选项"),
    )
    document = _export(
        tmp_path,
        crosstabs=[{"title": "性别交叉", "table": dataframe}],
    )
    table = _table_with_header(document, ["选项", "男", "合计"])
    assert len(table.rows) == len(dataframe) + 1
    assert len(table.columns) == len(dataframe.columns) + 1


def test_ranking_exports_question_heading_and_summary_table(tmp_path):
    from engine.stats import ranking_table

    df = pd.DataFrame({"__TEST__A": ["1", "2", None], "__TEST__B": ["2", "1", "1"]})
    summary = ranking_table(df, list(df.columns), {"__TEST__A": "硅基", "__TEST__B": "铂金硅"}, 2)
    unit = {"kind": "ranking", "section": "正式", "title": "__TEST__材料排序", "display_no": "Q1"}
    document = _export(
        tmp_path, project_name="__TEST__ranking", units=[unit],
        stats_by_unit={"Q1": {"table": summary}}, n_by_unit={"Q1": len(df)},
    )
    assert any("__TEST__材料排序【排序题】" in text for text in _paragraph_texts(document))
    table = _table_with_header(document, ["", "硅基", "铂金硅"])
    assert [[cell.text for cell in row.cells] for row in table.rows[1:]] == [
        [rank, *values.tolist()] for rank, values in summary.iterrows()
    ]
    assert len(document.inline_shapes) == 0
