"""ECharts configuration builders governed by the reporting SOP."""

from __future__ import annotations


# 图表标题统一用这个颜色（ECharts 的 title.textStyle.color，matplotlib 的
# figure.suptitle(color=...)）——用户指定的色号，跟下面选项调色板是配套的一次改版。
TITLE_COLOR = "#245785"

# 单系列图表（常规单选/多选题）按选项逐个上色时循环使用的调色板——用户指定的十色列表，
# 前五色是"实际用过、确认好看"的（蓝/浅蓝/灰/绿/黄），后五色是扩展到十色时依次加入的。
# 选项数超过 10 个时从头循环。
OPTION_COLOR_PALETTE = [
    "#2E5797",  # 蓝
    "#5B9BD5",  # 浅蓝
    "#A6A6A6",  # 灰
    "#70AD47",  # 绿
    "#FFC000",  # 黄
    "#ED7D31",  # 橙
    "#6B4E9E",  # 紫
    "#1F7A8C",  # 青
    "#B23B3B",  # 红
    "#455A64",  # 石墨
]

# "极简"界面风格配的第二套图表色板——按用户要求查过 Bauhaus 和 Morandi 两套配色逻辑
# 再调的：Bauhaus 的道理是"用对比而不是和谐去分辨"（色相/明度要拉开，让人一眼分清
# 哪块是哪块，不是靠好看的搭配），Morandi 的道理是"每个颜色都掺一点灰/白，去掉高
# 饱和度那种视觉噪音"。这十个颜色饱和度统一压低（约 15%-45%），但色相刻意在色轮上
# 摊开、明度也刻意有深有浅（不是十个同一个色系的深浅渐变）——问卷图表终究是要让人
# 看出选项之间的数字差异，太接近的邻近色会互相看不清，纯 Morandi 那种"整体和谐"
# 用在数据图表上反而是缺点，这里是两套逻辑各取需要的一半，不是照抄某一套。
OPTION_COLOR_PALETTE_MINIMALIST = [
    "#8CAC6C",  # 灰绿 sage
    "#C7966B",  # 陶土 terracotta
    "#8DA1B0",  # 灰蓝 stone blue
    "#B86651",  # 砖红 brick
    "#9AB6A8",  # 桉叶灰绿 eucalyptus
    "#C4AA6E",  # 芥末 ochre
    "#C99CA7",  # 灰粉 dusty rose
    "#7C7396",  # 灰紫 stone plum
    "#D1C9A9",  # 沙色 sand putty
    "#915046",  # 深赭红 umber red
]


def _option_color(index: int, palette: list[str] | None = None) -> str:
    """Cycle through the option palette for the given zero-based option index."""

    active_palette = palette or OPTION_COLOR_PALETTE
    return active_palette[index % len(active_palette)]


def choose_chart_type(q_type: str, n_options: int) -> str:
    """Choose the SOP-mandated chart type for a closed question."""

    if q_type == "single":
        return "pie" if n_options <= 5 else "bar_h"
    if q_type == "multi":
        return "bar_h"
    raise ValueError(f"Unsupported question type for charting: {q_type}")


def build_chart_config(
    chart_type: str,
    stats_result: list[dict],
    title: str,
    footer: str,
    color_palette: list[str] | None = None,
) -> dict:
    """Build a single-series ECharts option using preformatted labels.

    color_palette：不传就用默认的十色 OPTION_COLOR_PALETTE；界面切到"极简"风格时，
    调用方会传 OPTION_COLOR_PALETTE_MINIMALIST 进来，图表颜色跟着界面风格换。
    """

    if chart_type == "pie":
        palette = [_option_color(i, color_palette) for i in range(len(stats_result))]
        series = [
            {
                "type": "pie",
                "center": ["50%", "55%"],
                "radius": "60%",
                "data": [
                    {
                        "name": row["option"],
                        "value": row["n"],
                        "label": {
                            # 选项文字是中英双语拼在一起的时候会很长（比如"新品牌专注于
                            # 电动汽车 / The new brand focuses on EV"），跟人数/占比拼在
                            # 一行超出图表边界，ECharts 默认行为是整行截断成"..."，连
                            # 百分比都看不到——这是真实截图暴露出来的问题。改成选项文字和
                            # 人数/占比分两行，并且允许按 width 自动换行（不是硬截断），
                            # 百分比这一行本身很短，永远不会被截断。
                            "formatter": f"{row['option']}\n{row['count_pct_label']}",
                            "overflow": "break",
                            "width": 180,
                        },
                        "itemStyle": {
                            "color": palette[i],
                            "borderColor": "#ffffff",
                            "borderWidth": 2,
                        },
                    }
                    for i, row in enumerate(stats_result)
                ],
            }
        ]
        return {
            "title": {"text": title, "left": "center", "textStyle": {"color": TITLE_COLOR}},
            "color": palette,
            "tooltip": {"trigger": "item"},
            "series": series,
            "_footer": footer,
        }

    if chart_type == "bar_h":
        palette = [_option_color(i, color_palette) for i in range(len(stats_result))]
        data = [
            {
                "value": row["n"],
                "label": {
                    "show": True,
                    "position": "right",
                    "formatter": row["count_pct_label"],
                },
                "itemStyle": {"color": palette[i]},
            }
            for i, row in enumerate(stats_result)
        ]
        return {
            "title": {"text": title, "left": "center", "textStyle": {"color": TITLE_COLOR}},
            "color": palette,
            "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
            "xAxis": {"type": "value"},
            "yAxis": {
                "type": "category",
                "data": [row["option"] for row in stats_result],
            },
            "series": [{"type": "bar", "data": data}],
            "_footer": footer,
        }

    raise ValueError(f"Unsupported chart type: {chart_type}")


def build_multi_series_chart_config(
    categories: list[str], series: list[dict], title: str, footer: str,
    color_palette: list[str] | None = None,
) -> dict:
    """Build a grouped horizontal bar chart, using the same option color palette
    as every other chart in the report.

    真实反馈："这两个颜色差异太小，好像不是我们之前规定的颜色"——这个函数原来
    固定用 SERIES_COLORS 这一套只有四个蓝色深浅变化的窄色板，跟报告里其它图表
    统一用的十色 OPTION_COLOR_PALETTE（蓝/浅蓝/灰/绿/黄……色相互相拉开，一眼就
    能分清）不是同一套，两个系列之间对比度也不够。改成默认也用 OPTION_COLOR_PALETTE
    （不传 color_palette 时），保持跟其它图表视觉一致；界面切到"极简"风格时，
    调用方按跟别处一样的规矩传 OPTION_COLOR_PALETTE_MINIMALIST 进来。
    """

    if len(series) > 4:
        raise ValueError("At most 4 series are supported by a grouped comparison chart")

    active_palette = color_palette or OPTION_COLOR_PALETTE
    configured_series = [
        {
            "name": item["name"],
            "type": "bar",
            "data": item["data"],
            "itemStyle": {"color": active_palette[index % len(active_palette)]},
        }
        for index, item in enumerate(series)
    ]
    return {
        "title": {"text": title, "left": "center", "textStyle": {"color": TITLE_COLOR}},
        "color": [active_palette[i % len(active_palette)] for i in range(len(series))],
        "legend": {"data": [item["name"] for item in series]},
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "xAxis": {"type": "value"},
        "yAxis": {"type": "category", "data": categories},
        "series": configured_series,
        "_footer": footer,
    }
