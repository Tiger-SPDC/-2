"""Observation 抽取器单元测试。"""

from __future__ import annotations

from unittest import mock

import pytest

from industry_intelligence.llm.provider import LLMError, LLMProvider
from industry_intelligence.metrics import ObservationExtractor, create_observation_id


@pytest.fixture
def mock_provider():
    provider = mock.Mock(spec=LLMProvider)
    provider.generate_structured.return_value = {"observations": []}
    return provider


def _one_obs(
    metric_id: str = "station_count",
    entity_id: str = "特来电",
    value: float = 100.0,
    confidence: float = 0.9,
) -> dict[str, object]:
    return {
        "metric_id": metric_id,
        "entity_id": entity_id,
        "value": value,
        "unit": "座",
        "confidence": confidence,
        "evidence_text": "累计建设100座充电站",
    }


def test_extract_single(mock_provider, make_doc) -> None:
    mock_provider.generate_structured.return_value = {"observations": [_one_obs()]}
    extractor = ObservationExtractor(mock_provider)
    obs = extractor.extract(make_doc(document_id="d1"), ["station_count"], ["特来电"])
    assert len(obs) == 1
    assert obs[0].metric_id == "station_count"
    assert obs[0].entity_id == "特来电"
    assert obs[0].value == 100.0
    assert obs[0].unit == "座"
    assert obs[0].document_id == "d1"


def test_extract_multiple(mock_provider, make_doc) -> None:
    mock_provider.generate_structured.return_value = {
        "observations": [
            _one_obs(),
            _one_obs(metric_id="charger_count", value=200.0),
        ]
    }
    obs = ObservationExtractor(mock_provider).extract(
        make_doc(), ["station_count", "charger_count"], ["特来电"]
    )
    assert len(obs) == 2


def test_filters_low_confidence(mock_provider, make_doc) -> None:
    mock_provider.generate_structured.return_value = {
        "observations": [
            _one_obs(value=100.0, confidence=0.2),
            _one_obs(value=200.0, confidence=0.8),
        ]
    }
    obs = ObservationExtractor(mock_provider).extract(
        make_doc(), ["station_count"], ["特来电"]
    )
    assert len(obs) == 1
    assert obs[0].value == 200.0


def test_empty_result(mock_provider, make_doc) -> None:
    obs = ObservationExtractor(mock_provider).extract(
        make_doc(), ["station_count"], ["特来电"]
    )
    assert obs == []


def test_empty_doc_shortcuts_without_llm(mock_provider, make_doc) -> None:
    extractor = ObservationExtractor(mock_provider)
    doc = make_doc(title="", content_text="")
    assert extractor.extract(doc, ["station_count"], ["特来电"]) == []
    mock_provider.generate_structured.assert_not_called()


def test_empty_entities_shortcuts(mock_provider, make_doc) -> None:
    extractor = ObservationExtractor(mock_provider)
    assert extractor.extract(make_doc(), ["station_count"], []) == []
    mock_provider.generate_structured.assert_not_called()


def test_llm_failure_returns_empty(mock_provider, make_doc) -> None:
    mock_provider.generate_structured.side_effect = LLMError("boom")
    obs = ObservationExtractor(mock_provider).extract(
        make_doc(), ["station_count"], ["特来电"]
    )
    assert obs == []


def test_non_object_field_skipped(mock_provider, make_doc) -> None:
    mock_provider.generate_structured.return_value = {
        "observations": [_one_obs(), {"metric_id": "x"}]
    }
    obs = ObservationExtractor(mock_provider).extract(
        make_doc(), ["station_count"], ["特来电"]
    )
    assert len(obs) == 1


def test_deterministic_observation_id() -> None:
    assert create_observation_id("d1", "station_count", "特来电", 100.0) == create_observation_id(
        "d1", "station_count", "特来电", 100.0
    )
    assert create_observation_id("d1", "station_count", "特来电", 100.0) != create_observation_id(
        "d1", "station_count", "特来电", 200.0
    )


def test_extract_uses_metric_enum_in_schema(mock_provider, make_doc) -> None:
    extractor = ObservationExtractor(mock_provider)
    extractor.extract(make_doc(), ["station_count", "charger_count"], ["特来电"])
    schema = mock_provider.generate_structured.call_args.args[1]
    item = schema["properties"]["observations"]["items"]
    assert item["properties"]["metric_id"]["enum"] == ["station_count", "charger_count"]
