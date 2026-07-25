from pathlib import Path

from maestro.bootstrap import build_platform
from maestro.config import Settings


def test_runtime_core_has_no_manufacturing_dependencies() -> None:
    root = Path("src/maestro/runtime")
    text = "\n".join(path.read_text("utf-8") for path in root.rglob("*.py"))
    forbidden = [
        "ortools",
        "kitting",
        "dispatch_work_order",
        "send_expedite",
        "PlanningStrategy",
        "GoalSpec",
        "TypedPlan",
        "PlanStep",
    ]
    assert [word for word in forbidden if word in text] == []


def test_legacy_engine_packages_are_removed() -> None:
    assert not Path("src/maestro/engines").exists()
    assert not Path("src/maestro/orchestrator").exists()


def test_removed_dependencies_are_absent() -> None:
    pyproject = Path("pyproject.toml").read_text("utf-8")
    assert all(name not in pyproject for name in ["ortools", "chromadb", "python-docx", "python-pptx"])


# Generic host primitives a Skill's allowed-tools may name.  They carry no
# domain semantics, so their presence is not a B1 violation; anything outside
# this set must arrive as an installed capability, never from the Runtime.
GENERIC_PRIMITIVES = {
    "read_file",
    "glob",
    "grep",
    "write_file",
    "edit_file",
    "read_artifact",
    "skill_read_resource",
    "skill_run_script",
}


def test_default_runtime_has_no_installed_manufacturing_capability(tmp_path: Path) -> None:
    platform = build_platform(
        Settings(skills_dir=tmp_path / "skills", workspace_root=tmp_path / "workspace")
    )
    installed = {spec.name for spec in platform.capabilities.snapshot().values()}
    assert installed - GENERIC_PRIMITIVES == set()
    assert platform.skill_catalog.discover() == {}


def test_no_domain_bridge_is_wired_into_the_composition_root(tmp_path: Path) -> None:
    """Domain capability must be installed by a host, never by build_platform."""
    assert not Path("src/maestro/scheduling_query.py").exists()
    text = Path("src/maestro/bootstrap.py").read_text("utf-8")
    assert "scheduling" not in text.lower()
