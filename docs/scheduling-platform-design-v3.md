# 生产调度与排产 Agent 平台 — 设计文档 v3（修订版）

> 本文档在 v2（`scheduling-platform-design-v2.md`）基础上修订，v2 停止维护。目标不变：一个**可运行的骨架**验证「一个平台 / 三个引擎 / 一个入口」架构，业务逻辑桩化、真实系统集成留接口。
>
> **v3 修订说明（相对 v2 的实质变更）：**
> 1. 新增 **术语表** 与 **排产粒度声明**（§0）——明确当前为「产能桶粗排」，工序级细排列为后续版本，消除 FlowShop/JobShop 命名与实际建模的错位。
> 2. 排产策略抽象修正（§6）：**建模结构与优化目标正交**——策略声明 `supported_objectives`，`objective` 参与策略选择并作为求解参数，修复 v2 示例 A「用户要最小拖期却命中 Makespan 策略」的自相矛盾。
> 3. `product_line` 改为**主数据反查**，不再依赖用户口述/LLM 抽取（§6.5）。
> 4. 新增 **计划版本（Plan）与冻结期** 概念（§4.1、§6.6）：重排自动锁定在制/已下发任务令。
> 5. 齐套检查引入**物料预留（allocation）**语义（§4.1、§7.4），修复同一库存被多个任务令重复承诺的问题。
> 6. 事件层**平台化**（§8）：事件经统一路由可达任一引擎（v0.1 仍只有调度引擎消费）；新增**去重 / 聚合 / 抑制**三道防线；预留 `replan_request` 事件类型，删除 v2 中与「引擎独立」原则矛盾的 `run_scheduling_solver` 工具。
> 7. 待确认动作语义修正（§7.3）：**确认即执行单个动作，不恢复 ReAct 循环**；`PendingAction` 增加 `expires_at`。
> 8. 求解器工程要求（§6.6）：强制 `time_limit`、拖期建为**软约束**、不可行原因由 **solve 前数据预检**给出（CP-SAT 的 INFEASIBLE 不附带原因，"求解器返回不可行原因"的说法不成立）。
> 9. 路由层定位调整（§5）：**LLM 结构化分类为主路径，嵌入路由为可选加速层**（`EMBED_MODEL` 未配置则跳过）；query/scheduling 边界改为**按「是否有副作用」划分**——一切只读查询归 query。
> 10. 审计与遥测分流（§4.6）：业务审计（audit）与 ReAct 步级思考日志（trace）分为两条流。
> 11. 文档瑕疵修正：源码路径为 `src/scheduling_platform/`（`platform` 是 stdlib 名，禁用）；目录树 `query/` 缩进修正；Mock 事件由「随机产生」改为**脚本化场景**保证测试可复现。

---

## 0. 术语表与排产粒度声明

### 0.1 术语表

| 本平台用语 | 代码名 | 实际语义 | 行业/学术对照 |
|---|---|---|---|
| **排产** | `PlanningEngine` | 生成生产计划：订单分配到产线与日期，优化目标（拖期/完工时间等） | 学术文献中常称 *scheduling*（如 job-shop scheduling）。本平台统一称 Planning，避免与下行混淆 |
| **调度（执行）** | `SchedulingEngine` | 计划执行层：派工下发、催料、齐套、异常处置 | 学术意义上更接近 *execution management / dispatching*。代码名 `SchedulingEngine` 保留（历史兼容），文档语义以本表为准；如未来重构，推荐更名 `ExecutionEngine` |
| **查询** | `QueryEngine` | 一切**只读**问答：概念、知识库、历史、实时状态 | RAG + 只读工具 |

> **命名纪律**：任何新增工具/模块，凡涉及"调用排产求解器"一律用 `planning`/`solve` 词根，禁止再出现 `run_scheduling_solver` 这类把两个引擎语义搅在一起的命名（v2 的该工具已删除，见 §4.3）。

### 0.2 排产粒度声明（重要）

**当前版本的排产是「产能桶粗排」（capacity-bucket planning）**：

- 决策粒度：订单 → 产线 → 日期区间；约束为产线**日产能**、产品匹配、产线可用性。
- 领域模型**没有** Operation（工序）/ Routing（工艺路线）/ Machine（设备）实体，因此**建不出**严格意义的 flow-shop / job-shop 工序级模型。现有策略名 `FlowShopTardiness` / `JobShopMakespan` 沿用自 v0.1 代码，**其实际实现均为产能桶模型**，仅目标函数与建模细节不同——命名与学术模型的差异以本节声明为准，策略重命名列入 `TODO(v0.3)`。
- **工序级细排**（Operation × Machine 时间区间调度，真正的 job-shop）列为 **v0.4+**，前置条件：领域模型补 `Operation` / `Routing`，集成层补工艺路线与设备数据接口。粗排与细排的数据需求、算法、结果结构完全不同，**不允许在同一策略里含糊混用**。

---

## 1. 项目目标与范围

### 1.1 一句话定位
一个面向生产计划员/调度员的 AI Agent 平台：用户通过**统一对话入口**提出请求，平台自动判断属于**排产 / 调度执行 / 查询**意图，路由到对应引擎执行，并支持调度引擎被**系统事件**自动唤醒。

### 1.2 范围

**做：**
- 架构骨架：统一入口（Orchestrator）+ 三个引擎（排产/调度/查询，三种范式）+ 共享底座
- Orchestrator 意图路由（显式命令 → LLM 分类为主 → 可选嵌入加速 → 澄清）
- **排产引擎（固定工作流）**：抽参（主数据反查产品线）→ 选策略（建模×目标正交）→ 求解（带 time_limit 的产能桶模型）→ 校验 → 解释；结果以**计划版本**落盘
- **调度引擎（ReAct 智能体）**：思考-行动-观察循环 + 工具集 + 写操作两道护栏（前置断言 + 强制授权）+ 三个循环护栏 + **主体级并发互斥**
- **查询引擎（RAG + LLM + 只读工具）**：概念/知识/历史/**实时状态**的一切只读问答
- **事件层（平台级）**：定时巡检 + 事件总线 + **去重/聚合/抑制** → 事件转任务唤醒调度智能体（v0.1 唯一消费者），预留路由到其他引擎
- 共享底座：主数据、集成层（Mock MES/ERP/WMS）、工具库（含前置断言）、向量库、embedding、记忆、权限与审计、**计划存储**
- HTTP API（FastAPI）+ CLI
- 全链路决策日志：业务审计（audit）与步级遥测（trace）**分流**

**不做（留接口/桩）：**
- **引擎间交叉调用的执行**——但 v3 起**预留机制**：`replan_request` 事件类型 + 平台级事件路由（见 §8），v0.2 打开开关即可，不动架构
- 工序级细排（v0.4+，见 §0.2）
- 真实 MES/ERP/WMS 对接（MockAdapter）
- 真实消息发送（写 outbox / 日志）
- 多用户认证体系——但**确认动作与用户身份绑定列为 v0.2 第一优先级**（见 §4.6）
- 复合任务拆解、会话粘性（v0.2）
- RAG 高级检索（rerank、混合检索）（v0.2+）

### 1.3 技术栈
- 语言：**Python 3.12**（ortools 支持 3.11–3.13，**不支持 3.14**）
- LLM 调用：**OpenAI 兼容接口**（`openai` SDK，`base_url`/`api_key`/`model` 走环境变量；默认示例 DeepSeek）
- 求解器：**OR-Tools CP-SAT**（所有 `solve` 强制携带 time limit，见 §6.6）
- 嵌入路由（可选层）：`EMBED_MODEL` 未配置则整层跳过
- Web：**FastAPI** + `uvicorn`；数据校验 **Pydantic v2**
- 事件：`asyncio` + 内存队列（不引入 Celery/Redis，留接口）
- 配置 `pydantic-settings` + `.env`；测试 `pytest`；依赖 `pyproject.toml`（`uv`）

---

## 2. 总体架构

```
                        ┌──────────────────────────────────┐
   用户 (CLI / HTTP) ───▶│      Orchestrator (统一入口)        │
                        │  意图路由: LLM分类为主+嵌入可选+澄清  │
                        └──────────────┬───────────────────┘
          ┌────────────────────────────┼────────────────────────────┐
          ▼                            ▼                            ▼
┌──────────────────┐      ┌──────────────────────┐      ┌────────────────────┐
│  PlanningEngine   │      │  SchedulingEngine     │      │   QueryEngine       │
│  排产引擎          │      │  调度执行引擎          │      │   查询引擎(只读)      │
│  范式: 固定工作流   │      │  范式: ReAct 智能体    │      │  范式: RAG+LLM      │
│  抽参→选策略→求解   │      │  工具集+思考-行动循环   │      │  +只读实时工具       │
│  →校验→解释→计划版本│      │  +前置断言+强制授权     │      │  检索→增强→回答      │
└─────────┬────────┘      └──────────┬───────────┘      └─────────┬──────────┘
          │                          │                            │
          │        ┌─────────────────┴─────────────────┐          │
          │        │       EventLayer 事件层(平台级)      │          │
          │        │  巡检 → 去重/聚合/抑制 → 事件路由      │          │
          │  ◀─────│  v0.1: 仅唤醒调度引擎                │          │
          │(replan │  v0.2: replan_request → 排产引擎     │          │
          │ 预留)   └─────────────────┬─────────────────┘          │
          └──────────────────────────┼────────────────────────────┘
                                      ▼
        ┌───────────────────────────────────────────────────────────┐
        │                     SharedFoundation 共享底座               │
        │  MasterData主数据 │ IntegrationLayer集成层(MES/ERP/WMS Mock) │
        │  ToolRegistry工具库 │ Memory记忆 │ AuthZ权限 │ Audit/Trace   │
        │  LLMClient封装 │ VectorStore向量库 │ PlanStore计划版本存储    │
        └───────────────────────────────────────────────────────────┘
```

### 2.1 核心设计原则（务必遵守）
0. **三引擎三范式**：排产 = 固定工作流（确定性/可复现，LLM 只做翻译与解释）；调度执行 = ReAct 智能体（路径多变，护栏兜底）；查询 = RAG + LLM（只读）。
1. **引擎边界按「是否有副作用」划分**（v3 修订）：
   - **一切只读请求归 QueryEngine**——概念、知识库、历史、**实时状态查询**（"料齐了吗""几个在制工单"）。QueryEngine 可调只读工具取实时数据。
   - **SchedulingEngine 只接「要做事」的请求**——催料、下发、改状态、异常处置。
   - 理由：v2 把"查齐套状态"划给调度、"查在制工单"划给查询，两类话术语义几乎无差别，任何路由方法都必然打架；按副作用划分后边界清晰、路由示例好写。
2. **引擎独立（执行层面）**：v0.1 三引擎互不直接调用，只经共享底座取用能力。但**协作机制预留**：调度智能体可发布 `replan_request` 事件回投事件总线（v0.1 仅落日志，v0.2 路由到排产引擎并过 `requires_confirmation`——触发重排本身是高危动作）。
3. **集成层抽象**：所有外部系统访问走 `IntegrationAdapter` 抽象接口，初始用 `MockAdapter`，业务代码绝不直连外部系统。
4. **动作分级授权**：所有写操作经 `AuthZ`（`auto` / `requires_confirmation`），全部进审计。ReAct 任何路径不得绕过。
5. **LLM 输出结构化**：驱动控制流的 LLM 调用必须返回受约束的结构化结果（Pydantic）；工具调用走结构化 tool_calls。
6. **可观测且分流**：业务审计（写操作/授权/路由判定）进 `AuditLog`；ReAct 步级思考/观察进 `TraceLog`。两者量级、保留期、受众不同（见 §4.6）。
7. **事件驱动是平台级设施**：事件经统一防线（去重/聚合/抑制）后转任务，v0.1 唯一消费者是调度智能体；对话触发与事件触发复用同一智能体。
8. **计划是有版本的**（v3 新增）：排产结果以 `Plan`（draft/published/superseded）落 `PlanStore`；调度下发只依据 published 计划；重排自动冻结在制/已下发任务令。

---

## 3. 目录结构

```
scheduling_platform/
├── pyproject.toml
├── .env.example
├── README.md
├── src/
│   └── scheduling_platform/        # 注意: 包名不能叫 platform(stdlib 名, 会遮蔽依赖导入)
│       ├── __init__.py
│       ├── main.py                  # FastAPI 应用入口
│       ├── cli.py                   # 命令行交互入口
│       ├── config.py                # 配置 (pydantic-settings)
│       │
│       ├── orchestrator/
│       │   ├── orchestrator.py      # 统一入口主类
│       │   ├── router.py            # 意图路由(显式命令+LLM分类主路径+嵌入可选层+澄清)
│       │   ├── embedding_router.py  # 嵌入路由(可选加速层, EMBED_MODEL 未配置则跳过)
│       │   ├── route_examples.yaml  # 各类别示例话术
│       │   └── schemas.py
│       │
│       ├── engines/
│       │   ├── base.py              # Engine 抽象基类
│       │   ├── planning/
│       │   │   ├── engine.py        # 排产引擎(编排:抽参→选策略→求解→校验→解释→计划入库)
│       │   │   ├── extractor.py     # 抽参(order_ids/偏好由 LLM 抽; product_line 主数据反查)
│       │   │   ├── selector.py      # 策略选择(建模结构×目标 两维匹配)
│       │   │   ├── registry.py      # 策略注册表
│       │   │   ├── strategies/
│       │   │   │   ├── base.py          # PlanningStrategy 抽象基类(supported_objectives)
│       │   │   │   ├── flowshop_tardiness.py   # 产能桶-最小拖期(CP-SAT) TODO(v0.3)重命名
│       │   │   │   ├── jobshop_makespan.py     # 产能桶-最小完工(CP-SAT) TODO(v0.3)重命名
│       │   │   │   └── simple_dispatch.py      # EDD 派单规则(非优化类示范)
│       │   │   ├── validator.py     # 通用硬约束校验 + solve 前数据预检(不可行归因)
│       │   │   ├── strategy_mapping.yaml  # (产品线,目标)→策略 配置表
│       │   │   └── schemas.py       # PlanningRequest(含 horizon) 等
│       │   ├── scheduling/
│       │   │   ├── engine.py        # 调度执行引擎(ReAct入口,双触发,主体级互斥)
│       │   │   ├── agent_loop.py    # ReAct循环(思考→行动→观察+护栏)
│       │   │   ├── preconditions.py # 写操作前置断言(硬规则)
│       │   │   └── schemas.py
│       │   └── query/               # (v2 目录树误将本目录嵌于 scheduling/ 下, 此处修正)
│       │       ├── query_engine.py  # 检索→(只读工具取实时数据)→增强→生成
│       │       ├── retriever.py     # 向量检索(RAG)
│       │       └── schemas.py
│       │
│       ├── events/
│       │   ├── event_bus.py         # 内存事件总线
│       │   ├── dedup.py             # 去重/聚合/抑制(v3 新增, 见 §8)
│       │   ├── scheduler.py         # 定时巡检(含预测性齐套扫描, 带提前期窗口)
│       │   └── handlers.py          # 事件→任务描述→路由到消费引擎(v0.1 仅调度)
│       │
│       ├── foundation/
│       │   ├── master_data.py       # 主数据访问(含 order→product→product_line 反查)
│       │   ├── integration/
│       │   │   ├── base.py          # IntegrationAdapter 抽象接口(含 get_calendar 预留)
│       │   │   └── mock_adapter.py  # 模拟 MES/ERP/WMS(含简单物料预留、脚本化事件场景)
│       │   ├── tools/
│       │   │   ├── registry.py      # 工具注册表(含前置断言挂载)
│       │   │   └── builtin.py       # 内置工具(只读/写操作; 无 run_scheduling_solver)
│       │   ├── plan_store.py        # 计划版本存储(v3 新增; 初始内存实现)
│       │   ├── vectorstore.py
│       │   ├── embedding.py
│       │   ├── memory.py
│       │   ├── authz.py             # 权限/动作分级(PendingAction 含 expires_at)
│       │   ├── audit.py             # AuditLog(业务审计) + TraceLog(步级遥测) 两条流
│       │   └── llm.py
│       │
│       └── domain/
│           └── models.py            # 领域模型(含 Plan / MaterialReservation, v3 新增)
│
├── data/
│   └── mock/
│       ├── orders.json / bom.json / lines.json / inventory.json / work_orders.json
│       ├── knowledge/               # RAG 知识文档
│       └── event_scenarios.json     # 脚本化事件场景(v3: 替代随机事件, 测试可复现)
└── tests/
    ├── test_router.py / test_planning.py / test_scheduling.py / test_events.py
```

---

## 4. 共享底座 (SharedFoundation)

### 4.1 领域模型 (`domain/models.py`)

v2 已有实体保持不变：`Order` / `BomItem` / `ProductionLine` / `Material` / `WorkOrder` / `Shortage` / `KittingResult` / `ProductionException` / `SystemEvent` / `ActionResult` / `PendingAction`。

**v3 修订与新增：**

- `Plan`（**新增**）：计划版本。
  ```python
  class Plan(BaseModel):
      plan_id: str
      version: int
      status: Literal["draft", "published", "superseded"]
      strategy_name: str
      objective: str
      horizon_start: date
      horizon_end: date
      assignments: list[PlanAssignment]   # 订单→产线→起止日期
      frozen_wo_ids: list[str]            # 本次求解被冻结(不可移动)的任务令
      created_at: datetime
  ```
  - 排产结果一律以 `draft` 写入 `PlanStore`；用户认可后 `published`（v0.1 可由 CLI/API 一步确认）；新版本发布时旧版本置 `superseded`。
  - **调度引擎的下发动作只依据 `published` 计划**——解决"下发依据哪个版本"的悬空问题。
- `MaterialReservation`（**新增**）：物料预留。`reservation_id, material_id, wo_id, qty, created_at`。齐套检查按"库存 −已有预留"计算可用量，判齐套即写预留（Mock 内存实现即可）。**禁止**多个 WO 对同一库存重复判齐套（v2 缺陷，见 §7.4）。
- `PendingAction` **增加** `expires_at: datetime | None`——超时未确认的动作过期失效（超时升级策略 v0.2）。
- `Calendar`（**接口预留**）：工厂日历/班次。v0.1 不建模（默认每天可用、产能恒定），但 `IntegrationAdapter` 预留 `get_calendar()`，避免后续动接口。
- `Operation` / `Routing`：**v0.4 工序级细排的前置实体，本版本不定义**（见 §0.2）。

### 4.2 集成层 (`foundation/integration/`)

```python
class IntegrationAdapter(ABC):
    # 读 (ERP/MES/WMS)
    async def get_orders(self, filters: dict) -> list[Order]: ...
    async def get_bom(self, product_id: str) -> list[BomItem]: ...
    async def get_lines(self) -> list[ProductionLine]: ...
    async def get_inventory(self, material_ids: list[str]) -> list[Material]: ...
    async def get_work_orders(self, filters: dict) -> list[WorkOrder]: ...
    async def get_material_status(self, material_id: str) -> dict: ...
    async def get_calendar(self, line_id: str | None = None) -> dict:
        """工厂日历/班次。v0.1 Mock 返回'全年每天可用'; 接口先立住。"""
    # 物料预留 (v3 新增)
    async def reserve_materials(self, wo_id: str, items: list[dict]) -> list[MaterialReservation]: ...
    async def get_reservations(self, material_ids: list[str]) -> list[MaterialReservation]: ...
    # 写 (需经 AuthZ)
    async def dispatch_work_order(self, wo_id: str) -> ActionResult: ...
    async def update_work_order_status(self, wo_id: str, status: str) -> ActionResult: ...
    async def send_message(self, recipient: str, channel: str, content: str) -> ActionResult: ...
    # 事件源
    async def poll_events(self) -> list[SystemEvent]: ...
```

**`mock_adapter.py`**：读接口从 `data/mock/*.json`；写接口写内存 outbox/action_log；预留用内存字典。`poll_events` **不再随机产生事件**（v2 缺陷：测试不可复现），改为读取 `data/mock/event_scenarios.json` 的脚本化场景（按时间步/调用次数触发既定事件序列），演示与测试均可复现。

### 4.3 工具库 (`foundation/tools/`)
- `registry.py`：`ToolRegistry`，工具含 `name`/`description`/`parameters`(JSON schema)/`handler`，可导出 OpenAI function-calling 格式；写操作挂前置断言。
- `builtin.py` 内置工具（**都通过 IntegrationAdapter 实现**）：
  - 只读：`query_orders`, `query_inventory`, `query_work_orders`, `check_kitting`, `analyze_material_shortage`, `analyze_exception_impact`
  - 写操作（过两道护栏）：`send_expedite_message`, `dispatch_work_order`, `update_work_order_status`, `notify_personnel`
  - 辅助：`classify_exception`（LLM 工具）, `record_followup`
  - `request_replan`（**v3 替代 v2 的 `run_scheduling_solver`**）：不直接调求解器（那会破坏引擎独立原则且命名错乱——v2 文档内部自相矛盾处），而是发布 `replan_request` 事件到事件总线。v0.1 该事件仅落日志+待办；v0.2 路由到排产引擎，且触发重排列为 `requires_confirmation` 动作。

### 4.4 LLM 封装 (`foundation/llm.py`)
同 v2：`complete(system, messages, tools=None)`（封装内完成工具循环）与 `classify(system, user_input, schema)`（JSON 模式优先、能力降级、失败重试一次并回喂错误）。兼容差异由 `LLMClient` 吸收，业务无感。不硬编码任何密钥/base_url。

### 4.5 记忆 (`foundation/memory.py`)
同 v2：`ConversationMemory` 按 `session_id` 存对话历史 + 当前引擎（会话粘性 v0.2 预留）+ 上次排产结果引用（存 `plan_id`，不再复制结果本体——结果在 `PlanStore`）。

### 4.6 权限与审计 (`foundation/authz.py`, `foundation/audit.py`)
- `AuthZ` 分级同 v2：读恒允许；内部催料 `auto`；供应商催料 / 下任务令 / 改状态 `requires_confirmation`；配置表驱动。
- `requires_confirmation` 动作生成 `PendingAction`（含 `expires_at`），语义见 §7.3（**单动作确认执行**）。
- **v0.2 第一优先级（v3 明确）**：`/chat/confirm` 当前无鉴权，任何持有 action_id 者可批准供应商催料/下发——单用户 demo 可接受，多用户前**必须**将确认动作与用户身份绑定并记录批准人。
- **审计/遥测分流（v3 修订）**：
  - `AuditLog`（业务审计）：写操作、授权判定、路由判定、策略选择、计划发布。低量、长保留、面向业务复盘。
  - `TraceLog`（步级遥测）：ReAct 每步思考/工具调用/观察、LLM 调用明细。高量、短保留、面向调试。
  - v0.1 两者都可先落结构化日志文件+内存列表，但**必须是两条独立的流**，避免业务审计被调试噪声淹没。

---

## 5. Orchestrator（统一入口）

### 5.1 职责
接收用户输入 → 路由判断意图 → 调用对应引擎 → 返回结果；低置信度时澄清。

### 5.2 路由器 (`router.py`)

> **v3 定位调整**：本平台是**低 QPS 内部工具**（单个计划员/调度员使用），LLM 小模型直接分类的延迟与成本完全可接受、准确率更高；嵌入路由需要维护示例话术、调双阈值、建误判回流闭环，运维成本不低。因此 v3 把主次反转：**LLM 结构化分类是主路径；嵌入路由是可选加速层**（`EMBED_MODEL` 未配置则整层跳过），流量大了再启用并逐步前移负载。margin 判据、示例话术、回流机制等 v2 设计全部保留，只是层级定位变化。
> 路由匹配的是**意图**，不是**字面**——"排产是什么？"是 query 不是 planning，纯关键词匹配的反模式继续禁止。

**分层判断，按顺序：**

**第 0 层：显式命令（硬规则，仅零歧义场景）**
- UI 明确动作、斜杠命令（`/排产`、`/催料`）→ 直接路由，`route_method=explicit`。
- **绝不**做"出现『排产』二字就判排产"的关键词猜测。

**第 1 层（可选）：嵌入路由（配置了 `EMBED_MODEL` 才启用）**
- 各类别示例话术 embed 成原型；**置信判据必须用 margin**：`top1_score ≥ 阈值A` 且 `top1 − top2 ≥ 阈值B` 才直接路由；仅高分但两类贴近 → 降级下一层。记录 top1/top2/margin。

**第 2 层（主路径）：LLM 结构化分类**
- `LLMClient.classify`，输入含最近 N 轮上下文与当前会话引擎，强制返回：
  ```python
  class RouteDecision(BaseModel):
      intent: Literal["planning", "scheduling", "query", "ambiguous"]
      confidence: float
      entities: dict
      reason: str
  ```
- `confidence ≥ 0.8` 且 intent 明确 → 路由；否则 → 第 3 层。

**第 3 层：用户澄清（带选项）**
- **选项式回答 → 直接按所选路由，不重跑分类**（重跑会把已明确的选择又搞模糊）。
- 开放式回答 → 合并上下文回到第 2 层。

**类别定义（v3 按副作用划界，写进分类 prompt）：**
- `planning`：要**生成/重新生成计划**——"帮我排产""重排这批单""2号线停了，重排"。
- `scheduling`：要**执行有副作用的动作**——"催一下料""下发任务令""设备报警了，处置一下"。
- `query`：**一切只读**——概念（"排产是什么"）、知识（"齐套率怎么算"）、历史（"上次那个排产结果"）、**实时状态（"料齐了吗""哪些任务缺料开不了工""几个在制工单"）**。

**易混淆对照例句（v3 修订版，写进第 2 层 prompt）：**
| 用户输入 | 正确意图 | 区别点 |
|---|---|---|
| 把这批订单重新排一下 | planning | 重新求解计划 |
| 排产是什么 / 解释一下排产 | query | 概念，不执行 |
| 把今天的任务令下发了 | scheduling | 执行动作 |
| 2号线停了，重排 | planning | 触发重新求解 |
| **2号线那批料齐了吗** | **query**（v2 误划 scheduling） | **只读状态查询，无副作用** |
| **哪些任务因为缺料开不了工** | **query**（v2 误划 scheduling） | **只读查询** |
| 缺料的单帮我催一下 | scheduling | 催料是写动作 |
| 给供应商催一下 A 物料 | scheduling | 写动作 |
| 上次那个排产结果呢 | query | 查历史 |
| 这个系统怎么用 | query | 使用咨询 |

**全程可观测与闭环**：每次路由记录走到哪层、各层判定、最终路由、用户是否纠正，进 `AuditLog`；误判案例回流补充示例话术/分类 prompt。

### 5.3 v0.2 预留
- 会话粘性：延续性短句优先归当前会话引擎。
- 复合任务：识别 `composite` 并拆解为有序 steps（`RouteDecision` 预留 `steps` 字段）。

---

## 6. 排产引擎 (PlanningEngine) — 策略插件化

> **核心现实：不存在「一个排产算法」，只有「一族排产策略」。** 引擎本体不绑定算法，只负责「抽参 → 选策略 → 求解 → 校验 → 解释 → 计划入库」编排；每种排产场景是可插拔策略插件。
>
> **v3 关键修正——建模结构与优化目标正交**：
> - **产品线决定建模结构**（可行域与约束形态：换型、模具、保质期……）。
> - **objective 决定目标函数**（min_tardiness / min_makespan / min_setup……）。
> - 一个策略 = 一个**建模模板**，声明它支持哪些目标（`supported_objectives`），求解时读取 `request.objective` 构造目标函数。**禁止**为每个（产品线×目标）组合写一个策略类（组合爆炸），也**禁止**选择层只看产品线、把用户明说的目标静默丢弃（v2 示例 A 的 bug：用户要"别拖期"，规则映射却命中 Makespan 策略）。
> - 现有 `FlowShopTardiness` / `JobShopMakespan` 是"目标焊死"的旧结构，迁移到 `supported_objectives` 列为 `TODO(v0.3)`；过渡期允许一个策略只支持一个目标，但**选择层必须校验目标匹配**，不匹配即澄清而非静默选错。

### 6.1 流程（对话驱动）
```
意图+实体 → [extractor] 抽 order_ids/偏好/horizon; product_line 由主数据反查
        → [validator.precheck] solve 前数据预检(产能总量/产品匹配/数据完备, 给人话不可行原因)
        → [selector] 选策略: (产品线,目标) 两维匹配 → LLM辅助 → 澄清
        → [strategy.solve] 带 time_limit 求解(拖期为软约束)
        → [validator] 通用硬约束校验 + 策略特有校验
        → LLM 解释 → 计划以 draft 写入 PlanStore → 返回(可迭代, 确认后 publish)
```

### 6.2 策略抽象 — `strategies/base.py`

```python
class PlanningStrategy(ABC):
    # --- 元信息(供选择层使用) ---
    name: str
    applicable_product_lines: list[str]
    scenario_description: str          # 自然语言"何时该用它"(喂给LLM选择器)
    supported_objectives: list[str]    # v3: 该建模模板支持的目标函数(替代单一 objective_type)
    granularity: Literal["capacity_bucket", "operation_level"]  # v3: 排产粒度声明(见§0.2)

    @abstractmethod
    def required_data(self) -> list[str]:
        """声明需要哪些额外数据(如换型矩阵、模具数量、保质期), 供输入校验"""

    @abstractmethod
    def validate_input(self, request, data) -> ValidationReport:
        """策略特有的输入完备性校验(缺数据则报告)"""

    @abstractmethod
    def solve(self, request, data, *, time_limit_s: float) -> PlanningResult:
        """带时间预算求解。到时返回当前最优可行解并在结果中标注 is_optimal=False。
        拖期类目标必须建为软约束(目标函数惩罚), 保证模型在数据预检通过后恒有解。"""

    @abstractmethod
    def explain_hints(self, result) -> dict:
        """提供给 LLM 生成解释的结构化要点"""
```

设计收益不变：加新产品线 = 新增策略类并注册，不动引擎、不动其它策略（开闭原则）。

### 6.3 策略注册表 — `registry.py`
同 v2：启动时注册，`get(name)` / `list_all()` / 按产品线查询。

### 6.4 策略选择层 — `selector.py`

**第 1 层 — 规则映射（`strategy_mapping.yaml`，两维匹配）**
```yaml
# v3: match 支持 product_line / scenario / objective 组合
- match: { product_line: "SMT贴片" }
  strategy: "SetupMinimizeHeuristic"       # TODO(v0.2)
- match: { product_line: "注塑" }
  strategy: "JobShopMakespan"
- match: { product_line: "食品灌装", scenario: "保质期敏感" }
  strategy: "BatchProcessScheduling"        # TODO(v0.2)
- match: { product_line: "*" }
  strategy: "FlowShopTardiness"
```
命中后**必须校验目标匹配**：`request.objective ∈ strategy.supported_objectives`？
- 匹配（或用户未指定目标，用策略默认）→ 选定，`solve` 以该 objective 构造目标函数。
- 不匹配（如注塑命中的模板不支持 min_tardiness）→ **不静默丢弃用户目标**：向用户澄清「注塑线常用模具约束建模（目标：最小完工），你要求最小拖期——按哪个来？」或降级 LLM 辅助找支持该目标的候选策略。

**第 2 层 — LLM 辅助选择（规则未命中时）**：把已注册策略的 `name + scenario_description + supported_objectives` 喂给 LLM，结合请求选择，返回结构化结果：
```python
class StrategySelection(BaseModel):
    strategy_name: str
    confidence: float
    reason: str
```

**第 3 层 — 低置信澄清**：`confidence < 阈值` → 向用户澄清（带候选策略选项）。宁可问一次，不可选错一次。

### 6.5 各组件

- **`extractor.py`**（v3 修订）：
  ```python
  class PlanningRequest(BaseModel):
      order_ids: list[str]
      line_ids: list[str] = []
      horizon_start: date | None = None     # v3 新增: 排产时间窗(缺省=今天)
      horizon_end: date | None = None       # v3 新增: 缺省=今天+配置的默认窗口(如14天)
      product_line: str | None = None       # v3: 由主数据反查得出, 非用户口述
      scenario: str | None = None
      objective: str | None = None          # 参与策略选择(§6.4), 不再被丢弃
      locked_assignments: list[dict] = []   # 用户手动锁定项
      excluded_lines: list[str] = []
  ```
  - **`product_line` 获取规则（v3 强制）**：LLM 只从用户话中抽 `order_ids` 与约束偏好；`product_line` 由 `order_ids → Order.product_id → 主数据` 反查得出。用户口述的产品线仅用于**冲突提示**（口述"注塑"但订单实为 SMT → 提示确认，不直接采信）。理由：产品线是 ERP 主数据事实，靠口述+LLM 抽取会把"选错建模"的风险引入系统，且 validator 查不出来。
  - `horizon` 是排产的基本输入（CP-SAT 时间域依赖它），v2 缺失，v3 补齐。
- **`strategies/`**：v0.1 保持 3 个示范策略（两个 CP-SAT 产能桶模型 + 一个 EDD 派单规则），证明插件机制与"非优化算法平等共存"。真实产品线策略 `TODO(v0.2)` 占位。
- **`validator.py`**（v3 扩展为两职责）：
  1. **solve 前数据预检（新增）**：产能总量粗校验（总需求 vs 窗口内总产能）、产品-产线匹配存在性、必要数据完备性。**不可行的"人话原因"由预检给出**——CP-SAT 返回 INFEASIBLE 时不附带原因，v2 §6.5"无解时返回明确不可行原因"的表述在工程上不成立；正确做法是拖期建软约束（预检通过后模型恒有解）+ 预检拦截真正的硬性不可行并归因。
  2. **solve 后通用硬约束校验**：产能、产品匹配、交期统计，独立复核不信任求解器；策略特有约束由各策略自检。
- **冻结期（v3 新增，重排场景强制）**：重排时引擎**自动**将 `status ∈ (dispatched, in_progress)` 的任务令加入锁定集（连同用户手动 `locked_assignments`），求解中这些分配不可移动，结果记入 `Plan.frozen_wo_ids`。理由："2号线停了，重排"时计划员不可能手动列出所有在制单；不冻结在制单的重排结果在车间无法执行。
- **解释**：求解结果 + 校验报告 + `explain_hints()` 交给 LLM 生成解释；`is_optimal=False`（到时返回）时明确告知"时间预算内的近优解"。

### 6.6 关键要求
- 计算只能由策略 `solve` 做，**不允许 LLM 生成排程结果**。
- **每次 `solve` 必须携带 `time_limit_s`**（config 可配，默认如 10s；CP-SAT 支持到时返回当前最优）。`POST /chat` 同步等待仅适用于演示规模；真实规模（数百订单×数十产线，求解分钟级）应改异步任务 + SSE 进度推送，接口形态 `TODO(v0.2)` 预留。
- 引擎本体不 import 具体策略类，只经 `StrategyRegistry`。
- 策略选择决策（命中规则/LLM、**目标匹配校验结果**、置信度）全部进 `AuditLog`。
- **求解结果写 `PlanStore`（draft），确认后 publish**；调度引擎只读 published 计划。

---

## 7. 调度执行引擎 (SchedulingEngine) — ReAct 智能体范式

> 范式与理由同 v2：执行层任务路径多变（催料、齐套、下发、异常处置交织），把现有系统接口包装成工具让 LLM 编排，成本远低于为每条业务流写死状态机；不确定性由两道护栏兜住。
> （术语注意：本引擎语义为"执行管理"，见 §0.1 术语表。）

### 7.1 双触发（两条入口，同一个智能体）
- **对话触发**：Orchestrator 路由进来（有副作用的请求，如"帮我催一下缺料的单"）。
- **事件触发**：EventLayer 唤醒（经 §8 三道防线过滤后的事件转任务描述）。
- 复用同一 ReAct 智能体，仅初始任务不同。

### 7.2 ReAct 循环（`engine.py` + `agent_loop.py`）

循环主体同 v2：
```
给定任务 → [Reason] → [Act: 结构化 tool_call]
  → (写操作) [前置断言] → [AuthZ] → [执行] → [Observe] → 循环
  直到任务完成 或 触达终止条件
```

**循环护栏（必须实现）**：最大步数、工具白名单、死循环检测（连续重复同工具同参数即中断）、只读优先。

**并发护栏（v3 新增，必须实现）**：
- **主体级互斥**：每个 agent run 声明其操作主体（wo_id / material_id 集合）；同一主体已有进行中的 run 时，新触发（无论对话还是事件）**排队或拒绝并说明**，不并行执行。理由：对话与事件可并发唤醒多个实例，两个实例同时催同一物料/同时操作同一 WO 会产生重复写操作，内存队列无幂等保障。
- v0.1 用进程内 `asyncio.Lock` 字典按主体加锁即可；跨进程锁 `TODO(v0.2)`。

### 7.3 写操作的两道护栏（安全的命根子）

**护栏一：前置断言（代码硬规则，不依赖 LLM 记得检查）**
- 同 v2：写操作工具注册时附带硬规则断言，不满足直接拦截并回喂原因：
  - `dispatch_work_order`：WO 已齐套 **且** 前道完成 **且**（v3 新增）**属于当前 `published` 计划**（呼应 §4.1 计划版本）。
  - `send_expedite_message`：确实缺料 **且** 近期未重复催。

**护栏二：强制授权（AuthZ，人工确认关口）**
- 分级同 v2：内部催料 `auto`；供应商催料/下任务令/改状态 `requires_confirmation`。
- **待确认动作语义（v3 修正）**：
  - v2 表述"待确认动作会中断当前循环，等用户确认后**续跑**"——续跑要求 agent 状态快照与恢复，v0.1 全内存实现做不到（重启即丢），事件触发的 run 也无人在场等待。
  - **v3 语义：确认即执行该单个动作，不恢复 ReAct 循环。** 智能体把 `requires_confirmation` 动作登记为 `PendingAction`（含完整参数与 `expires_at`）后**继续或结束当前循环**（可继续处理不依赖该动作结果的其他工作）；用户确认时系统**直接执行该动作**并记审计，不重新唤醒智能体。若需基于执行结果继续工作，作为新任务重新触发。
  - `expires_at` 超时未确认 → 动作失效并进待办提醒；超时升级（自动上报主管等）`TODO(v0.2)`。
  - 事件触发产生的待确认动作写入「待办/通知」（v0.1 打印+日志）。

> 两道护栏分工不变：**前置断言**保证"流程前提对"（拦漏步/乱序），**授权**保证"这一步人认可"（拦单步错）。

### 7.4 调度工具集
同 v2 三类（只读/写操作/辅助，见 §4.3 列表），直接包装现有系统接口、不追求精致原语（控成本）。**v3 修订**：
- `check_kitting` 基于**预留语义**计算（§4.1）：可用量 = 库存 − 在先预留；判齐套即写预留。杜绝"两个 WO 共享同一份库存都判齐套、下发后才发现缺料"——这正是齐套检查要防的事故。
- `request_replan` 见 §4.3：发 `replan_request` 事件，不直接调求解器。
- 异常处置的关键决策仍留人：智能体做分类、影响分析、给建议，改派/插单等关键写操作一律 `requires_confirmation`。

### 7.5 关键要求
- ReAct 每步思考/行动/断言/授权/观察进 **TraceLog**；写操作与授权判定进 **AuditLog**（§4.6 分流）。
- 写操作必须过两道护栏，任何路径不得绕过。
- 最大步数、白名单、死循环检测、**主体级互斥**四个护栏齐备。
- 事件触发与对话触发复用同一智能体，仅初始任务描述不同。

---

## 7B. 查询引擎 (QueryEngine) — RAG + LLM + 只读工具

> **v3 职责扩大（按副作用划界的结果）**：一切只读问答归本引擎——概念解释、知识库问答（排产规则/异常处置手册/SOP）、历史查询、**实时状态查询**（"料齐了吗""哪些任务缺料开不了工""几个在制工单"）。它不执行任何写操作。

### 7B.1 结构（`engines/query/`）
```
query 请求
  └─▶ [Retrieve] 从 VectorStore 检索知识库片段
        + (按需) 调只读工具取实时数据(check_kitting/query_work_orders/query_inventory...)
  └─▶ [Augment] 检索结果/实时数据分区组装进 prompt, 标明来源
  └─▶ [Generate] LLM 生成回答, 附引用来源
```

### 7B.2 关键要求
- **只读**：不得触发任何写操作，不挂 AuthZ 写路径。若用户在查询中顺带要求动作（"缺料的单帮我催一下"），路由层应判为 scheduling；查询引擎兜底遇到动作请求时回复引导，而非执行。
- **检索为先**：概念/知识类必须先检索再生成，禁止纯靠 LLM 记忆瞎答；检索不到如实说明，不编造。
- 实时状态类查询可直接走只读工具（不必强行过向量检索）。
- chunking/embedding 与路由层共用 embedding client；rerank/混合检索 v0.2+。

---

## 8. 事件层 (EventLayer) — 平台级设施

### 8.1 组件
- **`event_bus.py`**：`asyncio.Queue` 内存事件总线，`publish` / `subscribe`。`SystemEvent`：`event_id, type, payload, timestamp`。事件类型含 `material_shortage_warning` / `equipment_alarm` / `quality_issue` / **`replan_request`（v3 预留）**。
- **`scheduler.py`**：定时巡检（间隔可配，默认 30s）：
  1. `IntegrationAdapter.poll_events()` 拉外部事件；
  2. **预测性齐套扫描**——只扫描 `planned_start` 落在**提前期窗口**内的待开工任务令（窗口 = 物料催料周期，可配默认如 3 天）。v2 未定义窗口，会对所有未来任务令无差别报警；预警早于催料周期才有业务意义。
- **`dedup.py`（v3 新增，三道防线，publish 前生效）**：
  1. **去重**：同 `(type, 主体key)` 在**处置窗口**（可配，如 30 分钟）内只发布一次。主体 key 如 `material_shortage:{wo_id}` / `equipment_alarm:{line_id}`。否则 30s 巡检会让同一缺料每轮重复产生事件、重复唤醒 ReAct（每次多个 LLM 调用），成本与重复动作双失控——前置断言"未重复催"只兜得住催料这一个动作，兜不住重复唤醒本身。
  2. **聚合**：同一物料短缺影响 N 个任务令 → 聚合为**一个**事件/任务（"物料 M 短缺，影响 WO-1..WO-N"），而非 N 个 agent run。
  3. **抑制**：主体已有进行中的 agent 任务（§7.2 互斥表可查）→ 不再唤醒。
- **`handlers.py`**：事件 → 任务描述 → **按路由表分发到消费引擎**。v0.1 路由表：
  - `material_shortage_warning` → 调度智能体："某物料短缺影响 WO-x..，请归因并催料"
  - `equipment_alarm` → 调度智能体："某设备报警，请做影响分析并给处置建议（关键决策待人确认）"
  - `replan_request` → 落日志+待办（**v0.2 改为 → 排产引擎，执行前过 `requires_confirmation`**）
  - 这样 v0.2 打开"异常→影响分析→重排"闭环时**只改路由表，不动架构**。

### 8.2 运行方式
- FastAPI 启动时后台 asyncio task 跑巡检 + 消费循环。
- `POST /events` 手动注入事件（测试用），注入的事件同样过三道防线。

---

## 9. 接口设计

### 9.1 HTTP API（`main.py`）
- `POST /chat`：统一对话入口。`{session_id, message}` → `{reply, route_decision, pending_actions?, data?}`。
- `POST /chat/confirm`：确认待执行动作。`{session_id, action_id, approved}`。语义：**执行该单个动作**（§7.3），过期动作返回失效提示。
- `POST /events`：注入系统事件（测试）。
- `GET /audit`：查审计日志。`GET /pending`：查待确认动作。`GET /health`。
- 计划相关（v3 新增，最小集）：`GET /plans`（列版本）、`POST /plans/{plan_id}/publish`（发布 draft）。

### 9.2 CLI（`cli.py`）
交互式 REPL：路由判定 + 回复 + 待确认动作；支持 `confirm <action_id>` 与计划发布。

---

## 10. 数据流示例（验证实现正确）

**示例 A — 排产（v3 修正版：用户目标不再被丢弃）**
```
用户: "把注塑线的订单 O001,O002,O003 排一下，尽量别拖期"
→ Router: LLM 分类 → planning
→ Extractor: order_ids=[O001..O003], objective=min_tardiness, horizon 缺省=今天+14天
→ 主数据反查: O001..O003 → 产品 → product_line="注塑"(与口述一致, 无冲突提示)
→ Validator.precheck: 产能总量/产品匹配预检通过
→ Selector: mapping 命中 注塑→JobShopMakespan → 校验目标: min_tardiness ∉ supported_objectives
   → 不静默选错! 澄清: "注塑线默认按模具约束建模(最小完工); 你要求最小拖期,
      可选 ① 换用拖期优化模板 ② 维持注塑模板(以完工时间为目标)" → 用户选①
→ FlowShopTardiness.solve(time_limit=10s): 返回排程(is_optimal 标注)
→ Validator: 通用校验 + 策略校验 → 报告
→ 计划以 draft 入 PlanStore; LLM 解释(含 explain_hints) → 返回; 用户确认后 publish
```

**示例 B — 催料（对话驱动，ReAct 编排）**
```
用户: "缺料的单帮我催一下"
→ Router: scheduling(有副作用)
→ ReAct: check_kitting(预留语义) → analyze_material_shortage → send_expedite_message
   → 前置断言(确实缺料+未重复催) → AuthZ(内部auto/供应商待确认, PendingAction 带 expires_at)
   → record_followup → 汇报: 已催N条+待确认M条
→ 步级过程进 TraceLog; 写操作/授权进 AuditLog
```

**示例 B2 — 前置断言拦截（护栏一验证）**
```
用户: "把 WO-200 下发了"
→ ReAct: dispatch_work_order(WO-200)
→ 前置断言: WO-200 未齐套(且不在 published 计划) → 拦截, 原因回喂
→ 智能体解释不能下发 + 建议先催料
（验证: ReAct 即便想直接下发, 也被代码硬规则拦住, 不依赖 LLM 记得检查）
```

**示例 C — 事件驱动（含 v3 防线验证）**
```
[巡检] WO-123 计划 2 天后开工(落在3天提前期窗口), 缺料 → material_shortage_warning
→ dedup: 30分钟处置窗口内首次 → 放行; 同物料还影响 WO-124/125 → 聚合为一个任务
→ handler → 唤醒调度 ReAct(主体锁: material M) → 归因 → 催料(过两道护栏)
→ 下一轮巡检(30s后)同一缺料 → 去重拦截, 不再重复唤醒  ✅
```

**示例 D — 低置信澄清**
```
用户: "3号线那批单有问题，处理下"
→ LLM 分类 → ambiguous, confidence=0.5
→ 澄清: "想让我做哪个？① 重新排产 ② 查异常并处置"
→ 用户选② → 直接路由 scheduling, 不重跑分类
```

**示例 E — 只读查询归 query（v3 边界验证）**
```
用户: "2号线那批料齐了吗"
→ Router: query(只读状态查询, v2 曾误划 scheduling)
→ QueryEngine: 调只读工具 check_kitting → 组装回答, 附数据来源
用户: "排产是什么？"
→ Router: query(概念) → RAG 检索→增强→生成, 附知识库来源, 不进排产引擎  ✅
```

---

## 11. 实现优先级

1. 项目骨架：目录、配置、领域模型（含 `Plan`/`MaterialReservation`）、mock 数据（含知识文档与 `event_scenarios.json`）。
2. 共享底座：`IntegrationAdapter`+`MockAdapter`（含预留、脚本化事件）、`LLMClient`、`VectorStore`、`Audit/Trace` 双流、`AuthZ`（`expires_at`）、`ToolRegistry`+内置工具、`PlanStore`、`Memory`。
3. Orchestrator + Router（LLM 分类主路径 + 可选嵌入层 + 澄清）。
4. PlanningEngine：extractor（主数据反查）→ precheck → 策略框架（`supported_objectives` 校验）→ 2-3 示范策略（带 time_limit）→ validator → 解释 → PlanStore。
5. SchedulingEngine：agent_loop + 四护栏（步数/白名单/死循环/**主体互斥**）+ 两道写护栏 + 工具集（预留语义齐套）。
6. QueryEngine：retriever + 只读工具接入 + 检索→增强→生成。
7. EventLayer：event_bus + **dedup 三道防线** + scheduler（提前期窗口）+ handlers（事件路由表）。
8. 接口层：FastAPI + CLI（含计划发布）。
9. 测试：各引擎与路由 pytest（LLM mock；事件场景脚本化保证可复现）。

---

## 12. 验收标准

**沿用 v2 的核心验收**（策略插件化：加策略不动引擎；两类算法共存；ReAct 自主编排；B2 断言拦截；三循环护栏+步级日志；写操作双护栏不可绕过；RAG 附来源、检索不到不编造；事件自动唤醒；选项式澄清不重跑分类；审计可查；MockAdapter 可替换业务无感；pytest 全绿），**v3 新增/修订**：

- [ ] **示例 A：用户目标不被丢弃**——objective 与策略 `supported_objectives` 不匹配时触发澄清，而非静默选错（v2 缺陷回归项）。
- [ ] `product_line` 由主数据反查得出；用户口述与主数据冲突时提示确认。
- [ ] 排产结果以 `Plan(draft)` 入 `PlanStore`，发布后 `published`；`dispatch_work_order` 前置断言校验 WO 属于 published 计划。
- [ ] **重排自动冻结**：存在 `dispatched/in_progress` 任务令时重排，这些 WO 出现在 `Plan.frozen_wo_ids` 且分配未被移动。
- [ ] **齐套预留**：两个 WO 依赖同一份不足库存时，只有一个判齐套（预留语义验证）。
- [ ] 每次 `solve` 带 time_limit；到时返回近优解并在解释中标注。
- [ ] 不可行原因由 **solve 前预检**给出人话归因（如"窗口内总产能不足"），而非依赖求解器 INFEASIBLE。
- [ ] **事件去重**：连续两轮巡检发现同一缺料，只产生一次 agent 唤醒（示例 C 回归项）。
- [ ] **事件聚合**：同一物料影响多个 WO 聚合为一个任务。
- [ ] **主体互斥**：对同一 WO 并发触发两个任务时，第二个排队/拒绝而非并行写。
- [ ] `PendingAction` 过期后确认返回失效提示；确认语义为执行单个动作（不恢复循环）。
- [ ] "2号线那批料齐了吗"路由到 **query** 并经只读工具回答（v3 边界回归项）。
- [ ] `EMBED_MODEL` 未配置时路由完整可用（LLM 主路径验证）。
- [ ] AuditLog 与 TraceLog 为两条独立流；`GET /audit` 只含业务审计。
- [ ] Mock 事件按 `event_scenarios.json` 脚本触发，同一场景两次运行结果一致（可复现验证）。

---

## 13. 给 Claude Code 的实现备注

- 包路径为 `src/scheduling_platform/`，**禁止**命名为 `platform`（stdlib 名遮蔽依赖导入）。
- 不硬编码 API key；`LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL` 走 `.env`（`.env.example` 给 DeepSeek 示例占位）；`EMBED_MODEL` 可选，未配置时嵌入路由层跳过。
- 所有 LLM 调用带解析失败重试一次（错误回喂）；彻底失败时降级（分类失败→ambiguous 澄清；抽参失败→regex 兜底；解释失败→模板）。**降级模式下求解/齐套/催料/下发/事件/审计全部可用**，架构可离线验证。
- 优先架构清晰、接口隔离、可运行；桩处用 `# TODO(v0.2)` / `# TODO(v0.3 策略重命名/supported_objectives 迁移)` / `# TODO(v0.4 工序级细排)` 标注。
- 写清晰 docstring 与类型注解；关键控制流加结构化日志。
- mock 数据支撑全部示例跑通，且必须包含：可排订单、缺料任务令、**同一物料多 WO 竞争**（验证预留）、**在制任务令**（验证冻结）、**事件场景含重复缺料**（验证去重）。
