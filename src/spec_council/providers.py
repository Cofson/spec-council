"""LLM providers. Plain HTTP via urllib, so the package has no runtime dependencies."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass


class ProviderError(RuntimeError):
    pass


@dataclass
class Provider:
    name: str
    model: str

    def complete(self, system: str, prompt: str) -> str:  # pragma: no cover - interface
        raise NotImplementedError


def _post_json(url: str, payload: dict, headers: dict, timeout: int = 120) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:500]
        raise ProviderError(f"HTTP {e.code} from {url}: {body}") from e
    except urllib.error.URLError as e:
        raise ProviderError(f"Could not reach {url}: {e.reason}") from e


def _key(env: str) -> str:
    value = os.environ.get(env)
    if not value:
        raise ProviderError(f"Set {env} to use this provider.")
    return value


class AnthropicProvider(Provider):
    def complete(self, system: str, prompt: str) -> str:
        data = _post_json(
            "https://api.anthropic.com/v1/messages",
            {
                "model": self.model,
                "max_tokens": 4096,
                "system": system,
                "messages": [{"role": "user", "content": prompt}],
            },
            {"x-api-key": _key("ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01"},
        )
        return "".join(b.get("text", "") for b in data.get("content", []))


class OpenAIProvider(Provider):
    def complete(self, system: str, prompt: str) -> str:
        data = _post_json(
            "https://api.openai.com/v1/chat/completions",
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            },
            {"Authorization": f"Bearer {_key('OPENAI_API_KEY')}"},
        )
        return data["choices"][0]["message"]["content"]


class GeminiProvider(Provider):
    def complete(self, system: str, prompt: str) -> str:
        key = _key("GEMINI_API_KEY")
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={key}"
        )
        data = _post_json(
            url,
            {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            },
            {},
        )
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts)


class MockProvider(Provider):
    """Offline provider for demos and tests. Deterministic, no network.

    Critics raise one issue per round and approve from round 3 on.
    The editor appends a short changelog entry to the spec.
    """

    def complete(self, system: str, prompt: str) -> str:
        round_no = _extract_round(prompt)
        if "You are the editor" in system:
            spec = prompt.split("<spec>", 1)[1].split("</spec>", 1)[0].strip()
            return f"{spec}\n\n<!-- revised in round {round_no} by mock editor -->"
        if round_no >= 3:
            return "VERDICT: APPROVE\n\nNo blocking issues left."
        return (
            "VERDICT: REVISE\n\n"
            f"- [round {round_no}] Error handling is not specified for the main flow.\n"
            f"- [round {round_no}] Acceptance criteria should be measurable."
        )


def _extract_round(prompt: str) -> int:
    marker = "Review round "
    if marker in prompt:
        tail = prompt.split(marker, 1)[1]
        digits = "".join(ch for ch in tail[:4] if ch.isdigit())
        if digits:
            return int(digits)
    return 1


PROVIDERS = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
    "mock": MockProvider,
}


def make_provider(name: str, model: str) -> Provider:
    try:
        cls = PROVIDERS[name]
    except KeyError:
        raise ProviderError(
            f"Unknown provider '{name}'. Use one of: {', '.join(sorted(PROVIDERS))}."
        ) from None
    return cls(name=name, model=model)
