"""哈希工具单元测试。"""

from __future__ import annotations

from industry_intelligence.utils.hashing import content_hash, url_hash


def test_url_hash_prefix_and_deterministic() -> None:
    a = url_hash("https://example.com/a")
    b = url_hash("https://example.com/a")
    assert a.startswith("url_")
    assert a == b
    assert len(a) == 4 + 64


def test_url_hash_canonicalizes_input() -> None:
    assert url_hash("https://WWW.example.com/a#frag") == url_hash("https://example.com/a")


def test_content_hash_prefix() -> None:
    assert content_hash("充电桩").startswith("crc_")


def test_content_hash_whitespace_normalized() -> None:
    assert content_hash("  充电桩\n 建设  ") == content_hash("充电桩 建设")


def test_content_hash_distinguishes_content() -> None:
    assert content_hash("充电桩建设") != content_hash("充电站建设")
