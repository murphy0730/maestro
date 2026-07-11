import json

from maestro.api.routes.chat import _sse


def test_sse_uses_real_newlines_and_a_blank_frame_boundary():
    frame = _sse("token", {"delta": "你好"})

    assert frame == f'event: token\ndata: {json.dumps({"delta": "你好"}, ensure_ascii=False)}\n\n'
    assert "\\n" not in frame
