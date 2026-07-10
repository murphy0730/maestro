"""技能执行的调用上下文 (contextvar) — 作用域化附件访问 + 嵌套预算。

`read_skill_file` / `list_skill_files` / `invoke_skill` 均**无 skill_name 入参**:
可访问哪些技能的附件、嵌套深度与全链路预算,都由本上下文携带,**不由 LLM 传参**,
从根上杜绝"传任意 skill_name 越权读取/执行其他技能包"与"绕过嵌套预算"。

SkillEngine 在运行每个 AgentLoop 前 set 本上下文、结束后 reset;嵌套子技能循环
set 一个 allowed_skills 收窄到自身、depth+1、visited 追加自身、共享同一 Budget 的
子上下文。全程在同一 asyncio 任务内 await,contextvar 的 set/reset(token) 语义成立。
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass

from maestro.engines.scheduling.run_state import Budget


@dataclass(frozen=True)
class SkillInvocationContext:
    allowed_skills: frozenset[str]  # 本次循环可读附件/可执行脚本的技能集
    depth: int  # 嵌套深度 (top-level=0)
    visited: frozenset[str]  # 祖先链 (含当前),用于环检测
    budget: Budget  # 全链路共享预算 (带锁原子扣减)


_current: contextvars.ContextVar[SkillInvocationContext | None] = contextvars.ContextVar(
    "skill_invocation_context", default=None
)


def current_context() -> SkillInvocationContext | None:
    return _current.get()


def set_context(ctx: SkillInvocationContext) -> contextvars.Token:
    return _current.set(ctx)


def reset_context(token: contextvars.Token) -> None:
    _current.reset(token)
