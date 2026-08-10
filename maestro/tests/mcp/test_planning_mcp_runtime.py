from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import maestro.api.app as app_module
from maestro.api.app import create_app
from maestro.bootstrap import build_platform
from maestro.config import Settings
from maestro.mcp import MCPServerConfig
from maestro.runtime.capabilities import CapabilityCall
from maestro.runtime.model import ModelAction


SERVER = Path(__file__).parent / "servers" / "planning_server.py"
PLANNING_READ_ONLY_TOOLS = (
    "list_planning_rules",
    "get_planning_overview",
    "compare_planning_solutions",
    "search_planning_entities",
    "diagnose_bottleneck",
    "explain_order_delay",
    "get_order_planning",
    "get_operation_planning",
)
PLANNING_TOOLS = (*PLANNING_READ_ONLY_TOOLS, "run_rule_planning")

QUESTIONS = [
    ("有哪些内置排产规则？", "list_planning_rules", {}),
    ("现在有多少候选排产方案？", "get_planning_overview", {}),
    ("各候选方案总延误时长分别是多少？", "compare_planning_solutions", {}),
    ("ORD-0004 的排产结果是什么？", "get_order_planning", {"order_query": "ORD-0004"}),
    (
        "OP-0004-02-01 排在什么时候？",
        "get_operation_planning",
        {"operation_query": "OP-0004-02-01"},
    ),
    (
        "名称包含 Turning 的工序有哪些？",
        "search_planning_entities",
        {"entity_type": "operation", "query": "Turning"},
    ),
    (
        "方案一真正卡住延误订单的瓶颈设备是什么？",
        "diagnose_bottleneck",
        {"solution_id": "S-1"},
    ),
    (
        "方案一中 ORD-0004 为什么延误？",
        "explain_order_delay",
        {"order_id": "ORD-0004", "solution_id": "S-1"},
    ),
]


class PlanningModel:
    def __init__(self, tool_name: str, arguments: dict[str, object]) -> None:
        self.tool_name = f"mcp__planning__{tool_name}"
        self.arguments = arguments
        self.payload: dict | None = None
        self.capability_names: list[str] = []

    async def next_turn(self, _context, capabilities, messages=None) -> ModelAction:
        self.capability_names = [capability.name for capability in capabilities]
        tool_messages = [message for message in messages or [] if message["role"] == "tool"]
        if not tool_messages:
            return ModelAction(
                kind="call",
                call=CapabilityCall(name=self.tool_name, arguments=self.arguments),
            )
        tool_message = tool_messages[-1]
        self.payload = json.loads(tool_message["content"])
        return ModelAction(kind="final", text=f"已根据排产结果回答：{self.payload.get('summary', '')}")


def local_config(**env: str) -> MCPServerConfig:
    return MCPServerConfig(
        name="planning",
        command=sys.executable,
        args=(str(SERVER),),
        env=env,
        read_only_tools=PLANNING_READ_ONLY_TOOLS,
    )


def run_via_api(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    config: MCPServerConfig,
    question: str,
    tool_name: str,
    arguments: dict[str, object],
    *,
    approve: bool = False,
) -> tuple[dict, str, PlanningModel]:
    monkeypatch.setenv("MAESTRO_DATA_DIR", str(tmp_path))
    platform = build_platform(Settings(summary_enabled=False))
    model = PlanningModel(tool_name, arguments)
    platform.runtime._model = model
    platform.mcp_config.upsert(config)
    monkeypatch.setattr(app_module, "build_platform", lambda: platform)

    with TestClient(create_app()) as client:
        created = client.post("/runs", json={"message": question})
        run_id = created.json()["run_id"]
        stream = client.get(f"/runs/{run_id}/stream")
        completed = client.get(f"/runs/{run_id}").json()
        if approve:
            approval = completed["pending_approvals"][0]
            client.post(
                f"/runs/{run_id}/approvals/{approval['approval_id']}",
                json={"approved": True, "expected_revision": completed["revision"]},
            )
            # 审批端点一决定就返回，剩下的在后台跑完；这条流结束时它才结束。
            stream = client.get(f"/runs/{run_id}/stream")
            completed = client.get(f"/runs/{run_id}").json()
    return completed, stream.text, model


def test_pending_mcp_approval_survives_an_app_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MCP-dependent Skills must be restored before a persisted approval is checked."""
    monkeypatch.setenv("MAESTRO_DATA_DIR", str(tmp_path))
    config = local_config()

    first = build_platform(Settings(summary_enabled=False))
    first.mcp_config.upsert(config)
    first.runtime._model = PlanningModel("run_rule_planning", {"rule_name": "ATC"})
    monkeypatch.setattr(app_module, "build_platform", lambda: first)
    with TestClient(create_app()) as client:
        created = client.post("/runs", json={"message": "使用 ATC 跑一遍排产"}).json()
        client.get(f"/runs/{created['run_id']}/stream")
        waiting = client.get(f"/runs/{created['run_id']}").json()

    assert waiting["status"] == "waiting_approval"
    assert "scheduling-query" in waiting["capability_versions"]

    second = build_platform(Settings(summary_enabled=False))
    second.runtime._model = PlanningModel("run_rule_planning", {"rule_name": "ATC"})
    monkeypatch.setattr(app_module, "build_platform", lambda: second)
    approval = waiting["pending_approvals"][0]
    with TestClient(create_app()) as client:
        approved = client.post(
            f"/runs/{waiting['run_id']}/approvals/{approval['approval_id']}",
            json={"approved": True, "expected_revision": waiting["revision"]},
        )
        client.get(f"/runs/{waiting['run_id']}/stream")
        completed = client.get(f"/runs/{waiting['run_id']}").json()

    assert approved.status_code == 202
    assert completed["status"] == "completed"
    assert completed["pending_approvals"] == []


@pytest.mark.parametrize(("question", "tool_name", "arguments"), QUESTIONS)
def test_planning_questions_complete_without_approval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    question: str,
    tool_name: str,
    arguments: dict[str, object],
) -> None:
    completed, stream, model = run_via_api(
        tmp_path, monkeypatch, local_config(), question, tool_name, arguments
    )

    assert completed["status"] == "completed"
    assert completed["path"] == "fast"
    assert completed["pending_approvals"] == []
    assert completed["final_text"].startswith("已根据排产结果回答：")
    assert model.tool_name in model.capability_names
    assert model.payload and model.payload["data"]["ok"] is True
    assert "event: step.succeeded" in stream
    assert "event: approval.requested" not in stream


def test_planning_tool_error_is_fed_back_to_the_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    completed, stream, model = run_via_api(
        tmp_path,
        monkeypatch,
        local_config(PLANNING_FAIL_TOOL="1"),
        "现在有多少候选排产方案？",
        "get_planning_overview",
        {},
    )

    assert completed["status"] == "completed"
    assert model.payload == {"error": "PLANNING_API_UNAVAILABLE"}
    assert "event: step.failed" in stream
    assert "event: step.succeeded" not in stream


def test_untrusted_planning_tool_still_requires_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = MCPServerConfig(
        name="planning",
        command=sys.executable,
        args=(str(SERVER),),
        read_only_tools=tuple(
            tool for tool in PLANNING_READ_ONLY_TOOLS if tool != "get_planning_overview"
        ),
    )

    completed, stream, model = run_via_api(
        tmp_path,
        monkeypatch,
        config,
        "现在有多少候选排产方案？",
        "get_planning_overview",
        {},
    )

    assert completed["status"] == "waiting_approval"
    assert len(completed["pending_approvals"]) == 1
    assert model.payload is None
    assert "event: approval.requested" in stream


def test_rule_planning_requires_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    completed, stream, model = run_via_api(
        tmp_path,
        monkeypatch,
        local_config(),
        "使用 ATC 跑一遍排产",
        "run_rule_planning",
        {"rule_name": "ATC"},
    )

    assert completed["status"] == "waiting_approval"
    assert len(completed["pending_approvals"]) == 1
    assert model.tool_name in model.capability_names
    assert model.payload is None
    assert "event: approval.requested" in stream


def test_rule_planning_returns_metrics_and_preview_after_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    completed, stream, model = run_via_api(
        tmp_path,
        monkeypatch,
        local_config(),
        "使用 ATC 跑一遍排产",
        "run_rule_planning",
        {"rule_name": "ATC"},
        approve=True,
    )

    assert completed["status"] == "completed"
    assert model.payload is not None
    planning = model.payload["data"]["data"]
    assert planning["rule_name"] == "ATC"
    assert planning["metrics"]["total_tardiness"] == 2.5
    assert planning["operation_count"] == 21
    assert len(planning["planning_preview"]) == 20
    assert planning["planning_truncated"] is True
    assert planning["latest_simulation_updated"] is True
    assert "event: approval.resolved" in stream
    assert "event: step.succeeded" in stream


@pytest.mark.skipif(
    os.environ.get("RUN_LLM4DRD_E2E") != "1",
    reason="set RUN_LLM4DRD_E2E=1 to run against the external llm4drd service",
)
def test_real_llm4drd_overview_through_runs_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root_value = os.environ.get("LLM4DRD_ROOT")
    if not root_value:
        pytest.fail("LLM4DRD_ROOT must point to the llm4drd checkout")
    root = Path(root_value)
    command = root / ".venv" / "bin" / "python"
    server = root / "mcp_server" / "server.py"
    if not command.is_file() or not server.is_file():
        pytest.fail("llm4drd Python or mcp_server/server.py is missing")
    config = MCPServerConfig(
        name="planning",
        command=str(command),
        args=(str(server),),
        env={
            "PLANNING_API_BASE_URL": os.environ.get(
                "PLANNING_API_BASE_URL", "http://127.0.0.1:8888"
            )
        },
        read_only_tools=PLANNING_READ_ONLY_TOOLS,
    )

    completed, stream, model = run_via_api(
        tmp_path,
        monkeypatch,
        config,
        "现在有多少候选排产方案？",
        "get_planning_overview",
        {},
    )

    assert completed["status"] == "completed"
    assert model.payload and model.payload["data"]["ok"] is True
    assert "event: step.succeeded" in stream
