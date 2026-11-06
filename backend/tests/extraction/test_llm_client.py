"""The OpenAI-compatible client builds the right request (urlopen is faked: no network)."""

import io
import json

from extraction import llm_client
from extraction.llm_client import OpenAICompatibleClient


def test_request_and_reply(monkeypatch):
    sent = {}

    def fake_urlopen(request, timeout):
        sent["url"], sent["timeout"] = request.full_url, timeout
        sent["auth"] = request.get_header("Authorization")
        sent["body"] = json.loads(request.data)
        reply = {"choices": [{"message": {"content": '{"ok": true}'}}]}
        return io.BytesIO(json.dumps(reply).encode())

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", fake_urlopen)
    client = OpenAICompatibleClient("http://gpu.local:8000/v1/", "key", "some-model", timeout=5)

    assert client.complete_json("sys", "user", {"type": "object"}) == '{"ok": true}'
    assert sent["url"] == "http://gpu.local:8000/v1/chat/completions"
    assert (sent["auth"], sent["timeout"]) == ("Bearer key", 5)
    body = sent["body"]
    assert (body["model"], body["temperature"]) == ("some-model", 0)
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    assert body["response_format"]["json_schema"]["schema"] == {"type": "object"}


def test_from_env(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_MODEL", "m")
    client = OpenAICompatibleClient.from_env()
    assert (client.base_url, client.api_key, client.model) == (
        "https://api.example.com/v1",
        "k",
        "m",
    )
