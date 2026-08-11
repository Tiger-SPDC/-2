"""指标观测：从文档抽取可量化指标。"""

from industry_intelligence.metrics.extractor import ObservationExtractor
from industry_intelligence.metrics.models import Observation, create_observation_id

__all__ = ["Observation", "ObservationExtractor", "create_observation_id"]
