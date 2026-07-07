"""调度引擎 (ReAct 智能体) 数据模型。

v0.2: 调度引擎从「固定 workflow」改为 ReAct 智能体 (推理-行动-观察循环)。
不再有 Expedite/Dispatch/Exception 等流程专用模型 —— 这些能力下沉为工具
(foundation/tools/builtin.py)，由智能体按需编排。此处只保留刻画一次 ReAct
运行轨迹的通用模型，便于回显「想了什么 / 调了什么工具 / 观察到什么」。
"""

from typing import Any

from pydantic import BaseModel, Field

from maestro.domain.models import PendingAction


class AgentStep(BaseModel):
    """ReAct 单步: 思考 + 一次工具调用 + 观察结果。"""

    thought: str = ""  # 模型本步的思考文本 (可能为空)
    tool: str  # 调用的工具名
    arguments: dict = Field(default_factory=dict)
    observation: Any = None  # 工具返回 / 被护栏拦截的说明
    blocked: bool = False  # 是否被前置断言/白名单拦截 (未真正执行)


class AgentResult(BaseModel):
    """一次 ReAct 运行的结果: 最终答复 + 完整轨迹 + 产生的待确认动作。"""

    answer: str
    steps: list[AgentStep] = Field(default_factory=list)
    pending_actions: list[PendingAction] = Field(default_factory=list)
    stop_reason: str = "final"  # final / max_steps / no_llm
