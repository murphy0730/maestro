"""主数据访问层。

对 IntegrationAdapter 的读接口做薄封装，提供引擎常用的便捷查询。
"""

from maestro.domain.models import Order, ProductionLine
from maestro.foundation.integration.base import IntegrationAdapter


class MasterDataService:
    def __init__(self, adapter: IntegrationAdapter):
        self._adapter = adapter

    async def get_orders(self, order_ids: list[str] | None = None) -> list[Order]:
        filters = {"order_ids": order_ids} if order_ids else {"status": "open"}
        return await self._adapter.get_orders(filters)

    async def get_lines(self, product_line: str | None = None) -> list[ProductionLine]:
        lines = await self._adapter.get_lines()
        if product_line:
            lines = [l for l in lines if l.product_line == product_line]
        return lines

    async def known_product_lines(self) -> list[str]:
        """全部已知产品线类别 (供抽参/选策略使用)。"""
        lines = await self._adapter.get_lines()
        seen: list[str] = []
        for l in lines:
            if l.product_line and l.product_line not in seen:
                seen.append(l.product_line)
        return seen
