"""LLM 客户端封装 (OpenAI 兼容接口)。

- base_url / api_key / model 全部来自配置，切换供应商 (OpenAI/DeepSeek/千问/vLLM)
  只改配置不改代码。
- `classify` 强制返回符合 Pydantic schema 的结构化结果；优先 JSON 模式，
  服务不支持时自动降级为 prompt 强约束 + JSON 提取。兼容差异在此层吸收。
- 所有失败统一抛 `LLMError`，业务侧据此降级 (如路由降级为 ambiguous 澄清)。
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, TypeVar

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

ToolExecutor = Callable[[str, dict], Awaitable[Any]]


@dataclass
class ToolCall:
    """模型在一步里请求调用的单个工具 (已解析参数)。"""

    id: str
    name: str
    arguments: dict


@dataclass
class AgentTurn:
    """ReAct 单步结果: 模型的文本 + 本步请求的工具调用。

    `assistant_message` 是 OpenAI 格式的 assistant 消息 (含 tool_calls)，
    调用方需把它原样追加进对话，再为每个 tool_call 追加 role=tool 的结果。
    """

    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    assistant_message: dict = field(default_factory=dict)


class LLMError(Exception):
    """LLM 不可用 / 调用失败 / 结构化输出解析失败。"""


class LLMClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        embed_base_url: str = "",
        embed_api_key: str = "",
        embed_model: str = "",
    ):
        self.model = model
        self.embed_model = embed_model
        self._client = None
        self._embed_client = None
        self._build_clients(base_url, api_key, embed_base_url, embed_api_key, embed_model)

    def _build_clients(
        self,
        base_url: str,
        api_key: str,
        embed_base_url: str,
        embed_api_key: str,
        embed_model: str,
    ) -> None:
        self._client = None
        self._embed_client = None
        if api_key:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        else:
            logger.warning("LLM_API_KEY 为空，LLM 功能不可用，业务侧将走降级路径")

        # Embedding 客户端: 仅当配置了 embed_model 时启用 (base_url/api_key 可独立或复用 LLM)
        if embed_model:
            key = embed_api_key or api_key
            url = embed_base_url or base_url
            if key:
                from openai import AsyncOpenAI

                self._embed_client = AsyncOpenAI(base_url=url, api_key=key)
            else:
                logger.warning("配置了 EMBED_MODEL 但无可用 api_key，嵌入路由不可用")

    def reconfigure(
        self,
        base_url: str,
        api_key: str,
        model: str,
        embed_base_url: str = "",
        embed_api_key: str = "",
        embed_model: str = "",
    ) -> None:
        """原地热更新连接参数 (设置弹框保存后由后端 PUT /models 或 /admin/reload-model 触发)。

        复用同一 LLMClient 实例: 已持有该实例的引擎 (调度/排产/查询)、工具注册表、
        嵌入客户端等引用无需重建，下次调用即用新连接。
        """
        self.model = model
        self.embed_model = embed_model
        self._build_clients(base_url, api_key, embed_base_url, embed_api_key, embed_model)

    @property
    def available(self) -> bool:
        return self._client is not None

    @property
    def embed_available(self) -> bool:
        return self._embed_client is not None

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """批量文本向量化 (OpenAI 兼容 /embeddings)。失败统一抛 LLMError。"""
        if not self.embed_available:
            raise LLMError("embedding 未配置 (EMBED_MODEL 为空或无 api_key)")
        try:
            resp = await self._embed_client.embeddings.create(model=self.embed_model, input=texts)
        except Exception as e:  # noqa: BLE001 — 网络/服务异常统一转 LLMError
            raise LLMError(f"embedding 调用失败: {e}") from e
        return [d.embedding for d in resp.data]

    # ── 通用调用 (含工具循环) ─────────────────────────────────

    async def complete(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_executor: ToolExecutor | None = None,
        max_tool_rounds: int = 5,
    ) -> str:
        """通用对话调用。

        传入 tools 时使用 OpenAI function-calling 机制：在本方法内完成
        「解析 tool_calls → 执行工具 → role=tool 回填 → 继续对话」的循环，
        直到模型给出最终文本。
        """
        if not self.available:
            raise LLMError("LLM 未配置 (LLM_API_KEY 为空)")
        msgs: list[dict] = [{"role": "system", "content": system}, *messages]
        for _ in range(max_tool_rounds):
            kwargs: dict = {"model": self.model, "messages": msgs}
            if tools:
                kwargs["tools"] = tools
            try:
                resp = await self._client.chat.completions.create(**kwargs)
            except Exception as e:  # noqa: BLE001 — 网络/服务异常统一转 LLMError
                raise LLMError(f"LLM 调用失败: {e}") from e
            msg = resp.choices[0].message
            if msg.tool_calls and tool_executor:
                msgs.append(
                    {
                        "role": "assistant",
                        "content": msg.content or "",
                        "tool_calls": [tc.model_dump() for tc in msg.tool_calls],
                    }
                )
                for tc in msg.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                        result = await tool_executor(tc.function.name, args)
                    except Exception as e:  # noqa: BLE001 — 工具失败回喂给模型
                        result = {"error": str(e)}
                    msgs.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(result, ensure_ascii=False, default=str),
                        }
                    )
                continue
            return msg.content or ""
        raise LLMError(f"工具调用循环超过 {max_tool_rounds} 轮未收敛")

    # ── ReAct 单步 (不在封装内执行工具，交调用方编排护栏) ─────

    async def chat_turn(
        self, system: str, messages: list[dict], tools: list[dict] | None = None
    ) -> AgentTurn:
        """ReAct 单步调用: 返回模型本步的文本与请求的 tool_calls，**不执行工具**。

        与 `complete` 的区别: 此处把工具调用的控制权交还给调用方 (调度引擎的
        agent_loop)，以便在 Act 与 Execute 之间插入前置断言 / 授权 / 审计两道护栏。
        """
        if not self.available:
            raise LLMError("LLM 未配置 (LLM_API_KEY 为空)")
        msgs: list[dict] = [{"role": "system", "content": system}, *messages]
        kwargs: dict = {"model": self.model, "messages": msgs}
        if tools:
            kwargs["tools"] = tools
        try:
            resp = await self._client.chat.completions.create(**kwargs)
        except Exception as e:  # noqa: BLE001 — 网络/服务异常统一转 LLMError
            raise LLMError(f"LLM 调用失败: {e}") from e
        msg = resp.choices[0].message
        raw_calls = msg.tool_calls or []
        calls: list[ToolCall] = []
        for tc in raw_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
        assistant_message: dict = {"role": "assistant", "content": msg.content or ""}
        if raw_calls:
            assistant_message["tool_calls"] = [tc.model_dump() for tc in raw_calls]
        return AgentTurn(
            text=msg.content or "", tool_calls=calls, assistant_message=assistant_message
        )

    # ── 结构化分类 ───────────────────────────────────────────

    async def classify(self, system: str, user_input: str, schema: type[T]) -> T:
        """强制返回符合 schema 的结构化结果；解析/校验失败重试一次 (回喂错误)。"""
        if not self.available:
            raise LLMError("LLM 未配置 (LLM_API_KEY 为空)")
        schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        sys_prompt = (
            f"{system}\n\n"
            "你必须只输出一个 JSON 对象，不要输出任何其它文字或代码块标记。\n"
            f"JSON 必须符合以下 JSON Schema:\n{schema_json}"
        )
        msgs: list[dict] = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_input},
        ]
        last_err: Exception | None = None
        for attempt in range(2):
            content = await self._chat_json(msgs)
            try:
                return schema.model_validate(_extract_json(content))
            except (ValidationError, ValueError) as e:
                last_err = e
                logger.warning("结构化输出解析失败 (attempt=%d): %s", attempt, e)
                msgs.append({"role": "assistant", "content": content})
                msgs.append(
                    {
                        "role": "user",
                        "content": f"上面的输出无法解析: {e}\n请重新输出，只输出符合 schema 的 JSON 对象。",
                    }
                )
        raise LLMError(f"结构化输出解析失败 (已重试): {last_err}")

    async def _chat_json(self, messages: list[dict]) -> str:
        """优先 JSON 模式；服务不支持 response_format 时自动降级为纯 prompt 约束。"""
        try:
            resp = await self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0,
                response_format={"type": "json_object"},
            )
        except Exception as e:  # noqa: BLE001
            logger.info("JSON 模式不可用，降级为 prompt 约束: %s", e)
            try:
                resp = await self._client.chat.completions.create(
                    model=self.model, messages=messages, temperature=0
                )
            except Exception as e2:  # noqa: BLE001
                raise LLMError(f"LLM 调用失败: {e2}") from e2
        return resp.choices[0].message.content or ""


def _extract_json(text: str) -> dict:
    """从文本中提取首个 JSON 对象 (容忍代码块/前后缀文字)。"""
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("输出中未找到 JSON 对象")
    return json.loads(text[start : end + 1])
