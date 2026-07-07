"""策略选择层 — 与 Orchestrator 路由同构: 规则优先、LLM 兜底、低置信澄清。

第 1 层: strategy_mapping.yaml 规则映射 (确定且可审计)
第 2 层: LLM 辅助选择 (把已注册策略的 name + scenario_description 喂给 LLM)
第 3 层: 低置信 → 澄清「这批单属于哪种排产场景?」。宁可问一次，不可选错一次。
"""

import logging
from pathlib import Path

import yaml

from maestro.engines.planning.registry import StrategyRegistry
from maestro.engines.planning.schemas import (
    PlanningRequest,
    SelectionOutcome,
    StrategySelection,
)
from maestro.foundation.llm import LLMClient, LLMError

logger = logging.getLogger(__name__)

DEFAULT_MAPPING_PATH = Path(__file__).with_name("strategy_mapping.yaml")

SELECT_SYSTEM = """你是排产策略选择器。根据用户的排产请求，从候选策略中选出最合适的一个。
每个策略的适用场景如下:

{catalog}

返回 strategy_name 必须是候选策略名之一；confidence 为 0~1，没把握就给低分。"""


class StrategySelector:
    def __init__(
        self,
        registry: StrategyRegistry,
        llm: LLMClient,
        confidence_threshold: float = 0.7,
        mapping_path: Path | None = None,
    ):
        self._registry = registry
        self._llm = llm
        self._threshold = confidence_threshold
        path = mapping_path or DEFAULT_MAPPING_PATH
        self._mapping: list[dict] = yaml.safe_load(path.read_text(encoding="utf-8")) or []

    async def select(self, request: PlanningRequest) -> SelectionOutcome:
        # ── 第 1 层: 规则映射 ─────────────────────────────────
        for rule in self._mapping:
            match = rule.get("match", {})
            name = rule.get("strategy", "")
            pl = match.get("product_line")
            if pl == "*":
                # 兜底仅在产品线已识别时生效；未知交给 LLM/澄清
                if not request.product_line:
                    continue
            elif pl != request.product_line:
                continue
            if (sc := match.get("scenario")) and sc != request.scenario:
                continue
            if not self._registry.has(name):
                logger.warning("[SELECT] 映射表策略 %s 未注册，跳过", name)
                continue
            logger.info("[SELECT] rule → %s (product_line=%s)", name, request.product_line)
            return SelectionOutcome(
                strategy_name=name,
                method="rule",
                confidence=1.0,
                reason=f"规则映射命中: product_line={request.product_line}, scenario={request.scenario}",
            )

        # ── 第 2 层: LLM 辅助选择 ─────────────────────────────
        candidates = self._registry.list_all()
        catalog = "\n".join(
            f"- {s.name}: {s.scenario_description} (目标: {s.objective_type})" for s in candidates
        )
        try:
            sel = await self._llm.classify(
                SELECT_SYSTEM.format(catalog=catalog),
                f"排产请求: {request.model_dump_json()}",
                StrategySelection,
            )
            if sel.confidence >= self._threshold and self._registry.has(sel.strategy_name):
                logger.info("[SELECT] llm → %s conf=%.2f", sel.strategy_name, sel.confidence)
                return SelectionOutcome(
                    strategy_name=sel.strategy_name,
                    method="llm",
                    confidence=sel.confidence,
                    reason=sel.reason,
                )
            reason = f"LLM 选择置信度不足或策略未注册: {sel.strategy_name} conf={sel.confidence}"
        except LLMError as e:
            reason = f"规则未命中且 LLM 选择不可用: {e}"

        # ── 第 3 层: 低置信 → 澄清 ───────────────────────────
        logger.info("[SELECT] 需澄清: %s", reason)
        return SelectionOutcome(
            method="none",
            confidence=0.0,
            reason=reason,
            needs_clarification=True,
            candidates=[f"{s.name}: {s.scenario_description}" for s in candidates],
        )
