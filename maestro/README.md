# 生产调度与排产 Agent 平台 (v0.2)

「一个平台 / 三个引擎 / 一个入口」: 用户通过统一对话入口提出请求，平台自动判断
属于**排产**、**调度**还是**查询**意图，路由到对应引擎执行；调度引擎还能被系统事件
(缺料预警/设备报警) **自动唤醒**。三个引擎对应三种范式:

- **排产 PlanningEngine —— 固定工作流**: 抽参 → 选策略(插件化) → 求解 → 校验 → 解释。
- **调度 SchedulingEngine —— ReAct 智能体**: 思考→行动→观察循环，自主编排工具；
  钉死循环护栏 (最大步数 / 工具白名单 / 绕圈检测) 与写护栏 (前置断言 + 授权)。
- **查询 QueryEngine —— RAG + LLM**: 检索知识库 → 增强提示 → 生成 (只读工具，答案附来源)。

```
用户 (CLI / HTTP) → Orchestrator (嵌入语义路由 → LLM 分类 → 低置信澄清/澄清后直接路由)
                      ├─ PlanningEngine   排产: 固定工作流 (策略插件化)
                      ├─ SchedulingEngine 调度: ReAct 智能体, 齐套/催料/下发/异常 (对话+事件双触发)
                      └─ QueryEngine      查询: RAG + 只读工具 (答案附来源)
                                  ↑ EventLayer: 定时巡检 + 内存事件总线 (事件→任务描述唤醒智能体)
SharedFoundation: 集成层(MockAdapter) / 齐套底座 / 工具库 / LLM封装 / 向量库+嵌入 / 记忆 / AuthZ / 审计
```

> **与设计文档的偏离**: 文档中包名为 `src/platform/`，因 `platform` 是 Python
> 标准库模块名 (会遮蔽 openai/uvicorn 等依赖的 import)，实际包名为
> `src/maestro/`，其余结构与文档一致。

## 安装

```bash
cd maestro
uv venv --python 3.12          # ortools 暂不支持 3.14；3.11/3.12/3.13 均可
source .venv/bin/activate
uv pip install -e ".[dev]"
```

(不用 uv 的话: `python3.12 -m venv .venv && pip install -e ".[dev]"`)

## 配置 .env

```bash
cp .env.example .env
# 编辑 .env 填入 LLM_API_KEY (默认 DeepSeek；换 OpenAI/千问/vLLM 只改三个 LLM_ 变量)
```

**意图路由 (三层，设计文档 5.2)**: ①嵌入语义路由 (向量相似度 + margin 判据，命中即
直接路由) → ②LLM 结构化分类 (嵌入低置信/不可用时) → ③低置信澄清 (澄清后选项式回答
直接路由、开放式回答回到 LLM 层)。嵌入需配 `EMBED_MODEL` (见 .env)，留空则跳过第①层
直接走 LLM。

**无 API Key 也能跑**: 嵌入/LLM 不可用时路由降级为澄清，抽参退化为正则、解释退化为
模板，其余全链路 (排产求解/齐套/催料/下发/事件驱动/审计) 仍然可用，便于先验证架构。

## 运行

```bash
# CLI (推荐先体验)
python -m maestro.cli

# HTTP API
uvicorn maestro.main:app --reload
```

### CLI 走查 (对应设计文档 4 个示例)

```text
你> 把注塑线的订单 O001,O002,O003 排一下，尽量别拖期
    → 路由 planning；选择器按产品线"注塑"命中 JobShopMakespan；OR-Tools 求解 + 解释

你> 现在有哪些任务因为缺料开不了工，帮我催一下
    → 路由 scheduling；齐套→催料；内部催料自动发(outbox)，供应商催料返回待确认

你> confirm <action_id>          # 确认供应商催料 / 任务令下发
你> patrol                       # 手动跑一次巡检: 自动发现缺料任务令并唤醒调度引擎 (示例C)
你> 3号线那批单有问题，处理下      # 低置信 → 带选项澄清 (示例D)
你> audit / pending              # 审计日志 / 待确认动作
```

### HTTP API

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/chat` | 统一对话入口 `{session_id, message}` |
| POST | `/chat/confirm` | 确认待执行动作 `{session_id, action_id, approved}` |
| POST | `/events` | 手动注入系统事件 (测试事件驱动) `{type, payload}` |
| GET | `/audit` | 审计日志 (`?action=&limit=`) |
| GET | `/pending` | 待确认动作 |
| GET | `/health` | 健康检查 |
| GET | `/extension-catalog/skills` | Skill Hub 远程目录（搜索、来源、更新状态） |
| GET | `/extension-catalog/connectors` | MCP 连接器市场 |
| POST | `/extension-catalog/sync` | 手动增量同步（Bearer 管理凭证） |

```bash
# 注入缺料事件，观察调度引擎被自动唤醒 (服务端日志可见催料动作)
curl -X POST localhost:8000/events -H 'content-type: application/json' \
  -d '{"type":"material_shortage_warning","payload":{"wo_id":"WO-123"}}'
curl localhost:8000/audit | python -m json.tool
```

## 测试

```bash
pytest          # LLM 全部 mock，不发网络请求
```

## 关键设计

- **策略插件化**: 排产引擎不绑定算法，只编排「选策略→跑→校验→解释」。新产品线 =
  新增一个 `PlanningStrategy` 子类并在 `bootstrap.py` 注册 (见 `tests/test_planning.py::test_strategy_plugin_registration`)。
  v0.1 自带 3 个示范策略: FlowShopTardiness (CP-SAT 最小拖期，兜底)、
  JobShopMakespan (CP-SAT 最小完工，注塑)、SimpleDispatch (EDD 纯规则，SMT)。
- **策略选择三层**: `strategy_mapping.yaml` 规则映射 → LLM 辅助 → 低置信澄清。
- **动作分级授权**: 写操作统一走 `ActionGate` (auto / requires_confirmation)，
  全部进审计；供应商催料、任务令下发、异常通知均需人确认。
- **集成层抽象**: 业务只依赖 `IntegrationAdapter` 接口；接真实 MES/ERP/WMS 时
  实现该接口并在 `bootstrap.py` 替换 `MockAdapter` 即可，引擎/工具零改动。
- **事件驱动**: 巡检 (拉外部事件 + 预测性齐套扫描) → 事件总线 → 调度引擎，
  事件被翻译成任务描述唤醒同一个 ReAct 智能体 (与对话路径复用同一套工具与护栏)。

## v0.2 预留 (代码中以 TODO(v0.2) 标注)

会话粘性路由 / 复合任务拆解 (`RouteDecision.steps`) / 催料超时自动升级 /
前道工序校验 / 换型最少与保质期策略 / 多任务令物料分配 / 异常复盘知识沉淀。
