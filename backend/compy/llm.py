"""Provider-neutral LLM wrapper for revision-history wording."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

from .models import DiffItem


@dataclass
class LLMConfig:
    provider: str = "none"
    model: str = "gpt-4o-mini"
    api_key: str = ""
    base_url: str = ""
    timeout_seconds: int = 30

    @classmethod
    def from_env(cls) -> "LLMConfig":
        provider = os.getenv("COMPY_LLM_PROVIDER", "none").lower()
        return cls(
            provider=provider,
            model=os.getenv("COMPY_LLM_MODEL", "gpt-4o-mini"),
            api_key=os.getenv("OPENAI_API_KEY", "") if provider == "openai" else os.getenv("STGPT_API_KEY", ""),
            base_url=os.getenv("COMPY_LLM_BASE_URL", ""),
        )


class LLMClient:
    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or LLMConfig.from_env()

    def summarize_change(self, diff_item: DiffItem) -> str:
        if self.config.provider in {"", "none", "disabled"}:
            return ""
        if not self.config.api_key:
            return ""
        if self.config.provider == "openai":
            return self._chat_completion(
                self.config.base_url or "https://api.openai.com/v1/chat/completions",
                diff_item,
            )
        if self.config.provider == "stgpt":
            if not self.config.base_url:
                return ""
            return self._chat_completion(self.config.base_url, diff_item)
        return ""

    def _chat_completion(self, url: str, diff_item: DiffItem) -> str:
        payload = {
            "model": self.config.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You write concise technical-document revision history entries.",
                },
                {
                    "role": "user",
                    "content": (
                        f"Change type: {diff_item.change_type}\n"
                        f"Section: {diff_item.section_number} {diff_item.section_title}\n"
                        f"Old evidence: {diff_item.old_snippet}\n"
                        f"New evidence: {diff_item.new_snippet}\n"
                        "Return one concise revision-history sentence."
                    ),
                },
            ],
            "temperature": 0.2,
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            return ""
        choices = data.get("choices") or []
        if not choices:
            return ""
        return str(choices[0].get("message", {}).get("content", "")).strip()


class ChangeSummarizer:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or LLMClient()

    def summarize(self, diff_items: list[DiffItem]) -> list[DiffItem]:
        for item in diff_items:
            item.ai_summary = self.llm_client.summarize_change(item)
            if not item.ai_summary:
                item.ai_summary = self._fallback_summary(item)
        return diff_items

    @staticmethod
    def _fallback_summary(item: DiffItem) -> str:
        label = f"{item.section_number} {item.section_title}".strip() or "Document"
        if item.change_type == "added":
            return f"Added in {label}: {item.new_snippet}".strip()
        if item.change_type == "deleted":
            return f"Deleted from {label}: {item.old_snippet}".strip()
        return f"Changed in {label}: {item.old_snippet} -> {item.new_snippet}".strip()
