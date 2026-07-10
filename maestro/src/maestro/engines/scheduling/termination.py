from dataclasses import dataclass

from maestro.engines.scheduling.run_state import AgentStatus, RunState


@dataclass(frozen=True)
class TerminationPolicy:
    max_steps: int
    repeat_limit: int = 3
    blocked_limit: int = 3

    def status_for(self, state: RunState, iteration: int) -> AgentStatus | None:
        if iteration >= self.max_steps:
            return AgentStatus.MAX_STEPS
        if self.is_stuck(state):
            return AgentStatus.STUCK
        return None

    def is_stuck(self, state: RunState) -> bool:
        if any(count >= self.repeat_limit for count in state.seen.values()):
            return True
        recent = state.steps[-self.blocked_limit :]
        return len(recent) >= self.blocked_limit and all(step.blocked for step in recent)

    @staticmethod
    def needs_forced_final(status: AgentStatus) -> bool:
        return status in (AgentStatus.MAX_STEPS, AgentStatus.STUCK)
