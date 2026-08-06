"""关注列表测试。"""

from __future__ import annotations

from fx_tracker import watchlist


def test_add_remove_list(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(watchlist.config, "data_dir", str(tmp_path))

    assert watchlist.list_pairs(123) == []
    assert watchlist.add_pair(123, "btc", "usd") is True
    assert watchlist.add_pair(123, "BTC", "USD") is False
    assert watchlist.list_pairs(123) == [("BTC", "USD")]
    assert watchlist.remove_pair(123, "btc", "usd") is True
    assert watchlist.list_pairs(123) == []
