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


def test_srt_wrap_keeps_command_args_out_of_srt_options(tmp_path):
    runtime = SrtRuntime(executable=tmp_path / "srt")
    argv, settings = runtime.wrap(
        ["python", "run.py", "--help"], tmp_path, []
    )
    settings.unlink(missing_ok=True)
    assert argv[-4:] == ["--", "python", "run.py", "--help"]


@pytest.mark.asyncio
async def test_script_artifacts_survive_run_cleanup(tmp_path):
    store = SkillStore(tmp_path / "skills")
    store.save(
        _meta(),
        "body",
        {"scripts/run.py": b"open('out.pptx', 'w').write('deck')"},
    )
    meta = store.get("script-skill")
    store.trust(meta.name, meta.package_sha256)
    service = SkillScriptExecutionService(
        store, tmp_path / "runs", tmp_path / "skills", srt=_NoSrt()
    )
    result = await service.execute({
        "skill_id": meta.name,
        "script": "scripts/run.py",
        "args": [],
        "package_sha256": meta.package_sha256,
    })
    assert result["status"] == "completed"
    assert len(result["artifacts"]) == 1
    artifact = result["artifacts"][0]
    assert artifact["name"] == "out.pptx"
    assert artifact["download_url"].endswith("/out.pptx")
    saved = tmp_path / "runs" / "artifacts" / artifact["download_url"].removeprefix("/artifacts/")
    with open(saved) as handle:
        assert handle.read() == "deck"


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


async def test_run_root_lives_in_system_tmp_not_data_root(tmp_path, monkeypatch):
    """DEF-3: 执行现场建在系统短路径 tmp (长数据根不再撑爆 unix socket 上限)，
    产物仍归档到数据根 artifacts 目录。"""
    import os
    import tempfile as _tempfile
    import maestro.skills.script_execution as se

    deep_root = tmp_path / ("very-long-data-root-" + "d" * 60)
    store = SkillStore(deep_root / "skills")
    store.save(_meta(), "body", {"scripts/run.py": b"open('out.txt','w').write('x')\nprint('ok')"})
    meta = store.get("script-skill")
    store.trust(meta.name, meta.package_sha256)

    captured = {}
    real_mkdtemp = _tempfile.mkdtemp

    def spy_mkdtemp(prefix=None, dir=None):
        captured["dir"] = dir
        return real_mkdtemp(prefix=prefix, dir=dir)

    monkeypatch.setattr(se.tempfile, "mkdtemp", spy_mkdtemp)
    service = SkillScriptExecutionService(
        store, deep_root / "runs", deep_root / "skills", srt=_NoSrt())
    result = await service.execute({
        "skill_id": meta.name, "script": "scripts/run.py",
        "args": [], "package_sha256": meta.package_sha256,
    })
    assert result["status"] == "completed"
    assert captured["dir"] == ("/tmp" if os.name != "nt" else None)  # 不在数据根下
    # 产物归档仍在数据根
    assert result["artifacts"], "脚本产物应被归档"
    assert (deep_root / "runs" / "artifacts").exists()


async def test_srt_infra_failure_falls_back_to_guarded_host(tmp_path, monkeypatch):
    """DEF-3: SRT 运行期基础设施故障 (mux socket EINVAL) 自动回退宿主机受控执行。"""
    store = SkillStore(tmp_path / "skills")
    store.save(_meta(), "body", {"scripts/run.py": b"print('recovered')"})
    meta = store.get("script-skill")
    store.trust(meta.name, meta.package_sha256)
    service = SkillScriptExecutionService(
        store, tmp_path / "runs", tmp_path / "skills", srt=_NoSrt())

    calls = []
    orig = SkillScriptExecutionService._run_once

    async def fake(self, skill_id, script, args, files, allow_sandbox):
        calls.append(allow_sandbox)
        if allow_sandbox:
            return {"status": "failed", "execution_mode": "srt", "exit_code": 1, "stdout": "",
                    "stderr": "Error: listen EINVAL: invalid argument /x/workspace/srt-mux-1-0.sock"}
        return await orig(self, skill_id, script, args, files, allow_sandbox)

    monkeypatch.setattr(SkillScriptExecutionService, "_run_once", fake)
    result = await service.execute({
        "skill_id": meta.name, "script": "scripts/run.py",
        "args": [], "package_sha256": meta.package_sha256,
    })
    assert calls == [True, False]
    assert result["execution_mode"] == "guarded_host"
    assert result["status"] == "completed"
    assert result["stdout"].strip() == "recovered"
    assert result["fallback_reason"] == "srt_infrastructure_failure"


async def test_script_own_failure_is_not_retried(tmp_path, monkeypatch):
    """脚本自身失败 (非 SRT 基础设施) 不得触发宿主机重跑。"""
    store = SkillStore(tmp_path / "skills")
    store.save(_meta(), "body", {"scripts/run.py": b"raise SystemExit(3)"})
    meta = store.get("script-skill")
    store.trust(meta.name, meta.package_sha256)
    service = SkillScriptExecutionService(
        store, tmp_path / "runs", tmp_path / "skills", srt=_NoSrt())

    calls = []
    orig = SkillScriptExecutionService._run_once

    async def fake(self, skill_id, script, args, files, allow_sandbox):
        calls.append(allow_sandbox)
        if allow_sandbox:
            return {"status": "failed", "execution_mode": "srt", "exit_code": 3, "stdout": "",
                    "stderr": "Traceback: ValueError: bad input"}
        return await orig(self, skill_id, script, args, files, allow_sandbox)

    monkeypatch.setattr(SkillScriptExecutionService, "_run_once", fake)
    result = await service.execute({
        "skill_id": meta.name, "script": "scripts/run.py",
        "args": [], "package_sha256": meta.package_sha256,
    })
    assert calls == [True]
    assert result["status"] == "failed"
    assert "fallback_reason" not in result


async def test_check_usable_rejects_overlong_socket_path(tmp_path):
    """DEF-3 静态预检: cwd 过长导致 mux socket 必然超限时直接判不可用。"""
    import os
    if os.name == "nt":
        return  # unix socket 上限只在 POSIX 生效
    from pathlib import Path as _P
    from maestro.execution.srt import SrtRuntime

    rt = SrtRuntime(executable=_P("/bin/echo"))
    deep = tmp_path / ("x" * 120)
    deep.mkdir()
    assert await rt.check_usable(deep, []) is False
