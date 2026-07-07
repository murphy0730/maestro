"""意图路由器: 嵌入语义路由 → LLM 结构化分类 → (低置信交澄清)。

分层 (设计文档 5.2，嵌入路由替换原规则预筛):
  第 1 层  嵌入语义路由: 向量相似度高且可区分 → 直接路由 (route_method=embedding)
  第 2 层  LLM 结构化分类: 嵌入低置信/不可用时调用 (route_method=llm)
  第 3 层  置信度门控 + 澄清: 由 Orchestrator 据 confidence 决定；嵌入与 LLM 都
           不可用时降级为 ambiguous (route_method=fallback) 触发澄清

澄清后的「直接路由」在 Orchestrator 内处理 (不再回到本路由器)。
实体抽取 (订单/任务令/产线) 各路径统一复用 extract_entities。
"""

import json
import logging
import re

from maestro.config import Settings
from maestro.foundation.llm import LLMClient, LLMError
from maestro.orchestrator.embedding_router import EmbeddingRouter
from maestro.orchestrator.schemas import RouteDecision

logger = logging.getLogger(__name__)

CLASSIFY_SYSTEM = """你是生产计划/调度平台的意图分类器。把用户输入分为四类:

- planning: 排产意图 —— 需要重新求解生产计划(排程/重排/优化排程)。
- scheduling: 调度执行意图 —— 围绕既有计划的执行: 齐套检查、催料、任务令下发、异常处置。
- query: 纯数据查询，不需要求解也不需要执行动作。
- ambiguous: 无法判断。

易混淆对照例句(务必参考):
| 用户输入 | 正确意图 | 区别点 |
| 把这批订单重新排一下 | planning | 要重新求解计划 |
| 把今天的任务令下发了 | scheduling | 执行动作，不重排 |
| 2号线停了，重排 | planning | 触发重新求解 |
| 2号线那批料齐了吗 | scheduling | 查齐套状态 |
| 哪些任务因为缺料开不了工 | scheduling | 齐套+异常查询 |
| 帮这批单优化一下排程 | planning | 求解优化 |
| 给供应商催一下 A 物料 | scheduling | 催料动作 |

entities 中抽取关键实体，键名约定: order_ids(订单号列表)、wo_ids(任务令号列表)、
line_ids(产线号列表)、materials(物料列表)。
confidence 为 0~1 的判定置信度，没把握就给低分并倾向 ambiguous。"""


def _classify_system(skill_candidates: list[tuple[str, str]]) -> str:
    """LLM 分类系统提示: 无技能时逐字节等于 CLASSIFY_SYSTEM (零行为变更),
    有可路由技能时追加技能候选清单 + skill intent 填充指引。"""
    if not skill_candidates:
        return CLASSIFY_SYSTEM
    block = "\n".join(f"- skill:{name}: {desc}" for name, desc in skill_candidates)
    return (
        CLASSIFY_SYSTEM
        + "\n\n此外有可路由的「技能(skill)」用于长尾流程化任务:\n"
        + block
        + '\n若匹配某技能，intent 填 "skill"，skill_id 填该技能 name。'
    )


def extract_entities(message: str) -> dict:
    """正则抽取常见实体 (订单/任务令/产线)，作为各路由路径的实体补充。"""
    entities: dict = {}
    if order_ids := re.findall(r"(?<![A-Z0-9-])O\d{3,}", message):
        entities["order_ids"] = order_ids
    if wo_ids := re.findall(r"WO-\d+", message):
        entities["wo_ids"] = wo_ids
    line_ids = re.findall(r"(?<![A-Z])L\d+", message)
    line_ids += [f"L{n}" for n in re.findall(r"(\d+)\s*号线", message)]
    if line_ids:
        entities["line_ids"] = list(dict.fromkeys(line_ids))
    return entities


class IntentRouter:
    def __init__(
        self, llm: LLMClient, settings: Settings, embed_router: EmbeddingRouter | None = None,
        skills=None,
    ):
        self._llm = llm
        self._settings = settings
        self._embed = embed_router
        self._skills = skills

    def _skill_candidates(self) -> list[tuple[str, str]]:
        if self._skills is None:
            return []
        return [(m.name, m.description) for m in self._skills.routable()]

    async def route(
        self,
        message: str,
        history: list[dict] | None = None,
        current_engine: str | None = None,
        skip_embedding: bool = False,
    ) -> RouteDecision:
        """skip_embedding=True 时跳过第 1 层直接走 LLM 分类 (用于澄清后的开放式回答:
        已是疑难案例，按设计文档回到 LLM 层，不再走嵌入)。"""
        entities = extract_entities(message)

        # ── 第 1 层: 嵌入语义路由 ─────────────────────────────
        if not skip_embedding and self._embed and self._embed.available:
            try:
                result = await self._embed.classify(message)
                if (
                    result.intent != "ambiguous"
                    and result.score >= self._settings.embed_confidence_threshold
                    and result.confident
                ):
                    logger.info(
                        "[ROUTE] embedding → %s score=%.2f", result.intent, result.score
                    )
                    if result.intent.startswith("skill:"):
                        return RouteDecision(
                            intent="skill",
                            skill_id=result.intent.split(":", 1)[1],
                            confidence=round(result.score, 3),
                            entities=entities,
                            reason=f"嵌入语义路由 (score={result.score:.2f})",
                            route_method="embedding",
                        )
                    return RouteDecision(
                        intent=result.intent,
                        confidence=round(result.score, 3),
                        entities=entities,
                        reason=(
                            f"嵌入语义路由 (score={result.score:.2f}, "
                            f"margin={result.margin:.2f})"
                        ),
                        route_method="embedding",
                    )
                logger.info(
                    "[ROUTE] embedding 低置信 (score=%.2f margin=%.2f) → LLM 分类",
                    result.score, result.margin,
                )
            except LLMError as e:
                logger.warning("[ROUTE] embedding 不可用 → LLM 分类: %s", e)

        # ── 第 2 层: LLM 结构化分类 ───────────────────────────
        if self._llm.available:
            try:
                decision = await self._llm.classify(
                    _classify_system(self._skill_candidates()),
                    self._build_input(message, history, current_engine), RouteDecision
                )
                decision.route_method = "llm"
                for k, v in entities.items():  # 正则实体兜底合并
                    decision.entities.setdefault(k, v)
                if decision.intent == "skill" and self._skills is not None:
                    routable_names = {m.name for m in self._skills.routable()}
                    if decision.skill_id not in routable_names:
                        decision = RouteDecision(
                            intent="ambiguous", confidence=0.0,
                            entities=decision.entities,
                            reason=f"LLM 选择了不存在的技能 {decision.skill_id}",
                            route_method="llm",
                        )
                logger.info(
                    "[ROUTE] llm → %s conf=%.2f reason=%s",
                    decision.intent, decision.confidence, decision.reason,
                )
                return decision
            except LLMError as e:
                logger.warning("[ROUTE] LLM 分类失败，降级为 ambiguous: %s", e)

        # ── 降级: 嵌入与 LLM 均不可用/低置信 → ambiguous → 澄清 ──
        return RouteDecision(
            intent="ambiguous",
            confidence=0.0,
            entities=entities,
            reason="嵌入与 LLM 分类均不可用或低置信",
            route_method="fallback",
        )

    @staticmethod
    def _build_input(message: str, history: list[dict] | None, current_engine: str | None) -> str:
        # TODO(v0.2): 会话粘性 —— 延续性短句优先归当前会话引擎
        context_lines = []
        if history:
            context_lines.append("最近对话:\n" + json.dumps(history[-6:], ensure_ascii=False))
        if current_engine:
            context_lines.append(f"当前会话所处引擎: {current_engine}")
        return "\n\n".join([*context_lines, f"用户输入: {message}"])
