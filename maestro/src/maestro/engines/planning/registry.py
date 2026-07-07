"""策略注册表。

启动时注册所有策略实例；新策略只需注册一次即可被选择器发现 (开闭原则)。
"""

import logging

from maestro.engines.planning.strategies.base import PlanningStrategy

logger = logging.getLogger(__name__)


class StrategyRegistry:
    def __init__(self):
        self._strategies: dict[str, PlanningStrategy] = {}

    def register(self, strategy: PlanningStrategy) -> None:
        if not strategy.name:
            raise ValueError("策略必须定义 name")
        if strategy.name in self._strategies:
            raise ValueError(f"策略 {strategy.name} 已注册")
        self._strategies[strategy.name] = strategy
        logger.info("[STRATEGY] 注册策略: %s (%s)", strategy.name, strategy.objective_type)

    def get(self, name: str) -> PlanningStrategy:
        if name not in self._strategies:
            raise KeyError(f"策略 {name} 未注册")
        return self._strategies[name]

    def has(self, name: str) -> bool:
        return name in self._strategies

    def list_all(self) -> list[PlanningStrategy]:
        return list(self._strategies.values())

    def find_by_product_line(self, product_line: str) -> list[PlanningStrategy]:
        return [
            s
            for s in self._strategies.values()
            if product_line in s.applicable_product_lines or "*" in s.applicable_product_lines
        ]
