from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

import requests

from .models import LLMConfigError, LLMResponseError


def load_dotenv() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


class LLMClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None, model: str | None = None):
        load_dotenv()
        self.base_url = (base_url or os.getenv("LLM_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.api_key = api_key or os.getenv("LLM_API_KEY")
        self.model = model or os.getenv("LLM_MODEL") or "gpt-4o-mini"

    def require_configured(self) -> None:
        if not self.api_key:
            raise LLMConfigError("未配置 LLM_API_KEY。请在环境变量中配置 OpenAI-compatible API key 后再运行 AI 分析。")

    def chat_json(self, messages: List[Dict[str, str]], temperature: float = 0.2) -> Dict[str, Any]:
        self.require_configured()
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "response_format": {"type": "json_object"},
            },
            timeout=120,
        )
        if response.status_code >= 400:
            raise LLMResponseError(f"LLM 请求失败：{response.status_code} {response.text[:500]}")
        payload = response.json()
        content = payload["choices"][0]["message"]["content"]
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMResponseError(f"LLM 未返回合法 JSON：{content[:500]}") from exc
