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

from maestro.config import Settings
from maestro.engines.planning.engine import PlanningEngine
from maestro.engines.planning.extractor import PlanningExtractor
from maestro.engines.planning.registry import StrategyRegistry
from maestro.engines.planning.selector import StrategySelector
from maestro.engines.planning.strategies.flowshop_tardiness import FlowShopTardiness
from maestro.engines.planning.strategies.jobshop_makespan import JobShopMakespan
from maestro.engines.planning.strategies.simple_dispatch import SimpleDispatch
from maestro.engines.planning.validator import PlanValidator
from maestro.engines.query.ingestor import KnowledgeIngestor
from maestro.engines.query.query_engine import QueryEngine
from maestro.engines.query.retriever import KnowledgeRetriever
from maestro.engines.scheduling.agent_loop import AgentLoop
from maestro.engines.scheduling.engine import SCHEDULING_SYSTEM, SchedulingEngine
from maestro.engines.scheduling.preconditions import (
    make_dispatch_precondition,
    make_expedite_precondition,
)
from maestro.events.event_bus import EventBus
from maestro.events.handlers import register_event_handlers
from maestro.events.scheduler import PatrolScheduler
from maestro.foundation.audit import AuditLog
from maestro.foundation.authz import ActionGate, AuthZ, PendingActionStore
from maestro.foundation.chunking import Chunker
from maestro.foundation.embedding import EmbeddingClient
from maestro.foundation.integration.base import IntegrationAdapter
from maestro.foundation.integration.mock_adapter import MockAdapter
from maestro.foundation.kitting import KittingService
from maestro.foundation.llm import LLMClient
from maestro.foundation import model_config as mc
from maestro.foundation.loaders import build_loader_registry
from maestro.foundation.master_data import MasterDataService
from maestro.foundation.memory import ConversationMemory
from maestro.foundation.observation_store import ObservationStore
from maestro.foundation.permissions import PermissionEngine
from maestro.foundation.session_store import SessionStore
from maestro.foundation.tools.builtin import (
    QUERY_READONLY_TOOLS,
    FollowupStore,
    register_builtin_tools,
    scheduling_tools,
)
from maestro.foundation.tools.registry import Precondition, ToolRegistry
from maestro.tools import ToolManager, ToolRegistry as FrameworkToolRegistry
from maestro.tools import initialize_tools as initialize_framework_tools
from maestro.tools.bridge import register_framework_tools
from maestro.foundation.vectorstore import VectorStore
from maestro.orchestrator.embedding_router import EmbeddingRouter, load_examples
from maestro.orchestrator.orchestrator import Orchestrator
from maestro.orchestrator.router import IntentRouter
from maestro.skills.engine import SkillEngine
from maestro.skills.store import SkillStore


@dataclass
class Platform:
    settings: Settings
    adapter: IntegrationAdapter
    audit: AuditLog
    authz: AuthZ
    pending: PendingActionStore
    gate: ActionGate
    observations: ObservationStore
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
    skill_store: SkillStore
    skill_engine: SkillEngine
    named_preconditions: dict[str, Precondition]


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
    # 统一权限引擎 (allow/deny/ask): 同一实例既作 ActionGate 的写动作决策来源,
    # 也供调度 ReAct 的 can_use_tool 层评估读/中性工具 (决策集中、可审计)。
    permissions = PermissionEngine()
    authz = AuthZ(engine=permissions)
    pending = PendingActionStore()
    gate = ActionGate(authz, pending, audit)
    # 工具观察离线暂存 (方案2): 大结果存 store, 上下文/轨迹只放 ref 句柄; 供 read_observation
    # 工具与 GET /observations/{ref} 取回。进程内、FIFO 淘汰。
    observations = ObservationStore(cap=settings.react_observation_store_max)
    # LLM 连接参数: 优先用 settings.json 中用户启用的 active provider (model_providers)，
    # 否则回退到扁平默认值 / 环境变量 (.env)。这样"设置弹框启用模型"后重启后端即生效。
    (
        llm_base_url,
        llm_api_key,
        llm_model,
        embed_base_url,
        embed_api_key,
        embed_model,
    ) = mc.resolve_from_providers(settings.model_providers, settings)
    llm = llm or LLMClient(
        llm_base_url,
        llm_api_key,
        llm_model,
        embed_base_url,
        embed_api_key,
        embed_model,
    )
    session_store = SessionStore(settings.sessions_dir)
    memory = ConversationMemory(session_store)
    master = MasterDataService(adapter)
    kitting = KittingService(adapter, audit)
    followups = FollowupStore()

    # 工具库 (三引擎共享): 注册内置工具 + 为高危写操作挂前置断言 (两道写护栏之一)
    tools = ToolRegistry()
    register_builtin_tools(tools, adapter, gate, kitting, llm, followups, observations)
    tools.attach_precondition("dispatch_work_order", make_dispatch_precondition(kitting, adapter))
    tools.attach_precondition("send_expedite_message", make_expedite_precondition(kitting, followups))

    # 新工具框架 (tools/) 桥接: 通用工具 (glob/todo_write/tool_search/web_fetch 等) 注册进
    # 共享工具库，技能 allowed_tools 可按名引用；requires_confirm 工具在桥内被框架权限门
    # 拦截 → 经 gate 生成 PendingAction (随 actions 事件下发前台确认卡片)。
    framework_tools = initialize_framework_tools(FrameworkToolRegistry())
    register_framework_tools(
        tools,
        tool_manager=ToolManager(registry=framework_tools),
        gate=gate,
        framework_tools=framework_tools,
    )

    # 命名前置断言表 (供技能包 frontmatter `tool_preconditions` 按名引用):
    # 普通字典，不建 Registry 类。键即断言名，与 preconditions.py 的工厂一一对应。
    named_preconditions: dict[str, Precondition] = {
        "dispatch_ready": make_dispatch_precondition(kitting, adapter),
        "expedite_valid": make_expedite_precondition(kitting, followups),
    }

    # 技能包仓库 + read_skill_file 工具 (kind="read"。不进 QUERY_READONLY_TOOLS；
    # 调度白名单取注册表全集故含之，但仅在技能执行体内被显式调用时才有意义)。
    skill_store = SkillStore(settings.skills_dir)

    async def _read_skill_file(skill_name: str, path: str) -> dict:
        return skill_store.read_attachment(skill_name, path)

    tools.register(
        name="read_skill_file",
        description="读取当前技能包的附属文件(参考资料/模板)。仅在技能执行体内有意义。",
        parameters={
            "type": "object",
            "properties": {
                "skill_name": {"type": "string"},
                "path": {"type": "string"},
            },
            "required": ["skill_name", "path"],
        },
        handler=_read_skill_file,
        kind="read",
    )

    # 技能引擎 (按 skill_id 执行单个技能包内的 AgentLoop；不拥有 Context Panel)
    skill_engine = SkillEngine(
        llm, tools, pending, audit, skill_store, settings, named_preconditions,
        observations=observations,
    )

    # 调度引擎 (ReAct 智能体)。白名单 = 此刻注册表全集，故须在所有工具注册之后构造。
    agent = AgentLoop(
        llm, tools, pending, audit, SCHEDULING_SYSTEM, scheduling_tools(tools),
        settings.react_max_steps,
        observation_max_bytes=settings.react_observation_max_bytes,
        permissions=permissions,
        observations=observations,
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
    if settings.vector_backend == "chroma":
        from maestro.foundation.chroma_store import ChromaVectorStore
        vectorstore = ChromaVectorStore(embedder, settings.chroma_dir)
    else:
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
    embed_router = EmbeddingRouter(llm, load_examples(), skills=skill_store)
    router = IntentRouter(llm, settings, embed_router, skills=skill_store)
    orchestrator = Orchestrator(
        router, planning_engine, scheduling_engine, query_engine, memory, audit, gate, settings,
        skill_engine=skill_engine,
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
        observations=observations,
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
        skill_store=skill_store,
        skill_engine=skill_engine,
        named_preconditions=named_preconditions,
    )
