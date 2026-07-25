from __future__ import annotations

from pathlib import Path

import pytest

from maestro.runtime.capabilities import (
    CapabilityCall,
    CapabilityRegistry,
    RiskLevel,
)
from maestro.runtime.skills import SKILL_SCRIPT_CAPABILITY, SkillCatalog
from maestro.runtime.store import ArtifactStore
from maestro.skills.package import compute_package_hash
from maestro.skills.trust import SkillTrustStore
from maestro.tools.skill_scripts import normalize_script, register_skill_script_capability


@pytest.fixture
def skill(tmp_path: Path) -> Path:
    root = tmp_path / "skills" / "runner"
    (root / "scripts").mkdir(parents=True)
    (root / "SKILL.md").write_text(
        "---\nname: runner\ndescription: runner\n---\nrun scripts/hello.py\n", "utf-8"
    )
    (root / "scripts" / "hello.py").write_text(
        "import os, sys\n"
        "print('hello', *sys.argv[1:])\n"
        "open('out.txt', 'w').write('produced')\n"
        "print('LEAK' if os.environ.get('LLM_API_KEY') else 'clean')\n",
        "utf-8",
    )
    return root


@pytest.fixture
def harness(tmp_path: Path, skill: Path):
    registry = CapabilityRegistry()
    catalog = SkillCatalog({"project": tmp_path / "skills"}, registry)
    catalog.discover()
    trust = SkillTrustStore(tmp_path / "skills")
    artifacts = ArtifactStore(tmp_path / "artifacts")
    register_skill_script_capability(registry, catalog, trust, artifacts)
    return registry, trust, artifacts


async def run(registry: CapabilityRegistry, **arguments):
    spec = registry.require(SKILL_SCRIPT_CAPABILITY)
    return await spec.executor(
        CapabilityCall(name=SKILL_SCRIPT_CAPABILITY, arguments=arguments), None
    )


def test_script_capability_always_requires_human_approval(harness) -> None:
    """writes=True + HIGH is what makes the Policy Gate demand confirmation."""
    registry, _trust, _artifacts = harness
    spec = registry.require(SKILL_SCRIPT_CAPABILITY)

    assert spec.writes is True
    assert spec.risk is RiskLevel.HIGH


async def test_untrusted_script_is_refused(harness) -> None:
    registry, _trust, _artifacts = harness

    result = await run(registry, skill="runner", script="hello.py")

    assert result.status == "failed"
    assert "未被信任" in result.error_message


async def test_trusted_script_runs_and_keeps_its_artifacts(harness, skill: Path) -> None:
    registry, trust, artifacts = harness
    trust.trust("runner", skill)

    result = await run(registry, skill="runner", script="hello.py", arguments=["world"])

    assert result.status == "succeeded", result.error_message
    assert "hello world" in result.content["stdout"]
    # The throwaway workspace is deleted, so output must be copied out first.
    produced = result.content["artifacts"]
    assert [item["path"] for item in produced] == ["out.txt"]
    assert artifacts.get(produced[0]["artifact_id"]) == b"produced"


async def test_sandbox_does_not_inherit_secrets(
    harness, skill: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry, trust, _artifacts = harness
    monkeypatch.setenv("LLM_API_KEY", "super-secret")
    trust.trust("runner", skill)

    result = await run(registry, skill="runner", script="hello.py")

    assert "clean" in result.content["stdout"]
    assert "super-secret" not in result.content["stdout"]


async def test_editing_a_trusted_skill_invalidates_its_trust(harness, skill: Path) -> None:
    registry, trust, _artifacts = harness
    trust.trust("runner", skill)
    before = compute_package_hash(skill)

    (skill / "scripts" / "hello.py").write_text("print('rewritten')\n", "utf-8")

    assert compute_package_hash(skill) != before
    assert trust.status("runner", skill).valid is False
    result = await run(registry, skill="runner", script="hello.py")
    assert result.status == "failed"
    assert "已变更" in result.error_message


async def test_script_path_cannot_escape_the_package(harness, skill: Path, tmp_path: Path) -> None:
    registry, trust, _artifacts = harness
    trust.trust("runner", skill)
    (tmp_path / "evil.py").write_text("print('pwned')\n", "utf-8")

    result = await run(registry, skill="runner", script="../../evil.py")

    assert result.status == "failed"
    assert "pwned" not in str(result.content)


async def test_only_known_interpreters_are_accepted(harness, skill: Path) -> None:
    registry, trust, _artifacts = harness
    (skill / "scripts" / "tool.bin").write_bytes(b"\x7fELF")
    trust.trust("runner", skill)

    result = await run(registry, skill="runner", script="tool.bin")

    assert result.status == "failed"


async def test_a_hanging_script_is_killed(harness, skill: Path, monkeypatch) -> None:
    registry, trust, _artifacts = harness
    (skill / "scripts" / "hang.py").write_text("import time\ntime.sleep(30)\n", "utf-8")
    trust.trust("runner", skill)
    monkeypatch.setattr("maestro.tools.skill_scripts._TIMEOUT_SECONDS", 1.0)

    result = await run(registry, skill="runner", script="hang.py")

    assert result.status == "failed"
    assert result.content["timed_out"] is True


def test_normalize_script_adds_the_prefix_models_forget() -> None:
    assert normalize_script("hello.py") == "scripts/hello.py"
    assert normalize_script("scripts/hello.py") == "scripts/hello.py"
    assert normalize_script("./hello.py") == "scripts/hello.py"


def test_trust_survives_a_restart(tmp_path: Path, skill: Path) -> None:
    """The old in-process dict lost every grant on restart."""
    skills_dir = tmp_path / "skills"
    SkillTrustStore(skills_dir).trust("runner", skill)

    assert SkillTrustStore(skills_dir).is_trusted("runner", skill) is True
