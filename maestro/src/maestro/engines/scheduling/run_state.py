from dataclasses import dataclass, field
from enum import Enum

from maestro.engines.scheduling.schemas import AgentStep


class AgentStatus(str, Enum):
    RUNNING = "running"
    FINISHED = "final"
    MAX_STEPS = "max_steps"
    STUCK = "stuck"
    ERROR = "error"


@dataclass
class RunState:
    messages: list[dict]
    steps: list[AgentStep] = field(default_factory=list)
    seen: dict[tuple[str, str], int] = field(default_factory=dict)
    status: AgentStatus = AgentStatus.RUNNING
    answer: str = ""
    nudges: int = 0

    @classmethod
    def start(cls, task: str, history: list[dict] | None = None) -> "RunState":
        return cls(messages=[*(history or []), {"role": "user", "content": task}])

    def finish(self, answer: str) -> None:
        self.answer = answer
        self.status = AgentStatus.FINISHED

    def request_nudge(self, message: str, limit: int) -> None:
        if self.nudges >= limit:
            self.status = AgentStatus.FINISHED
            return
        self.nudges += 1
        self.messages.append({"role": "user", "content": message})

    def record_tool_step(
        self,
        thought: str,
        tool: str,
        arguments: dict,
        tool_call_id: str,
        content: str,
        observation: object,
        blocked: bool,
    ) -> None:
        self.steps.append(
            AgentStep(
                thought=thought,
                tool=tool,
                arguments=arguments,
                observation=observation,
                blocked=blocked,
            )
        )
        self.messages.append({"role": "tool", "tool_call_id": tool_call_id, "content": content})
