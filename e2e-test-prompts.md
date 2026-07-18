# 制造排产 Agent — 端到端测试提示词套件（E2E Test Prompt Suite）

> 用途：让一个大模型（或你自己）扮演"端到端测试工程师"，通过聊天接口驱动整套系统，
> 逐条验证其全部公开能力，并产出带证据的测试报告。
> 重点覆盖你提到的 **A 技能能力**——即系统的 Agent 技能（Skill）能力：多轮对话、工具使用、
> Skill 使用、以及 **Skill 的三层加载（渐进式披露）**。

---

## 0. 关于"你提到的 A 技能能力"

我把你说的 **A 技能能力** 理解为系统的 **Agent 技能（Skill）能力**——即把一份 `SKILL.md`
当作可执行的 ReAct 流程来 **加载 → 路由 → 调用工具 → 按需读取附件/脚本**。
其中"**Skill 的三层加载**"对应设计文档里的 **渐进式披露（progressive disclosure）** 三层：

| 层 | 名称 | 何时加载 | 路由层是否可见 | 测试落点 |
|----|------|----------|----------------|----------|
| **L1** | frontmatter 元数据层 | 导入即落盘索引，启动即载入 | ✅ 可见 `description` + `when_to_use` | 技能在目录里、能被路由候选命中，但正文未读 |
| **L2** | SKILL.md 正文层 | **触发执行时才从磁盘读** | ❌ 路由阶段不读正文 | 触发后回复遵循正文指令；route 帧先出（只有 skill_id），随后才出 tokens |
| **L3** | 附件 & 脚本层 | **执行中按需读取** | ❌ | `read_skill_file` 读附件；`run_skill_script` 跑脚本（需先 trust） |

> 另有两套容易混淆的"三层"概念，不属于"加载"：① 三层**意图路由**（embedding→LLM→澄清）；
> ② 三层**权限体系**（Skill 权限层 / 工具规则层 / 运行时确认层）。本套件把它们单列测试。

---

## 1. 环境准备

- 后端已起在 `:8000`（用 `./restart.sh all` 或 `uvicorn maestro.main:app`）。
- **接口路径（实测）**：后端直接监听在根路径，**无 `/api/v1` 前缀**。
  - 聊天：`POST /chat/stream`（SSE）、`POST /chat`、`POST /chat/clarify`、`POST /chat/confirm`
  - 技能：`GET /skills`、`POST /skills/import`、`DELETE /skills/{name}`、`POST /skills/{name}/trust`
  - 事件：`POST /events`；待确认：`GET /pending`；审计：`GET /audit`
  - 若你通过前端代理 / 网关访问且文档要求 `/api/v1`，请自行在下面所有路径前补 `/api/v1`。
- `mode` 默认是 `plan`：在 `plan` 模式下写操作会被**挂起**（返回 pending，不执行）。
  要测"写操作真正落地"，请用 `mode:"auto"` 并在出现 pending 后用 `/chat/confirm` 确认。
- 已落地演示技能（开箱即用）：`quick-hello`（无工具，回复以 `[技能测试]` 开头）、
  `tool-inspector`（用 todo_write/glob/read_file/tool_search/write_file，验证权限门）。
- 需先导入的技能：见第 4 节 `capacity-report` / `weekly-report`（带附件）/ `hello-script`（带脚本）。

---

## 2. 测试者系统提示词（Meta Prompt）

把下面这段直接作为系统提示词交给一个具备 `curl`/Bash 能力的 LLM，它即可自动跑完本套件。

```text
你是一名「制造排产 Agent 平台」的端到端测试工程师。你的任务是通过聊天接口（HTTP SSE）
驱动整个系统，逐条验证其公开能力，并产出带证据的测试报告。不要臆造任何结果。

# 测试方法
1. 每条用例用 curl 调流式接口（同一用例的多轮用同一个 session_id 以复用历史）：
   curl -N -X POST http://localhost:8000/chat/stream \
     -H 'Content-Type: application/json' \
     -d '{"session_id":"<用例ID>","message":"<输入提示词>","route":"auto","mode":"auto"}'
   （直接打后端 :8000 时无 /api/v1 前缀；走网关需补前缀。）

2. 逐帧解析 SSE（"event: <类型>" 后为帧类型，"data: <JSON>" 为内容）：
   - route 帧：看 intent（planning/scheduling/query/skill/ambiguous）、
     route_method（embedding/llm/clarified/forced）、skill_id。
   - clarify 帧：needs_clarification 触发，含 options（id/label/route_to）；
     随后用 POST /chat/clarify {"session_id":..,"option_id":"1","route_to":"scheduling"} 回选。
   - context 帧：engine=skill 或 scheduling，含 steps（工具调用步骤）。
   - token 帧：逐字回复（delta）。
   - actions 帧：pending 待确认动作（写操作）。用 POST /chat/confirm 确认：
     curl -X POST http://localhost:8000/chat/confirm -H 'Content-Type: application/json' \
       -d '{"session_id":"<用例ID>","action_id":"<actions帧里的id>","approved":true}'
   - done / error 帧：收尾。

3. 对每条用例记录：输入、路由决策、关键帧、最终回复要点、断言是否通过。
4. 写操作（dispatch_work_order / send_expedite_message / write_file 等）在 mode=auto 下
   会产出 pending action，必须先用 /chat/confirm 确认后才真正执行；断言"已执行"前必须先确认。
5. 无 LLM / 无 Embedding 时系统走降级路径，如实记录降级行为，不视为失败。

# 断言原则
- 路由正确性：输入应命中预期引擎 / 技能。
- 护栏有效性：写操作必经 ActionGate，未确认不得落地。
- 技能隔离：技能不能调用白名单外工具（会被 blocked）。
- 如实告知：降级 / 缺数据时不臆造。
- 三层加载：L1 仅元数据可见、L2 触发才读正文、L3 执行中才读附件 / 脚本。

# 输出
每条用例输出：✅/❌ + 证据（关键 SSE 帧或回复摘录）+ 备注。最后给一份汇总表（用例 / 预期 / 结果 / 证据位置）。
```

---

## 3. 测试矩阵

> 每个用例给出：输入提示词、预期路由/引擎、断言点、验证方式。多轮用例用同一个 `session_id`。

### 3.1 多轮对话（Multi-turn）

| 用例 | 输入提示词 | 预期 | 断言点 |
|------|-----------|------|--------|
| **M1** 同引擎上下文继承 | 第1轮：`session_id=t-m1` → "2号线那批料齐了吗？"<br>第2轮：同 session → "那把齐套的下发到产线" | 两轮都进 scheduling | 第2轮无需再报产线/物料实体，靠 history 中的"2号线"与齐套结果推进；出现 dispatch 相关 pending |
| **M2** 跨引擎引用 | 第1轮：`t-m2` → "查一下 O001 订单的状态"（query）<br>第2轮：同 session → "把和 O001 相关的任务令下发"（scheduling） | 1→query，2→scheduling | 第2轮能从 history 取到 O001 关联任务令，不要求重复输入订单号 |
| **M3** 会话持久化 | 在 `t-m3` 发一条消息，记下回复；重启后端后用 `GET /sessions/t-m3/messages` 或再发一条，确认历史/标题仍在 | 重启后 history 与 current_engine 可回载 | 重启后新轮能看到前轮上下文（不丢记忆） |

### 3.2 三层意图路由（Routing）

| 用例 | 输入提示词 | 预期 | 断言点 |
|------|-----------|------|--------|
| **R1** 高置信 embedding 路由 | `session_id=t-r1` → "给我出一份今天的产能报告"（需先导入 capacity-report，见 §4） | intent=skill, route_method=embedding, skill_id=capacity-report | 第①层直接命中；若未配 EMBED_MODEL 则应降级到 LLM 层（route_method=llm） |
| **R2** LLM 分类路由 | `t-r2` → "把今天到期的订单重新优化排一下" | intent=planning, route_method=llm | 无种子句时靠 LLM 分类命中 planning |
| **R3** 低置信澄清 | `t-r3` → "帮我处理一下"（模糊） | needs_clarification=true，options 含 排产/调度/查询 三选项 | 收到 clarify 帧；随后 `POST /chat/clarify` 回选 "1" → 直接路由原请求（route_method=clarified） |
| **R4** 强制路由 | `t-r4` → "把 WO-101 下发到产线"，body 里 `route:"scheduling"` | 跳过路由，直达 scheduling | route 帧 route_method=forced（或等效），不进入 embedding/LLM |

### 3.3 三大引擎（Engines）

| 用例 | 输入提示词 | 预期引擎 | 断言点 |
|------|-----------|----------|--------|
| **P1** 排产触发 | `t-p1` → "帮这批订单做一份排产计划" | planning | 返回 plan / 校验结果；memory 写入 last_planning_result |
| **P2** 策略切换 | `t-p2` → "2号线停了，把受影响订单重排" | planning | 策略选择器走规则/LLM/澄清，产出重排方案 |
| **P3** 齐套检查（只读） | `t-s1` → "2号线那批料齐了吗" | scheduling | 调 check_kitting，无写动作、无 pending |
| **P4** 催料（写+确认） | `t-s2` → "给供应商催一下 A 物料" | scheduling | send_expedite_message.supplier → 产出 pending；确认后执行 |
| **P5** 下发（前置断言+确认） | `t-s3` → "把 WO-101 下发到产线"，mode=auto | scheduling | 前置断言 dispatch_ready 校验齐套；产 pending；确认后落地 |
| **P6** 异常报警 | `t-s4` → "2号线报警了，处理一下" | scheduling | classify_exception + analyze_exception_impact + notify_personnel |
| **S7** 无 LLM 降级 | 临时去掉 LLM_API_KEY 后 `t-s7` → "2号线那批料齐了吗" | scheduling | 降级为确定性齐套总览，不报错 |
| **Q1** 查订单 | `t-q1` → "查一下 O001 订单的状态" | query | 只读工具，回复附 sources |
| **Q2** 查库存 | `t-q2` → "看看现在库存还有多少" | query | 只读，数据来自知识库/集成 |
| **Q3** 列任务令 | `t-q3` → "列出今天所有的任务令" | query | 只读，返回任务令清单 |

### 3.4 工具使用（Tool usage，含 ActionGate）

| 用例 | 输入提示词 / 方式 | 预期 | 断言点 |
|------|------------------|------|--------|
| **T1** 只读工具自由调用 | 走 scheduling 问"2号线那批料齐了吗" | check_kitting 等直接执行 | 无 pending，直接给结果 |
| **T2** 写工具 + ActionGate | 走 scheduling 下发 WO（见 P5） | 产 pending，需 /chat/confirm | 未确认前不落地；确认后落地 |
| **T3** 并发只读 | 让 LLM 同时查 orders + inventory | 两只读工具并发执行 | 都返回且无相互阻塞 |
| **T4** 延迟工具需先 tool_search | 显式调 tool_search 检索 web_fetch/sleep | 检索后才激活，返回完整定义 | 未检索前延迟工具不可用 |
| **T5** 白名单外拦截 | 让技能/agent 调未授权工具（见 SK4） | blocked_by_permission | 返回 blocked，不执行 |

### 3.5 Skill 的使用（重点）

> 已落地技能：`quick-hello`（无工具）、`tool-inspector`（用 todo_write/glob/read_file/tool_search/write_file）。

| 用例 | 输入提示词 / 方式 | 预期 | 断言点 |
|------|------------------|------|--------|
| **SK1** 显式选择技能（forced） | `t-sk1` → body 带 `skill_id:"quick-hello"`，消息任意（如"你好"） | intent=skill, route_method=forced, skill_id=quick-hello | 回复以 `[技能测试]` 开头（证明是技能执行体在跑，而非普通对话） |
| **SK2** 自动路由命中技能 | `t-sk2` → "给我出一份今天的产能报告"（需导入 capacity-report） | intent=skill（embedding 或 llm），skill_id=capacity-report | 路由到第④类意图 skill |
| **SK3** 技能内工具调用 | 运行 tool-inspector（`skill_id:"tool-inspector"`） | 依次调 todo_write/glob/read_file/tool_search | context 帧 steps 体现工具调用；最终输出体检报告表 |
| **SK4** 技能白名单强制 | 给某技能声明 `allowed_tools:[query_orders]`，但提示它"用 write_file 写个文件" | write_file 被 blocked | AgentLoop 现有护栏拦截，观察内容如实呈现 |
| **SK5** 技能前置断言 | 技能 `allowed_tools` 含 dispatch_work_order 且 `tool_preconditions:{dispatch_work_order:[dispatch_ready]}`，让其下发未齐套 WO | 写被拦截，reason 回喂 | 拦截源于追加断言，与内置 ActionGate 叠加；无技能路径不受影响 |
| **SK6** 嵌套技能 | 技能 A 的 SKILL.md 里写"调用 invoke_skill 执行 B"，并构造 A→B→A 环 | 环检测 + 深度上限（默认 2）生效 | 深度超限 / 成环时被拦，共享预算 |
| **SK7** 受信脚本 | 导入 hello-script（含 scripts/hello.py），触发运行 | 未 trust 前 run_skill_script 被拒；trust + 确认后执行，输出 "hello world" | `POST /skills/hello-script/trust` 绑定 package_sha256；每次执行仍过 ActionGate |

### 3.6 Skill 的三层加载（渐进式披露，重点）

| 用例 | 方式 | 预期（三层行为） | 断言点 |
|------|------|------------------|--------|
| **L1** 元数据层 | 导入 capacity-report 后，发一条**不触发它**的消息：`t-l1` → "查一下 O001 订单的状态" | 路由到 query（intent=query），**不会**误判为 skill | 证明：未执行时只用到 frontmatter 的 description/when_to_use 做路由候选，SKILL.md 正文未被读取。另用 `GET /skills` 验证返回的是元信息（无正文泄露） |
| **L2** 正文层 | `t-l2` → "给我出一份今天的产能报告"（命中 capacity-report） | route 帧先出（intent=skill, skill_id=capacity-report，仅元数据）→ 随后 token 流严格遵循 SKILL.md 正文的步骤（先拉任务令/订单，再 check_kitting，再汇总） | 证明：正文是**触发执行时**才从磁盘读（`SkillStore.get_body`）；路由阶段无正文。回复结构 = 正文规定的产能/瓶颈分析 |
| **L3a** 附件层 | 导入 weekly-report（含 templates/summary.md），`t-l3a` → "出一份周报" | 执行中调 `read_skill_file` 读取 templates/summary.md，再按模板格式输出 | `file_count>0` 时 read_skill_file 自动加入 allowed_tools；二进制附件只返元数据；路径穿越被拒 |
| **L3b** 脚本层 | 导入 hello-script，`t-l3b` → "运行演示脚本" | 未 trust → 拒绝；trust + /chat/confirm → 执行 scripts/hello.py，回显 "hello world" | 脚本需显式信任当前 package_sha256；包内容/脚本变化使信任失效；每次执行过 ActionGate |
| **L1+** 版本失效 | 导入技能 → 触发一次（L2 命中）→ 删除并重新导入同名技能 → 再触发 | 第二次路由仍正确命中新正文 | `SkillStore.version` 自增，EmbeddingRouter 缓存按 version 失效，重嵌新 when_to_use |

### 3.7 事件驱动唤醒（Event-driven）

| 用例 | 方式 | 预期 | 断言点 |
|------|------|------|--------|
| **E1** 缺料预警唤醒 | `POST /events` 注入 `{"type":"material_shortage_warning","payload":{"work_order":"WO-101","material":"A"}}` | 唤醒 scheduling ReAct，翻译为查齐套/催料任务 | 产生 check_kitting / send_expedite_message 的 pending；审计时间线含事件来源 |
| **E2** 设备报警唤醒 | 注入 `{"type":"equipment_alarm","payload":{"line":"L2"}}` | 评估影响 + notify_personnel | 复用同一 ReAct 循环 + 护栏 |

### 3.8 权限与护栏（Authorization）

| 用例 | 方式 | 预期 | 断言点 |
|------|------|------|--------|
| **AU1** 生产写始终需确认 | 任意写操作（dispatch / expedite / write_file） | 无论 plan / auto，都产 pending 待确认 | 测试 `test_permissions.py::test_production_writes_always_ask` 不变式 |
| **AU2** 白名单外工具拦截 | 见 SK4 / T5 | blocked | 技能/agent 不能越权 |
| **AU3** 业务指纹去重 | 连续注入两条相同 material_shortage_warning（同 WO） | 第二次被去重，不重复灌确认队列 | `action_fingerprint` 去重 |
| **AU4** plan 模式挂起写 | mode=plan 下发 WO | 写被挂起返回 pending，不执行（即使 auto 也应确认） | 与 AU1 一致 |

---

## 4. 可直接落地的测试资源（curl + 示例技能）

### 4.1 导入 capacity-report（用于 SK2 / R1 / L2）

```bash
curl -X POST http://localhost:8000/skills/import \
  -F "file=@docs/demo-skills/capacity-report.md"
# 验证
curl http://localhost:8000/skills
```

### 4.2 构造并导入 weekly-report（带附件，用于 L3a）

先在工作区建目录与文件：

`weekly-report/SKILL.md`
```markdown
---
name: weekly-report
display_name: 周报生成
description: 按模板生成周度生产报告
when_to_use:
  - 出一份周报
  - 帮我生成本周生产周报
allowed_tools: [query_orders, query_work_orders, read_skill_file]
---
你是周报生成技能执行体。步骤：
1. 用 read_skill_file 读取 templates/summary.md 模板。
2. 用 query_work_orders / query_orders 拉取本周数据。
3. 严格按模板格式输出周报；不要臆造数据。
```

`weekly-report/templates/summary.md`
```markdown
# 生产周报（{周期}）
## 一、总体概览
- 任务令总数：
- 已完成：
- 在制：
## 二、瓶颈与风险
## 三、下周建议
```

```bash
cd /tmp && zip -r weekly-report.zip weekly-report/
curl -X POST http://localhost:8000/skills/import -F "file=@weekly-report.zip"
```

### 4.3 构造并导入 hello-script（带脚本，用于 SK7 / L3b）

`hello-script/SKILL.md`
```markdown
---
name: hello-script
display_name: 脚本演示
description: 演示技能受信脚本执行流程（run_skill_script）
when_to_use:
  - 运行演示脚本
allowed_tools: [run_skill_script]
---
你是脚本演示技能。调用 run_skill_script 执行包内 scripts/hello.py，参数为 ["world"]，并把输出原样返回。
```

`hello-script/scripts/hello.py`
```python
import sys
print("hello", sys.argv[1] if len(sys.argv) > 1 else "skill")
```

```bash
cd /tmp && zip -r hello-script.zip hello-script/
curl -X POST http://localhost:8000/skills/import -F "file=@hello-script.zip"

# 先查包 hash（GET /skills 里 hello-script 的 package_sha256，或直接用导入响应）
# 信任（acknowledged_script_execution=true 表示已知晓每次执行都过 ActionGate）
curl -X POST http://localhost:8000/skills/hello-script/trust \
  -H 'Content-Type: application/json' \
  -d '{"package_sha256":"<从GET /skills取得>","acknowledged_script_execution":true}'
```

> 注：受信脚本执行仍会生成 pending action，需再用 `/chat/confirm` 确认后才真正运行。

---

## 5. 一条完整 E2E 示例（含预期 SSE）

以 **L2 正文层加载** 为例，展示一次完整调用与如何读帧断言：

```bash
curl -N -X POST http://localhost:8000/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"demo-l2","message":"给我出一份今天的产能报告","route":"auto","mode":"auto"}'
```

预期 SSE 帧序列（节选）：

```
event: route
data: {"intent":"skill","route_method":"embedding","skill_id":"capacity-report"}   # ← L1 命中，仅元数据

event: context
data: {"engine":"skill","payload":{"steps":[...],"skill_ids":["capacity-report"],"skill_names":["产能日报"]}}

event: token
data: {"delta":"根据今日任务令与订单数据，先拉取…"}                                 # ← L2 正文已加载，按正文步骤推进

event: token
data: {"delta":"齐套检查结果显示…产能瓶颈在…"}

event: done
data: {"message_id":"msg-xxxxxxxxxxxx"}
```

**断言**：① route 帧早于任何 token，且只含 skill_id（无正文泄露）→ L1 正确；
② 回复内容严格遵循 capacity-report 正文的"拉任务令→查订单→check_kitting→汇总瓶颈"步骤 → L2 已加载；
③ 全程未出现 actions 帧（该技能只有只读工具）→ 护栏一致。

---

## 6. 验收清单（Checklist）

- [ ] **多轮**：M1/M2 历史继承；M3 重启后记忆存活
- [ ] **路由三层**：R1 embedding 命中；R2 LLM 分类；R3 澄清+回选；R4 forced
- [ ] **三引擎**：P1/P2 planning；P3–P6/S7 scheduling；Q1–Q3 query
- [ ] **工具**：T1 只读放行；T2 写+确认；T3 并发；T4 延迟工具；T5 拦截
- [ ] **Skill 使用**：SK1 forced；SK2 自动路由；SK3 工具调用；SK4 白名单；SK5 前置断言；SK6 嵌套；SK7 脚本
- [ ] **Skill 三层加载**：L1 仅元数据；L2 触发读正文；L3a 附件；L3b 脚本+trust；L1+ 版本失效
- [ ] **事件**：E1/E2 唤醒 ReAct + 产 pending
- [ ] **权限**：AU1 写必确认；AU2 拦截；AU3 去重；AU4 plan 挂起

---

## 7. 备注 / 已知边界

- 若未配置 `EMBED_MODEL`：R1 的 route_method 会退化为 `llm`，属预期降级，非失败。
- 若未配置 `LLM_API_KEY`：路由降级为澄清、参数抽取走正则、解释走模板；但求解/齐套/催料/下发/事件/审计仍可用（degraded mode 可验证架构）。
- 写操作在任何模式下都产 pending（`test_production_writes_always_ask` 不变式），断言"已执行"前务必 `/chat/confirm`。
- 技能不能调用白名单外工具、不能绕过内置断言、不能禁用 ActionGate（安全不变式）。
