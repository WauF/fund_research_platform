"""An LLMClient for any OpenAI-compatible chat completions endpoint, using only the stdlib.

Covers hosted APIs and local servers alike (e.g. vLLM or Ollama on the advisor's GPU), so the
provider decision does not change the code. Only evaluations/ create one: routine tests never call
a real model (pytest-socket blocks it).
"""

from __future__ import annotations

import json
import os
import urllib.request


class OpenAICompatibleClient:
    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 300) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> OpenAICompatibleClient:
        """LLM_BASE_URL (e.g. https://api.openai.com/v1), LLM_API_KEY, LLM_MODEL."""
        return cls(
            os.environ["LLM_BASE_URL"], os.environ.get("LLM_API_KEY", ""), os.environ["LLM_MODEL"]
        )

    def complete_json(self, system: str, user: str, schema: dict) -> str:
        body = {
            "model": self.model,
            "temperature": 0,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "portfolio_report", "schema": schema},
            },
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            reply = json.load(response)
        return reply["choices"][0]["message"]["content"]
