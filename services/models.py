from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal


VerificationStatus = Literal[
    "unverified",
    "partially_verified",
    "verified",
    "unverifiable",
    "contradicted",
]


STATUS_LABELS = {
    "unverified": "未验证",
    "partially_verified": "部分验证",
    "verified": "已验证",
    "unverifiable": "无法验证",
    "contradicted": "被反证",
}

RISK_LABELS = {
    "high": "高",
    "medium": "中",
    "low": "低",
}

RED_FLAG_STATUS_LABELS = {
    "open": "未解决",
    "partially_resolved": "部分解决",
    "resolved": "已解决",
    "contradicted": "被反证",
}

RED_FLAG_TYPE_LABELS = {
    "team": "团队/人员",
    "customer": "客户",
    "revenue": "收入/财务",
    "qualification": "资质/合规",
    "financing": "融资",
    "technology": "技术",
    "logic": "商业逻辑",
    "other": "其他",
}

INDUSTRY_NODE_LABELS = {
    "upstream": "上游",
    "midstream": "中游",
    "downstream": "下游",
    "service": "配套服务",
    "customer": "客户",
    "regulator": "监管/政策",
    "company": "公司位置",
}


class AppError(Exception):
    """User-facing application error."""


class LLMConfigError(AppError):
    """Raised when LLM configuration is missing."""


class LLMResponseError(AppError):
    """Raised when LLM response cannot be parsed or validated."""


@dataclass(frozen=True)
class ParsedDocument:
    text: str
    chunks: List[Dict[str, Any]]
    parser: str
    warning: str = ""
