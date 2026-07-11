"""测试公共夹具。LLM 调用全部 mock 掉 (FakeLLM)，不发真实网络请求。"""

import json
import os
from pathlib import Path

import pytest

from maestro.config import Settings
from maestro.foundation.audit import AuditLog
from maestro.foundation.authz import ActionGate, AuthZ, PendingActionStore
from maestro.foundation.integration.mock_adapter import MockAdapter
from maestro.foundation.llm import AgentTurn, LLMError, ToolCall

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "mock"


@pytest.fixture(autouse=True, scope="session")
def _isolate_runtime_data(tmp_path_factory):
    """把运行时数据根 (sessions/chroma/skills/…) 指向临时目录,避免测试写入真实
    ~/.maestro；同时使 settings.json 源指向不存在的临时文件,不读真实用户模型配置。"""
    prev = os.environ.get("MAESTRO_DATA_DIR")
    os.environ["MAESTRO_DATA_DIR"] = str(tmp_path_factory.mktemp("maestro_runtime"))
    previous_token = os.environ.get("PRIVILEGED_API_TOKEN")
    os.environ["PRIVILEGED_API_TOKEN"] = "test-privileged-token"
    yield
    if prev is None:
        os.environ.pop("MAESTRO_DATA_DIR", None)
    else:
        os.environ["MAESTRO_DATA_DIR"] = prev
    if previous_token is None:
        os.environ.pop("PRIVILEGED_API_TOKEN", None)
    else:
        os.environ["PRIVILEGED_API_TOKEN"] = previous_token


# 确定性假嵌入的判别词表: 子串命中即该维度为 1，使余弦相似度对测试语句有意义。
_EMBED_VOCAB = [
    "排", "排产", "重排", "排程", "拖期",  # planning
    "下发", "催", "齐套", "缺料", "报警", "异常", "任务令",  # scheduling
    "查", "看", "库存", "状态", "多少", "几个", "列", "什么是", "BOM",  # query
    "产能", "报告", "日报", "瓶颈",  # skill
]


class FakeLLM:
    """LLM 替身: classify 按 schema 类型返回预置结果，无预置则抛 LLMError
    (触发业务侧降级路径，与真实 LLM 失败行为一致)。embed=True 时启用确定性假嵌入。"""

    def __init__(
        self,
        classify_map: dict | None = None,
        complete_reply: str | None = None,
        embed: bool = False,
        chat_script: list | None = None,
    ):
        self.classify_map = classify_map or {}
        self.complete_reply = complete_reply
        self._embed = embed
        # chat_script: ReAct 单步脚本列表。每项为:
        #   - str        → 最终答复 (无工具调用)
        #   - [(name, args), ...] → 本步请求的工具调用
        self.chat_script = list(chat_script or [])
        self._chat_idx = 0

    @property
    def available(self) -> bool:
        return bool(self.classify_map or self.complete_reply or self.chat_script)

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

    async def chat_turn(self, system, messages, tools=None) -> AgentTurn:
        if self._chat_idx >= len(self.chat_script):
            text = "已完成处理。"
            return AgentTurn(text=text, assistant_message={"role": "assistant", "content": text})
        item = self.chat_script[self._chat_idx]
        self._chat_idx += 1
        if isinstance(item, str):
            return AgentTurn(text=item, assistant_message={"role": "assistant", "content": item})
        calls, raw = [], []
        for j, (name, args) in enumerate(item):
            cid = f"call_{self._chat_idx}_{j}"
            calls.append(ToolCall(id=cid, name=name, arguments=args))
            raw.append(
                {
                    "id": cid,
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(args)},
                }
            )
        return AgentTurn(
            text="",
            tool_calls=calls,
            assistant_message={"role": "assistant", "content": "", "tool_calls": raw},
        )

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
        pending_actions_db=None,
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
