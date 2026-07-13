from maestro.api.routes.chat import ChatAttachment, ChatStreamRequest, _message_with_attachments


def test_stream_request_accepts_skill_and_attachment_together():
    request = ChatStreamRequest.model_validate(
        {
            "message": "分析附件",
            "skill_ids": ["capacity-report"],
            "attachments": [
                {
                    "name": "orders.csv",
                    "content_type": "text/csv",
                    "content": "id\nWO-1",
                    "size": 7,
                }
            ],
        }
    )

    assert request.skill_ids == ["capacity-report"]
    assert request.attachments[0].name == "orders.csv"


def test_attachment_content_is_added_to_engine_message():
    message = _message_with_attachments(
        "分析附件",
        [
            ChatAttachment(
                name="orders.csv", content_type="text/csv", content="id\nWO-1", size=7
            )
        ],
    )

    assert message.startswith("分析附件")
    assert '<attachment name="orders.csv">' in message
    assert "WO-1" in message


def test_attachment_wrapper_not_persisted_to_session(tmp_path, monkeypatch):
    """DEF-4: 会话历史持久化用户原文 + 附件元数据，不落 <attachment> 包装文本。"""
    from fastapi.testclient import TestClient
    from maestro.bootstrap import build_platform
    from maestro.config import Settings
    from maestro.main import app

    monkeypatch.chdir(tmp_path)
    s = Settings(llm_api_key="", audit_log_file=None,
                 sessions_dir=tmp_path / "sessions", skills_dir=tmp_path / "skills")
    platform = build_platform(settings=s)
    app.state.platform = platform
    client = TestClient(app)

    sid = platform.session_store.create("附件测试").session_id
    client.post("/chat", json={
        "session_id": sid, "message": "分析附件", "route": "query",
        "attachments": [{"name": "orders.csv", "content_type": "text/csv",
                         "content": "id\nWO-1", "size": 7}]})
    msgs = client.get(f"/sessions/{sid}/messages").json()
    user = [m for m in msgs if m["role"] == "user"][0]
    assert user["content"] == "分析附件"
    assert "<attachment" not in user["content"]
    assert user["attachments"] == [{"name": "orders.csv", "size": 7}]

    # 无附件消息: attachments 为空数组，content 原样
    client.post("/chat", json={"session_id": sid, "message": "无附件", "route": "query"})
    msgs = client.get(f"/sessions/{sid}/messages").json()
    plain = [m for m in msgs if m["role"] == "user"][-1]
    assert plain["content"] == "无附件"
    assert plain["attachments"] == []
