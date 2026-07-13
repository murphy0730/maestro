import json
import zipfile
from urllib.parse import unquote

from maestro.api.routes.chat import ChatAttachment, _message_with_attachments
from maestro.config import Settings
from maestro.skills.context import SkillInvocationContext, reset_context, set_context
from maestro.skills.office_artifacts import OfficeArtifactService, format_office_result_markdown
from maestro.engines.scheduling.run_state import Budget
from maestro.bootstrap import build_platform
from maestro.skills.schemas import SkillMeta


def _spec(kind: str) -> dict:
    return {
        "kind": kind,
        "filename": f"智能制造简报.{kind}",
        "title": "智能制造简报",
        "subtitle": "生产运营周报",
        "sections": [
            {
                "title": "本周重点",
                "paragraphs": ["本周围绕交付、质量与设备稳定性推进改善。"],
                "bullets": ["计划达成率 96%", "关键设备 OEE 提升 2.3 个百分点"],
            }
        ],
    }


def test_structured_office_service_creates_downloadable_docx_and_pptx(tmp_path):
    service = OfficeArtifactService(tmp_path)
    for kind in ("docx", "pptx"):
        result = service.create(_spec(kind))
        artifact = result["artifact"]
        path = tmp_path / "artifacts" / unquote(artifact["download_url"].removeprefix("/artifacts/"))
        assert path.is_file()
        assert zipfile.is_zipfile(path)
        assert artifact["name"] == f"智能制造简报.{kind}"
        assert f"[下载 智能制造简报.{kind}]" in format_office_result_markdown(result)


def test_docx_and_pptx_attachments_are_extracted_without_base64_leaking(tmp_path):
    service = OfficeArtifactService(tmp_path)
    for kind in ("docx", "pptx"):
        result = service.create(_spec(kind))
        artifact = result["artifact"]
        path = tmp_path / "artifacts" / unquote(artifact["download_url"].removeprefix("/artifacts/"))
        data = path.read_bytes()
        import base64

        encoded = base64.b64encode(data).decode()
        message = _message_with_attachments(
            "总结附件",
            [ChatAttachment(
                name=path.name,
                content_type=artifact["content_type"],
                content=encoded,
                size=len(data),
                encoding="base64",
            )],
        )
        assert "智能制造简报" in message
        assert encoded[:120] not in message


async def test_docx_skill_gets_structured_tool_and_confirmation(tmp_path):
    settings = Settings(
        llm_api_key="",
        vector_backend="memory",
        audit_log_file=None,
        pending_actions_db=None,
        sessions_dir=tmp_path / "sessions",
        skills_dir=tmp_path / "skills",
        skill_execution_dir=tmp_path / "runs",
    )
    platform = build_platform(settings=settings)
    platform.skill_store.save(
        SkillMeta(
            name="docx",
            description="Create Word documents",
            file_count=1,
            bytes=4,
            added_at="2026-01-01T00:00:00+00:00",
        ),
        "Create a Word document.",
        {},
    )
    token = set_context(SkillInvocationContext(
        allowed_skills=frozenset({"docx"}),
        depth=0,
        visited=frozenset({"docx"}),
        budget=Budget(4),
    ))
    try:
        pending = await platform.tools.execute("create_office_artifact", _spec("docx"))
    finally:
        reset_context(token)
    assert pending["pending_confirmation"] is True
    action, result = await platform.gate.confirm(pending["action_id"], True)
    assert action.status == "executed"
    detail = json.loads(result.detail)
    assert detail["artifact"]["download_url"].startswith("/artifacts/office-")
