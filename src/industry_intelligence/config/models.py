"""配置数据模型：System / Topic / Task 的类型化 dataclass。

这些模型是配置文件的 Schema，行业知识全部来自 YAML，核心代码不硬编码。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CollectionConfig:
    """采集参数（config/system.yaml -> collection）。"""

    max_concurrency: int = 5
    request_timeout_seconds: int = 20
    retries: int = 2
    user_agent: str = "industry-intelligence-agent"
    polite_delay_seconds: float = 1.5


@dataclass
class StorageConfig:
    """存储参数（config/system.yaml -> storage）。"""

    persistent_format: str = "jsonl"
    save_raw_html: bool = False
    save_text_snapshot: bool = True
    # 推送内容日志（每次微信推送尝试追加一条 JSONL 记录）
    push_log_path: str = "data/push_log.jsonl"


@dataclass
class QualityConfig:
    """质量门槛（config/system.yaml -> quality）。"""

    require_evidence_for_key_claim: bool = True
    reject_untraceable_numbers: bool = True


@dataclass
class LLMConfig:
    """LLM 接入参数（config/system.yaml -> llm）。"""

    provider: str = "deepseek"
    model: str = "deepseek-chat"
    api_key_env: str = "DEEPSEEK_API_KEY"
    base_url: str = "https://api.deepseek.com/v1"
    temperature: float = 0.1
    max_tokens: int = 4096


@dataclass
class AnalysisConfig:
    """竞争情报分析参数（config/system.yaml -> analysis）。

    enabled_dimensions：启用维度（competitor/market/technology/risk）。
    comparison_windows：历史比较窗口（周），如 [1, 4, 12, 52]。
    confidence_threshold：关键 Claim 的置信度门槛。
    """

    enabled_dimensions: list[str] = field(
        default_factory=lambda: ["competitor", "market", "technology", "risk"]
    )
    comparison_windows: list[int] = field(default_factory=lambda: [1, 4, 12, 52])
    confidence_threshold: float = 0.5


@dataclass
class ReportConfig:
    """报告生成开关（config/system.yaml -> report，Phase 4 启用）。

    markdown / excel / wechat_digest：三种报告格式开关。
    """

    markdown: bool = True
    excel: bool = True
    wechat_digest: bool = True


@dataclass
class ReviewConfig:
    """质量审查参数（config/system.yaml -> review，Phase 4 启用）。

    enabled：是否启用 Review Agent（7 项检查）。
    """

    enabled: bool = True


@dataclass
class NotificationConfig:
    """通知推送参数（config/system.yaml -> notification，Phase 4 启用）。

    serverchan_key_env：Server酱 SendKey 所在的环境变量名（Secret 不落库）。
    retry：推送失败重试次数；timeout_seconds：单次请求超时。
    """

    serverchan_key_env: str = "SERVERCHAN_KEY"
    retry: int = 2
    timeout_seconds: int = 10


@dataclass
class WebSearchEngineConfig:
    """网页搜索引擎配置（config/sources/search.yaml -> websearch.engines）。

    只含引擎参数，行业关键词一律来自 Topic/Task 配置。
    """

    id: str
    base_urls: list[str]
    params: dict[str, str] = field(default_factory=dict)
    max_results: int = 20
    delay_seconds: float | None = None
    user_agent: str | None = None
    enabled: bool = True


@dataclass
class WebSearchConfig:
    """网页搜索适配器配置段（config/sources/search.yaml -> websearch）。

    enabled=false 或引擎列表为空时回退 RSS 基线。
    """

    enabled: bool = False
    engines: list[WebSearchEngineConfig] = field(default_factory=list)


@dataclass
class SystemConfig:
    """系统级配置。"""

    timezone: str = "Asia/Shanghai"
    default_language: str = "zh-CN"
    collection: CollectionConfig = field(default_factory=CollectionConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    quality: QualityConfig = field(default_factory=QualityConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    report: ReportConfig = field(default_factory=ReportConfig)
    review: ReviewConfig = field(default_factory=ReviewConfig)
    notification: NotificationConfig = field(default_factory=NotificationConfig)


@dataclass
class CompanyEntity:
    """企业/品牌实体，含别名。"""

    canonical_name: str
    aliases: list[str] = field(default_factory=list)
    priority: int = 1


@dataclass
class TopicScope:
    """主题范围。"""

    regions: list[str] = field(default_factory=list)
    default_window_days: int = 7


@dataclass
class TopicEntities:
    """主题内的实体集合。"""

    companies: list[CompanyEntity] = field(default_factory=list)


@dataclass
class TopicKeywords:
    """主题关键词分组。"""

    core: list[str] = field(default_factory=list)
    products: list[str] = field(default_factory=list)
    market: list[str] = field(default_factory=list)
    technology: list[str] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)


@dataclass
class TopicProfile:
    """行业长期知识包（config/topics/*.yaml）。"""

    id: str
    name: str
    version: str
    scope: TopicScope = field(default_factory=TopicScope)
    entities: TopicEntities = field(default_factory=TopicEntities)
    keywords: TopicKeywords = field(default_factory=TopicKeywords)
    metrics: list[str] = field(default_factory=list)
    # 权威官方站点域名（用于 site: 限定检索；行业不同则列不同）
    official_domains: list[str] = field(default_factory=list)


@dataclass
class TaskWindow:
    """任务时间窗口。"""

    type: str = "rolling"
    days: int = 7


@dataclass
class TaskOverrides:
    """本次运行覆盖项；None 表示不覆盖，取 Topic 默认值。"""

    regions: list[str] | None = None
    companies: list[str] | None = None
    focus: list[str] | None = None


@dataclass
class TaskOutput:
    """任务输出参数。"""

    depth: str = "standard"
    notify: bool = True


@dataclass
class TaskConfig:
    """具体运行任务（config/tasks/*.yaml）。"""

    id: str
    topic_id: str
    enabled: bool = True
    window: TaskWindow = field(default_factory=TaskWindow)
    overrides: TaskOverrides | None = None
    output: TaskOutput = field(default_factory=TaskOutput)
