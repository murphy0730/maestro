"""本次请求的执行模式 (plan / auto)。

决策发生在 ActionGate.request() 内，而调用它的是 builtin.py 里签名形如
`async def dispatch_work_order(wo_id)` 的工具 handler —— registry.execute 以
`handler(**args)` 调用，没有地方能把 mode 塞进参数。故用 contextvar 承载。

Orchestrator.handle() 是唯一写入点 (三个引擎 + 技能引擎的共同入口)，
ActionGate.request() 是唯一读取点。

默认 "plan" 是故障安全值: 事件驱动唤醒与 CLI 不经 HTTP，拿到默认值，
写操作照旧需人工确认。
"""

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Literal

ExecMode = Literal["plan", "auto"]

_mode: ContextVar[ExecMode] = ContextVar("maestro_exec_mode", default="plan")


def current_mode() -> ExecMode:
    return _mode.get()


@contextmanager
def use_mode(mode: ExecMode) -> Iterator[None]:
    """在此上下文内切换执行模式。asyncio 子任务 (gather 并发调工具) 复制父 context，
    模式随之继承。"""
    token = _mode.set(mode)
    try:
        yield
    finally:
        _mode.reset(token)
