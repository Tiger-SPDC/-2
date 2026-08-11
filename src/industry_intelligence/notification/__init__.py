"""通知层（Phase 4）：Server酱等可替换通知 Adapter。"""

from industry_intelligence.notification.adapter import (
    NotificationAdapter,
    NotificationResult,
)
from industry_intelligence.notification.serverchan import ServerChanAdapter

__all__ = [
    "NotificationAdapter",
    "NotificationResult",
    "ServerChanAdapter",
]
