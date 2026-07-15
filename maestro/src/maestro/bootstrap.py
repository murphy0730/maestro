"""组装根 (composition root)。

唯一允许同时 import 三个引擎与具体策略/工具/护栏的地方；引擎本体不感知具体
策略，业务代码不感知具体适配器。FastAPI 与 CLI 共用此处的 build_platform()。

v0.2: 三引擎三范式 —
- 排产引擎 PlanningEngine: 固定工作流 (策略插件框架)。
- 调度引擎 SchedulingEngine: ReAct 智能体 (AgentLoop + 工具 + 两道写护栏)。
- 查询引擎 QueryEngine: RAG + LLM (向量库 + 只读工具)。
"""

import json
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
from maestro.domain.models import ActionResult
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
from maestro.foundation.mcp_config_store import MCPConfigStore
from maestro.foundation.tools.builtin import (
    QUERY_READONLY_TOOLS,
    FollowupStore,
    register_builtin_tools,
    scheduling_tools,
)
from maestro.foundation.tools.registry import Precondition, ToolRegistry
from maestro.mcp.manager import MCPManager
from maestro.mcp.types import MCPServerConfig, MCPTransportType
from maestro.tools import IntegratedToolManager, ToolRegistry as FrameworkToolRegistry
from maestro.tools import initialize_tools as initialize_framework_tools
from maestro.tools.bridge import register_framework_tools
from maestro.foundation.vectorstore import VectorStore
from maestro.orchestrator.embedding_router import EmbeddingRouter, load_examples
from maestro.orchestrator.orchestrator import Orchestrator
from maestro.orchestrator.router import IntentRouter
from maestro.skills.context import current_context
from maestro.skills.engine import SkillEngine
from maestro.skills.schemas import SkillValidationError
from maestro.skills.script_execution import SkillScriptExecutionService, result_detail
from maestro.skills.store import SkillStore
from maestro.extensions.store import ExtensionCatalogStore
from maestro.extensions.service import ExtensionCatalogService
from maestro.extensions.scheduler import CatalogScheduler
from maestro.extensions.catalog_tools import register_catalog_tools


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
    skill_scripts: SkillScriptExecutionService
    named_preconditions: dict[str, Precondition]
    mcp: IntegratedToolManager
    mcp_config_store: MCPConfigStore
    bridged_mcp_names: set[str]
    catalog_store: ExtensionCatalogStore | None
    catalog_service: ExtensionCatalogService | None
    catalog_scheduler: CatalogScheduler | None

    async def connect_mcp(self) -> None:
        """Connect configured MCP servers, bridge discovered tools, and refresh ReAct."""
        file_servers, _ = self.mcp_config_store.list()
        effective = {server.name: server for server in file_servers}
        effective.update({server.name: server for server in self.settings.mcp_servers})
        for server in effective.values():
            if not server.enabled:
                continue
            await self.mcp.mcp_manager.add_server(
                MCPServerConfig(
                    name=server.name,
                    transport_type=MCPTransportType(server.transport_type),
                    command=server.command,
                    args=server.args,
                    url=server.url,
                    env=server.env,
                )
            )
        await self.mcp.mcp_manager.connect_all()
        await self.refresh_mcp_tools()

    async def disconnect_mcp(self) -> None:
        await self.mcp.mcp_manager.disconnect_all()

    async def refresh_mcp_tools(self) -> None:
        for name in self.bridged_mcp_names:
            self.tools.unregister(name)
        await self.mcp.refresh_mcp_tools()
        self.bridged_mcp_names = set(register_framework_tools(
            self.tools,
            tool_manager=self.mcp.tool_manager,
            gate=self.gate,
            framework_tools=self.mcp.registry,
        ))
        self.scheduling_engine.refresh_tools(scheduling_tools(self.tools))


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
    pending = PendingActionStore(settings.pending_actions_db)
    gate = ActionGate(
        authz,
        pending,
        audit,
        revalidation_seconds=settings.pending_revalidation_seconds,
        expiration_seconds=settings.pending_expiration_seconds,
    )
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

    gate.register_executor(
        "dispatch_work_order",
        lambda params: adapter.dispatch_work_order(params["wo_id"]),
    )
    gate.register_executor(
        "update_work_order_status",
        lambda params: adapter.update_work_order_status(params["wo_id"], params["status"]),
    )
    gate.register_executor(
        "send_notification",
        lambda params: adapter.send_message(
            params["recipient"], params.get("channel", "im"), params["content"]
        ),
    )
    for action_type in ("send_expedite_message.supplier", "send_expedite_message.internal"):
        gate.register_executor(
            action_type,
            lambda params: adapter.send_message(
                params["recipient"], params.get("channel", "im"), params["content"]
            ),
        )

    async def _record_followup(params: dict) -> ActionResult:
        record = followups.add(params["note"], params.get("wo_id"), params.get("material_id"))
        return ActionResult(
            success=True,
            action="record_followup",
            detail=json.dumps(record, ensure_ascii=False, default=str),
        )

    gate.register_executor("record_followup", _record_followup)

    # 工具库 (三引擎共享): 注册内置工具 + 为高危写操作挂前置断言 (两道写护栏之一)
    tools = ToolRegistry()
    register_builtin_tools(tools, adapter, gate, kitting, llm, followups, observations)
    dispatch_precondition = make_dispatch_precondition(kitting, adapter)
    expedite_precondition = make_expedite_precondition(kitting, followups)
    tools.attach_precondition("dispatch_work_order", dispatch_precondition)
    tools.attach_precondition("send_expedite_message", expedite_precondition)

    async def _revalidate(precondition, params: dict) -> tuple[bool, str]:
        result = await precondition(params)
        return result.ok, result.reason

    gate.register_revalidator(
        "dispatch_work_order", lambda params: _revalidate(dispatch_precondition, params)
    )
    gate.register_revalidator(
        "send_expedite_message.supplier", lambda params: _revalidate(expedite_precondition, params)
    )
    gate.register_revalidator(
        "send_expedite_message.internal", lambda params: _revalidate(expedite_precondition, params)
    )

    # 新工具框架 (tools/) 桥接: 通用工具 (glob/todo_write/tool_search/web_fetch 等) 注册进
    # 共享工具库，技能 allowed_tools 可按名引用；需确认工具由 bridge 统一交给 ActionGate
    # 生成 PendingAction (随 actions 事件下发前台确认卡片)。
    framework_tools = initialize_framework_tools(
        FrameworkToolRegistry(),
        workspace_root=settings.execution_output_dir / "workspace",
    )
    mcp = IntegratedToolManager(mcp_manager=MCPManager(), tool_registry=framework_tools)
    register_framework_tools(
        tools,
        tool_manager=mcp.tool_manager,
        gate=gate,
        framework_tools=framework_tools,
    )

    # 命名前置断言表 (供技能包 frontmatter `tool_preconditions` 按名引用):
    # 普通字典，不建 Registry 类。键即断言名，与 preconditions.py 的工厂一一对应。
    named_preconditions: dict[str, Precondition] = {
        "dispatch_ready": dispatch_precondition,
        "expedite_valid": expedite_precondition,
    }

    # 扩展目录 (SkillHub / 连接器市场) 工具: 让调度 ReAct 与查询引擎能搜索/安装技能、添加连接器。
    # catalog_service 延迟绑定 platform (此时 platform 尚未构造)，仅在运行期方法调用时需要；
    # 须在 AgentLoop/QueryEngine 构造前注册，使其进入 scheduling_tools() 全集与只读白名单。
    catalog_store = ExtensionCatalogStore(settings.extension_catalog_data_dir)
    catalog_service = ExtensionCatalogService(catalog_store, platform=None)
    register_catalog_tools(tools, catalog_service, gate)

    # 技能包仓库 + read_skill_file 工具 (kind="read"。不进 QUERY_READONLY_TOOLS；
    # 调度白名单取注册表全集故含之，但仅在技能执行体内被显式调用时才有意义)。
    skill_store = SkillStore(settings.skills_dir)
    skill_scripts = SkillScriptExecutionService(
        skill_store,
        settings.skill_execution_dir,
        settings.skills_dir,
        timeout_seconds=settings.skill_script_timeout_seconds,
        max_output_bytes=settings.skill_script_max_output_bytes,
    )
    def _safe_rel(path: str) -> bool:
        """附件相对路径白名单: 非空、限长、无控制字符、无绝对路径/反斜杠/.. 段。"""
        if not path or len(path) > 255:
            return False
        if any(ord(c) < 32 for c in path):
            return False
        if path.startswith("/") or "\\" in path or ".." in path.split("/"):
            return False
        return True

    async def _read_skill_file(path: str) -> dict:
        """读取**当前技能**的附属文件。技能范围由 invocation context 携带,不接受
        skill_name 入参 —— 杜绝跨技能越权读取。"""
        ctx = current_context()
        if ctx is None or not ctx.allowed_skills:
            return {"blocked": "read_skill_file 仅在技能执行体内可用"}
        if not _safe_rel(path):
            return {"blocked": f"非法附件路径: {path}"}
        skills = sorted(ctx.allowed_skills)
        if len(skills) == 1:
            candidates = [(skills[0], path)]
        else:
            skill, separator, rel_path = path.partition("/")
            if not separator or skill not in ctx.allowed_skills or not _safe_rel(rel_path):
                return {"blocked": "多技能执行时请使用 skill_id/相对路径 读取附件"}
            candidates = [(skill, rel_path)]
        for skill, rel_path in candidates:
            try:
                att = skill_store.read_attachment(skill, rel_path)
            except SkillValidationError:
                continue
            try:
                text = att["bytes"].decode("utf-8")
            except UnicodeDecodeError:
                return {
                    "path": path,
                    "content_type": att["content_type"],
                    "size_bytes": att["size_bytes"],
                    "truncated": att["truncated"],
                    "binary": True,
                    "note": "二进制附件不可直接注入模型上下文",
                }
            return {
                "path": path,
                "text": text,
                "content_type": att["content_type"],
                "size_bytes": att["size_bytes"],
                "truncated": att["truncated"],
                "binary": False,
            }
        return {"blocked": f"附件 {path} 不存在于当前技能"}

    async def _list_skill_files() -> dict:
        """列出**当前技能**的附件 (path + size_bytes)。范围由 invocation context 决定。"""
        ctx = current_context()
        if ctx is None or not ctx.allowed_skills:
            return {"blocked": "list_skill_files 仅在技能执行体内可用"}
        skills = sorted(ctx.allowed_skills)
        files: list[dict] = []
        for skill in skills:
            for item in skill_store.list_attachments(skill):
                files.append({
                    **item,
                    "path": item["path"] if len(skills) == 1 else f"{skill}/{item['path']}",
                })
        return {"files": files}

    tools.register(
        name="read_skill_file",
        description="读取当前技能包的附属文件(参考资料/模板)。仅在技能执行体内有意义。",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        handler=_read_skill_file,
        kind="read",
    )
    tools.register(
        name="list_skill_files",
        description="列出当前技能包的附属文件清单(路径与大小)。仅在技能执行体内有意义。",
        parameters={"type": "object", "properties": {}},
        handler=_list_skill_files,
        kind="read",
    )

    async def _execute_skill_script(params: dict) -> ActionResult:
        result = await skill_scripts.execute(params)
        return ActionResult(
            success=result.get("status") == "completed",
            action="run_skill_script",
            detail=result_detail(result),
        )

    gate.register_executor("run_skill_script", _execute_skill_script)

    async def _run_skill_script(script: str, args: list[str] | None = None) -> dict:
        if not settings.skill_scripts_enabled:
            return {"blocked": "Skill 脚本执行已被管理员关闭"}
        ctx = current_context()
        if ctx is None or not ctx.allowed_skills:
            return {"blocked": "run_skill_script 仅在技能执行体内可用"}
        skills = sorted(ctx.allowed_skills)
        if len(skills) == 1:
            skill_id, rel_script = skills[0], script
        else:
            skill_id, separator, rel_script = script.partition("/")
            if not separator or skill_id not in ctx.allowed_skills:
                return {"blocked": "多技能执行时 script 必须使用 skill_id/相对路径"}
        meta = skill_store.get(skill_id)
        if meta is None:
            return {"blocked": f"技能 {skill_id} 不存在"}
        if not skill_store.is_trusted(skill_id, meta.package_sha256):
            return {
                "blocked": "技能当前版本尚未被本地用户信任，请先在技能菜单中信任当前 hash",
                "package_sha256": meta.package_sha256,
            }
        params = {
            "skill_id": skill_id,
            "script": rel_script,
            "args": args or [],
            "package_sha256": meta.package_sha256,
        }
        outcome = await gate.request(
            "run_skill_script",
            f"执行可信技能 {meta.effective_display_name} 的脚本 {rel_script}",
            params=params,
            actor="local-user",
        )
        if outcome.status == "pending" and outcome.action:
            return {
                "pending_confirmation": True,
                "action_id": outcome.action.action_id,
                "execution": "确认后优先使用 SRT；不可用时在宿主机受控执行",
            }
        if outcome.status == "denied":
            return {"blocked": "脚本执行被权限策略拒绝"}
        return {
            "executed": True,
            "result": outcome.result.detail if outcome.result else "",
        }

    tools.register(
        name="run_skill_script",
        description=(
            "执行当前已信任 Skill 声明的 Python/JavaScript 脚本。每次调用经过权限检查；"
            "SRT 可用时沙箱执行，否则用户确认后在宿主机受控执行。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "script": {"type": "string"},
                "args": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["script"],
        },
        handler=_run_skill_script,
        kind="write",
        parallelizable=False,
    )

    # 技能引擎 (按 skill_id 执行单个技能包内的 AgentLoop；不拥有 Context Panel)
    skill_engine = SkillEngine(
        llm, tools, pending, audit, skill_store, settings, named_preconditions,
        observations=observations,
    )

    # invoke_skill: 技能内有界递归调用另一技能 (深度/环/共享预算护栏在 SkillEngine)。
    # kind=aux 但 parallelizable=False —— 共享预算原子扣减须串行，禁止 gather 并发。
    async def _invoke_skill(skill_id: str, task: str, on_progress=None) -> dict:
        return await skill_engine.invoke_nested(skill_id, task, on_progress)

    tools.register(
        name="invoke_skill",
        description="调用另一个技能来完成子任务(有界递归)。返回该技能的结论。",
        parameters={
            "type": "object",
            "properties": {
                "skill_id": {"type": "string"},
                "task": {"type": "string"},
            },
            "required": ["skill_id", "task"],
        },
        handler=_invoke_skill,
        kind="aux",
        parallelizable=False,
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
        try:
            from maestro.foundation.chroma_store import ChromaVectorStore
            vectorstore = ChromaVectorStore(embedder, settings.chroma_dir)
        except Exception as error:  # noqa: BLE001 - RAG storage must not block the platform
            logging.getLogger(__name__).warning(
                "[BOOTSTRAP] Chroma 不可用，已回退内存向量库: %s", error
            )
            vectorstore = VectorStore(embedder)
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

    platform = Platform(
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
        skill_scripts=skill_scripts,
        named_preconditions=named_preconditions,
        mcp=mcp,
        mcp_config_store=MCPConfigStore(),
        bridged_mcp_names=set(),
        catalog_store=None,
        catalog_service=None,
        catalog_scheduler=None,
    )
    # 回填 catalog_service 的 platform 引用 (工具闭包已在上方注册时捕获同一 service 实例)。
    catalog_service.platform = platform
    catalog_service.migrate_installed_localizations()
    platform.catalog_store = catalog_store
    platform.catalog_service = catalog_service
    platform.catalog_scheduler = CatalogScheduler(catalog_service, settings)
    return platform
