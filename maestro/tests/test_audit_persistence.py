"""审计日志重启回灌与 actor 过滤 (DEF-1)。"""

from maestro.foundation.audit import AuditLog


def test_query_survives_restart_via_jsonl_rehydrate(tmp_path):
    f = tmp_path / "audit.jsonl"
    first = AuditLog(f)
    first.record("s1", "route", {"message": "排一下"}, None, {"intent": "planning"})
    first.record("system", "engine_wakeup:material_shortage_warning", {"wo_id": "WO-101"})
    first.record("s1", "confirm:dispatch_work_order", {"action_id": "abc"}, "requires_confirmation")

    reborn = AuditLog(f)  # 模拟重启
    entries = reborn.query(limit=100)
    assert [e.action for e in entries] == [
        "route", "engine_wakeup:material_shortage_warning", "confirm:dispatch_work_order"]
    assert entries[0].actor == "s1"
    assert entries[0].result == {"intent": "planning"}
    assert entries[0].timestamp <= entries[2].timestamp  # 时间戳来自文件原值


def test_rehydrate_skips_corrupt_lines(tmp_path):
    f = tmp_path / "audit.jsonl"
    AuditLog(f).record("s1", "route")
    with f.open("a", encoding="utf-8") as fh:
        fh.write("not-json\n{\"half\": \n")
    reborn = AuditLog(f)
    assert [e.action for e in reborn.query()] == ["route"]


def test_rehydrate_is_bounded(tmp_path):
    f = tmp_path / "audit.jsonl"
    log = AuditLog(f)
    for i in range(6):
        log.record("s1", f"act-{i}")
    reborn = AuditLog(f, rehydrate_max=3)
    assert [e.action for e in reborn.query()] == ["act-3", "act-4", "act-5"]


def test_query_actor_filter_applies_before_limit(tmp_path):
    log = AuditLog(None)
    log.record("s1", "route")
    for i in range(50):
        log.record("system", f"noise-{i}")
    # 旧实现先截 limit 再过滤会丢掉 s1 条目
    entries = log.query(limit=10, actor_in={"s1"})
    assert [e.action for e in entries] == ["route"]
