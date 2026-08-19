"""汇率走势图渲染（Pillow 生成 PNG，误差棒风格）。"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


_FONT_DIR = Path(__file__).parent / "fonts"
_FONT_PATH = _FONT_DIR / "NotoSansSC.ttf"

# 配色
_BG = (15, 23, 42)             # 深蓝底 #0F172A
_PANEL = (30, 41, 59)          # 面板 #1E293B
_GRID = (38, 50, 71)           # 网格线
_AXIS = (71, 85, 105)          # 坐标轴 #475569
_TEXT_MAIN = (241, 245, 249)   # 主文字 #F1F5F9
_TEXT_SUB = (148, 163, 184)    # 次要文字 #94A3B8
_BAR = (56, 189, 248)          # 误差棒 #38BDF8
_BAR_END = (129, 140, 248)     # 渐变端点 #818CF8
_UP = (248, 113, 113)          # 涨 #F87171
_DOWN = (52, 211, 153)         # 跌 #34D399
_MAX = (251, 191, 36)          # 最高 #FBBF24
_MIN = (52, 211, 153)          # 最低


_font_cache: dict[tuple[int, bool], ImageFont.FreeTypeFont] = {}


def _font(size: int, bold: bool = False):
    key = (size, bold)
    if key not in _font_cache:
        font = ImageFont.truetype(str(_FONT_PATH), size)
        try:
            font.set_variation_by_axes([700 if bold else 400])
        except Exception:
            try:
                font.set_variation_by_name("Bold" if bold else "Regular")
            except Exception:
                pass
        _font_cache[key] = font
    return _font_cache[key]


def _label(value: float) -> str:
    if value >= 1000:
        return f"{value:,.0f}"
    if value >= 1:
        return f"{value:.4f}"
    return f"{value:.6f}"


def _rounded(
    draw: ImageDraw.ImageDraw,
    box: list[int],
    radius: int,
    fill,
    outline=None,
    width: int = 1,
) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def render_chart(title: str, labels: list[str], values: list[float]) -> bytes:
    """把走势数据画成 PNG 图片（误差棒风格）。"""
    width, height = 980, 520
    left, right, top, bottom = 78, 950, 118, 440
    image = Image.new("RGB", (width, height), _BG)
    draw = ImageDraw.Draw(image)

    # ---------- 头部 ----------
    draw.text((36, 26), title, font=_font(32, True), fill=_TEXT_MAIN)
    if len(labels) >= 2:
        draw.text(
            (36, 76),
            f"{labels[0]}  ~  {labels[-1]}",
            font=_font(20),
            fill=_TEXT_SUB,
        )

    # 最新值 + 涨跌幅卡片
    latest = values[-1]
    first = values[0]
    delta = (latest - first) / first * 100 if first else 0.0
    rising = delta >= 0
    delta_color = _UP if rising else _DOWN
    chip_w, chip_h = 228, 58
    chip_x0 = width - 36 - chip_w
    chip_y0 = 26
    _rounded(
        draw,
        [chip_x0, chip_y0, chip_x0 + chip_w, chip_y0 + chip_h],
        14,
        _PANEL,
        _AXIS,
        1,
    )
    draw.text((chip_x0 + 14, chip_y0 + 6), "最新", font=_font(16), fill=_TEXT_SUB)
    draw.text(
        (chip_x0 + 14, chip_y0 + 24),
        _label(latest),
        font=_font(23, True),
        fill=_TEXT_MAIN,
    )
    arrow = "▲" if rising else "▼"
    delta_text = f"{arrow} {abs(delta):.2f}%"
    delta_font = _font(17, True)
    delta_w = draw.textlength(delta_text, font=delta_font)
    draw.text(
        (chip_x0 + chip_w - 14 - delta_w, chip_y0 + 30),
        delta_text,
        font=delta_font,
        fill=delta_color,
    )

    # ---------- 网格与坐标 ----------
    min_value = min(values)
    max_value = max(values)
    span = (max_value - min_value) or 1.0

    def y_for(value: float) -> float:
        return bottom - (value - min_value) / span * (bottom - top)

    def x_for(index: int) -> float:
        if len(values) == 1:
            return (left + right) / 2
        return left + (right - left) * index / (len(values) - 1)

    for index in range(6):
        grid_x = left + (right - left) * index / 5
        draw.line([(grid_x, top), (grid_x, bottom)], fill=_GRID, width=1)
    for index in range(6):
        grid_y = top + (bottom - top) * index / 5
        draw.line([(left, grid_y), (right, grid_y)], fill=_GRID, width=1)
        value = max_value - span * index / 5
        text = _label(value)
        text_w = draw.textlength(text, font=_font(20))
        draw.text(
            (left - 14 - text_w, grid_y - 11),
            text,
            font=_font(20),
            fill=_TEXT_SUB,
        )

    draw.line([(left, top), (left, bottom)], fill=_AXIS, width=2)
    draw.line([(left, bottom), (right, bottom)], fill=_AXIS, width=2)

    points = [(x_for(i), y_for(v)) for i, v in enumerate(values)]

    # 日期标签（首 / 中 / 尾）
    for index in (0, (len(labels) - 1) // 2, len(labels) - 1):
        if 0 <= index < len(labels):
            label = str(labels[index])
            label_font = _font(18)
            text_w = draw.textlength(label, font=label_font)
            draw.text(
                (
                    min(max(points[index][0] - text_w / 2, left), right - text_w),
                    bottom + 10,
                ),
                label,
                font=label_font,
                fill=_TEXT_SUB,
            )

    # ---------- 浅色趋势连接线（仅辅助阅读） ----------
    if len(points) >= 2:
        line_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        line_draw = ImageDraw.Draw(line_layer)
        line_draw.line(points, fill=(148, 163, 184, 150), width=1)
        image = Image.alpha_composite(image.convert("RGBA"), line_layer).convert("RGB")
        draw = ImageDraw.Draw(image)

    # ---------- 误差棒（局部波动范围：以该点为中心的 ±2 邻域高低） ----------
    dense = len(values) > 45
    bar_width = 1 if dense else 2
    cap = 4 if dense else 6
    dot_radius = 2 if dense else 3

    def _local_range(index: int) -> tuple[float, float]:
        window = values[max(0, index - 2): index + 3]
        return min(window), max(window)

    for index, (px, py) in enumerate(points):
        lo, hi = _local_range(index)
        y_lo, y_hi = y_for(lo), y_for(hi)
        draw.line([(px, y_hi), (px, y_lo)], fill=_BAR, width=bar_width)
        draw.line([(px - cap, y_hi), (px + cap, y_hi)], fill=_BAR, width=bar_width)
        draw.line([(px - cap, y_lo), (px + cap, y_lo)], fill=_BAR, width=bar_width)
        draw.ellipse(
            [px - dot_radius, py - dot_radius, px + dot_radius, py + dot_radius],
            fill="white",
            outline=_BAR_END,
            width=1,
        )

    # ---------- 最高 / 最低标记 ----------
    if len(values) >= 3:
        max_index = values.index(max_value)
        min_index = values.index(min_value)
        for idx, value, color, tag in (
            (max_index, max_value, _MAX, "高"),
            (min_index, min_value, _MIN, "低"),
        ):
            px, py = points[idx]
            if abs(px - points[-1][0]) < 24 and abs(py - points[-1][1]) < 24:
                continue
            draw.ellipse([px - 4, py - 4, px + 4, py + 4], fill=color, outline="white", width=1)
            tag_text = f"{tag} {_label(value)}"
            tag_font = _font(16, True)
            tag_w = draw.textlength(tag_text, font=tag_font)
            tag_x = max(left, min(px - tag_w / 2, right - tag_w - 8))
            tag_y = py - 38 if py > top + 70 else py + 18
            _rounded(
                draw,
                [int(tag_x - 4), int(tag_y - 3), int(tag_x + tag_w + 8), int(tag_y + 22)],
                7,
                _PANEL,
                _AXIS,
                1,
            )
            draw.text((tag_x, tag_y), tag_text, font=tag_font, fill=color)

    # ---------- 末点光晕 ----------
    last_x, last_y = points[-1]
    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    for radius, alpha in ((15, 42), (9, 80)):
        glow_draw.ellipse(
            [last_x - radius, last_y - radius, last_x + radius, last_y + radius],
            fill=(56, 189, 248, alpha),
        )
    image = Image.alpha_composite(image.convert("RGBA"), glow).convert("RGB")
    draw = ImageDraw.Draw(image)
    draw.ellipse(
        [last_x - 4, last_y - 4, last_x + 4, last_y + 4],
        fill="white",
        outline=_BAR,
        width=2,
    )

    # ---------- 图例说明 ----------
    note = "竖线 = 局部波动范围"
    note_font = _font(15)
    note_w = draw.textlength(note, font=note_font)
    draw.text((right - note_w, height - 28), note, font=note_font, fill=_TEXT_SUB)

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
