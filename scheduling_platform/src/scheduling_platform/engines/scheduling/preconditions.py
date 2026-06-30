"""写操作前置断言 (调度引擎的「第一道写护栏」)。

前置断言是**代码硬规则**，不依赖 LLM: 在高危写操作真正执行前核验业务硬前提，
不满足就拦截并把原因回喂给 ReAct (让它换思路或如实说明)，与之后的 ActionGate
(人工确认/授权) 共同构成两道护栏。

断言在此定义，但由组装根 (bootstrap) 用 registry.attach_precondition 挂到对应
工具上 —— foundation 层不反向依赖引擎层。
"""

from scheduling_platform.foundation.integration.base import IntegrationAdapter
from scheduling_platform.foundation.kitting import KittingService
from scheduling_platform.foundation.tools.builtin import FollowupStore
from scheduling_platform.foundation.tools.registry import Precondition, PreconditionResult


def make_dispatch_precondition(
    kitting: KittingService, adapter: IntegrationAdapter
) -> Precondition:
    """下发前置断言: 任务令必须已齐套 + 产线可用 (前道工序完成为桩，v0.2 待补)。"""

    async def precondition(args: dict) -> PreconditionResult:
        wo_id = args.get("wo_id")
        if not wo_id:
            return PreconditionResult(False, "缺少 wo_id")

        work_orders = await adapter.get_work_orders({"wo_ids": [wo_id]})
        if not work_orders:
            return PreconditionResult(False, f"任务令 {wo_id} 不存在")
        wo = work_orders[0]
        if wo.status != "draft":
            return PreconditionResult(False, f"任务令 {wo_id} 状态为 {wo.status}，仅 draft 可下发")

        results = await kitting.check([wo_id])
        if results and not results[0].is_kitted:
            missing = ", ".join(
                f"{s.material_id}缺{s.shortage_qty:g}{s.unit}" for s in results[0].shortages
            )
            return PreconditionResult(False, f"任务令 {wo_id} 未齐套 ({missing})，不可下发")

        lines = {ln.line_id: ln for ln in await adapter.get_lines()}
        line = lines.get(wo.line_id)
        if line is None or not line.available:
            return PreconditionResult(False, f"产线 {wo.line_id} 不可用，不可下发")

        # TODO(v0.2): 前道工序完成校验 —— 当前视为已满足 (桩)
        return PreconditionResult(True)

    return precondition


def make_expedite_precondition(
    kitting: KittingService, followups: FollowupStore
) -> Precondition:
    """催料前置断言: 带 material_id 时核验「确实缺料」且「未重复催过」。

    未提供 material_id 时无法断言缺料事实，放行交由 ActionGate 与人把关
    (内部自动发 / 供应商需确认)。
    """

    async def precondition(args: dict) -> PreconditionResult:
        material_id = args.get("material_id")
        if not material_id:
            return PreconditionResult(True)

        if followups.was_expedited(material_id):
            return PreconditionResult(False, f"物料 {material_id} 近期已催过，勿重复催料")

        results = await kitting.check()
        shorted = {s.material_id for r in results for s in r.shortages}
        if material_id not in shorted:
            return PreconditionResult(False, f"物料 {material_id} 当前不缺料，无需催料")

        return PreconditionResult(True)

    return precondition
