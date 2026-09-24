import pytest

from engine.chart_spec import (
    OPTION_COLOR_PALETTE,
    build_chart_config,
    build_multi_series_chart_config,
    choose_chart_type,
)


def test_choose_chart_type_follows_option_thresholds():
    assert choose_chart_type("single", 3) == "pie"
    assert choose_chart_type("single", 7) == "bar_h"
    assert choose_chart_type("multi", 2) == "bar_h"
    assert choose_chart_type("multi", 20) == "bar_h"


def test_choose_chart_type_rejects_non_closed_question():
    with pytest.raises(ValueError):
        choose_chart_type("open", 3)


def test_build_pie_config_uses_passed_title_footer_color_and_labels():
    stats = [
        {"option": "A", "n": 2, "pct": 66.7, "count_pct_label": "2人（66.7%）"},
        {"option": "B", "n": 1, "pct": 33.3, "count_pct_label": "1人（33.3%）"},
    ]

    config = build_chart_config("pie", stats, "偏好分布", "n = 3")

    assert config["title"] == {"text": "偏好分布", "left": "center", "textStyle": {"color": "#245785"}}
    assert config["_footer"] == "n = 3"
    assert config["color"] == OPTION_COLOR_PALETTE[:2]
    # 选项文字和人数/占比分两行（不是拼一行再用冒号连起来）——选项文字很长的时候
    # （中英双语拼在一起），ECharts 会把过长的整行截断看不到百分比，分两行 + 允许
    # 按宽度换行（不是硬截断）能保证人数/占比这行本身很短，不会被截断。
    assert config["series"][0]["data"][0]["label"]["formatter"] == "A\n2人（66.7%）"
    assert config["series"][0]["data"][0]["label"]["overflow"] == "break"
    assert config["series"][0]["center"] == ["50%", "55%"]


def test_build_pie_config_colors_each_slice_from_the_option_palette_with_border():
    stats = [
        {"option": "A", "n": 2, "pct": 66.7, "count_pct_label": "2人（66.7%）"},
        {"option": "B", "n": 1, "pct": 33.3, "count_pct_label": "1人（33.3%）"},
    ]

    config = build_chart_config("pie", stats, "偏好分布", "footer")

    slice_colors = [item["itemStyle"]["color"] for item in config["series"][0]["data"]]
    assert slice_colors == OPTION_COLOR_PALETTE[:2]
    assert len(set(slice_colors)) == 2  # 不同选项必须是不同颜色，不能退回单色
    for item in config["series"][0]["data"]:
        assert item["itemStyle"]["borderWidth"] > 0
        assert item["itemStyle"]["borderColor"]


def test_build_pie_config_cycles_palette_past_ten_options():
    stats = [
        {"option": str(i), "n": 1, "pct": 9.1, "count_pct_label": "1人（9.1%）"}
        for i in range(11)
    ]

    config = build_chart_config("pie", stats, "分布", "footer")

    colors = [item["itemStyle"]["color"] for item in config["series"][0]["data"]]
    assert colors[0] == colors[10] == OPTION_COLOR_PALETTE[0]
    assert colors[1] == OPTION_COLOR_PALETTE[1]


def test_build_horizontal_bar_config_uses_existing_count_pct_labels():
    stats = [
        {"option": "A", "n": 2, "pct": 100.0, "count_pct_label": "2人（100.0%）"},
        {"option": "B", "n": 1, "pct": 50.0, "count_pct_label": "1人（50.0%）"},
    ]

    config = build_chart_config("bar_h", stats, "选择原因", "footer")

    assert config["title"] == {"text": "选择原因", "left": "center", "textStyle": {"color": "#245785"}}
    assert config["yAxis"]["data"] == ["A", "B"]
    assert config["series"][0]["data"][0]["label"]["formatter"] == "2人（100.0%）"
    bar_colors = [item["itemStyle"]["color"] for item in config["series"][0]["data"]]
    assert bar_colors == OPTION_COLOR_PALETTE[:2]


def test_build_multi_series_config_uses_option_palette_by_default():
    # 真实反馈："这两个颜色差异太小，好像不是我们之前规定的颜色"——这个函数原来
    # 固定用只有四种蓝色深浅的窄色板，跟报告里其它图表统一用的十色 OPTION_COLOR_PALETTE
    # 不是同一套，改成默认也用这一套，跟其它图表视觉一致、对比度也够。
    series = [
        {"name": "组1", "data": [10.0, 20.0]},
        {"name": "组2", "data": [30.0, 40.0]},
    ]
    config = build_multi_series_chart_config(["A", "B"], series, "组间对比", "footer")

    assert config["title"] == {"text": "组间对比", "left": "center", "textStyle": {"color": "#245785"}}
    assert config["color"] == OPTION_COLOR_PALETTE[:2]
    assert [item["itemStyle"]["color"] for item in config["series"]] == OPTION_COLOR_PALETTE[:2]
    assert config["_footer"] == "footer"

    with pytest.raises(ValueError, match="At most 4"):
        build_multi_series_chart_config(
            ["A"],
            [{"name": str(index), "data": [index]} for index in range(5)],
            "title",
            "footer",
        )


def test_build_multi_series_config_accepts_custom_palette_for_minimalist_theme():
    # 界面切到"极简"风格时，调用方（app.py 的 _active_chart_palette()）会传
    # OPTION_COLOR_PALETTE_MINIMALIST 进来，图表颜色要跟着换，不能一直用默认色板。
    series = [{"name": "组1", "data": [10.0]}, {"name": "组2", "data": [20.0]}]
    custom_palette = ["#111111", "#222222", "#333333"]

    config = build_multi_series_chart_config(["A"], series, "标题", "footer", color_palette=custom_palette)

    assert config["color"] == ["#111111", "#222222"]
    assert [item["itemStyle"]["color"] for item in config["series"]] == ["#111111", "#222222"]
