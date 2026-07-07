# 生产调度与排产 Agent 平台 — 初始版本设计文档 (v0.1)

> 本文档作为 Claude Code 的实现规格。目标：生成一个**可运行的初始骨架**，验证「一个平台 / 两个引擎 / 一个入口」架构。初始版本聚焦**架构正确性与可扩展性**，业务逻辑用桩（stub）和模拟数据实现，真实系统集成留出清晰接口。

---

## 1. 项目目标与范围

### 1.1 一句话定位
一个面向生产计划员/调度员的 AI Agent 平台：用户通过**统一对话入口**提出请求，平台自动判断属于**排产**还是**调度**意图，路由到对应引擎执行，并支持调度引擎被**系统事件**自动唤醒。

### 1.2 初始版本（v0.1）范围

**做：**
- 架构骨架：统一入口（Orchestrator）+ **三个引擎（排产/调度/查询，三种范式）** + 共享底座
- Orchestrator 的意图路由（显式命令 → 嵌入路由 → LLM 分类 → 澄清）
- **排产引擎（固定工作流）**：抽参 → 选策略 → 调用求解器（OR-Tools 最小模型）→ 校验 → 解释
- **调度引擎（ReAct 智能体）**：思考-行动-观察循环 + 调度工具集 + 写操作两道护栏（前置断言 + 强制授权）+ 三个循环护栏
- **查询引擎（RAG + LLM）**：检索知识库 → 增强 → 生成，附来源；处理概念/知识类问题
- 调度引擎的**事件层**：定时巡检 + 事件队列，能被「缺料预警」这类事件自动唤醒调度智能体
- 共享底座：主数据、集成层（Mock MES/ERP/WMS）、工具库（含前置断言）、向量库、embedding、记忆、权限与审计
- 一个简单的 HTTP API（FastAPI）+ 命令行交互入口，方便测试
- 全链路决策日志（路由判定、ReAct 每步思考行动、工具调用都落日志）

**不做（留接口/桩）：**
- **引擎间交叉调用**（如调度触发重排）——v0.1 三引擎独立，留 v0.2+
- 真实 MES/ERP/WMS 对接（用 MockAdapter，接口已定义好，后续替换）
- 真实消息发送（催料消息打印到日志 / 写入 outbox，不真发）
- 复杂排产建模（只做一个最小可行的车间排产模型）
- 前端 UI（只提供 API + CLI）
- 多用户认证体系（权限层留接口，初始版本单用户）
- 复合任务拆解、会话粘性（v0.2 再加，但代码结构要预留）
- RAG 高级检索（rerank、混合检索）——v0.1 只做基础检索

### 1.3 技术栈
- 语言：**Python 3.11+**
- LLM 调用：**OpenAI 兼容接口**（OpenAI-compatible API，通过 `openai` Python SDK 的 `chat.completions`）。`base_url`、`api_key`、`model` 全部走环境变量配置，从而可无缝切换 OpenAI / DeepSeek / 通义千问 / 本地 vLLM 等任何兼容服务。默认配置以 DeepSeek 为例（`base_url=https://api.deepseek.com`, `model=deepseek-chat`），可覆盖。
- 求解器：**OR-Tools**（`ortools`）
- 嵌入路由：本地轻量 embedding 模型（如 `sentence-transformers` 的 `bge-small` 类）或经 OpenAI 兼容的 embedding 接口；用余弦相似度做语义路由。封装在独立 embedding client，便于替换。
- Web 框架：**FastAPI** + `uvicorn`
- 数据校验：**Pydantic v2**
- 异步任务/事件：初始版本用 Python `asyncio` + 内存队列（不引入 Celery/Redis，留接口）
- 配置：`pydantic-settings` + `.env`
- 测试：`pytest`
- 依赖管理：`pyproject.toml`（用 `uv` 或 `pip`）

---

## 2. 总体架构

```
                        ┌──────────────────────────────────┐
   用户 (CLI / HTTP) ───▶│      Orchestrator (统一入口)        │
                        │  意图路由: 嵌入路由→LLM分类→澄清     │
                        └──────────────┬───────────────────┘
          ┌────────────────────────────┼────────────────────────────┐
          ▼                            ▼                            ▼
┌──────────────────┐      ┌──────────────────────┐      ┌────────────────────┐
│  PlanningEngine   │      │  SchedulingEngine     │      │   QueryEngine       │
│  排产引擎          │      │  调度引擎              │      │   查询引擎           │
│  范式: 固定工作流   │      │  范式: ReAct 智能体    │      │  范式: RAG + LLM     │
│  抽参→选策略→求解   │      │  工具集 + 思考-行动循环 │      │  检索→增强→回答      │
│  →校验→解释        │      │  +前置断言+强制授权     │      │                    │
└─────────┬────────┘      └──────────┬───────────┘      └─────────┬──────────┘
          │                          │                            │
          │               ┌──────────┴──────────┐                 │
          │               │  EventLayer 事件层    │                 │
          │               │  定时巡检 + 事件队列   │                 │
          │               └──────────┬──────────┘                 │
          └──────────────────────────┼────────────────────────────┘
                                      ▼
        ┌───────────────────────────────────────────────────────────┐
        │                     SharedFoundation 共享底座               │
        │  MasterData主数据 │ IntegrationLayer集成层(MES/ERP/WMS Mock) │
        │  ToolRegistry工具库 │ Memory记忆 │ AuthZ权限 │ AuditLog审计 │
        │  LLMClient封装 │ VectorStore向量库(查询引擎用)              │
        └───────────────────────────────────────────────────────────┘

  三引擎三范式，各自独立(v0.1 不考虑引擎间交叉调用，留 v0.2+)
```

### 2.1 核心设计原则（务必遵守）
0. **三引擎三范式**：三个引擎各用最匹配其场景的范式，不强求统一——
   - **排产引擎 = 固定工作流**：流程已知，要确定性/可复现，LLM 只在固定节点做翻译与解释，不做运行时规划。
   - **调度引擎 = ReAct 智能体**：执行层路径多变，用「思考→行动→观察」循环灵活编排；工具直接包装现有系统接口（控制改造成本），安全性由**前置断言 + 强制授权**两道护栏保证。
   - **查询引擎 = RAG + LLM**：检索知识库/历史/概念后增强生成回答。
1. **引擎独立（v0.1）**：三引擎互不直接依赖、互不交叉调用，只各自通过共享底座取用能力。引擎间协作（如调度触发重排）为 **v0.2+** 预留，初始版本不实现。
2. **集成层抽象**：所有外部系统访问走 `IntegrationLayer` 的抽象接口，初始用 `MockAdapter`。业务代码**绝不**直接写死外部系统调用。
3. **动作分级授权（写操作的命根子）**：所有「写操作」（下任务令、发催料、改状态）必须经过 `AuthZ`，标注 `auto` 或 `requires_confirmation`，全部进 `AuditLog`。**调度引擎用 ReAct 时尤其关键**：ReAct 自由编排不得绕过授权，写操作前还须通过**前置断言**（见 7 节）。
4. **LLM 输出结构化**：所有用于驱动控制流的 LLM 调用必须返回受约束的结构化结果（Pydantic）。ReAct 的工具调用同样走结构化的 tool_calls，禁止自由文本驱动写操作。
5. **可观测**：路由判定、引擎决策、ReAct 每一步思考与行动、工具调用、LLM 调用，全部产生结构化日志。
6. **事件驱动是调度的一等公民**：调度引擎既能被对话调用，也能被事件层自动唤醒，两条路径复用同一套 ReAct 智能体逻辑。

---

## 3. 目录结构

```
maestro/
├── pyproject.toml
├── .env.example
├── README.md
├── src/
│   └── platform/
│       ├── __init__.py
│       ├── main.py                  # FastAPI 应用入口
│       ├── cli.py                   # 命令行交互入口
│       ├── config.py                # 配置 (pydantic-settings)
│       │
│       ├── orchestrator/
│       │   ├── __init__.py
│       │   ├── orchestrator.py      # 统一入口主类
│       │   ├── router.py            # 意图路由(显式命令+嵌入路由+LLM分类+澄清)
│       │   ├── embedding_router.py  # 嵌入路由(示例话术原型+margin判据)
│       │   ├── route_examples.yaml  # 各类别(planning/scheduling/query)示例话术
│       │   └── schemas.py           # 路由相关数据模型
│       │
│       ├── engines/
│       │   ├── __init__.py
│       │   ├── base.py              # Engine 抽象基类
│       │   ├── planning/
│       │   │   ├── __init__.py
│       │   │   ├── engine.py        # 排产引擎(只管编排:选策略→跑→校验→解释)
│       │   │   ├── extractor.py     # 自然语言→排产参数(含产品线/场景)抽取
│       │   │   ├── selector.py      # 策略选择层(规则映射+LLM辅助)
│       │   │   ├── registry.py      # 策略注册表
│       │   │   ├── strategies/      # 一族可插拔排产策略
│       │   │   │   ├── __init__.py
│       │   │   │   ├── base.py          # PlanningStrategy 抽象基类
│       │   │   │   ├── flowshop_tardiness.py   # 流水车间-最小拖期(OR-Tools)
│       │   │   │   ├── jobshop_makespan.py     # 作业车间-最小完工(OR-Tools)
│       │   │   │   └── simple_dispatch.py      # 派单规则(无需优化,示范插件)
│       │   │   ├── validator.py     # 通用硬约束校验(策略特有约束在策略内)
│       │   │   ├── strategy_mapping.yaml  # 产品线/场景→策略 配置表
│       │   │   └── schemas.py
│       │   └── scheduling/
│       │       ├── __init__.py
│       │       ├── engine.py        # 调度引擎(ReAct智能体入口,双触发)
│       │       ├── agent_loop.py    # ReAct循环(思考→行动→观察+护栏)
│       │       ├── preconditions.py # 写操作前置断言(硬规则)
│       │       └── schemas.py
│       │   └── query/
│       │       ├── __init__.py
│       │       ├── query_engine.py  # 查询引擎(检索→增强→生成)
│       │       ├── retriever.py     # 向量检索(RAG)
│       │       └── schemas.py
│       │
│       ├── events/
│       │   ├── __init__.py
│       │   ├── event_bus.py         # 内存事件队列
│       │   ├── scheduler.py         # 定时巡检
│       │   └── handlers.py          # 事件→调度ReAct智能体(转为初始任务)
│       │
│       ├── foundation/
│       │   ├── __init__.py
│       │   ├── master_data.py       # 主数据访问
│       │   ├── integration/
│       │   │   ├── __init__.py
│       │   │   ├── base.py          # IntegrationAdapter 抽象接口
│       │   │   └── mock_adapter.py  # 模拟 MES/ERP/WMS
│       │   ├── tools/
│       │   │   ├── __init__.py
│       │   │   ├── registry.py      # 工具注册表(含前置断言挂载)
│       │   │   └── builtin.py       # 内置工具(只读查询/写操作/异常分类等)
│       │   ├── vectorstore.py       # 向量库(查询引擎RAG用)
│       │   ├── embedding.py         # embedding客户端(路由+RAG共用)
│       │   ├── memory.py            # 会话记忆
│       │   ├── authz.py             # 权限/动作分级
│       │   ├── audit.py             # 审计日志
│       │   └── llm.py               # LLM 客户端封装
│       │
│       └── domain/
│           ├── __init__.py
│           └── models.py            # 核心领域模型(订单/BOM/产线/物料/任务令...)
│
├── data/
│   └── mock/                        # 模拟数据 (json/csv)
│       ├── orders.json
│       ├── bom.json
│       ├── lines.json
│       ├── inventory.json
│       └── work_orders.json
└── tests/
    ├── test_router.py
    ├── test_planning.py
    ├── test_scheduling.py
    └── test_events.py
```

---

## 4. 共享底座 (SharedFoundation)

### 4.1 领域模型 (`domain/models.py`)
用 Pydantic 定义核心实体。初始版本字段保持精简但可扩展：

- `Order`：订单。字段：`order_id`, `product_id`, `quantity`, `due_date`, `priority`, `status`
- `BomItem`：物料清单项。`product_id`, `material_id`, `qty_per_unit`
- `ProductionLine`：产线。`line_id`, `name`, `capacity_per_day`, `available`(bool), `supported_products`(list)
- `Material`：物料。`material_id`, `name`, `on_hand_qty`, `in_transit_qty`, `unit`
- `WorkOrder`：任务令。`wo_id`, `order_id`, `line_id`, `planned_start`, `planned_end`, `status`(draft/dispatched/in_progress/done/blocked)
- `KittingResult`：齐套结果。`wo_id`, `is_kitted`(bool), `shortages`(list of shortage), `estimated_ready_date`
- `ProductionException`：生产异常。`exception_id`, `type`(equipment/material/quality/personnel/process), `severity`, `source`, `description`, `affected_wo_ids`, `status`

### 4.2 集成层 (`foundation/integration/`)

**抽象接口 `base.py`** — 定义所有外部系统能力，业务层只依赖它：

```python
class IntegrationAdapter(ABC):
    # 读 (ERP/MES/WMS)
    async def get_orders(self, filters: dict) -> list[Order]: ...
    async def get_bom(self, product_id: str) -> list[BomItem]: ...
    async def get_lines(self) -> list[ProductionLine]: ...
    async def get_inventory(self, material_ids: list[str]) -> list[Material]: ...
    async def get_work_orders(self, filters: dict) -> list[WorkOrder]: ...
    async def get_material_status(self, material_id: str) -> dict:  # 在途/质检/被占用归因
        ...
    # 写 (需经 AuthZ)
    async def dispatch_work_order(self, wo_id: str) -> ActionResult: ...
    async def update_work_order_status(self, wo_id: str, status: str) -> ActionResult: ...
    async def send_message(self, recipient: str, channel: str, content: str) -> ActionResult: ...
    # 事件源
    async def poll_events(self) -> list[SystemEvent]:  # 巡检拉取报警/异常等
        ...
```

**`mock_adapter.py`** — 从 `data/mock/*.json` 读数据实现读接口；写接口打印日志 + 记录到内存 `outbox`/`action_log`，不真正调用外部系统；`poll_events` 随机/按规则产生几个模拟事件（如某任务令缺料、某产线报警）用于演示事件驱动。

### 4.3 工具库 (`foundation/tools/`)
- `registry.py`：`ToolRegistry`，工具用装饰器或显式注册。每个工具有 `name`、`description`、`parameters`(JSON schema)、`handler`，可导出为 **OpenAI function-calling（tools）格式**（`{"type":"function","function":{...}}`）。
- `builtin.py`：内置工具，**都通过 IntegrationAdapter 实现**，例如：
  - `query_orders`, `query_inventory`, `query_work_orders`
  - `check_kitting`（齐套检查）
  - `analyze_material_shortage`（缺料归因）
  - `send_expedite_message`（发催料消息，写操作 → 经 AuthZ）
  - `dispatch_work_order`（下任务令，写操作 → 经 AuthZ）
  - `run_scheduling_solver`（调用排产求解器）

### 4.4 LLM 封装 (`foundation/llm.py`)
- `LLMClient`：封装 **OpenAI 兼容接口**调用，内部用 `openai` SDK 的 `client.chat.completions.create(...)`。客户端初始化时从 config 读取 `base_url` / `api_key` / `model`，因此切换底层模型供应商（OpenAI / DeepSeek / 千问 / 本地 vLLM）只改配置、不改代码。
- 提供两个核心方法：
  - `complete(system, messages, tools=None) -> response`：通用调用。`system` 作为 `role="system"` 消息拼到 `messages` 前。`tools` 传入时使用 **OpenAI function-calling（tools / tool_calls）** 机制，方法负责解析返回的 `tool_calls`、执行对应工具、把结果以 `role="tool"` 回填并继续对话，直到模型给出最终文本（即在此封装内完成工具循环）。
  - `classify(system, user_input, schema: type[BaseModel]) -> BaseModel`：**结构化分类**，强制返回符合给定 Pydantic schema 的 JSON。**优先用 OpenAI 的 JSON 模式**（`response_format={"type": "json_object"}`，并在 prompt 中明确给出目标 JSON 结构）；拿到结果后用 Pydantic 校验，解析/校验失败重试一次（重试时把错误信息回喂给模型）。
    - 注意：不同兼容服务对 `response_format` 和 function-calling 的支持程度不一。封装内做能力降级——若服务不支持 JSON 模式，则退回「prompt 强约束只输出 JSON + 提取首个 JSON 块 + Pydantic 校验」的方式。这层兼容差异**必须**被 `LLMClient` 吸收，业务代码不感知。
- 模型名、`base_url`、`api_key` 全部从 config 读。**不要在代码里硬编码任何密钥或 base_url**。

### 4.5 记忆 (`foundation/memory.py`)
- `ConversationMemory`：按 `session_id` 存储对话历史 + 当前会话所处引擎（为 v0.2 会话粘性预留）+ 上一次排产结果等上下文。初始版本用内存字典实现，接口设计成可替换为持久化存储。

### 4.6 权限与审计 (`foundation/authz.py`, `foundation/audit.py`)
- `AuthZ`：给每个写操作定义授权策略。初始版本简单规则：
  - 读操作：始终允许
  - 发催料消息（内部）：`auto`
  - 发催料消息（外部供应商）：`requires_confirmation`
  - 下任务令：`requires_confirmation`
  - 改任务令状态：`requires_confirmation`
  - 策略用配置表驱动，方便调整。
- 当动作为 `requires_confirmation` 时，引擎不直接执行，而是返回一个**待确认动作**给用户，用户确认后再执行。
- `AuditLog`：记录所有 (时间, actor, 动作类型, 参数, 授权结果, 执行结果)。初始版本写结构化日志文件 + 内存列表，可查询。

---

## 5. Orchestrator（统一入口）

### 5.1 职责
接收用户输入 → 路由判断意图 → 调用对应引擎 → 返回结果。处理低置信度时的澄清。

### 5.2 路由器 (`router.py`) — 核心逻辑

> **设计原则**：路由匹配的是**意图**，不是**字面**。纯关键词匹配的根本缺陷在于匹配字面而非语义——例如「排产是什么？」会命中关键词「排产」而被错误路由到排产引擎，但用户其实只想**查询概念**。因此本设计**用语义嵌入路由替代关键词猜测**，关键词仅保留用于零歧义的显式命令。整体为「显式命令 → 嵌入路由 → LLM 分类 → 澄清」的分层递进，每层解决一类问题、解决不了才降级。

**分层判断，按顺序：**

**第 0 层：显式命令（硬规则，仅限零歧义场景）**
- **只处理 100% 确定、无歧义的显式指令**，不用于猜测模糊意图：
  - UI 上的明确动作（如点击「新建排产」按钮）→ 直接进对应引擎。
  - 斜杠命令（如 `/排产`、`/催料`、`/齐套`）→ 直接路由。
- 命中 → 直接路由，记日志（`route_method=explicit`）。无显式命令 → 进第 1 层。
- **注意**：这里**绝不**用「出现『排产』二字就判排产」这种关键词猜意图——那正是要被淘汰的反模式。

**第 1 层：嵌入路由（embedding routing，语义匹配）**
- 为每个路由目标准备一组**示例话术**，启动时 embed 成向量原型（prototype）。**类别必须包含独立的「查询/概念」类**（这是解决「排产是什么」问题的根本）：
  - `planning`：如「帮我排产」「把订单排到产线」「重排一下这批单」
  - `scheduling`：如「催一下料」「这批料齐了吗」「下发任务令」「设备报警了影响哪些单」
  - **`query`（查询/概念/闲聊）**：如「X 是什么」「怎么用这个系统」「解释一下齐套」「你能干嘛」「上次那个结果呢」
- 对用户输入 embed 后，与各类原型算相似度（取每类最相似的示例分，或类内平均，二选一并固定）。
- **置信判据必须用 margin，不能只看最高分**：
  - 设 `top1` = 最高相似度类，`top2` = 次高。
  - **直接路由的条件**：`top1_score >= 阈值A` **且** `(top1_score - top2_score) >= 阈值B`（margin 足够大，明显甩开第二名）。
  - 仅最高分高但两类贴近（如 0.82 vs 0.79，margin 太小）→ **判为模糊，降级第 2 层**，不直接路由。
- 满足条件 → 直接路由（含路由到 `query` handler），记日志（`route_method=embedding`，记录 top1/top2 分数与 margin）。否则 → 第 2 层。
- 阈值 A、B 可配置；初期可调高（更多走 LLM 兜底），随示例话术积累再调低让嵌入层多承担。

**第 2 层：LLM 结构化分类（嵌入模糊时的疑难裁决）**
- 调用 `LLMClient.classify`，传入：当前用户输入 + 最近 N 轮对话上下文 + 当前会话引擎（如有）。
- 强制返回如下 Pydantic 模型：

```python
class RouteDecision(BaseModel):
    intent: Literal["planning", "scheduling", "query", "ambiguous"]
    confidence: float          # 0~1
    entities: dict             # 抽取到的关键实体(产线/订单/任务令等)
    reason: str                # 判定理由(用于日志和解释)
```

- 分类 prompt 必须包含：四类的清晰定义（**含 query 类**）+ **易混淆对照例句**（见下），要求只输出 JSON。
- `confidence >= 0.8` 且 `intent in (planning, scheduling, query)` → 路由到对应目标（`query` → 轻量 query handler，用工具库直接回答）。
- `confidence < 0.8` 或 `intent == ambiguous` → 进第 3 层。

**第 3 层：用户澄清（带选项）+ 澄清后处理**
- 返回**带选项的澄清问题**给用户，不猜。例：「排产是什么？」若走到这里 → 「想让我做哪个？① 解释排产概念 ② 帮你执行排产」。
- **澄清后处理分两种，关键是选项式不重跑**：
  - **选项式回答**（用户点选了明确选项）→ **直接按所选选项路由，不再重新跑嵌入/LLM 分类**（重跑可能把已明确的选择又搞模糊）。
  - **开放式回答**（用户又补充了一段自然语言）→ 把新信息合并进上下文，**回到第 2 层 LLM 分类**（已是疑难案例，直接用 LLM，不必再走嵌入）。

**易混淆对照例句（必须写进第 2 层分类 prompt）：**
| 用户输入 | 正确意图 | 区别点 |
|---|---|---|
| 把这批订单重新排一下 | planning | 要重新求解计划 |
| **排产是什么 / 解释一下排产** | **query** | **只问概念，不要执行** |
| 把今天的任务令下发了 | scheduling | 执行动作，不重排 |
| 2号线停了，重排 | planning | 触发重新求解 |
| 2号线那批料齐了吗 | scheduling | 查齐套状态 |
| 哪些任务因为缺料开不了工 | scheduling | 齐套+异常查询 |
| 帮这批单优化一下排程 | planning | 求解优化 |
| 给供应商催一下 A 物料 | scheduling | 催料动作 |
| 上次那个排产结果呢 | query | 查历史，不重排 |
| 这个系统怎么用 | query | 使用咨询 |

**全程可观测与闭环**：每次路由都记录「走到哪一层、各层判定、嵌入 top1/top2/margin、LLM confidence、最终路由、用户是否澄清/纠正」进 `AuditLog`。这份决策日志回流用于**补充嵌入示例话术**（误判案例补进对应类别），使嵌入层越用越准、越来越多流量在第 1 层就解决（省延迟省成本）。

**工程注意**：
- 嵌入调用有延迟和成本。建议用轻量本地 embedding 模型（如 bge-small 类）或缓存常见输入向量；接口经 `LLMClient`/独立 embedding client 封装，便于替换。
- **冷启动**：初期示例话术少、嵌入层不稳，可调高阈值 A/B 让更多流量走 LLM 分类；随话术积累再下调，逐步把负载前移到嵌入层。

### 5.3 v0.2 预留（初始版本写好接口/TODO，不实现）
- 会话粘性：延续性短句优先归当前会话引擎。
- 复合任务：识别 `composite` 类型并拆解为有序 steps（如「重排+下发」），串行调用多引擎。
  - `RouteDecision` 预留 `steps: list[RouteStep] | None` 字段。

---

## 6. 排产引擎 (PlanningEngine) — 策略插件化

> **核心现实：不存在「一个排产算法」，只有「一族排产策略」。** 不同产品线建模方式、约束、目标、算法都不同（离散 job-shop / flow-shop、流程批量生产、换型最少、模具受限、保质期约束……，算法可能是 OR-Tools 精确求解、启发式/元启发式、或纯派单规则）。因此排产引擎本体**不绑定任何具体算法**，只负责「选策略 → 跑策略 → 校验 → 解释」的编排；每种排产场景是一个可插拔的**策略插件**。

### 6.1 流程（对话驱动）
```
意图+实体 → [extractor] 抽取排产请求(含 product_line / scenario)
        → [selector] 选择策略(规则映射优先, LLM辅助兜底)
        → [strategy.solve] 选中的策略自带建模+约束+算法
        → [validator] 通用硬约束校验 + 策略特有约束校验
        → LLM 生成解释 → 返回(可迭代)
```

### 6.2 策略抽象 — `strategies/base.py`
每个排产场景实现统一接口，引擎对所有策略一视同仁。算法内部（OR-Tools / 启发式 / 规则）引擎完全不感知：

```python
class PlanningStrategy(ABC):
    # --- 元信息(供策略选择层使用) ---
    name: str
    applicable_product_lines: list[str]   # 适用的产品线
    scenario_description: str              # 自然语言描述"何时该用它"(喂给LLM选择器)
    objective_type: str                    # 该策略优化的目标

    @abstractmethod
    def required_data(self) -> list[str]:
        """声明需要哪些额外数据(如换型矩阵、模具数量、保质期),供输入校验"""

    @abstractmethod
    def validate_input(self, request: "PlanningRequest", data: "PlanningData") -> ValidationReport:
        """策略特有的输入完备性校验(缺数据则报告)"""

    @abstractmethod
    def solve(self, request: "PlanningRequest", data: "PlanningData") -> "PlanningResult":
        """策略自己的建模+约束+算法。OR-Tools/启发式/规则皆可,引擎不关心内部实现"""

    @abstractmethod
    def explain_hints(self, result: "PlanningResult") -> dict:
        """提供给LLM生成解释的结构化要点(本策略关注什么、为何这么排)"""
```

设计收益：**加新产品线 = 新增一个策略类**，不动引擎、不动其它策略（开闭原则）；不同策略可用不同算法共存、互不干扰。

### 6.3 策略注册表 — `registry.py`
`StrategyRegistry`：启动时注册所有策略实例，提供 `get(name)` / `list_all()` / 按产品线查询。新策略只需注册一次即可被选择器发现。

### 6.4 策略选择层 — `selector.py`（新增关键组件）
逻辑与 Orchestrator 路由**同构**：规则优先、LLM 兜底、低置信澄清。

**第 1 层 — 规则映射（`strategy_mapping.yaml` 驱动，优先，确定且可审计）**
Extractor 抽出 `product_line` / `scenario` 后，查配置表直接命中：
```yaml
# strategy_mapping.yaml 示例
- match: { product_line: "SMT贴片" }
  strategy: "SetupMinimizeHeuristic"     # 换型成本高 → 优先减换型
- match: { product_line: "注塑" }
  strategy: "JobShopMakespan"            # 受模具约束 → 作业车间模型
- match: { product_line: "食品灌装", scenario: "保质期敏感" }
  strategy: "BatchProcessScheduling"
- match: { product_line: "*" }            # 兜底默认
  strategy: "FlowShopTardiness"
```

**第 2 层 — LLM 辅助选择（规则未命中时）**
把所有已注册策略的 `name + scenario_description` 喂给 LLM，结合用户请求选最合适策略，**返回结构化结果带置信度**：
```python
class StrategySelection(BaseModel):
    strategy_name: str
    confidence: float
    reason: str
```

**第 3 层 — 低置信澄清**
`confidence < 阈值` → 向用户澄清「这批单属于哪种排产场景？」（带候选策略选项）。**宁可问一次，不可选错一次**——与路由器一致。

### 6.5 各组件
- **`extractor.py`**：用 `LLMClient.classify` 把用户请求 + 主数据，转成结构化 `PlanningRequest`，**新增 `product_line` / `scenario` 抽取**：
  ```python
  class PlanningRequest(BaseModel):
      order_ids: list[str]
      line_ids: list[str]
      product_line: str | None = None       # 产品线(用于选策略)
      scenario: str | None = None           # 场景特征(如"保质期敏感"/"换型频繁")
      objective: str | None = None          # 可选,策略可有默认目标
      locked_assignments: list[dict] = []    # 用户锁定项(迭代用)
      excluded_lines: list[str] = []         # 不可用产线
  ```
- **`strategies/`**：一族策略。**初始版本(v0.1)不实现全部，但要把框架做对**，提供 2-3 个示范策略证明插件机制可用：
  - `FlowShopTardiness`（OR-Tools/CP-SAT，最小拖期）—— 作为默认策略，含一个最小可行车间模型：决策每单分到哪条线及起止时间；硬约束为产线日产能、产品匹配、排除不可用产线；目标最小化总拖期；无解时返回明确不可行原因。
  - `JobShopMakespan`（OR-Tools，最小完工时间）—— 证明「同框架不同建模/目标」可共存。
  - `SimpleDispatch`（纯派单规则，如 EDD 最早交期优先，**不调求解器**）—— 证明「非优化类算法也能作为策略插入」，与 OR-Tools 策略平等共存。
  - 其余真实产品线策略（换型最少的元启发式、流程批量+保质期等）用 `# TODO(v0.2)` 占位，照基类补即可。
- **`validator.py`**：**两层校验**——引擎统一做通用硬约束校验（产能、产品匹配、交期统计，独立于策略、不信任求解器二次确认）；策略特有约束（换型可行性、保质期、模具占用）由各策略 `validate_input` / 结果自检负责。
- **解释**：把求解结果 + 校验报告 + `strategy.explain_hints()` 一起交给 LLM 生成自然语言解释。

### 6.6 关键要求
- 计算只能由策略的 `solve` 做，**不允许 LLM 直接生成排程结果**。
- 引擎本体不得 import 任何具体策略类，只通过 `StrategyRegistry` 取用（保证可插拔）。
- 策略选择决策（命中规则还是 LLM、选了哪个、置信度）全部进 `AuditLog`，便于复盘选策略是否合理。
- 求解结果写入共享底座（供调度引擎读取下发），初始版本可只存内存。

---

## 7. 调度引擎 (SchedulingEngine) — ReAct 智能体范式

> **范式定调**：调度引擎用 **ReAct 智能体**（思考 Reason → 行动 Act → 观察 Observe 的循环），而非硬编码工作流。原因：执行层任务路径多变（催料、齐套、下发、异常处置交织），且本项目是对**现有数字化系统的改造**——把现有系统接口直接包装成工具让 LLM 编排，远比为每条业务流写死状态机/把每个接口重做成受控原语**省成本**。代价是 ReAct 的不确定性，因此用**两道护栏**把写操作的风险兜住（见 7.3）。

### 7.1 双触发（两条入口，同一个智能体）
- **对话触发**：Orchestrator 路由进来（如「帮我催一下缺料的单」）。
- **事件触发**：EventLayer 唤醒（如缺料预警、设备报警），把事件转成一段 ReAct 的初始任务描述。
- 两条路径**复用同一个 ReAct 智能体**，只是初始 prompt/任务不同。

### 7.2 ReAct 智能体结构（`engine.py` + `agent_loop.py`）

**循环主体**：
```
给定任务(来自对话或事件)
  └─▶ [Reason] LLM 思考下一步该做什么(基于已有观察)
        └─▶ [Act] LLM 输出一个 tool_call(结构化)
              └─▶ [前置断言] 若是写操作 → 先过 precondition 校验(见7.3)
                    └─▶ [授权] 若是写操作 → 过 AuthZ(auto / requires_confirmation)
                          └─▶ [执行] 调用工具(经 IntegrationAdapter)
                                └─▶ [Observe] 工具结果回喂
  ◀──────────────── 循环，直到 LLM 判定任务完成 或 触达最大步数/终止条件
```

**关键护栏（必须实现，不是可选）**：
- **最大步数限制**：防止无限循环/绕路，超限则停止并汇报当前进展。
- **工具白名单**：智能体只能调 `ToolRegistry` 中注册、且对调度场景授权的工具。
- **死循环检测**：检测连续重复调用同一工具同一参数，触发则中断并提示。
- **只读优先**：查询类工具自由调用；写操作类工具必须过 7.3 两道护栏。

### 7.3 写操作的两道护栏（调度引擎安全的命根子）

ReAct 自由编排的最大风险不是「单个动作错」（授权能拦），而是「漏前置步骤 / 顺序错」（授权拦不住）。因此对**有副作用的写操作**设两道关卡：

**护栏一：前置断言（Precondition Assertion）—— 代码硬规则，不依赖 LLM 记得检查**
- 每个写操作工具注册时，附带一组**前置条件断言**（几条硬规则即可，不是完整流程定义）。执行该写操作前，引擎自动校验，不满足直接拦截并把原因回喂给 ReAct。
- 例：
  - `dispatch_work_order`（下任务令）前置断言：该 WO 必须已齐套 **且** 前道工序完成（前道初始版本可简化/桩）。
  - `send_expedite_message`（催料）前置断言：该物料确实缺料 **且** 未在近期重复催过（防重复催）。
- 这层把「ReAct 漏掉必要前置校验就推进写操作」的最致命漏洞用代码兜住，**成本很低**（每个高危写操作几条规则），符合改造现实。

**护栏二：强制授权（AuthZ）—— 人工确认关口**
- 写操作过完前置断言后，再过 `AuthZ`：
  - 内部催料 → `auto`（写 outbox）。
  - 供应商催料、下任务令、改状态 → `requires_confirmation`（返回待确认动作，人确认后才执行）。
- ReAct 智能体**不得绕过授权直接执行写操作**；待确认动作会中断当前循环，等用户确认后续跑。

> 两道护栏的分工：**前置断言**保证「流程前提对」（拦漏步/乱序），**授权**保证「这一步人认可」（拦单步错）。二者缺一不可。

### 7.4 调度工具集（`foundation/tools/`，供 ReAct 调用）

把现有系统能力包装成工具（初始版本经 MockAdapter），ReAct 自由组合。**不追求把接口重做成精致原语，直接包装即可**（控成本）。至少提供：

- **只读类**（自由调用）：`check_kitting`（齐套检查）、`analyze_material_shortage`（缺料归因）、`query_work_orders`、`query_inventory`、`analyze_exception_impact`（异常影响分析：查受影响 WO 与受威胁订单交期）。
- **写操作类**（过两道护栏）：`send_expedite_message`（催料）、`dispatch_work_order`（下任务令）、`update_work_order_status`、`notify_personnel`（通知相关人）。
- **辅助类**：`classify_exception`（异常分类定级，LLM 工具）、`record_followup`（记录跟踪/复盘）。

> 原先 v0.1 的四个固定 workflow（齐套/催料/下发/异常）现在**不再是硬编码流程**，而是**化为上述工具 + ReAct 的自由编排**。例如「催料」不再是写死的 5 步，而是 ReAct 自己决定：先 `check_kitting` → 看结果 → `analyze_material_shortage` → 决定 → `send_expedite_message`（过护栏）→ `record_followup`。
> 「异常处置」的**关键决策仍留人**：ReAct 可以做分类、影响分析、给建议，但改派/插单等关键写操作一律 `requires_confirmation`。

### 7.5 关键要求
- ReAct 的**每一步思考与行动**都进 `AuditLog`（思考内容、选的工具、参数、前置断言结果、授权结果、观察结果）——这是 ReAct 可审计性的基础，务必完整。
- 写操作**必须**过「前置断言 + AuthZ」两道护栏，任何路径都不得绕过。
- 异常处置的**关键决策必须留人**：智能体只给建议和影响分析，关键执行需确认。
- 实现最大步数、工具白名单、死循环检测三个护栏。
- 事件触发与对话触发复用同一智能体，仅初始任务描述不同。

---

## 7B. 查询引擎 (QueryEngine) — RAG + LLM 范式

> **范式定调**：查询引擎处理「概念解释 / 知识问答 / 历史与状态查询」类意图（路由判为 `query` 的请求），用 **RAG（检索增强生成）+ LLM**。它不执行任何写操作，是只读的。这也是「排产是什么？」这类被路由层正确识别为 query 的请求的归宿。

### 7B.1 职责
- 回答概念性问题（「排产是什么」「齐套率怎么算」「这个系统怎么用」）。
- 回答基于知识库的问题（排产规则、异常处置手册、SOP）。
- 回答历史/状态查询（「上次那个排产结果呢」「现在有几个在制工单」——后者经只读工具查实时数据）。

### 7B.2 结构（`engines/query/`）
```
query 请求
  └─▶ [Retrieve] 从 VectorStore 检索相关文档片段(知识库)
        + (可选) 调只读工具取实时数据
  └─▶ [Augment] 把检索结果/数据组装进 prompt(分区组织，标明来源)
  └─▶ [Generate] LLM 基于增强上下文生成回答，附引用来源
```

### 7B.3 组件
- **`retriever.py`**：向量检索。把知识库文档 chunk → embed → 存入 `VectorStore`（共享底座，初始版本可用轻量本地向量库如 Chroma，或内存向量+余弦）。查询时检索 top-k 相关片段。
- **`query_engine.py`**：编排「检索 → 增强 → 生成」。对需要实时数据的查询（如「几个在制工单」），可调底座**只读工具**补充事实，与检索片段一起喂给 LLM。
- **知识库内容（初始 mock）**：放几篇示例文档——排产概念说明、齐套定义、异常处置手册片段——供 RAG 检索演示。
- **来源引用**：回答时标注引用了哪些知识库片段，便于核实（呼应平台「可解释/可信」原则）。

### 7B.4 关键要求
- **只读**：查询引擎不得触发任何写操作，不挂 AuthZ 写路径。
- **检索为先**：概念/知识类问题必须先检索再生成，禁止纯靠 LLM 记忆瞎答（防幻觉）；检索不到相关内容时如实说明，而非编造。
- RAG 的 chunking、embedding 与路由层的嵌入可共用同一 embedding client（共享底座）。
- v0.1 范围：把「检索→增强→生成」主链路跑通 + 几篇 mock 知识文档即可；高级检索（rerank、混合检索）留 v0.2+。

---

## 8. 事件层 (EventLayer)

### 8.1 组件
- **`event_bus.py`**：`asyncio.Queue` 实现的内存事件总线。`publish(event)` / `subscribe(handler)`。定义 `SystemEvent` 模型：`event_id`, `type`(material_shortage_warning / equipment_alarm / quality_issue ...), `payload`, `timestamp`。
- **`scheduler.py`**：定时巡检器。按固定间隔（配置，如 30 秒）调用 `IntegrationAdapter.poll_events()` 拉取系统事件，发布到 event_bus。同时做**预测性巡检**：扫描待开工任务令的齐套情况，对「即将因缺料卡住」的任务令主动产生 `material_shortage_warning` 事件。
- **`handlers.py`**：事件处理器，把事件**转换为一段初始任务描述**，唤醒调度 ReAct 智能体处理（不再映射到固定 workflow）：
  - `material_shortage_warning` → 任务："某WO即将开工但缺料，请归因并催料"
  - `equipment_alarm` → 任务："某设备报警，请做影响分析并给出处置建议(关键决策待人确认)"
  - 智能体处理结果中需要人确认的，写入「待办/通知」（初始版本打印 + 写日志）。

### 8.2 运行方式
- FastAPI 启动时，后台起一个 asyncio task 跑 `scheduler` 巡检 + event_bus 消费循环。
- 提供 API 手动注入事件（`POST /events`）方便测试事件驱动链路。

---

## 9. 接口设计

### 9.1 HTTP API (`main.py`, FastAPI)
- `POST /chat`：统一对话入口。请求 `{session_id, message}`，返回 `{reply, route_decision, pending_actions?, data?}`。
- `POST /chat/confirm`：确认待执行动作。请求 `{session_id, action_id, approved: bool}`。
- `POST /events`：手动注入系统事件（测试用）。
- `GET /audit`：查询审计日志。
- `GET /health`：健康检查。

### 9.2 CLI (`cli.py`)
- 一个交互式 REPL：读用户输入 → 调 Orchestrator → 打印路由判定 + 回复 + 待确认动作。支持确认动作。方便不开前端就能完整体验整条链路。

---

## 10. 数据流示例（用于验证实现正确）

**示例 A — 排产（对话驱动，含策略选择）**
```
用户: "把注塑线的订单 O001,O002,O003 排一下，尽量别拖期"
→ Router: 嵌入路由 → planning 高置信(margin足够) (route_method=embedding)
→ Extractor: PlanningRequest(order_ids=[O001,O002,O003], product_line="注塑", objective=min_tardiness)
→ Selector: 查 strategy_mapping → 注塑命中 JobShopMakespan (select_method=rule)
            (若产品线未配置 → LLM辅助选 → 低置信则向用户澄清场景)
→ Strategy.solve(OR-Tools): 求解，返回每单的产线与起止时间
→ Validator: 通用校验(产能/产品匹配/交期) + 策略特有校验 → 报告
→ LLM 解释(含 strategy.explain_hints): "采用作业车间模型...O003 因产能可能拖期1天..."
→ 返回用户
```

**示例 B — 催料（对话驱动，ReAct 智能体编排）**
```
用户: "现在有哪些任务因为缺料开不了工，帮我催一下"
→ Router: 嵌入路由 → scheduling 高置信 (route_method=embedding)
→ 调度 ReAct 智能体启动:
   [Reason] 要先找出缺料的任务令 → [Act] check_kitting → [Observe] 缺料清单
   [Reason] 需归因每个缺料 → [Act] analyze_material_shortage → [Observe] 卡在采购/质检/占用
   [Reason] 决定催料对象与文案 → [Act] send_expedite_message(写操作)
        → [前置断言] 确认确实缺料且未重复催 → 通过
        → [AuthZ] 内部催料 auto 发(outbox); 供应商催料 requires_confirmation → 待确认
   [Reason] 记录跟踪 → [Act] record_followup → [Observe] 已记录
   [判定完成] 汇报: 已催N条 + 待确认M条(列出文案)
→ 全过程每步思考/行动/护栏结果 → AuditLog
```

**示例 B2 — 下任务令被前置断言拦截（验证护栏一）**
```
用户: "把 WO-200 下发了"
→ scheduling ReAct: [Act] dispatch_work_order(WO-200)(写操作)
   → [前置断言] 校验: WO-200 未齐套 → 断言失败，拦截
   → [Observe] "WO-200 缺料未齐套，不能下发" 回喂
→ [Reason] 智能体改为解释为何不能下发 + 建议先催料
（验证: ReAct 即便想直接下发，也被代码硬规则拦住，不依赖LLM记得检查）
```

**示例 C — 事件驱动（无人开口，唤醒 ReAct 智能体）**
```
[scheduler 巡检] 发现 WO-123 计划明天开工但缺料 → 发布 material_shortage_warning
→ handler 把事件转为初始任务"WO-123即将开工但缺料，请处理"→ 唤醒调度 ReAct 智能体
→ 智能体自主编排: 归因 → 生成催料 → (过两道护栏)内部auto发/供应商待确认
→ 写 AuditLog + 通知(打印/日志)
```

**示例 D — 低置信澄清**
```
用户: "3号线那批单有问题，处理下"
→ Router: 嵌入路由 top1/top2 接近(margin不足)→降级LLM分类 → ambiguous, confidence=0.5
→ 返回澄清: "想让我做哪个？① 重新排产 ② 查这批单的齐套/异常并处置"
→ (用户点选② → 直接路由到 scheduling，不重跑分类)
```

**示例 E — 概念查询不被误路由（本次嵌入路由方案的核心验证）**
```
用户: "排产是什么？"
→ 第0层: 无显式命令，过
→ 第1层 嵌入路由: 与 query 类示例("X是什么")高相似，与 planning 类示例相似度低
   → top1=query 且 margin 足够 → 高置信判为 query (route_method=embedding)
→ 路由到轻量 query handler 解释概念，**不进排产引擎**  ✅
（对比：纯关键词路由会因命中"排产"二字误入排产引擎——这正是被淘汰的反模式）
```

---

## 11. 实现优先级（建议 Claude Code 按此顺序）

1. 项目骨架：目录、`pyproject.toml`、`config.py`、`.env.example`、领域模型、mock 数据文件（含几篇 RAG 知识文档）。
2. 共享底座：`IntegrationAdapter` + `MockAdapter`、`LLMClient`、`embedding` 客户端、`VectorStore`、`AuditLog`、`AuthZ`、`ToolRegistry`（含前置断言挂载）+ 内置工具、`Memory`。
3. Orchestrator + Router（显式命令 + 嵌入路由 + LLM 分类 + 澄清）。
4. PlanningEngine（**固定工作流**：extractor → 策略框架 base/registry/selector + 2-3个示范策略 → validator → 解释）。**先把策略插件框架和选择层做对，再填具体策略**。
5. SchedulingEngine（**ReAct 智能体**：agent_loop 思考-行动-观察循环 + 三护栏(最大步数/工具白名单/死循环检测) + 写操作两道护栏(preconditions 前置断言 + AuthZ) + 调度工具集）。
6. QueryEngine（**RAG + LLM**：retriever 向量检索 + query_engine 检索→增强→生成）。
7. EventLayer（event_bus + scheduler + handlers，事件转初始任务唤醒调度智能体）。
8. 接口层：FastAPI `main.py` + `cli.py`。
9. 测试：每个引擎和路由的基础 pytest 用例（LLM 调用在测试中 mock 掉）。

---

## 12. 验收标准（初始版本跑通即算成功）

- [ ] CLI 启动后，输入示例 A，能看到路由判为 planning，**策略选择层按产品线选中对应策略**，并返回一个 OR-Tools 求出的排程结果 + 自然语言解释。
- [ ] **新增一个排产策略只需加一个策略类并注册，无需改动引擎本体或其它策略**（策略插件化验证）。
- [ ] **至少有两个不同算法类型的策略共存**（如一个 OR-Tools 策略 + 一个纯派单规则策略），且能被选择器正确区分选用。
- [ ] 输入示例 B，路由判为 scheduling，**调度 ReAct 智能体自主编排**齐套→归因→催料，返回已催与待确认清单。
- [ ] **示例 B2：ReAct 想下发未齐套的任务令时，被前置断言拦截**（验证护栏一：不依赖 LLM 记得检查，代码硬规则兜底）。
- [ ] 调度引擎的 ReAct 循环实现了**最大步数、工具白名单、死循环检测**三个护栏；**每步思考与行动进审计日志**。
- [ ] 所有写操作必须先过**前置断言**再过 **AuthZ**，任何路径不得绕过；供应商催料/下任务令为「待确认」。
- [ ] **查询引擎**：输入概念问题（如示例 E 经路由到 query），走 **RAG 检索→增强→生成**并附来源；检索不到时如实说明不编造。
- [ ] 通过 `POST /events` 注入缺料事件（或等巡检自动触发），能看到调度 ReAct 智能体被**自动唤醒**并产生催料动作（示例 C）。
- [ ] 输入示例 D，能触发**带选项的澄清**而不是瞎猜；用户选项式回答后**直接按选项路由，不重跑分类**。
- [ ] 输入示例 E「排产是什么？」，被嵌入路由正确判为 **query 类**并由查询引擎解释概念，**不进排产引擎**。
- [ ] 嵌入路由置信判据使用 **margin（top1 - top2）**，仅最高分高但两类贴近时能正确降级到 LLM 分类。
- [ ] 所有写操作都出现在 `GET /audit` 的审计日志中。
- [ ] 替换 `MockAdapter` 为真实适配器时，业务代码（三引擎）无需改动（接口隔离验证）。
- [ ] 三引擎各自独立可跑，无引擎间交叉调用（v0.1 范围）。
- [ ] `pytest` 全绿（LLM mock）。

---

## 13. 给 Claude Code 的实现备注

- **不要硬编码 API key**；从 `.env` 读，`.env.example` 给占位。
- LLM 配置走 config / `.env`，包含三项：`LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`，均可覆盖。`.env.example` 给出 DeepSeek 示例（`LLM_BASE_URL=https://api.deepseek.com`、`LLM_MODEL=deepseek-chat`、`LLM_API_KEY=` 留空占位），并注释说明换成 OpenAI（`https://api.openai.com/v1` + `gpt-4o-mini` 等）或本地 vLLM 只需改这三项。
- 所有 LLM 调用必须有**解析失败重试一次**的保护，并在彻底失败时降级（如分类失败时降级为 ambiguous 触发澄清）。
- 写清晰的 docstring 和类型注解；关键控制流加结构化日志。
- 优先保证**架构清晰、接口隔离、可运行**，而非业务完备。业务逻辑桩处用 `# TODO(v0.2):` 标注清楚后续要做什么。
- 提供 `README.md`：如何装依赖、配 `.env`、起服务、跑 CLI、跑测试。
- 模拟数据要能支撑上面 4 个示例完整跑通（设计 mock 数据时确保：有可排的订单、有缺料的任务令、有可触发的异常）。
