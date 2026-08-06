"""汇率走势图渲染（Pillow 生成 PNG，无需外部渲染服务）。"""

from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageDraw, ImageFont


def _font(size: int = 18):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # 旧版 Pillow
        return ImageFont.load_default()


def _label(value: float) -> str:
    if value >= 1000:
        return f"{value:,.0f}"
    if value >= 1:
        return f"{value:.4f}"
    return f"{value:.6f}"


def render_chart(title: str, labels: list[str], values: list[float]) -> bytes:
    """把走势数据画成 PNG 图片。"""
    width, height = 900, 420
    left, right, top, bottom = 80, 870, 55, 370
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    font = _font()

    draw.text((left, 15), title, fill="black", font=font)

    min_value = min(values)
    max_value = max(values)
    span = (max_value - min_value) or 1.0

    def y_for(value: float) -> float:
        return bottom - (value - min_value) / span * (bottom - top)

    for index in range(5):
        grid_y = top + (bottom - top) * index / 4
        draw.line([(left, grid_y), (right, grid_y)], fill="lightgray")
        value = max_value - span * index / 4
        draw.text((4, grid_y - 9), _label(value), fill="black", font=font)

    draw.line([(left, top), (left, bottom)], fill="black")
    draw.line([(left, bottom), (right, bottom)], fill="black")

    count = len(values)
    if count == 1:
        points = [((left + right) // 2, y_for(values[0]))]
    else:
        points = [
            (left + (right - left) * index / (count - 1), y_for(value))
            for index, value in enumerate(values)
        ]
    draw.line(points, fill="blue", width=2)

    if labels:
        draw.text((left - 10, bottom + 6), str(labels[0]), fill="black", font=font)
        draw.text(
            (right - 90, bottom + 6),
            str(labels[-1]),
            fill="black",
            font=font,
        )
    if points:
        last_x, last_y = points[-1]
        draw.ellipse([last_x - 5, last_y - 5, last_x + 5, last_y + 5], fill="red")

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
