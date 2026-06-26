"""排产引擎测试: 策略求解 / 选择层 / 插件机制 / 端到端。"""

from datetime import date

from conftest import FakeLLM

from scheduling_platform.bootstrap import build_platform
from scheduling_platform.engines.planning.registry import StrategyRegistry
from scheduling_platform.engines.planning.schemas import (
    PlanningData,
    PlanningRequest,
    PlanningResult,
    StrategySelection,
    ValidationReport,
)
from scheduling_platform.engines.planning.selector import StrategySelector
from scheduling_platform.engines.planning.strategies.base import PlanningStrategy
from scheduling_platform.engines.planning.strategies.flowshop_tardiness import FlowShopTardiness
from scheduling_platform.engines.planning.strategies.jobshop_makespan import JobShopMakespan
from scheduling_platform.engines.planning.strategies.simple_dispatch import SimpleDispatch
from scheduling_platform.engines.planning.validator import PlanValidator


def make_registry() -> StrategyRegistry:
    registry = StrategyRegistry()
    registry.register(FlowShopTardiness())
    registry.register(JobShopMakespan())
    registry.register(SimpleDispatch())
    return registry


async def planning_data(adapter, order_ids: list[str]) -> PlanningData:
    orders = await adapter.get_orders({"order_ids": order_ids})
    lines = await adapter.get_lines()
    return PlanningData(orders=orders, lines=lines, today=date.today())


# ── 策略求解 ─────────────────────────────────────────────────


async def test_flowshop_tardiness_solves(adapter):
    data = await planning_data(adapter, ["O001", "O002", "O003"])
    result = FlowShopTardiness().solve(PlanningRequest(), data)
    assert result.status in ("optimal", "feasible")
    assert len(result.assignments) == 3
    report = PlanValidator().validate(result, PlanningRequest(), data)
    assert report.passed, report.issues


async def test_jobshop_makespan_solves(adapter):
    data = await planning_data(adapter, ["O001", "O002", "O003"])
    result = JobShopMakespan().solve(PlanningRequest(), data)
    assert result.status in ("optimal", "feasible")
    assert result.kpis["makespan_days"] >= 1
    assert PlanValidator().validate(result, PlanningRequest(), data).passed


async def test_simple_dispatch_rule_strategy(adapter):
    """非优化类算法 (EDD 规则) 与 OR-Tools 策略平等共存。"""
    data = await planning_data(adapter, ["O004"])
    result = SimpleDispatch().solve(PlanningRequest(), data)
    assert result.status == "feasible"
    assert result.assignments[0].line_id == "L3"
    assert PlanValidator().validate(result, PlanningRequest(), data).passed


async def test_infeasible_when_no_compatible_line(adapter):
    data = await planning_data(adapter, ["O001"])
    request = PlanningRequest(excluded_lines=["L1", "L2"])  # 注塑线全排除
    result = FlowShopTardiness().solve(request, data)
    assert result.status == "infeasible"
    assert "O001" in (result.infeasible_reason or "")


# ── 策略选择层 ───────────────────────────────────────────────


async def test_selector_rule_mapping():
    selector = StrategySelector(make_registry(), FakeLLM())
    outcome = await selector.select(PlanningRequest(product_line="注塑"))
    assert outcome.strategy_name == "JobShopMakespan"
    assert outcome.method == "rule"


async def test_selector_wildcard_fallback():
    selector = StrategySelector(make_registry(), FakeLLM())
    outcome = await selector.select(PlanningRequest(product_line="总装"))
    assert outcome.strategy_name == "FlowShopTardiness"
    assert outcome.method == "rule"


async def test_selector_llm_assist_when_product_line_unknown():
    llm = FakeLLM(
        classify_map={
            StrategySelection: StrategySelection(
                strategy_name="FlowShopTardiness", confidence=0.9, reason="交期敏感"
            )
        }
    )
    selector = StrategySelector(make_registry(), llm)
    outcome = await selector.select(PlanningRequest())
    assert outcome.strategy_name == "FlowShopTardiness"
    assert outcome.method == "llm"


async def test_selector_clarifies_on_low_confidence():
    selector = StrategySelector(make_registry(), FakeLLM())  # LLM 不可用
    outcome = await selector.select(PlanningRequest())
    assert outcome.needs_clarification
    assert len(outcome.candidates) == 3


# ── 策略插件机制 (开闭原则验证) ───────────────────────────────


class DummyStrategy(PlanningStrategy):
    """新增策略 = 加一个类并注册，不动引擎和其它策略。"""

    name = "Dummy"
    applicable_product_lines = ["测试线"]
    scenario_description = "测试用"
    objective_type = "noop"

    def required_data(self):
        return []

    def validate_input(self, request, data):
        return ValidationReport()

    def solve(self, request, data):
        return PlanningResult(strategy_name=self.name, status="feasible")

    def explain_hints(self, result):
        return {}


async def test_strategy_plugin_registration():
    registry = make_registry()
    registry.register(DummyStrategy())
    assert registry.has("Dummy")
    assert len(registry.list_all()) == 4
    assert registry.find_by_product_line("测试线")


# ── 端到端 (LLM 全降级路径: 正则抽参 + 规则选策略 + 模板解释) ──


async def test_engine_end_to_end_offline(settings):
    # 嵌入路由判 planning；抽参/选策略/解释均走规则与模板降级 (LLM 仍 mock)
    platform = build_platform(settings=settings, llm=FakeLLM(embed=True))
    response = await platform.orchestrator.handle(
        "s1", "把注塑线的订单 O001,O002,O003 排一下，尽量别拖期"
    )
    assert response.route.intent == "planning"
    assert response.route.route_method == "embedding"
    plan = response.data["plan"]
    assert plan["strategy_name"] == "JobShopMakespan"  # 注塑 → 规则映射
    assert len(plan["assignments"]) == 3
    assert response.data["validation"]["passed"]
    # 策略选择决策进了审计
    assert platform.audit.query(action="strategy_selection")
