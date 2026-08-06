"""走势图画图测试。"""

from __future__ import annotations

from fx_tracker import chart


def test_render_chart_returns_png() -> None:
    png = chart.render_chart(
        "JPY/CNY 30d",
        ["08-01", "08-02", "08-03"],
        [0.0428, 0.0430, 0.0429],
    )

    assert png.startswith(b"\x89PNG")
    assert len(png) > 1000
