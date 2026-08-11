"""分析层数据模型：Claim / ClaimEvidence / IndexScore / TrendIndicator / AnalysisResult。

Phase 3 的产出是结构化分析结果（可追溯的 Claim + Evidence），不是格式化报告。
claim_type 与 evidence_role 的取值与 SQLite CHECK 约束保持一致（小写）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256

# ---------------------------------------------------------------------------
# 常量（替代魔法字符串）
# ---------------------------------------------------------------------------

# 分析维度
ANALYSIS_COMPETITOR = "competitor"
ANALYSIS_MARKET = "market"
ANALYSIS_TECHNOLOGY = "technology"
ANALYSIS_RISK = "risk"
ANALYSIS_TYPES = frozenset(
    {ANALYSIS_COMPETITOR, ANALYSIS_MARKET, ANALYSIS_TECHNOLOGY, ANALYSIS_RISK}
)

# Claim 类型（LLM 结构化输出的 enum 取值）
CLAIM_TYPE_FACT = "fact"
CLAIM_TYPE_INFERENCE = "inference"
CLAIM_TYPE_FORECAST = "forecast"
CLAIM_TYPE_UNKNOWN = "unknown"
CLAIM_TYPES = frozenset(
    {CLAIM_TYPE_FACT, CLAIM_TYPE_INFERENCE, CLAIM_TYPE_FORECAST, CLAIM_TYPE_UNKNOWN}
)

# 证据角色
EVIDENCE_ROLE_PRIMARY = "primary_source"
EVIDENCE_ROLE_CROSS_VALIDATION = "cross_validation"
EVIDENCE_ROLE_CONTEXT = "context"
EVIDENCE_ROLES = frozenset(
    {EVIDENCE_ROLE_PRIMARY, EVIDENCE_ROLE_CROSS_VALIDATION, EVIDENCE_ROLE_CONTEXT}
)

# 内部指数名称（确定性计算，非官方统计）
INDEX_CAI = "competitive_activity_index"  # 竞争活动度
INDEX_MMI = "market_momentum_index"  # 市场动量
INDEX_THI = "technology_heat_index"  # 技术热度
INDEX_RSI = "risk_signal_index"  # 风险信号
INDEX_EVIDENCE_COVERAGE = "evidence_coverage"  # 关键 Claim 证据覆盖率

# 7 种历史趋势指标
TREND_EVENT_VELOCITY = "event_velocity"
TREND_SHARE_OF_VOICE = "share_of_voice"
TREND_MAJOR_PROJECT_GROWTH = "major_project_growth"
TREND_TECH_HEAT_CHANGE = "technology_heat_change"
TREND_PRICE_CHANGE = "price_change"
TREND_CHANNEL_CHANGE = "channel_change"
TREND_NEGATIVE_RISK_CHANGE = "negative_risk_change"
TREND_INDICATORS = frozenset(
    {
        TREND_EVENT_VELOCITY,
        TREND_SHARE_OF_VOICE,
        TREND_MAJOR_PROJECT_GROWTH,
        TREND_TECH_HEAT_CHANGE,
        TREND_PRICE_CHANGE,
        TREND_CHANNEL_CHANGE,
        TREND_NEGATIVE_RISK_CHANGE,
    }
)


def make_claim_id(claim_text: str, analysis_type: str, run_id: str) -> str:
    """确定性 Claim ID：sha256(claim_text|analysis_type|run_id)[:16]。

    相同输入得到相同 ID，保证分析结果幂等、可去重。
    """
    payload = f"{claim_text}|{analysis_type}|{run_id}"
    return sha256(payload.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class Claim:
    """一条分析结论，必须能链接到至少一条 Evidence。"""

    claim_id: str
    claim_text: str
    claim_type: str
    confidence: float
    entity_id: str | None
    analysis_type: str
    topic_id: str
    run_id: str

    def __post_init__(self) -> None:
        if self.claim_type not in CLAIM_TYPES:
            raise ValueError(f"invalid claim_type: {self.claim_type!r}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0,1]: {self.confidence!r}")


@dataclass
class ClaimEvidence:
    """Claim 与事实来源（文档或观测）之间的链接。"""

    claim_id: str
    document_id: str | None = None
    observation_id: str | None = None
    evidence_role: str = EVIDENCE_ROLE_PRIMARY

    def __post_init__(self) -> None:
        if self.document_id is None and self.observation_id is None:
            raise ValueError("ClaimEvidence requires document_id or observation_id")
        if self.evidence_role not in EVIDENCE_ROLES:
            raise ValueError(f"invalid evidence_role: {self.evidence_role!r}")


@dataclass
class IndexScore:
    """内部指数得分（确定性计算，0-100；components 记录加权因子明细）。"""

    index_name: str
    entity_id: str | None
    score: float
    period_start: str
    period_end: str
    components: dict[str, float] = field(default_factory=dict)


@dataclass
class TrendIndicator:
    """单一趋势指标：三点比较（current / previous / 4 周均值基准）。

    baseline_avg 为 4 周基准窗口的平均水平，作为当前 vs 上周之外的长周期参照；
    entity_id 用于 share_of_voice 这类按实体拆分的指标（其余为 None）。
    """

    indicator_name: str
    current_value: float
    previous_value: float
    delta: float = 0.0
    delta_pct: float = 0.0
    window_weeks: int = 4
    baseline_avg: float = 0.0
    entity_id: str | None = None


@dataclass
class AnalysisResult:
    """单个分析维度（Competitor/Market/Technology/Risk）的输出汇总。"""

    analysis_type: str
    period_start: str
    period_end: str
    claims: list[Claim] = field(default_factory=list)
    evidences: list[ClaimEvidence] = field(default_factory=list)
    indices: list[IndexScore] = field(default_factory=list)
    trends: list[TrendIndicator] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
