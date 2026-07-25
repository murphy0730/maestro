"""Rolling conversation summarization for turns that fall out of the history window."""

from __future__ import annotations

from typing import Protocol

from maestro.foundation.llm import LLMClient

SUMMARY_KEY = "conversation-summary"

SUMMARY_SYSTEM_PROMPT = """你是一个对话压缩器。给定一段【已有摘要】和【本次新增对话】，输出更新后的、简洁且信息密集的完整摘要。
必须保留：用户的目标与意图；已做出的决策及其理由；关键实体与标识符（如编号、名称、日期、数量）；未完成的待办与开放问题；用户明确提出的约束或偏好；对后续连续性重要的工具结果。
必须丢弃：寒暄与重复表述、过长的原文逐字引用（改用自己的简述）、工具调用的过程性细节。
只输出更新后的摘要正文，不要任何前缀、不要 markdown 代码块、使用中文。"""


class SummaryStore(Protocol):
    """Persist one rolling summary per session plus the cursor it already covers."""

    def get_summary(self, session_id: str) -> tuple[str, int]: ...

    def set_summary(self, session_id: str, summary: str, summarized_until: int) -> None: ...


class HistorySummarizer(Protocol):
    @property
    def available(self) -> bool: ...

    async def summarize(self, prior_summary: str, turns: list[dict]) -> str: ...


def render_summary_input(prior_summary: str, turns: list[dict]) -> str:
    rendered = "\n".join(f"{turn['role']}: {turn['content']}" for turn in turns)
    return (
        "[已有摘要]\n"
        f"{prior_summary}\n\n"
        "[本次新增对话]\n"
        f"{rendered}\n\n"
        "请把【本次新增对话】合并进【已有摘要】，输出更新后的完整摘要。"
    )


class LLMHistorySummarizer:
    """Translate the existing LLM boundary into a summarization call, never a ReAct turn."""

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    @property
    def available(self) -> bool:
        return self._llm.available

    async def summarize(self, prior_summary: str, turns: list[dict]) -> str:
        text = await self._llm.complete(
            SUMMARY_SYSTEM_PROMPT,
            [{"role": "user", "content": render_summary_input(prior_summary, turns)}],
        )
        return text.strip()
