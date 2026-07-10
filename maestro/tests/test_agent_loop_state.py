from maestro.engines.scheduling.run_state import AgentStatus, RunState
from maestro.engines.scheduling.schemas import AgentStep
from maestro.engines.scheduling.termination import TerminationPolicy


def test_run_state_nudges_then_finishes():
    state = RunState.start("检查齐套")

    state.request_nudge("继续", limit=1)
    assert state.status == AgentStatus.RUNNING
    assert state.messages[-1] == {"role": "user", "content": "继续"}

    state.request_nudge("继续", limit=1)
    assert state.status == AgentStatus.FINISHED


def test_termination_policy_detects_hard_limit_and_repeated_tool_call():
    policy = TerminationPolicy(max_steps=2, repeat_limit=3, blocked_limit=3)
    state = RunState.start("检查齐套")

    assert policy.status_for(state, iteration=2) == AgentStatus.MAX_STEPS

    state.seen[("check_kitting", "{}")]=3
    assert policy.status_for(state, iteration=0) == AgentStatus.STUCK


def test_termination_policy_detects_repeated_blocked_steps():
    policy = TerminationPolicy(max_steps=8, repeat_limit=3, blocked_limit=3)
    state = RunState.start("检查齐套")
    state.steps = [
        AgentStep(tool="check_kitting", blocked=True),
        AgentStep(tool="query_inventory", blocked=True),
        AgentStep(tool="dispatch_work_order", blocked=True),
    ]

    assert policy.status_for(state, iteration=0) == AgentStatus.STUCK
