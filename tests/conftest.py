"""Pytest 共享 fixtures。"""

from __future__ import annotations

from pathlib import Path

import pytest

from industry_intelligence.config.models import (
    CompanyEntity,
    TaskConfig,
    TopicEntities,
    TopicKeywords,
    TopicProfile,
    TopicScope,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"


@pytest.fixture
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def rss_fixture() -> Path:
    return FIXTURES_DIR / "rss" / "sample_feed.xml"


@pytest.fixture
def html_fixture() -> Path:
    return FIXTURES_DIR / "html" / "sample_page.html"


@pytest.fixture
def duplicate_html_fixture() -> Path:
    return FIXTURES_DIR / "html" / "duplicate_page.html"


@pytest.fixture
def sample_topic() -> TopicProfile:
    """直接构造的最小有效 Topic。"""
    return TopicProfile(
        id="t1",
        name="充电基础设施（测试）",
        version="1.0",
        scope=TopicScope(regions=["中国"], default_window_days=7),
        entities=TopicEntities(
            companies=[
                CompanyEntity(canonical_name="特来电", aliases=["特来电新能源"], priority=1),
                CompanyEntity(canonical_name="星星充电", aliases=[], priority=2),
            ]
        ),
        keywords=TopicKeywords(core=["充电桩", "充电基础设施"], events=["政策", "招标"]),
        metrics=["station_count"],
    )


@pytest.fixture
def sample_task() -> TaskConfig:
    """直接构造的最小有效 Task。"""
    return TaskConfig(id="tk1", topic_id="t1", enabled=True)


@pytest.fixture
def make_doc():
    """NormalizedDocument 工厂，可用关键字覆盖任意字段。"""
    from industry_intelligence.core.document import NormalizedDocument

    def _make(**overrides) -> NormalizedDocument:
        defaults: dict[str, object] = {
            "document_id": "d1",
            "canonical_url": "https://example.com/d1",
            "source_id": "rss:demo",
            "title": "测试标题",
            "content_text": "测试正文",
            "content_hash": "c1",
            "url_hash": "u1",
            "source_grade": "C",
            "topic_id": "t1",
        }
        defaults.update(overrides)
        return NormalizedDocument(**defaults)

    return _make
