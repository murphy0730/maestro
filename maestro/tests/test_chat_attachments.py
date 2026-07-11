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
