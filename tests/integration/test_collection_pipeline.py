"""端到端整合测试：配置 → 搜索计划 → RSS 采集 → 标准化 → 去重 → JSONL 持久化。

全部使用 file:// fixture，不走网络。
"""

from __future__ import annotations

from pathlib import Path

from industry_intelligence.collectors import SearchPlanner
from industry_intelligence.config.loader import load_task, load_topic, resolve_task
from industry_intelligence.normalization import Deduplicator
from industry_intelligence.sources import RSSAdapter
from industry_intelligence.storage import JSONLStore


def _run_pipeline(
    rss_fixture: Path,
    store: JSONLStore,
    dedup: Deduplicator | None = None,
) -> tuple[int, int]:
    """跑一遍 RSS 采集链路，返回 (新文档数, 重复文档数)。

    dedup 复用同一实例时模拟同一次运行内重复出现同一内容。
    """
    adapter = RSSAdapter({"test": rss_fixture.as_uri()})
    dedup = dedup if dedup is not None else Deduplicator()
    new_count = 0
    dup_count = 0
    for item in adapter.discover(queries=[], context={}):
        raw = adapter.fetch(item)
        parsed = adapter.parse(raw, item)
        doc = adapter.normalize(parsed, topic_id="charging_pile")
        if dedup.register(doc):
            store.append(doc)
            new_count += 1
        else:
            dup_count += 1
    return new_count, dup_count


def test_full_pipeline_then_dedup_on_second_run(
    rss_fixture: Path, tmp_path: Path
) -> None:
    store = JSONLStore(tmp_path / "collection.jsonl")
    dedup = Deduplicator()

    # 第一次：5 条 RSS 全部为新文档
    new1, dup1 = _run_pipeline(rss_fixture, store, dedup)
    assert new1 == 5
    assert dup1 == 0
    assert store.count() == 5

    # 同一去重实例再跑一遍：全部命中 Layer 1 去重，0 新增、0 重复写入
    new2, dup2 = _run_pipeline(rss_fixture, store, dedup)
    assert new2 == 0
    assert dup2 == 5
    assert store.count() == 5


def test_planner_to_adapter_linkage(fixtures_dir: Path, tmp_path: Path) -> None:
    """planner 生成的查询计划可被 RSS 适配器消费。"""
    topic = load_topic("valid_charging_pile", config_dir=fixtures_dir)
    task = load_task("valid_weekly", config_dir=fixtures_dir)
    resolved = resolve_task(task, topic)
    plans = SearchPlanner().generate_plans(topic, resolved)
    assert plans

    adapter = RSSAdapter({"test": (fixtures_dir / "rss" / "sample_feed.xml").as_uri()})
    items = adapter.discover(plans, context={})
    assert len(items) == 5

    store = JSONLStore(tmp_path / "pipeline.jsonl")
    assert store.count() == 0
