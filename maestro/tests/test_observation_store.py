"""方案2 验收: 大观察离线暂存 + ref 句柄 + 分页读取。

覆盖 ObservationStore 的 put/get/淘汰, 以及 AgentLoop 超限观察离线 + read_observation 取回。
"""

import json

from conftest import FakeLLM

from maestro.engines.scheduling.agent_loop import AgentLoop
from maestro.foundation.observation_store import ObservationStore
from maestro.foundation.tools.registry import ToolRegistry


# ── ObservationStore 单元 ───────────────────────────────────


def test_put_returns_bounded_handle():
    store = ObservationStore()
    rows = [{"order_id": f"O-{i}", "status": "open", "qty": i} for i in range(500)]
    handle = store.put(rows)
    assert handle["observation_ref"] == "obs-1"
    assert handle["kind"] == "list"
    assert handle["total"] == 500
    assert handle["item_keys"] == ["order_id", "status", "qty"]
    assert len(handle["preview"]) == 3  # 预览有界
    # 句柄本身远小于原始体量
    assert len(json.dumps(handle, ensure_ascii=False).encode()) < 4096


def test_get_list_pagination():
    store = ObservationStore()
    rows = [{"i": i} for i in range(50)]
    ref = store.put(rows)["observation_ref"]
    page = store.get(ref, offset=10, limit=5)
    assert page["items"] == [{"i": i} for i in range(10, 15)]
    assert page["total"] == 50 and page["has_more"] is True
    last = store.get(ref, offset=45, limit=20)
    assert last["items"] == [{"i": i} for i in range(45, 50)]
    assert last["has_more"] is False


def test_get_dict_by_keys():
    store = ObservationStore()
    ref = store.put({"a": 1, "b": 2, "c": 3})["observation_ref"]
    assert store.get(ref, keys=["a", "c"]) == {
        "observation_ref": ref, "kind": "dict", "keys": {"a": 1, "c": 3}
    }
    # 不传 keys → 顶层键 + 预览
    view = store.get(ref)
    assert view["item_keys"] == ["a", "b", "c"]


def test_get_missing_ref_errors():
    assert "error" in ObservationStore().get("obs-999")


def test_fifo_eviction():
    store = ObservationStore(cap=2)
    r1 = store.put([1])["observation_ref"]
    store.put([2])
    store.put([3])  # 触发淘汰最旧 (r1)
    assert "error" in store.get(r1)
    assert "error" not in store.get("obs-3")


# ── AgentLoop 集成: 离线 + read_observation 取回 ───────────


def _loop(llm, tools, gate, audit, allowed, store):
    return AgentLoop(
        llm, tools, gate.pending, audit, "", allowed, 8,
        observation_max_bytes=1024, observations=store,
    )


async def test_agent_offloads_large_observation_and_reads_back(audit, gate):
    """大 list 观察 → step.observation 为 ref 句柄 + 回喂有界; 模型再 read_observation 取回分页。"""
    store = ObservationStore()
    big = [{"order_id": f"O-{i}", "note": "x" * 50} for i in range(200)]

    async def big_list():
        return big

    async def read_observation(ref: str, offset: int = 0, limit: int = 20, keys=None):
        return store.get(ref, offset=offset, limit=limit, keys=keys)

    tools = ToolRegistry()
    tools.register("big_list", "大列表", {"type": "object", "properties": {}}, big_list, kind="read")
    tools.register(
        "read_observation", "分页取回",
        {"type": "object", "properties": {"ref": {"type": "string"}, "offset": {"type": "integer"},
                                          "limit": {"type": "integer"}}, "required": ["ref"]},
        read_observation, kind="read",
    )
    llm = FakeLLM(chat_script=[
        [("big_list", {})],
        [("read_observation", {"ref": "obs-1", "offset": 0, "limit": 5})],
        "已取回前 5 条。",
    ])
    captured: list = []
    orig = llm.chat_turn

    async def spy(system, messages, tools=None):
        captured.append([dict(m) for m in messages])
        return await orig(system, messages, tools=tools)

    llm.chat_turn = spy  # type: ignore[method-assign]
    result = await _loop(llm, tools, gate, audit, ["big_list", "read_observation"], store).run("查")

    # step0: 离线句柄 (非有损截断)
    h = result.steps[0].observation
    assert h["observation_ref"] == "obs-1" and h["kind"] == "list" and h["total"] == 200
    assert "truncated" not in h  # 不是旧的有损截断
    # 回喂 LLM 的 tool 消息有界 (句柄, 非 10KB 原文)
    tool_msg = next(m for m in captured[1] if m["role"] == "tool")
    assert len(tool_msg["content"].encode()) < 2048
    # step1: read_observation 取回了对应分页
    page = result.steps[1].observation
    assert len(page["items"]) == 5 and page["items"][0]["order_id"] == "O-0"
    assert result.answer == "已取回前 5 条。"


async def test_agent_small_observation_untouched_with_store(audit, gate):
    """未超限观察即使配了 store 也原样保留 (零行为变更)。"""
    store = ObservationStore()

    async def small():
        return {"status": "ok"}

    tools = ToolRegistry()
    tools.register("small", "小", {"type": "object", "properties": {}}, small, kind="read")
    llm = FakeLLM(chat_script=[[("small", {})], "结论"])
    result = await _loop(llm, tools, gate, audit, ["small"], store).run("t")
    assert result.steps[0].observation == {"status": "ok"}
