"""会话持久化测试: SessionStore 落盘 + ConversationMemory 重启回载 (agent 不失忆)。"""

from scheduling_platform.foundation.memory import ConversationMemory
from scheduling_platform.foundation.session_store import SessionStore


def test_store_roundtrip_and_auto_title(tmp_path):
    store = SessionStore(tmp_path)
    meta = store.create()
    store.append_message(meta.session_id, "user", "帮我重排注塑车间这批订单，交期优先")
    store.append_message(meta.session_id, "assistant", "已完成重排。")

    assert store.get(meta.session_id).message_count == 2
    # 自动标题取首条用户消息前 20 字
    assert store.get(meta.session_id).title.startswith("帮我重排注塑车间这批订单")
    msgs = store.get_messages(meta.session_id)
    assert [m["role"] for m in msgs] == ["user", "assistant"]


def test_memory_rehydrates_after_restart(tmp_path):
    # 第一段进程: 正常对话并设当前引擎
    store1 = SessionStore(tmp_path)
    meta = store1.create()
    memory1 = ConversationMemory(store1)
    memory1.append(meta.session_id, "user", "3号线缺料了，催一下")
    memory1.append(meta.session_id, "assistant", "已生成催料动作，待确认。")
    memory1.set_engine(meta.session_id, "scheduling")

    # 模拟重启: 全新 store + memory 实例，从磁盘回载
    store2 = SessionStore(tmp_path)
    memory2 = ConversationMemory(store2)
    state = memory2.get(meta.session_id)

    assert [m["content"] for m in state.history] == [
        "3号线缺料了，催一下",
        "已生成催料动作，待确认。",
    ]
    assert state.current_engine == "scheduling"
    # context 是进程内瞬态，重启后为空
    assert state.context == {}


def test_memory_without_store_still_works():
    memory = ConversationMemory()
    memory.append("s1", "user", "hi")
    memory.set_engine("s1", "query")
    assert memory.get("s1").history == [{"role": "user", "content": "hi"}]


def test_delete_removes_meta_and_messages(tmp_path):
    store = SessionStore(tmp_path)
    meta = store.create()
    store.append_message(meta.session_id, "user", "x")
    assert store.delete(meta.session_id) is True
    assert store.get(meta.session_id) is None
    assert store.get_messages(meta.session_id) == []
    assert store.delete(meta.session_id) is False
