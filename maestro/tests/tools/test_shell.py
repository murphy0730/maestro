"""The `bash` primitive: arbitrary command execution behind a mandatory approval.

The approval is the real gate, so the first test here pins it. The rest cover
containment (which is defence in depth, not a boundary) and the failure modes
that must come back as data the model can act on.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from maestro.bootstrap import build_platform
from maestro.config import Settings
from maestro.runtime.capabilities import (
    CapabilityCall,
    CapabilityRegistry,
    RiskLevel,
)
from maestro.runtime.policy import PolicyContext, PolicyEffect, PolicyGate
from maestro.tools import register_shell_capability
from maestro.tools.shell import SHELL_CAPABILITY

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="shell 断言基于 POSIX /bin/sh"
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "note.txt").write_text("hello\n", "utf-8")
    return root


@pytest.fixture
def registry(workspace: Path) -> CapabilityRegistry:
    registry = CapabilityRegistry()
    register_shell_capability(registry, workspace)
    return registry


async def run(registry: CapabilityRegistry, command: str | None = None, **extra):
    arguments = {} if command is None else {"command": command}
    spec = registry.require(SHELL_CAPABILITY)
    assert spec.executor is not None
    return await spec.executor(
        CapabilityCall(name=SHELL_CAPABILITY, arguments={**arguments, **extra}), None
    )


def test_every_call_requires_human_approval(registry: CapabilityRegistry) -> None:
    """Arbitrary execution is only acceptable because a human confirms each call."""
    spec = registry.require(SHELL_CAPABILITY)
    assert spec.writes is True
    assert spec.risk is RiskLevel.HIGH

    decision = PolicyGate([]).evaluate(
        CapabilityCall(name=SHELL_CAPABILITY, arguments={"command": "ls"}),
        spec,
        PolicyContext(principal_id="u1"),
    )

    assert decision.effect is PolicyEffect.REQUIRE_CONFIRMATION


async def test_runs_in_the_workspace_and_returns_output(
    registry: CapabilityRegistry,
) -> None:
    result = await run(registry, "cat note.txt")

    assert result.status == "succeeded"
    assert result.content["stdout"].strip() == "hello"
    assert result.content["exit_code"] == 0


async def test_can_write_inside_the_workspace(
    registry: CapabilityRegistry, workspace: Path
) -> None:
    result = await run(registry, "printf built > out.txt")

    assert result.status == "succeeded"
    assert (workspace / "out.txt").read_text("utf-8") == "built"


async def test_a_failing_command_returns_its_own_answer(
    registry: CapabilityRegistry,
) -> None:
    """A non-zero exit is data for the model, not a runtime failure."""
    result = await run(registry, "cat missing-file.txt")

    assert result.status == "succeeded"
    assert result.content["exit_code"] != 0
    assert result.content["stderr"]


async def test_a_hanging_command_is_killed(registry: CapabilityRegistry, monkeypatch) -> None:
    monkeypatch.setattr("maestro.tools.shell._TIMEOUT_SECONDS", 0.5)

    result = await run(registry, "sleep 5")

    assert result.status == "failed"
    assert result.content["timed_out"] is True


async def test_missing_or_blank_command_is_refused(registry: CapabilityRegistry) -> None:
    for result in (await run(registry), await run(registry, "   ")):
        assert result.status == "failed"
        assert "command" in (result.error_message or "")


async def test_an_over_long_command_is_refused(registry: CapabilityRegistry) -> None:
    result = await run(registry, "echo " + "x" * 9_000)

    assert result.status == "failed"
    assert "过长" in (result.error_message or "")


async def test_host_secrets_are_not_inherited(
    registry: CapabilityRegistry, monkeypatch
) -> None:
    monkeypatch.setenv("LLM_API_KEY", "super-secret")

    result = await run(registry, "env")

    assert "LLM_API_KEY" not in result.content["stdout"]
    assert "super-secret" not in result.content["stdout"]


async def test_isolation_is_reported_truthfully(registry: CapabilityRegistry) -> None:
    """Never claim more containment than actually took effect."""
    result = await run(registry, "true")

    assert result.content["isolation"] in {"seatbelt", "baseline"}
    if sys.platform != "darwin":
        assert result.content["isolation"] == "baseline"


@pytest.mark.skipif(sys.platform != "darwin", reason="seatbelt 仅在 macOS 生效")
async def test_seatbelt_confines_writes_outside_the_workspace(
    registry: CapabilityRegistry,
) -> None:
    # Deliberately NOT under `tmp_path`: the profile allows the whole
    # `/private/var/folders` tree so a sandboxed process can use TMPDIR, and a
    # pytest temp directory lives there. Asserting from inside it would prove
    # nothing. See `sandbox._profile`.
    outside = Path("/private/tmp/maestro-shell-escape-test.txt")
    outside.unlink(missing_ok=True)

    result = await run(registry, f"printf x > {outside}")

    if result.content["isolation"] != "seatbelt":
        pytest.skip("此宿主未启用 seatbelt")
    try:
        assert not outside.exists()
        assert result.content["exit_code"] != 0
    finally:
        outside.unlink(missing_ok=True)


@pytest.mark.skipif(sys.platform != "darwin", reason="seatbelt 仅在 macOS 生效")
async def test_seatbelt_denies_network(registry: CapabilityRegistry) -> None:
    result = await run(
        registry, "python3 -c \"import socket; socket.create_connection(('1.1.1.1', 80), 3)\""
    )

    if result.content["isolation"] != "seatbelt":
        pytest.skip("此宿主未启用 seatbelt")
    assert result.content["exit_code"] != 0


def test_a_skill_declaring_allowed_tools_bash_now_discovers(tmp_path: Path) -> None:
    """This is why the capability exists: `Bash` is the commonest declaration."""
    skills = tmp_path / "skills"
    path = skills / "builder" / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        "---\nname: builder\ndescription: build\nallowed-tools: [Bash, Read]\n---\nbuild it\n"
    )

    platform = build_platform(
        Settings(skills_dir=skills, workspace_root=tmp_path / "workspace")
    )

    assert platform.skill_catalog.errors == []
    assert platform.skill_catalog.metadata("builder").allowed_tools == (
        SHELL_CAPABILITY,
        "read_file",
    )
