import asyncio
from dataclasses import dataclass, field
from enum import Enum

from maestro.engines.scheduling.schemas import AgentStep


@dataclass
class Budget:
    """全链路 LLM 请求预算 (跨嵌套技能循环共享)，带锁原子扣减，防无界递归爆炸。

    top-level 技能循环创建一个 Budget，嵌套子技能循环复用同一实例；每轮消耗一个
    额度，耗尽即令当前循环收敛 (走 forced final 出结论)。单技能不嵌套时，循环自身的
    max_steps 通常先触顶，Budget 不生效。
    """

    remaining: int
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def take(self) -> bool:
        async with self._lock:
            if self.remaining <= 0:
                return False
            self.remaining -= 1
            return True


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
    active_tools: set[str] = field(default_factory=set)

    @classmethod
    def start(
        cls, task: str, history: list[dict] | None = None, active_tools: list[str] | None = None
    ) -> "RunState":
        return cls(
            messages=[*(history or []), {"role": "user", "content": task}],
            active_tools=set(active_tools or []),
        )

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
