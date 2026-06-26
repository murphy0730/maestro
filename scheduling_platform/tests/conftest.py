"""测试公共夹具。LLM 调用全部 mock 掉 (FakeLLM)，不发真实网络请求。"""

from pathlib import Path

import pytest

from scheduling_platform.config import Settings
from scheduling_platform.foundation.audit import AuditLog
from scheduling_platform.foundation.authz import ActionGate, AuthZ, PendingActionStore
from scheduling_platform.foundation.integration.mock_adapter import MockAdapter
from scheduling_platform.foundation.llm import LLMError

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "mock"


# 确定性假嵌入的判别词表: 子串命中即该维度为 1，使余弦相似度对测试语句有意义。
_EMBED_VOCAB = [
    "排", "排产", "重排", "排程", "拖期",  # planning
    "下发", "催", "齐套", "缺料", "报警", "异常", "任务令",  # scheduling
    "查", "看", "库存", "状态", "多少", "几个", "列", "什么是", "BOM",  # query
]


class FakeLLM:
    """LLM 替身: classify 按 schema 类型返回预置结果，无预置则抛 LLMError
    (触发业务侧降级路径，与真实 LLM 失败行为一致)。embed=True 时启用确定性假嵌入。"""

    def __init__(
        self,
        classify_map: dict | None = None,
        complete_reply: str | None = None,
        embed: bool = False,
    ):
        self.classify_map = classify_map or {}
        self.complete_reply = complete_reply
        self._embed = embed

    @property
    def available(self) -> bool:
        return bool(self.classify_map or self.complete_reply)

    @property
    def embed_available(self) -> bool:
        return self._embed

    async def classify(self, system, user_input, schema):
        if schema in self.classify_map:
            value = self.classify_map[schema]
            return value(user_input) if callable(value) else value
        raise LLMError("FakeLLM: 无预置分类结果")

    async def complete(self, system, messages, tools=None, tool_executor=None, **kwargs):
        if self.complete_reply is None:
            raise LLMError("FakeLLM: 无预置回复")
        return self.complete_reply

    async def embed(self, texts):
        if not self._embed:
            raise LLMError("FakeLLM: 嵌入未启用")
        return [[1.0 if kw in t else 0.0 for kw in _EMBED_VOCAB] for t in texts]


@pytest.fixture
def settings() -> Settings:
    return Settings(
        llm_api_key="",
        mock_data_dir=DATA_DIR,
        audit_log_file=None,
        patrol_interval_seconds=0.1,
    )


@pytest.fixture
def adapter(settings) -> MockAdapter:
    return MockAdapter(settings.mock_data_dir)


@pytest.fixture
def audit() -> AuditLog:
    return AuditLog(file_path=None)


@pytest.fixture
def gate(audit) -> ActionGate:
    return ActionGate(AuthZ(), PendingActionStore(), audit)
