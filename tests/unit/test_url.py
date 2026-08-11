"""URL 规范化单元测试。"""

from __future__ import annotations

from industry_intelligence.utils.url import canonicalize_url


def test_lowercase_host_and_strip_www() -> None:
    assert canonicalize_url("https://WWW.Example.COM/a") == "https://example.com/a"


def test_remove_fragment() -> None:
    assert canonicalize_url("https://example.com/a#section") == "https://example.com/a"


def test_sort_and_filter_query_params() -> None:
    url = "https://example.com/a?utm_source=x&b=2&a=1&fbclid=abc&c=3"
    assert canonicalize_url(url) == "https://example.com/a?a=1&b=2&c=3"


def test_strip_trailing_slash() -> None:
    assert canonicalize_url("https://example.com/a/") == "https://example.com/a"


def test_keep_port() -> None:
    assert canonicalize_url("https://example.com:8443/a") == "https://example.com:8443/a"


def test_file_uri_safe() -> None:
    assert canonicalize_url("file:///D:/path/page.html").startswith("file:///")
