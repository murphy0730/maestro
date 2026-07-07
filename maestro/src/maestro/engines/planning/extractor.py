"""自然语言 → 排产参数抽取 (含产品线/场景)。

优先 LLM 结构化抽取；LLM 不可用时降级为正则/关键词抽取，保证平台可运行。
"""

import logging
import re

from maestro.engines.planning.schemas import PlanningRequest
from maestro.foundation.llm import LLMClient, LLMError
from maestro.foundation.master_data import MasterDataService

logger = logging.getLogger(__name__)

EXTRACT_SYSTEM = """你是排产参数抽取器。从用户请求中抽取结构化排产请求:
- order_ids: 明确提到的订单号 (如 O001)；没提到则留空列表(表示全部待排订单)。
- line_ids: 明确指定使用的产线号 (如 L1)；"N号线"映射为"LN"。
- product_line: 产品线类别，必须取自已知列表: {product_lines}；判断不出则为 null。
- scenario: 场景特征 (如"保质期敏感"/"换型频繁"/"紧急插单")；没有则为 null。
- objective: 排产目标，如 min_tardiness(少拖期)/min_makespan(最快完工)；没说则为 null。
- excluded_lines: 用户说不可用/停机/排除的产线号列表。
- locked_assignments: 留空列表 (迭代锁定功能 v0.2)。"""


class PlanningExtractor:
    def __init__(self, llm: LLMClient, master_data: MasterDataService):
        self._llm = llm
        self._master = master_data

    async def extract(self, message: str, entities: dict | None = None) -> PlanningRequest:
        entities = entities or {}
        known = await self._master.known_product_lines()
        try:
            request = await self._llm.classify(
                EXTRACT_SYSTEM.format(product_lines=known), message, PlanningRequest
            )
            logger.info("[EXTRACT] llm → %s", request.model_dump_json())
        except LLMError as e:
            logger.warning("[EXTRACT] LLM 不可用，降级为正则抽取: %s", e)
            request = self._regex_extract(message, known)
            logger.info("[EXTRACT] regex → %s", request.model_dump_json())
        # 路由层实体兜底合并
        if not request.order_ids and entities.get("order_ids"):
            request.order_ids = entities["order_ids"]
        return request

    @staticmethod
    def _regex_extract(message: str, known_product_lines: list[str]) -> PlanningRequest:
        order_ids = re.findall(r"(?<![A-Z0-9-])O\d{3,}", message)
        # 产品线: 长名优先匹配 (避免 "SMT" 抢先命中 "SMT贴片")
        product_line = next(
            (pl for pl in sorted(known_product_lines, key=len, reverse=True) if pl in message),
            None,
        )
        line_ids = re.findall(r"(?<![A-Z])L\d+", message)
        line_ids += [f"L{n}" for n in re.findall(r"(\d+)\s*号线", message)]
        excluded = [
            f"L{n}" for n in re.findall(r"(\d+)\s*号线(?:停|坏|不能用|不可用|检修)", message)
        ]
        line_ids = [l for l in dict.fromkeys(line_ids) if l not in excluded]
        objective = None
        if re.search(r"拖期|延误|交期", message):
            objective = "min_tardiness"
        elif re.search(r"完工|最快|尽快做完", message):
            objective = "min_makespan"
        return PlanningRequest(
            order_ids=order_ids,
            line_ids=line_ids,
            product_line=product_line,
            objective=objective,
            excluded_lines=excluded,
        )
