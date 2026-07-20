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


def test_default_runtime_has_no_installed_manufacturing_capability(tmp_path: Path) -> None:
    platform = build_platform(Settings(skills_dir=tmp_path / "skills"))
    assert platform.capabilities.snapshot().values() == ()
    assert platform.skill_catalog.discover() == {}
