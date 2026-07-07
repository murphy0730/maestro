"""排产引擎 — 只管编排: 抽参 → 选策略 → 跑策略 → 校验 → 解释。

关键约束:
- 计算只能由策略的 solve 做，不允许 LLM 直接生成排程结果。
- 引擎本体不 import 任何具体策略类，只通过 StrategyRegistry 取用 (可插拔)。
- 策略选择决策全部进 AuditLog。
"""

import asyncio
import json
import logging
from datetime import date

from maestro.engines.base import Engine, EngineResponse, ProgressFn, emit_progress
from maestro.engines.planning.extractor import PlanningExtractor
from maestro.engines.planning.registry import StrategyRegistry
from maestro.engines.planning.schemas import (
    PlanningData,
    PlanningRequest,
    PlanningResult,
    ValidationReport,
)
from maestro.engines.planning.selector import StrategySelector
from maestro.engines.planning.validator import PlanValidator
from maestro.foundation.audit import AuditLog
from maestro.foundation.llm import LLMClient, LLMError
from maestro.foundation.master_data import MasterDataService
from maestro.foundation.memory import ConversationMemory

logger = logging.getLogger(__name__)

EXPLAIN_SYSTEM = (
    "你是排产结果解释员。根据求解结果、校验报告与策略要点，用简洁的中文向"
    "生产计划员解释这份排程: 用了什么策略、每个订单排在哪条线什么时间、"
    "是否有拖期及原因、校验是否通过。不要编造数据。"
)


class PlanningEngine(Engine):
    name = "planning"

    def __init__(
        self,
        extractor: PlanningExtractor,
        selector: StrategySelector,
        registry: StrategyRegistry,
        master_data: MasterDataService,
        validator: PlanValidator,
        llm: LLMClient,
        audit: AuditLog,
        memory: ConversationMemory,
    ):
        self._extractor = extractor
        self._selector = selector
        self._registry = registry
        self._master = master_data
        self._validator = validator
        self._llm = llm
        self._audit = audit
        self._memory = memory

    async def handle_chat(
        self,
        message: str,
        entities: dict,
        session_id: str,
        history: list[dict] | None = None,
        on_progress: ProgressFn | None = None,
    ) -> EngineResponse:
        # 固定工作流，不使用多轮 history
        # 1) 抽参
        await emit_progress(on_progress, "解析排产参数…")
        request = await self._extractor.extract(message, entities)

        # 2) 加载数据快照
        orders = await self._master.get_orders(request.order_ids or None)
        if not orders:
            return EngineResponse(reply="没有找到可排产的订单，请确认订单号或订单状态。")
        lines = await self._master.get_lines(request.product_line)
        if not lines:
            lines = await self._master.get_lines()
        data = PlanningData(orders=orders, lines=lines, today=date.today())

        # 3) 选策略 (规则映射优先, LLM 辅助, 低置信澄清)
        await emit_progress(on_progress, "选择排产策略…")
        selection = await self._selector.select(request)
        self._audit.record(
            actor=session_id,
            action="strategy_selection",
            params={"request": request.model_dump(mode="json")},
            result={
                "strategy": selection.strategy_name,
                "method": selection.method,
                "confidence": selection.confidence,
                "reason": selection.reason,
            },
        )
        if selection.needs_clarification:
            return EngineResponse(
                reply=(
                    "这批单属于哪种排产场景？我有以下候选策略，请告诉我产品线或场景:\n"
                    + "\n".join(f"- {c}" for c in selection.candidates)
                ),
                needs_clarification=True,
                clarification_options=selection.candidates,
            )

        strategy = self._registry.get(selection.strategy_name)  # type: ignore[arg-type]

        # 4) 策略特有输入校验
        input_report = strategy.validate_input(request, data)
        if not input_report.passed:
            return EngineResponse(
                reply="排产输入不完备，无法求解:\n" + "\n".join(f"- {i}" for i in input_report.issues),
                data={"input_validation": input_report.model_dump()},
            )

        # 5) 求解 (计算只由策略做；CP-SAT 为阻塞调用，放线程池)
        await emit_progress(on_progress, f"求解中 ({strategy.name})…")
        result = await asyncio.to_thread(strategy.solve, request, data)
        self._audit.record(
            actor=session_id,
            action="planning_solve",
            params={"strategy": strategy.name, "orders": [o.order_id for o in orders]},
            result={"status": result.status, "objective": result.objective_value},
        )
        if result.status == "infeasible":
            return EngineResponse(
                reply=f"无法生成可行排程: {result.infeasible_reason}",
                data={"plan": result.model_dump(mode="json")},
            )

        # 6) 通用硬约束校验 (不信任求解器，二次确认)
        await emit_progress(on_progress, "校验排程并生成解释…")
        report = self._validator.validate(result, request, data)

        # 7) LLM 解释 (失败降级为模板)
        reply = await self._explain(result, report, strategy.explain_hints(result))

        # 8) 结果写入共享底座 (初始版本存会话记忆; TODO(v0.2): 供调度引擎读取下发)
        self._memory.set_context(session_id, "last_planning_result", result.model_dump(mode="json"))

        return EngineResponse(
            reply=reply,
            data={"plan": result.model_dump(mode="json"), "validation": report.model_dump()},
        )

    async def _explain(
        self, result: PlanningResult, report: ValidationReport, hints: dict
    ) -> str:
        fallback = self._template_explain(result, report)
        try:
            payload = {
                "result": result.model_dump(mode="json"),
                "validation": report.model_dump(),
                "strategy_hints": hints,
            }
            return await self._llm.complete(
                EXPLAIN_SYSTEM,
                [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            )
        except LLMError:
            return fallback

    @staticmethod
    def _template_explain(result: PlanningResult, report: ValidationReport) -> str:
        lines = [
            f"排产完成 (策略: {result.strategy_name}, 解状态: {result.status})",
            "排程明细:",
        ]
        for a in result.assignments:
            tard = f"，拖期 {a.tardiness_days} 天" if a.tardiness_days > 0 else "，按期"
            lines.append(
                f"- {a.order_id} → {a.line_id}: {a.start_date} ~ {a.end_date} (交期 {a.due_date}{tard})"
            )
        if result.kpis:
            lines.append(f"关键指标: {json.dumps(result.kpis, ensure_ascii=False)}")
        lines.append("校验: " + ("通过" if report.passed else "未通过 → " + "; ".join(report.issues)))
        return "\n".join(lines)
