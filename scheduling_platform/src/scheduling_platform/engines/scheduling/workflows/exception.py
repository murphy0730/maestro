"""异常处置 workflow — Agent 做分诊+辅助，不做全自动决策。

分类定级 (LLM+规则) → 影响分析 (查数据+计算) → 处置建议 (候选方案返回给人选择)
→ 通知协调 (写操作经 AuthZ, requires_confirmation) → 复盘沉淀 (骨架: 结构化记录)。
关键决策必须留人: Agent 只给建议和影响分析，执行需确认。
"""

import json
import logging
from datetime import date, timedelta

from scheduling_platform.domain.models import PendingAction, ProductionException
from scheduling_platform.engines.scheduling.schemas import ExceptionAssessment
from scheduling_platform.foundation.audit import AuditLog
from scheduling_platform.foundation.authz import ActionGate
from scheduling_platform.foundation.integration.base import IntegrationAdapter
from scheduling_platform.foundation.llm import LLMClient, LLMError

logger = logging.getLogger(__name__)

ASSESS_SYSTEM = """你是生产异常分诊员。把异常归类 (equipment/material/quality/personnel/process)
并判定紧急度 (low/medium/high/critical)。判断依据: 是否停线、影响范围、交期威胁。"""

# 处置建议规则表: 异常类型 → 候选方案 (返回给人选择，不自动执行)
PROPOSAL_RULES: dict[str, list[str]] = {
    "equipment": [
        "通知设备维修立即到场，受影响任务令暂挂",
        "将受影响订单改派到可用产线 (需触发重排 → 转排产引擎)",
        "等待修复后按原计划继续，接受交期延迟",
    ],
    "material": [
        "触发催料闭环 (齐套检查 + 催料)",
        "调整任务令顺序，先做物料齐套的订单",
        "部分数量先行生产，缺口到货后补单",
    ],
    "quality": [
        "通知质检到场判定，受影响批次暂扣",
        "追溯同批次物料/在制品并隔离",
        "降级/让步接收 (需质量负责人审批)",
    ],
    "personnel": ["调配其他班组顶岗", "调整排班/加班", "降低当日产能目标并重排"],
    "process": ["通知工艺工程师到场分析", "回退到上一版工艺参数", "暂停该工序并隔离在制品"],
}

NOTIFY_TARGETS: dict[str, str] = {
    "equipment": "设备维修-赵工",
    "material": "采购主管-钱进",
    "quality": "质量负责人-孙莉",
    "personnel": "生产主管-周强",
    "process": "工艺工程师-吴敏",
}


class ExceptionWorkflow:
    def __init__(
        self,
        adapter: IntegrationAdapter,
        gate: ActionGate,
        audit: AuditLog,
        llm: LLMClient,
    ):
        self._adapter = adapter
        self._gate = gate
        self._audit = audit
        self._llm = llm
        self.case_log: list[dict] = []  # 复盘沉淀骨架 (TODO(v0.2): 存入记忆/知识库)

    async def handle(self, exc: ProductionException) -> dict:
        # 1) 分类与定级 (LLM, 失败降级关键词规则)
        assessment = await self._assess(exc)

        # 2) 影响分析: 受影响任务令 + 受威胁订单交期
        affected_wos = []
        if exc.affected_wo_ids:
            affected_wos = await self._adapter.get_work_orders({"wo_ids": exc.affected_wo_ids})
        threatened_orders = []
        if affected_wos:
            orders = await self._adapter.get_orders(
                {"order_ids": [w.order_id for w in affected_wos]}
            )
            deadline = date.today() + timedelta(days=7)
            threatened_orders = [o for o in orders if o.due_date <= deadline]

        # 3) 处置建议: 候选方案返回给人选择，不自动执行关键决策
        proposals = PROPOSAL_RULES[assessment.type]

        # 4) 通知协调: 写操作经 AuthZ (requires_confirmation)，确认后才发
        pending: list[PendingAction] = []
        recipient = NOTIFY_TARGETS[assessment.type]
        content = (
            f"[{assessment.severity.upper()}] 生产异常 {exc.exception_id}: {exc.description} "
            f"(类型: {assessment.type}, 受影响任务令: {', '.join(exc.affected_wo_ids) or '待确认'})，请尽快到场处理。"
        )
        gate_result = await self._gate.request(
            "send_notification",
            description=f"通知 {recipient} 到场处置异常 {exc.exception_id}",
            params={"exception_id": exc.exception_id, "recipient": recipient, "content": content},
            executor=lambda: self._adapter.send_message(recipient, "im", content),
        )
        if gate_result.action:
            pending.append(gate_result.action)

        # 5) 复盘沉淀 (骨架): 结构化记录时间线
        case = {
            "exception": exc.model_dump(mode="json"),
            "assessment": assessment.model_dump(),
            "affected_work_orders": [w.wo_id for w in affected_wos],
            "threatened_orders": [
                {"order_id": o.order_id, "due_date": o.due_date.isoformat()} for o in threatened_orders
            ],
            "proposals": proposals,
        }
        self.case_log.append(case)
        self._audit.record(
            actor="system",
            action="exception_handled",
            params={"exception_id": exc.exception_id, "description": exc.description},
            result={
                "type": assessment.type,
                "severity": assessment.severity,
                "affected": [w.wo_id for w in affected_wos],
            },
        )
        return {**case, "pending_actions": pending}

    async def _assess(self, exc: ProductionException) -> ExceptionAssessment:
        try:
            return await self._llm.classify(
                ASSESS_SYSTEM, json.dumps(exc.model_dump(mode="json"), ensure_ascii=False),
                ExceptionAssessment,
            )
        except LLMError:
            return self._rule_assess(exc)

    @staticmethod
    def _rule_assess(exc: ProductionException) -> ExceptionAssessment:
        text = exc.description
        if any(k in text for k in ("报警", "停机", "设备", "压力", "温度", "故障")):
            return ExceptionAssessment(type="equipment", severity="high", reason="关键词规则: 设备类")
        if any(k in text for k in ("缺料", "物料", "断料")):
            return ExceptionAssessment(type="material", severity="medium", reason="关键词规则: 物料类")
        if any(k in text for k in ("质量", "不良", "报废")):
            return ExceptionAssessment(type="quality", severity="high", reason="关键词规则: 质量类")
        if any(k in text for k in ("请假", "缺勤", "人员")):
            return ExceptionAssessment(type="personnel", severity="medium", reason="关键词规则: 人员类")
        return ExceptionAssessment(type="process", severity="medium", reason="关键词规则: 默认工艺类")
