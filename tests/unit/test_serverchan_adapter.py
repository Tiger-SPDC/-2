"""ServerChanAdapter 单元测试：成功、重试、失败不抛出（全部离线，mock requests）。"""

from __future__ import annotations

from unittest import mock

import requests

from industry_intelligence.notification.serverchan import ServerChanAdapter


def _resp(ok: bool, status_code: int = 200) -> mock.Mock:
    resp = mock.Mock()
    resp.ok = ok
    resp.status_code = status_code
    return resp


def test_send_success() -> None:
    with mock.patch("requests.post", return_value=_resp(True)) as post:
        adapter = ServerChanAdapter(sendkey="key-abc", retry=2)
        result = adapter.send("标题", "内容")
    assert result.success is True
    assert result.retry_count == 1
    assert result.error is None
    post.assert_called_once()
    url = post.call_args[0][0]
    assert url == "https://sctapi.ftqq.com/key-abc.send"


def test_send_retries_then_fails() -> None:
    with mock.patch("requests.post", side_effect=requests.ConnectionError("down")) as post:
        adapter = ServerChanAdapter(sendkey="key-abc", retry=2)
        result = adapter.send("标题", "内容")
    assert result.success is False
    assert result.retry_count == 3  # retry + 1 次尝试
    assert post.call_count == 3
    assert "down" in (result.error or "")


def test_send_http_error_retries() -> None:
    with mock.patch("requests.post", return_value=_resp(False, status_code=500)) as post:
        adapter = ServerChanAdapter(sendkey="key-abc", retry=1)
        result = adapter.send("标题", "内容")
    assert result.success is False
    assert post.call_count == 2
    assert "500" in (result.error or "")


def test_no_sendkey_returns_failure_without_request() -> None:
    with mock.patch("requests.post") as post:
        adapter = ServerChanAdapter(sendkey=None)
        result = adapter.send("标题", "内容")
    assert result.success is False
    assert "not configured" in (result.error or "")
    post.assert_not_called()


def test_send_does_not_raise() -> None:
    with mock.patch("requests.post", side_effect=requests.Timeout("slow")):
        adapter = ServerChanAdapter(sendkey="key", retry=0)
        result = adapter.send("标题", "内容")  # 不应抛出
    assert result.success is False
