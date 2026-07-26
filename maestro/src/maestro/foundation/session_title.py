"""Generate short conversation titles from the first user question."""

import logging

from maestro.foundation.llm import LLMClient, LLMError

logger = logging.getLogger(__name__)

DEFAULT_SESSION_TITLES = frozenset({"新对话", "新任务"})
MAX_SESSION_TITLE_LENGTH = 15

_TITLE_PROMPT = """根据用户的第一个问题生成一个简洁、准确的会话标题。
标题不超过15个字符。只输出标题，不要加引号、书名号、句号或“标题：”前缀。"""


def _clean_title(value: str, fallback: str) -> str:
    title = " ".join(value.split()).strip()
    for prefix in ("标题：", "标题:"):
        if title.startswith(prefix):
            title = title[len(prefix):].strip()
    title = title.strip("《》「」『』【】[]“”\"'").strip()
    if not title:
        title = " ".join(fallback.split()).strip() or "新对话"
    return title[:MAX_SESSION_TITLE_LENGTH]


async def generate_session_title(llm: LLMClient, question: str) -> str:
    """Return a model-generated title, falling back safely when LLM is unavailable."""
    try:
        generated = await llm.complete(
            _TITLE_PROMPT,
            [{"role": "user", "content": question}],
        )
    except LLMError as error:
        logger.warning("会话标题生成失败，已使用首问降级: %s", error)
        generated = ""
    return _clean_title(generated, question)
