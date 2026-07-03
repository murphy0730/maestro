"""组装根 (composition root)。

唯一允许同时 import 三个引擎与具体策略/工具/护栏的地方；引擎本体不感知具体
策略，业务代码不感知具体适配器。FastAPI 与 CLI 共用此处的 build_platform()。

v0.2: 三引擎三范式 —
- 排产引擎 PlanningEngine: 固定工作流 (策略插件框架)。
- 调度引擎 SchedulingEngine: ReAct 智能体 (AgentLoop + 工具 + 两道写护栏)。
- 查询引擎 QueryEngine: RAG + LLM (向量库 + 只读工具)。
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
from scheduling_platform.engines.query.ingestor import KnowledgeIngestor
from scheduling_platform.engines.query.query_engine import QueryEngine
from scheduling_platform.engines.query.retriever import KnowledgeRetriever
from scheduling_platform.engines.scheduling.agent_loop import AgentLoop
from scheduling_platform.engines.scheduling.engine import SCHEDULING_SYSTEM, SchedulingEngine
from scheduling_platform.engines.scheduling.preconditions import (
    make_dispatch_precondition,
    make_expedite_precondition,
)
from scheduling_platform.events.event_bus import EventBus
from scheduling_platform.events.handlers import register_event_handlers
from scheduling_platform.events.scheduler import PatrolScheduler
from scheduling_platform.foundation.audit import AuditLog
from scheduling_platform.foundation.authz import ActionGate, AuthZ, PendingActionStore
from scheduling_platform.foundation.chunking import Chunker
from scheduling_platform.foundation.embedding import EmbeddingClient
from scheduling_platform.foundation.integration.base import IntegrationAdapter
from scheduling_platform.foundation.integration.mock_adapter import MockAdapter
from scheduling_platform.foundation.kitting import KittingService
from scheduling_platform.foundation.llm import LLMClient
from scheduling_platform.foundation.loaders import build_loader_registry
from scheduling_platform.foundation.master_data import MasterDataService
from scheduling_platform.foundation.memory import ConversationMemory
from scheduling_platform.foundation.session_store import SessionStore
from scheduling_platform.foundation.tools.builtin import (
    QUERY_READONLY_TOOLS,
    SCHEDULING_TOOLS,
    FollowupStore,
    register_builtin_tools,
)
from scheduling_platform.foundation.tools.registry import ToolRegistry
from scheduling_platform.foundation.vectorstore import VectorStore
from scheduling_platform.orchestrator.embedding_router import EmbeddingRouter, load_examples
from scheduling_platform.orchestrator.orchestrator import Orchestrator
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
    session_store: SessionStore
    llm: LLMClient
    tools: ToolRegistry
    strategy_registry: StrategyRegistry
    planning_engine: PlanningEngine
    scheduling_engine: SchedulingEngine
    query_engine: QueryEngine
    ingestor: KnowledgeIngestor
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
    session_store = SessionStore(settings.sessions_dir)
    memory = ConversationMemory(session_store)
    master = MasterDataService(adapter)
    kitting = KittingService(adapter, audit)
    followups = FollowupStore()

    # 工具库 (三引擎共享): 注册内置工具 + 为高危写操作挂前置断言 (两道写护栏之一)
    tools = ToolRegistry()
    register_builtin_tools(tools, adapter, gate, kitting, llm, followups)
    tools.attach_precondition("dispatch_work_order", make_dispatch_precondition(kitting, adapter))
    tools.attach_precondition("send_expedite_message", make_expedite_precondition(kitting, followups))

    # 调度引擎 (ReAct 智能体)
    agent = AgentLoop(
        llm, tools, pending, audit, SCHEDULING_SYSTEM, SCHEDULING_TOOLS, settings.react_max_steps
    )
    scheduling_engine = SchedulingEngine(agent, kitting, audit)

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

    # 查询引擎 (RAG + LLM): 向量库 + 摄取管线 + 知识检索器 + 只读工具
    # embedding 与 llm 均复用同一份配置 (Settings.embed_* / llm_*)，此处只注入实例。
    embedder = EmbeddingClient(llm)
    vectorstore = VectorStore(embedder)
    loaders = build_loader_registry()
    chunker = Chunker()
    ingestor = KnowledgeIngestor(
        vectorstore, loaders, chunker, settings.knowledge_dir, settings.knowledge_upload_dir
    )
    retriever = KnowledgeRetriever(vectorstore, ingestor, settings.rag_top_k)
    query_engine = QueryEngine(
        llm, tools, retriever, adapter, QUERY_READONLY_TOOLS, settings.rag_top_k
    )

    # 统一入口
    embed_router = EmbeddingRouter(llm, load_examples())
    router = IntentRouter(llm, settings, embed_router)
    orchestrator = Orchestrator(
        router, planning_engine, scheduling_engine, query_engine, memory, audit, gate, settings
    )

    # 事件层 (事件唤醒调度引擎的 ReAct 智能体)
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
        session_store=session_store,
        llm=llm,
        tools=tools,
        strategy_registry=strategy_registry,
        planning_engine=planning_engine,
        scheduling_engine=scheduling_engine,
        query_engine=query_engine,
        ingestor=ingestor,
        orchestrator=orchestrator,
        bus=bus,
        patrol=patrol,
    )
