import json

import pytest

from maestro.bootstrap import build_platform
from maestro.config import Settings
from maestro.execution.srt import SrtRuntime
from maestro.skills.context import SkillInvocationContext, reset_context, set_context
from maestro.skills.schemas import SkillMeta, SkillValidationError
from maestro.skills.script_execution import SkillScriptExecutionService
from maestro.skills.store import SkillStore
from maestro.engines.scheduling.run_state import Budget


def _meta(name="script-skill"):
    return SkillMeta(
        name=name,
        description="script",
        scripts=["scripts/run.py"],
        file_count=1,
        added_at="2026-07-11T00:00:00Z",
    )


class _NoSrt(SrtRuntime):
    def __init__(self):
        super().__init__(executable=None)
        self.executable = None


def test_trust_is_bound_to_current_package_hash(tmp_path):
    store = SkillStore(tmp_path)
    store.save(_meta(), "body", {"scripts/run.py": b"print('ok')"})
    meta = store.get("script-skill")
    assert meta and meta.package_sha256
    store.trust(meta.name, meta.package_sha256)
    assert store.is_trusted(meta.name) is True
    assert store.trust_status(meta.name)["level"] == "user_trusted"
    with pytest.raises(SkillValidationError):
        store.trust(meta.name, "0" * 64)


def test_delete_revokes_trust(tmp_path):
    store = SkillStore(tmp_path)
    store.save(_meta(), "body", {"scripts/run.py": b"print('ok')"})
    meta = store.get("script-skill")
    store.trust(meta.name, meta.package_sha256)
    assert store.delete(meta.name)
    assert json.loads((tmp_path / "trust.json").read_text()) == {}


@pytest.mark.asyncio
async def test_trusted_script_runs_guarded_on_host_when_srt_unavailable(tmp_path):
    store = SkillStore(tmp_path / "skills")
    store.save(_meta(), "body", {"scripts/run.py": b"print('hello trusted')"})
    meta = store.get("script-skill")
    store.trust(meta.name, meta.package_sha256)
    service = SkillScriptExecutionService(
        store,
        tmp_path / "runs",
        tmp_path / "skills",
        srt=_NoSrt(),
    )
    result = await service.execute({
        "skill_id": meta.name,
        "script": "scripts/run.py",
        "args": [],
        "package_sha256": meta.package_sha256,
    })
    assert result["status"] == "completed"
    assert result["execution_mode"] == "guarded_host"
    assert result["stdout"].strip() == "hello trusted"


@pytest.mark.asyncio
async def test_untrusted_script_is_rejected_before_execution(tmp_path):
    store = SkillStore(tmp_path / "skills")
    store.save(_meta(), "body", {"scripts/run.py": b"print('no')"})
    meta = store.get("script-skill")
    service = SkillScriptExecutionService(
        store, tmp_path / "runs", tmp_path / "skills", srt=_NoSrt()
    )
    with pytest.raises(SkillValidationError, match="未被本地用户信任"):
        await service.execute({
            "skill_id": meta.name,
            "script": "scripts/run.py",
            "args": [],
            "package_sha256": meta.package_sha256,
        })


@pytest.mark.asyncio
async def test_skill_tool_requires_action_gate_confirmation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = Settings(
        llm_api_key="",
        audit_log_file=None,
        pending_actions_db=None,
        sessions_dir=tmp_path / "sessions",
        skills_dir=tmp_path / "skills",
        skill_execution_dir=tmp_path / "runs",
    )
    platform = build_platform(settings=settings)
    platform.skill_scripts._srt = _NoSrt()
    platform.skill_store.save(
        _meta(), "body", {"scripts/run.py": b"print('confirmed')"}
    )
    meta = platform.skill_store.get("script-skill")
    platform.skill_store.trust(meta.name, meta.package_sha256)
    token = set_context(SkillInvocationContext(
        allowed_skills=frozenset({meta.name}),
        depth=0,
        visited=frozenset({meta.name}),
        budget=Budget(4),
    ))
    try:
        pending = await platform.tools.execute(
            "run_skill_script", {"script": "scripts/run.py", "args": []}
        )
    finally:
        reset_context(token)
    assert pending["pending_confirmation"] is True
    action, result = await platform.gate.confirm(pending["action_id"], True)
    assert action.status == "executed"
    detail = json.loads(result.detail)
    assert detail["execution_mode"] == "guarded_host"
    assert detail["stdout"].strip() == "confirmed"
