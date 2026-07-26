from __future__ import annotations

from types import SimpleNamespace

import pytest

from maestro.foundation.llm import LLMClient


class RecordingCompletions:
    def __init__(self) -> None:
        self.kwargs: dict | None = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        message = SimpleNamespace(content="ok", tool_calls=[])
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def client_with_recorder(base_url: str, model: str) -> tuple[LLMClient, RecordingCompletions]:
    client = LLMClient(base_url, "", model)
    completions = RecordingCompletions()
    client._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return client, completions


@pytest.mark.asyncio
async def test_chat_turn_disables_thinking_for_official_deepseek_v4() -> None:
    client, completions = client_with_recorder(
        "https://api.deepseek.com", "deepseek-v4-pro"
    )

    await client.chat_turn("system", [{"role": "user", "content": "hello"}])

    assert completions.kwargs is not None
    assert completions.kwargs["extra_body"] == {"thinking": {"type": "disabled"}}


@pytest.mark.asyncio
async def test_chat_turn_does_not_send_deepseek_extension_to_other_providers() -> None:
    client, completions = client_with_recorder(
        "https://api.openai.com/v1", "gpt-5"
    )

    await client.chat_turn("system", [{"role": "user", "content": "hello"}])

    assert completions.kwargs is not None
    assert "extra_body" not in completions.kwargs
