"""组装根 (composition root)。

唯一允许同时 import 两个引擎与具体策略类的地方；引擎本体不感知具体策略，
业务代码不感知具体适配器。FastAPI 与 CLI 共用此处的 build_platform()。
"""

import logging
from dataclasses import dataclass

from scheduling_platform.config import Settings
from scheduling_platform.engines.planning.engine import PlanningEngine
from scheduling_platform.engines.planning.extractor import PlanningExtractor
from scheduling_platform.engines.planning.registry import StrategyRegistry
from scheduling_platform.engines.planning.selector import StrategySelector
from scheduling_platform.engines.planning.strategies.flowshop_tardiness import FlowShopTardiness
from scheduling_platform.engines.planning.strategies.jobshop_makespan import JobShopMakespan
from scheduling_platform.engines.planning.strategies.simple_dispatch import SimpleDispatch
from scheduling_platform.engines.planning.validator import PlanValidator
from scheduling_platform.engines.scheduling.engine import SchedulingEngine
from scheduling_platform.engines.scheduling.workflows.dispatch import DispatchWorkflow
from scheduling_platform.engines.scheduling.workflows.exception import ExceptionWorkflow
from scheduling_platform.engines.scheduling.workflows.expediting import ExpeditingWorkflow
from scheduling_platform.engines.scheduling.workflows.kitting import KittingWorkflow
from scheduling_platform.events.event_bus import EventBus
from scheduling_platform.events.handlers import register_event_handlers
from scheduling_platform.events.scheduler import PatrolScheduler
from scheduling_platform.foundation.audit import AuditLog
from scheduling_platform.foundation.authz import ActionGate, AuthZ, PendingActionStore
from scheduling_platform.foundation.integration.base import IntegrationAdapter
from scheduling_platform.foundation.integration.mock_adapter import MockAdapter
from scheduling_platform.foundation.llm import LLMClient
from scheduling_platform.foundation.master_data import MasterDataService
from scheduling_platform.foundation.memory import ConversationMemory
from scheduling_platform.foundation.tools.builtin import register_builtin_tools
from scheduling_platform.foundation.tools.registry import ToolRegistry
from scheduling_platform.orchestrator.embedding_router import EmbeddingRouter, load_examples
from scheduling_platform.orchestrator.orchestrator import Orchestrator, QueryHandler
from scheduling_platform.orchestrator.router import IntentRouter


@dataclass
class Platform:
    settings: Settings
    adapter: IntegrationAdapter
    audit: AuditLog
    authz: AuthZ
    pending: PendingActionStore
    gate: ActionGate
    memory: ConversationMemory
    llm: LLMClient
    tools: ToolRegistry
    strategy_registry: StrategyRegistry
    planning_engine: PlanningEngine
    scheduling_engine: SchedulingEngine
    orchestrator: Orchestrator
    bus: EventBus
    patrol: PatrolScheduler


def build_platform(
    settings: Settings | None = None,
    llm: LLMClient | None = None,
    adapter: IntegrationAdapter | None = None,
) -> Platform:
    """构建并装配整个平台。llm/adapter 可注入替身 (测试用)。"""
    settings = settings or Settings()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )

    # 共享底座
    adapter = adapter or MockAdapter(settings.mock_data_dir)
    audit = AuditLog(settings.audit_log_file)
    authz = AuthZ()
    pending = PendingActionStore()
    gate = ActionGate(authz, pending, audit)
    llm = llm or LLMClient(
        settings.llm_base_url,
        settings.llm_api_key,
        settings.llm_model,
        settings.embed_base_url,
        settings.embed_api_key,
        settings.embed_model,
    )
    memory = ConversationMemory()
    master = MasterDataService(adapter)

    # 调度引擎 (四个 workflow)
    kitting = KittingWorkflow(adapter, audit)
    expediting = ExpeditingWorkflow(adapter, gate, audit, llm)
    dispatch = DispatchWorkflow(adapter, gate, audit, kitting)
    exception = ExceptionWorkflow(adapter, gate, audit, llm)
    scheduling_engine = SchedulingEngine(kitting, expediting, dispatch, exception, audit)

    # 排产引擎 (策略插件框架)
    strategy_registry = StrategyRegistry()
    strategy_registry.register(FlowShopTardiness())
    strategy_registry.register(JobShopMakespan())
    strategy_registry.register(SimpleDispatch())
    selector = StrategySelector(
        strategy_registry, llm, confidence_threshold=settings.strategy_confidence_threshold
    )
    extractor = PlanningExtractor(llm, master)
    planning_engine = PlanningEngine(
        extractor, selector, strategy_registry, master, PlanValidator(), llm, audit, memory
    )

    # 工具库 + 统一入口
    tools = ToolRegistry()
    register_builtin_tools(tools, adapter, gate, kitting)
    query_handler = QueryHandler(llm, tools, adapter)
    embed_router = EmbeddingRouter(llm, load_examples())
    router = IntentRouter(llm, settings, embed_router)
    orchestrator = Orchestrator(
        router, planning_engine, scheduling_engine, query_handler, memory, audit, gate, settings
    )

    # 事件层
    bus = EventBus()
    register_event_handlers(bus, scheduling_engine)
    patrol = PatrolScheduler(adapter, bus, kitting, settings)

    return Platform(
        settings=settings,
        adapter=adapter,
        audit=audit,
        authz=authz,
        pending=pending,
        gate=gate,
        memory=memory,
        llm=llm,
        tools=tools,
        strategy_registry=strategy_registry,
        planning_engine=planning_engine,
        scheduling_engine=scheduling_engine,
        orchestrator=orchestrator,
        bus=bus,
        patrol=patrol,
    )
