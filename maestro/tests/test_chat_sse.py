import json

from maestro.api.routes.chat import _sse, _sse_from_response
from maestro.orchestrator.schemas import ChatResponse


def test_sse_uses_real_newlines_and_a_blank_frame_boundary():
    frame = _sse("token", {"delta": "你好"})

    assert frame == f'event: token\ndata: {json.dumps({"delta": "你好"}, ensure_ascii=False)}\n\n'
    assert "\\n" not in frame


def _context_frame(frames: list[str]) -> dict:
    frame = next(f for f in frames if f.startswith("event: context"))
    return json.loads(frame.split("data: ", 1)[1])


async def _collect(resp: ChatResponse) -> list[str]:
    return [frame async for frame in _sse_from_response(resp)]


async def test_context_frame_marks_skill_runs_as_skill_engine():
    resp = ChatResponse(reply="ok", data={
        "steps": [{"tool": "run_skill_script"}], "stop_reason": "final",
        "skill_ids": ["ppt-generator"], "skill_names": ["PPT 生成"],
    })
    data = _context_frame(await _collect(resp))
    assert data["engine"] == "skill"
    assert data["payload"]["skill_ids"] == ["ppt-generator"]
    assert data["payload"]["skill_names"] == ["PPT 生成"]


async def test_context_frame_scheduling_unchanged_without_skill_ids():
    resp = ChatResponse(reply="ok", data={
        "steps": [{"tool": "query_orders"}], "stop_reason": "final",
    })
    data = _context_frame(await _collect(resp))
    assert data["engine"] == "scheduling"
    assert "skill_ids" not in data["payload"]
