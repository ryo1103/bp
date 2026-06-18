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
