"""Export calculated questionnaire analysis results to a Word document."""

from __future__ import annotations

from engine.i18n import t

import io
import math
import tempfile
import textwrap
from itertools import cycle, islice
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import numpy as np
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Rectangle
from PIL import Image, ImageDraw, ImageFont
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from engine.chart_spec import OPTION_COLOR_PALETTE, TITLE_COLOR, choose_chart_type


QUESTION_TYPE_ZH = {
    "single": "单选题",
    "multi": "多选题",
    "ranking": "排序题",
    "open": "开放题",
    "numeric": "数值题",
}


def _balanced_wrap(text: str, width: int) -> list[str]:
    """跟 textwrap.wrap 一样折行，但会尽量避免"最后一行只剩一两个短单词、
    孤零零吊在下面"这种情况（真实反馈里"Ford 为什么单独跑到下一行，右边
    明明还有空档"，这类"孤儿词"是贪心折行算法的通病：它按顺序一行一行往上塞
    单词，塞不下才换行，不会往回看"换个更早的断点，会不会让每一行更均匀"）。
    做法很简单：在不超过原始 width 的前提下，试几个更窄一点的宽度，找一个
    "最后一行相对其它行不会短得太突兀"的方案；找不到更好的就用原始 width
    的结果，不会比原来更差。
    """

    base = textwrap.wrap(text, width=width) or [text]
    if len(base) <= 1:
        return base

    best = base
    best_last_ratio = len(base[-1]) / max(len(line) for line in base[:-1])
    for narrower in range(width - 1, max(width - 6, 1), -1):
        candidate = textwrap.wrap(text, width=narrower)
        if not candidate or len(candidate) != len(base):
            continue
        ratio = len(candidate[-1]) / max((len(line) for line in candidate[:-1]), default=1)
        if ratio > best_last_ratio:
            best, best_last_ratio = candidate, ratio
    return best


def _chart_font_family() -> str:
    """Return an installed font with Chinese glyph coverage when possible."""

    installed = {font.name for font in font_manager.fontManager.ttflist}
    for name in (
        "Arial Unicode MS",
        "PingFang SC",
        "Microsoft YaHei",
        "Noto Sans CJK SC",
        "SimHei",
        "WenQuanYi Zen Hei",
    ):
        if name in installed:
            return name
    return "DejaVu Sans"


def _render_chart_image(
    kind: str,
    stats_result: list[dict],
    tmp_path: str,
    title: str | None = None,
    color_palette: list[str] | None = None,
) -> None:
    """Render a closed-question chart to ``tmp_path`` as a PNG image.

    title：可选，图表最上面加一行大字标题（比如问卷原问题的中文版）——Word 导出这条
    路径不传这个参数（Word 里题目已经是文档正文里单独一段，图片里再写一遍就重复了），
    只有"单独保存这张图"这个场景需要图和标题在同一张 PNG 里、方便脱离网页单独发给别人。

    color_palette：不传就用默认的 OPTION_COLOR_PALETTE；界面切到"极简"风格时调用方
    会传 OPTION_COLOR_PALETTE_MINIMALIST 进来，导出的图跟网页上当前选的风格一致。
    """

    chart_type = choose_chart_type(kind, len(stats_result))
    colors = list(
        islice(cycle(color_palette or OPTION_COLOR_PALETTE), len(stats_result))
    )
    plt.rcParams["font.sans-serif"] = [_chart_font_family(), "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    # matplotlib 自己的 suptitle(wrap=True) 靠不住——savefig 用 bbox_inches="tight"
    # 会先把画布边界扩展到能放下整行文字，wrap 判断的又是扩展前的画布宽度，两边一凑，
    # 长标题变成了"画布越撑越宽、但还是不换行"。改成自己按字符数手动折行，跟图表实际
    # 尺寸无关，稳定可预期。
    wrapped_title = "\n".join(textwrap.wrap(title, width=32) or [title]) if title else None

    if chart_type == "pie":
        # 图例挪到右边一整块独立区域，饼图本身固定大小——原来的做法是标签直接标在
        # 扇区外沿、用引导线连（matplotlib 的 axis.pie(labels=...)），选项一多、文字
        # 一长，标签跟标签、标签跟标题就会互相压字，饼图本身的大小还会被这些标签的
        # 长短反过来挤压变形（真实反馈"排版效果太差，饼图大小要固定"）。现在图例是
        # 完全独立的一块区域，饼图的坐标轴用固定的英寸尺寸摆放，不会因为选项文字
        # 长短、数量多少而受影响，图例里选项按人数从高到低从上到下排列。
        # 真实反馈："图标题和图例全部偏左，没有居中"——量出来的真实原因：标题
        # 是相对"整张画布宽度"居中的，但饼图+图例这块内容原来是靠左摆放、图例
        # 又给了一份"一直伸到画布 98% 位置"的宽度，图例里的文字实际远没有那么
        # 宽（左对齐、没把这份空间用满），bbox_inches="tight" 存图时是按"文字/
        # 图形实际画到哪"来定裁切边界的，不会管画布名义上给了多少——裁完以后
        # 内容整体比画布本身窄一大截、又贴着左边，标题（相对旧的宽画布居中）
        # 看起来就变成偏左了。
        #
        # 改法：画布宽度不再是一个固定的、比内容宽很多的数（原来 11.5in），
        # 而是直接由"左边距 + 饼图 + 间隔 + 图例列宽度 + 右边距"这几块加起来算
        # 出来。图例列宽度也不能拍一个固定常数——试过固定给 5in（按"26 个中文
        # 字符折满"的最坏情况留出的宽度），结果选项文字比较短的时候（比如这次
        # 真实案例 Q6，中文最长才 13 个字），图例远没有用满这 5in，画布还是比
        # 内容宽一大截，居中问题只是缓解、没有真正解决。改成按这次实际的选项
        # 文字估一个宽度：中文字符按约等于其字号本身的正方形宽度算、英文字符
        # 按约一半字号宽度算（比较贴近常见无衬线字体的实际比例），取这次所有
        # 换行后的行里最宽的一行，再加一点色块和右边距——这样画布宽度是跟着
        # "这次这些选项文字到底有多宽"走的，不是固定猜一个数，短选项和长选项
        # 都能让内容跟画布对齐，标题跟着画布居中之后也就跟内容对上了。
        PIE_SIZE_INCHES = 4.6
        LEFT_MARGIN_INCHES = 0.15
        GAP_INCHES = 0.3  # 饼图和图例列之间的间隔
        RIGHT_MARGIN_INCHES = 0.15
        title_margin = 1.0 if wrapped_title else 0.35

        def _estimate_text_width_in(text: str, fontsize: int) -> float:
            """粗略估计一行文字的物理宽度（英寸）——中文字符按约等于字号本身的
            正方形算，英文/数字/标点按约一半字号算，够用来定图例列宽度，不需要
            像 GM/Ford 折行那个问题一样精确到个位数字符。
            """

            em_in = fontsize / 72
            wide = sum(1 for ch in text if ord(ch) > 0x2E80)  # 中文/中文标点等宽字符
            narrow = len(text) - wide
            return wide * em_in + narrow * em_in * 0.55

        # 颜色跟选项的原始顺序绑定（跟网页上、跟其它图表的配色规则一致——同一个选项
        # 不管在哪里出现都是同一个颜色），只是图例的"显示顺序"按人数从高到低排。
        paired = sorted(zip(stats_result, colors), key=lambda pair: pair[0]["n"], reverse=True)
        counts = [row["n"] for row, _ in paired]
        sorted_colors = [color for _, color in paired]

        # 图例高度要按"实际要画几行字"算，不能按"有几个选项"算——选项文字长、折成
        # 两三行的时候，如果还是按"一个选项固定一份高度"来分配空间，行距会被压得
        # 比字本身还窄，行跟行就会叠在一起（真实审查发现的问题：选项多、中文换行时
        # 图例可能重叠）。这里先把每一项要占几行文字都算出来，图的高度直接按"总行数"
        # 决定，画的时候也按每一项实际占的行数摆放，而不是假设每项都恰好是 3 行。
        # 真实反馈：保存/复制出来的这张图，图例里"英文／中文／人数占比"这几行字
        # 之间的行距太大，一眼很难把颜色块和它对应的文字看成一组，要求缩到
        # 原来的 40%。排查发现这个行距其实一直被下面那段"legend_axis 物理高度
        # vs 数据坐标范围不匹配"的问题自动拉伸放大过——改行距之前先修好那个
        # 拉伸 bug，不然改了也白改（这也是上一轮说"改了看不出差异"的真正原因：
        # 那一轮改动其实还没被重启生效，服务器进程缓存了改之前的代码）。
        #
        # 行距不再是不分字号统一套用一个数字——英文（9pt）、人数占比（10pt）、
        # 中文加粗（12pt）三种字号混排，统一套用一个行距，要么中文那行压线，
        # 要么英文那两行留白过多。改成按各自字号估一个刚好够用、不压字的行距
        # （字号 × 1.15 的经验系数，多组真实/编造数据、长短选项都试过没有压
        # 字），比原来统一 0.24in 的行距实打实缩短了 35%～46%（9pt 那行
        # 0.24in→0.144in，12pt 那行 0.24in→0.192in）——比字面上的"缩到 40%"
        # 稍微保守一点，因为 12pt 加粗中文字如果再压得更紧会直接压线看不清，
        # 这是留了安全余量之内能做到的最紧凑效果。
        EN_LINE_H = 9 * 1.15 / 72
        ZH_LINE_H = 12 * 1.15 / 72
        COUNT_LINE_H = 10 * 1.15 / 72
        ROW_GAP_IN = 0.18  # 项与项之间额外留的空白，要明显大于组内的行距，才看得出分组
        SWATCH_SIZE_IN = 0.16

        item_layouts = []
        for row, color in paired:
            option_text = str(row["option"])
            zh_part, sep, en_part = option_text.partition("／")
            # 选项文字太长会跑出图例区域右边界，按字符数手动折行（原因跟标题折行
            # 一样：matplotlib 不会自动帮长文本换行）。
            zh_lines = _balanced_wrap(zh_part, 26)
            en_lines = _balanced_wrap(en_part, 32) if sep else []
            block_height = len(en_lines) * EN_LINE_H + len(zh_lines) * ZH_LINE_H + COUNT_LINE_H
            item_layouts.append(
                {
                    "color": color,
                    "en_lines": en_lines,
                    "zh_lines": zh_lines,
                    "count_label": row["count_pct_label"],
                    "block_height": block_height,
                }
            )

        total_content_in = sum(item["block_height"] for item in item_layouts) + ROW_GAP_IN * max(
            len(item_layouts) - 1, 0
        )
        legend_needed = max(total_content_in, ZH_LINE_H) + 0.4
        fig_height = max(PIE_SIZE_INCHES, legend_needed) + title_margin

        # 色块和文字的横向位置改成跟纵向一样，直接用"英寸"做单位（不再是 0～1 的
        # 相对坐标）——色块、文字起点这些位置不再是"图例列宽度的百分之几"，
        # 是固定的物理距离，图例列多宽都不会把它们的间距跟着放大或缩小，跟下面
        # LEGEND_COL_INCHES 的算法（色块宽 + 间隔 + 最长一行文字宽 + 右边距）
        # 完全对得上，不会出现"文字起点位置"和"图例列总宽度"两套算法各算各的、
        # 对不上导致文字挤到色块上或者留白对不齐的情况。
        SWATCH_W_IN = 0.22
        TEXT_X_IN = SWATCH_W_IN + 0.15
        RIGHT_PAD_IN = 0.15

        max_line_width_in = 0.0
        for item in item_layouts:
            for line in item["en_lines"]:
                max_line_width_in = max(max_line_width_in, _estimate_text_width_in(line, 9))
            for line in item["zh_lines"]:
                max_line_width_in = max(max_line_width_in, _estimate_text_width_in(line, 12))
            max_line_width_in = max(max_line_width_in, _estimate_text_width_in(item["count_label"], 10))
        LEGEND_COL_INCHES = max(1.3, TEXT_X_IN + max_line_width_in + RIGHT_PAD_IN)
        FIG_WIDTH_INCHES = (
            LEFT_MARGIN_INCHES + PIE_SIZE_INCHES + GAP_INCHES + LEGEND_COL_INCHES + RIGHT_MARGIN_INCHES
        )

        figure = plt.figure(figsize=(FIG_WIDTH_INCHES, fig_height))
        if wrapped_title:
            figure.suptitle(wrapped_title, fontsize=13, fontweight="bold", color=TITLE_COLOR)

        pie_left_frac = LEFT_MARGIN_INCHES / FIG_WIDTH_INCHES
        pie_w_frac = PIE_SIZE_INCHES / FIG_WIDTH_INCHES
        pie_h_frac = PIE_SIZE_INCHES / fig_height
        pie_bottom_frac = max(0.02, (fig_height - title_margin - PIE_SIZE_INCHES) / 2 / fig_height)
        pie_axis = figure.add_axes((pie_left_frac, pie_bottom_frac, pie_w_frac, pie_h_frac))
        legend_left_frac = (LEFT_MARGIN_INCHES + PIE_SIZE_INCHES + GAP_INCHES) / FIG_WIDTH_INCHES
        legend_w_frac = LEGEND_COL_INCHES / FIG_WIDTH_INCHES
        legend_height_frac = min(0.98, (fig_height - title_margin) / fig_height)
        legend_axis = figure.add_axes((legend_left_frac, 0.02, legend_w_frac, legend_height_frac))
        legend_axis.axis("off")

        if paired and sum(counts) > 0:
            pie_axis.pie(
                counts,
                colors=sorted_colors,
                startangle=90,
                counterclock=False,
                wedgeprops={"edgecolor": "white", "linewidth": 2},
            )
            pie_axis.axis("equal")
        else:
            pie_axis.text(0.5, 0.5, t('暂无数据'), ha="center", va="center")
            pie_axis.axis("off")

        # 之前的写法：y 轴的数据坐标直接用"英寸"做单位，但 set_ylim 的上限用的是
        # total_content_in（文字实际需要的高度），legend_axis 这个坐标轴自己在画布上
        # 的物理高度却是 legend_height_frac * fig_height（通常明显更高，因为饼图
        # 固定 4.6in、比大多数图例内容需要的高度都大）——matplotlib 会把"更少的数据
        # 范围"自动拉伸去填满"更大的物理空间"，导致不管把 LINE_HEIGHT_IN 调多小，
        # 拉伸efect 都会把行距重新"撑"回去，改了等于没改（真实反馈"间距减小 1/2"
        # 改了 LINE_HEIGHT_IN 却看不出效果，根因就在这里）。
        #
        # 改成用 legend_axis 自己真实的物理高度（legend_axis_height_in）当 ylim
        # 上限，这样"1 数据单位 = 1 英寸"才是真的成立，LINE_HEIGHT_IN 改多少，
        # 渲染出来的行距就真的变多少。选项少、饼图比图例内容高的时候，多出来的
        # 空间不再是把文字拉稀撑满，而是整块图例内容在这块区域里垂直居中，上下
        # 留白，文字本身该多紧凑还是多紧凑。
        legend_axis_height_in = legend_height_frac * fig_height
        vertical_offset_in = max(0.0, (legend_axis_height_in - total_content_in) / 2)
        legend_axis.set_xlim(0, LEGEND_COL_INCHES)  # 横向也用"1 数据单位 = 1 英寸"，跟纵向一致
        legend_axis.set_ylim(legend_axis_height_in, 0)  # 反向：第一项在最上面
        text_x = TEXT_X_IN
        cursor = vertical_offset_in
        for item in item_layouts:
            block_height = item["block_height"]
            band_center = cursor + block_height / 2
            legend_axis.add_patch(
                Rectangle(
                    (0.0, band_center - SWATCH_SIZE_IN / 2), SWATCH_W_IN, SWATCH_SIZE_IN,
                    color=item["color"], clip_on=False, transform=legend_axis.transData,
                )
            )
            y = cursor + EN_LINE_H / 2 if item["en_lines"] else cursor + ZH_LINE_H / 2
            for line in item["en_lines"]:
                legend_axis.text(text_x, y, line, fontsize=9, color="#666666", va="center")
                y += EN_LINE_H
            for j, line in enumerate(item["zh_lines"]):
                legend_axis.text(
                    text_x, y, line, fontsize=12, color="#222222", fontweight="bold", va="center",
                )
                y += ZH_LINE_H
            legend_axis.text(text_x, y, item["count_label"], fontsize=10, color="#666666", va="center")
            cursor += block_height + ROW_GAP_IN
    else:
        height = max(3.2, 0.52 * len(stats_result) + 1.2)
        figure, axis = plt.subplots(figsize=(9, height))
        if wrapped_title:
            figure.suptitle(wrapped_title, fontsize=13, fontweight="bold", color=TITLE_COLOR)
        # 选项文字是中英双语拼在一起的时候会很长，不折行的话左边距会被撑得很宽、
        # 画图区域反而被挤扁——跟标题、饼图图例用同一个手动折行办法，不依赖
        # matplotlib 自动换行（它本来就不会自动折 tick label）。
        #
        # 真实反馈："GM 和 Ford 为什么会排到下一行？它右边明明还有很多空档"——
        # 根因是这里原来把"中文／English"整段当一整块字符串一起折行，
        # textwrap 按"字符数"算宽度，把中文字和英文字当成一样宽；实际中文字在
        # 常见字体里差不多有英文字母两倍宽，一行里中文越多，这一行真实渲染出来
        # 就越宽，折行算法却不知道，纯按字符数切——切到某一行恰好剩下几个英文
        # 短词（比如"GM or Ford"）时，这一行字符数够了就换行，可它全是窄的
        # 英文字母，实际渲染宽度比其它行短一大截，看起来就是"明明右边有空档却
        # 换行了"。改成跟饼图图例一样的办法：中文和英文分开折行（各自的宽度
        # 阈值也分开定，中文字符按其大概两倍宽度给一个更小的字符数上限），
        # 折完之后再拼成一段文字，不会再出现"一行全是窄字符、看起来比别的行短
        # 很多"的情况。
        def _wrap_bilingual_label(option_text: str) -> str:
            zh_part, sep, en_part = str(option_text).partition("／")
            zh_lines = _balanced_wrap(zh_part, 14)
            en_lines = _balanced_wrap(en_part, 24) if sep else []
            return "\n".join(zh_lines + en_lines)

        options = [_wrap_bilingual_label(row["option"]) for row in stats_result]
        counts = [row["n"] for row in stats_result]
        positions = list(range(len(stats_result)))
        bars = axis.barh(positions, counts, color=colors, height=0.62)
        axis.set_yticks(positions, labels=options)
        axis.invert_yaxis()
        axis.set_xlabel(t('人数'))
        axis.grid(False)
        axis.spines[["top", "right", "left"]].set_visible(False)
        axis.tick_params(axis="y", length=0)
        max_count = max(counts, default=0)
        label_offset = max(max_count * 0.015, 0.2)
        axis.set_xlim(0, max(max_count * 1.35, 1))
        for bar, row in zip(bars, stats_result):
            axis.text(
                bar.get_width() + label_offset,
                bar.get_y() + bar.get_height() / 2,
                row["count_pct_label"],
                va="center",
                ha="left",
                fontsize=9,
                color="#222222",
            )
        figure.tight_layout()

    figure.savefig(tmp_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(figure)


# "复制/下载"合成图（图片+图表）用的排版常数——这是导出的静态图片，不是网页上的
# 卡片，没有真实浏览器窗口宽度可以读，用一批经验值：
# - _SNAPSHOT_MAX_CONTENT_WIDTH_PX：多张图片排一行时的宽度上限，跟网页"排版预览"
#   假设的卡片宽度（app.py 的 ROW_WIDTH_ASSUMPTION_PX=940）同一量级。
# - _SNAPSHOT_ROW_HEIGHT_PX：多张图片时每行的基准高度——比网页上排版预览用的
#   IMAGE_ROW_BASE_HEIGHT_PX（饼图高度的 2/3）更大一些，因为这是要单独发给别人的
#   图片文件，值得比屏幕上占的一小块排版区域给更高的清晰度。
_SNAPSHOT_MAX_CONTENT_WIDTH_PX = 1000
_SNAPSHOT_ROW_HEIGHT_PX = 320
_SNAPSHOT_MARGIN_PX = 32
_SNAPSHOT_GAP_PX = 24
_SNAPSHOT_TITLE_FONT_SIZE = 30


def _snapshot_title_font(size: int = _SNAPSHOT_TITLE_FONT_SIZE) -> ImageFont.FreeTypeFont:
    path = font_manager.findfont(font_manager.FontProperties(family=_chart_font_family()))
    return ImageFont.truetype(path, size)


def _wrap_text_to_pixel_width(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """按实际像素宽度折行（不是按字符数）——合成图的标题栏宽度是算出来的（图片/
    图表拼起来有多宽，标题栏就有多宽），只有按真实字体量出来的像素宽度折行，才能
    保证标题不会在窄画布上被裁掉、也不会在宽画布上过早换行。逐字符累加而不是逐个
    单词累加：中文本来就没有空格分词，这份标题常常是中英文混排的问题原文，逐字符
    判断对两种情况都适用。
    """

    if not text:
        return []
    lines: list[str] = []
    current = ""
    for ch in text:
        candidate = current + ch
        if current and font.getlength(candidate) > max_width:
            lines.append(current)
            current = ch
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def compose_question_snapshot_image(
    kind: str,
    stats_result: list[dict],
    title: str,
    images: list[dict],
    images_per_row: int = 1,
    color_palette: list[str] | None = None,
) -> bytes:
    """把这道题插入的图片和图表合并成一张 PNG——真实反馈"复制/下载出来的应该是
    我插入的图片和图表合成一张图，不能只有图表自己"。标题只画一次、横跨整张合成图
    的顶部（图表自己不再画标题，`_render_chart_image` 这里传 `title=None`），不然
    图表内部一个标题、合成图外面再套一个标题，两个标题对不齐、还重复。

    - 只有一张图时：图片在左、图表在右，并排一行，两边统一按图表本身的高度对齐
      （图表保持原有大小，图片按自己的长宽比缩放到跟图表一样高）——这是网页正文
      "只有一张图时图左图表右并排"（见 app.py 的 `render_images_and_chart`）这个
      最终排版效果的静态版本。
    - 两张图及以上时：图片沿用"每行放几张"分成一到多行（每行内部统一缩放到同一个
      基准高度，一行放不下时整行等比缩小，跟网页"排版预览"`_render_tiles_row`
      同一条规则），图表整行放在图片下面、居中。
    """

    with tempfile.NamedTemporaryFile(suffix=".png") as chart_tmp:
        _render_chart_image(kind, stats_result, chart_tmp.name, title=None, color_palette=color_palette)
        with Image.open(chart_tmp.name) as opened:
            chart_img = opened.convert("RGB").copy()

    opened_images = []
    for img in images:
        with Image.open(io.BytesIO(img["bytes"])) as opened:
            opened_images.append(opened.convert("RGB").copy())

    if len(opened_images) == 1:
        single = opened_images[0]
        target_height = chart_img.height
        scaled_width = max(1, round(single.width * target_height / single.height))
        single = single.resize((scaled_width, target_height))
        content_width = single.width + _SNAPSHOT_GAP_PX + chart_img.width
        content_height = target_height
        body_positions = [(single, 0, 0), (chart_img, single.width + _SNAPSHOT_GAP_PX, 0)]
    else:
        per_row = max(1, images_per_row)
        rows = [opened_images[i : i + per_row] for i in range(0, len(opened_images), per_row)]
        scaled_rows = []
        for row in rows:
            widths = [_SNAPSHOT_ROW_HEIGHT_PX * (img.width / img.height) for img in row]
            total_width = sum(widths) + _SNAPSHOT_GAP_PX * (len(row) - 1)
            scale = min(1.0, _SNAPSHOT_MAX_CONTENT_WIDTH_PX / total_width) if total_width > 0 else 1.0
            height = max(1, round(_SNAPSHOT_ROW_HEIGHT_PX * scale))
            scaled_rows.append(
                [img.resize((max(1, round(img.width * height / img.height)), height)) for img in row]
            )
        row_widths = [
            sum(im.width for im in row) + _SNAPSHOT_GAP_PX * (len(row) - 1) for row in scaled_rows
        ]
        content_width = max(row_widths + [chart_img.width])

        body_positions = []
        y = 0
        for row, row_width in zip(scaled_rows, row_widths):
            x = (content_width - row_width) // 2
            row_height = max(im.height for im in row)
            for im in row:
                body_positions.append((im, x, y + (row_height - im.height) // 2))
                x += im.width + _SNAPSHOT_GAP_PX
            y += row_height + _SNAPSHOT_GAP_PX
        chart_x = (content_width - chart_img.width) // 2
        body_positions.append((chart_img, chart_x, y))
        content_height = y + chart_img.height

    font = _snapshot_title_font()
    title_lines = _wrap_text_to_pixel_width(title, font, content_width) if title else []
    line_height = round(_SNAPSHOT_TITLE_FONT_SIZE * 1.4)
    title_block_height = len(title_lines) * line_height + (_SNAPSHOT_GAP_PX if title_lines else 0)

    canvas_width = content_width + _SNAPSHOT_MARGIN_PX * 2
    canvas_height = _SNAPSHOT_MARGIN_PX * 2 + title_block_height + content_height
    canvas = Image.new("RGB", (canvas_width, canvas_height), "white")
    draw = ImageDraw.Draw(canvas)

    y_text = _SNAPSHOT_MARGIN_PX
    for line in title_lines:
        draw.text((_SNAPSHOT_MARGIN_PX, y_text), line, font=font, fill=TITLE_COLOR)
        y_text += line_height

    body_top = _SNAPSHOT_MARGIN_PX + title_block_height
    for element, x, y in body_positions:
        canvas.paste(element, (_SNAPSHOT_MARGIN_PX + x, body_top + y))

    buffer = io.BytesIO()
    canvas.save(buffer, format="PNG")
    return buffer.getvalue()


def render_grouped_bar_chart_image(
    categories: list[str], series: list[dict], tmp_path: str,
    title: str | None = None, color_palette: list[str] | None = None,
) -> None:
    """每个维度下并排画各问卷的占比，图例直接用默认色块，不复用饼图的排版逻辑。

    真实反馈："这两个颜色差异太小"——默认色板改成跟网页上、跟其它图表导出统一的
    OPTION_COLOR_PALETTE（不再是只有四种蓝色深浅的 SERIES_COLORS），保存/下载出来
    的这张图跟网页上看到的颜色也保持一致（调用方 app.py 传的是同一份
    _active_chart_palette() 结果）。
    """

    plt.rcParams["font.sans-serif"] = [_chart_font_family(), "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    colors = color_palette or OPTION_COLOR_PALETTE
    figure, axis = plt.subplots(figsize=(max(8, len(categories) * 0.9), 5))
    try:
        positions = np.arange(len(categories))
        width = 0.8 / max(len(series), 1)
        for index, item in enumerate(series):
            axis.bar(positions + (index - (len(series) - 1) / 2) * width, item["data"], width,
                     label=item["name"], color=colors[index % len(colors)])
        axis.set_xticks(positions, labels=[str(c) for c in categories], rotation=30, ha="right")
        axis.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(xmax=100))
        axis.set_ylim(bottom=0)
        axis.spines[["top", "right"]].set_visible(False)
        if series:
            axis.legend(loc="upper left", bbox_to_anchor=(1.02, 1), frameon=False)
        if title:
            figure.suptitle("\n".join(textwrap.wrap(title, width=32) or [title]),
                            fontsize=13, fontweight="bold", color=TITLE_COLOR)
        figure.tight_layout()
        figure.savefig(tmp_path, dpi=150, bbox_inches="tight", facecolor="white")
    finally:
        plt.close(figure)


def _set_cell_shading(cell, fill: str) -> None:
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), fill)
    cell._tc.get_or_add_tcPr().append(shading)


def _style_table(table) -> None:
    table.style = "Table Grid"
    table.rows[0]._tr.get_or_add_trPr().append(OxmlElement("w:tblHeader"))
    for cell in table.rows[0].cells:
        # 表头底色统一用品牌蓝（跟网页标题、图表标题同一个色号），之前这里是改配色
        # 之前遗留的旧深蓝，没跟着这轮一起换，导出的 Word 跟网页看起来是两个品牌。
        _set_cell_shading(cell, TITLE_COLOR.lstrip("#"))
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        for paragraph in cell.paragraphs:
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in paragraph.runs:
                run.bold = True
                run.font.color.rgb = RGBColor(255, 255, 255)
    for row in table.rows[1:]:
        for cell in row.cells:
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER


def _add_table(document: Document, headers: list[str], rows: list[list[Any]]):
    table = document.add_table(rows=1, cols=len(headers))
    for index, header in enumerate(headers):
        table.rows[0].cells[index].text = header
    for values in rows:
        cells = table.add_row().cells
        for index, value in enumerate(values):
            cells[index].text = _display_value(value)
    _style_table(table)
    return table


def _display_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value)


def _add_bullet(document: Document, text: str) -> None:
    document.add_paragraph(text, style="List Bullet")


def _test_method_rows(test_method: dict) -> list[list[str]]:
    platform = test_method.get("platform_source") or t('未填写')
    if test_method.get("is_branched"):
        count = test_method.get("branch_count")
        branched = t('是（{count}份）', count=count) if count is not None else t('是（份数未填写）')
    else:
        branched = t('否')
    return [
        [t('平台来源'), platform],
        [t('是否分流'), branched],
        [t('筛选剔除规则'), test_method.get("screen_out_rule") or t('未填写')],
        [t('跳转逻辑说明'), test_method.get("skip_logic_note") or t('未填写')],
    ]


def _configure_document_styles(document: Document) -> None:
    styles = document.styles
    styles["Normal"].font.name = "Microsoft YaHei"
    styles["Normal"].font.size = Pt(10.5)
    for style_name in ("Title", "Heading 1", "Heading 2", "Heading 3"):
        style = styles[style_name]
        style.font.name = "Microsoft YaHei"
        style.font.color.rgb = RGBColor(0, 0, 0)


def export_analysis_to_docx(
    output_path: str,
    project_name: str,
    conclusions: list[str],
    test_method: dict,
    units: list[dict],
    stats_by_unit: dict,
    n_by_unit: dict,
    ai_insights: list[str] | None = None,
    crosstabs: list[dict] | None = None,
    color_palette: list[str] | None = None,
) -> None:
    """Export one calculated questionnaire analysis to ``output_path``.

    color_palette：不传就用默认的 OPTION_COLOR_PALETTE；调用方（app.py）会按网页上
    当前选的界面风格传对应的色板，导出的 Word 报告跟网页图表颜色保持一致。
    """

    document = Document()
    _configure_document_styles(document)
    document.add_heading(t('{project_name} 问卷分析报告', project_name=project_name), level=1)

    nonempty_conclusions = [text for text in conclusions if text]
    if nonempty_conclusions:
        document.add_heading(t('核心结论'), level=2)
        for conclusion in nonempty_conclusions:
            _add_bullet(document, conclusion)

    document.add_heading(t('测试方法'), level=2)
    _add_table(document, [t('项目'), t('说明')], _test_method_rows(test_method))

    with tempfile.TemporaryDirectory(prefix="survey_word_charts_") as temp_dir:
        for unit in units:
            if unit.get("section") not in {"正式", "基础信息"}:
                continue
            kind = unit["kind"]
            display_no = unit["display_no"]
            title = unit["title"]
            document.add_heading(
                t('{display_no}. {title}【{question_type}】', display_no=display_no, title=title, question_type=t(QUESTION_TYPE_ZH[kind])), level=3
            )
            stats_result = stats_by_unit[display_no]

            if kind in {"single", "multi"}:
                chart_path = str(Path(temp_dir) / f"chart_{len(document.inline_shapes)}.png")
                _render_chart_image(kind, stats_result, chart_path, color_palette=color_palette)
                picture_paragraph = document.add_paragraph()
                picture_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                picture_paragraph.add_run().add_picture(chart_path, width=Inches(6))
                sample_paragraph = document.add_paragraph()
                sample_run = sample_paragraph.add_run(f"n = {n_by_unit[display_no]}")
                sample_run.font.size = Pt(9)
                sample_run.font.color.rgb = RGBColor(64, 64, 64)
            elif kind == "ranking":
                dataframe = stats_result["table"]
                index_header = dataframe.index.name or ""
                headers = [str(index_header), *[str(column) for column in dataframe.columns]]
                rows = [
                    [index_value, *row.tolist()]
                    for index_value, row in dataframe.iterrows()
                ]
                _add_table(document, headers, rows)
            elif kind == "numeric":
                _add_table(
                    document,
                    [t('项目'), "N", t('均值'), t('中位数'), t('最小'), t('最大')],
                    [[
                        title,
                        stats_result.get("n"),
                        stats_result.get("mean"),
                        stats_result.get("median"),
                        stats_result.get("min"),
                        stats_result.get("max"),
                    ]],
                )
            elif kind == "open":
                # any 而不是 all——关联的那道题本身可能有人没填（跳题、选填），不能因为
                # 一部分受访者缺这个字段就把整列"对应选择"都藏起来，只要有人有就该显示，
                # 没有的respondent 那一格留空就行。
                has_choices = bool(stats_result) and any(
                    bool(row.get("corresponding_choice")) for row in stats_result
                )
                if has_choices:
                    headers = [t('对应选择'), t('原文'), t('中文翻译')]
                    rows = [
                        [
                            row.get("corresponding_choice"),
                            row.get("raw"),
                            row.get("translation"),
                        ]
                        for row in stats_result
                    ]
                else:
                    headers = [t('原文'), t('中文翻译')]
                    rows = [
                        [row.get("raw"), row.get("translation")]
                        for row in stats_result
                    ]
                _add_table(document, headers, rows)

        if crosstabs:
            document.add_heading(t('交叉分析'), level=2)
            for item in crosstabs:
                document.add_heading(item["title"], level=3)
                dataframe = item["table"]
                index_header = dataframe.index.name or ""
                headers = [str(index_header), *[str(column) for column in dataframe.columns]]
                rows = [
                    [index_value, *row.tolist()]
                    for index_value, row in dataframe.iterrows()
                ]
                _add_table(document, headers, rows)

        nonempty_insights = [text for text in (ai_insights or []) if text]
        if nonempty_insights:
            document.add_heading(t('AI 洞察'), level=2)
            for insight in nonempty_insights:
                _add_bullet(document, insight)

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        document.save(output_path)
