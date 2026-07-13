# Claude Code 完整功能测试提示词

下面的内容可以原样交给 Claude Code。测试范围以当前工作区中的真实实现为准；Skill 测试只使用当前环境已经导入的 Skill，不从 `docs/` 或扩展目录导入测试 Skill。

```text
你现在是一名资深 QA 工程师和全栈测试工程师。请对当前仓库执行一次完整、可复现、有证据的功能测试。

仓库路径：
/Users/zhouwentao/Desktop/manufacturing-agent

目标：
1. 基于当前工作区中的真实实现测试，不以设计文档里的规划功能代替代码事实。
2. 覆盖后端、前端、API、SSE、持久化、安全权限和主要端到端业务流程。
3. 输出测试报告和缺陷报告，但不要修复业务代码。
4. 所有结论必须有命令输出、HTTP 响应、浏览器截图、日志或源码位置作为证据。

## 一、不可违反的约束

- 当前工作区存在未提交改动，它们属于用户。
- 禁止执行 git reset、git checkout、git clean、stash，禁止覆盖用户修改。
- 不要格式化、重构或修复源码。
- 除测试报告、截图、请求响应记录等测试产物外，不修改仓库文件。
- 不读取、打印或在报告中暴露 API Key、Bearer Token、MCP secret env。
- 测试不得写入用户真实的 `~/.maestro` 或用户配置的数据目录。
- 后端测试进程必须使用独立的 `MAESTRO_DATA_DIR`，例如 `/tmp/maestro-functional-test-<timestamp>`。
- 使用测试专用 `PRIVILEGED_API_TOKEN`，报告中不得记录完整 token。
- 不要杀死不属于本次测试的进程。
- 外部网络、真实 LLM、Embedding 或 MCP 不可用时，标记 `BLOCKED`，然后继续测试离线降级与安全路径。
- 对 LLM 输出只校验事实、路由、动作状态、引用和安全约束，不要求逐字匹配。
- 不允许为了让测试通过而修改产品代码。
- Skill 测试只能使用测试开始前已经导入的 Skill。
- 严禁从 `docs/`、`docs/demo-skills/`、扩展目录、网络目录或临时生成文件导入 Skill。
- 严禁调用扩展中心安装新的 Skill 来满足测试前置条件。
- 真实 SkillStore 只能读取；任何信任、撤销、删除、执行产物等测试必须作用于临时副本。

## 二、开始前阅读和盘点

先完整阅读：
- `AGENTS.md`
- `maestro/README.md`
- `docs/api-contract/api-contract-v2.md`
- `maestro/src/maestro/api/app.py`
- `maestro/src/maestro/bootstrap.py`
- `maestro/src/maestro/foundation/integration/mock_adapter.py`
- `maestro/src/maestro/skills/`
- `frontend/src/router/index.tsx`
- `frontend/src/pages/Workspace.tsx`
- `frontend/src/api/`
- `maestro/tests/`
- `frontend/src` 中已有的 `*.test.ts` 和 `*.test.tsx`

执行盘点：
1. `git status --short`。
2. 列出实际注册的 FastAPI 路由。
3. 列出现有后端和前端测试。
4. 对照代码和 API 契约，建立“已实现 / 条件实现 / 未实现”清单。
5. 不测试 `TODO(v0.2)` 中明确延期且代码尚未实现的功能。
6. 契约、README 和代码不一致时，以当前代码行为为准，并记录文档偏差。

## 三、已导入 Skill 的安全快照

这一步必须在设置隔离 `MAESTRO_DATA_DIR` 之前完成。

1. 只读定位真实运行时数据根：
   - 如果已有本项目后端在运行，通过 `GET /skills` 记录当前已导入 Skill 的元数据；
   - 同时检查当前 shell 的 `MAESTRO_DATA_DIR`；
   - 未设置时，默认候选目录为 `~/.maestro/skills`；
   - 如果项目配置指向其他数据根，读取配置解析逻辑确认真实目录；
   - 不输出 Skill 文件中的密钥、个人数据或外部服务凭证。

2. 保存“测试开始前 Skill 清单”，至少记录：
   - name
   - display_name
   - version
   - package_sha256
   - compatibility_status
   - allowed_tools
   - 是否包含脚本或附件（如果元数据可判断）
   - trust 状态

3. 创建隔离目录：
   `TEST_DATA_DIR=/tmp/maestro-functional-test-<timestamp>`

4. 把真实 SkillStore 完整复制到：
   `$TEST_DATA_DIR/skills`

5. 复制后校验：
   - 临时副本的 Skill 数量和 name 集合必须与测试开始前清单一致；
   - 不得修改真实 SkillStore；
   - 后续后端必须从 `$TEST_DATA_DIR` 启动；
   - 如果无法安全定位或复制真实 SkillStore，Skill 用例标记 `BLOCKED`，禁止改用 docs 下的示例 Skill。

## 四、自动化回归基线

后端：
```bash
cd /Users/zhouwentao/Desktop/manufacturing-agent/maestro
./.venv/bin/pytest -q
```

前端：
```bash
cd /Users/zhouwentao/Desktop/manufacturing-agent/frontend
npm test -- --reporter=dot
npm run lint
npm run build
npm run test:electron
```

记录每个命令的退出码、通过/失败数量、耗时、warning，以及失败测试的完整名称和关键堆栈。不要因为已有测试通过就跳过端到端测试。

## 五、启动隔离测试环境

优先使用 8000 和 5173。如果端口已占用：
- 判断占用者是否为本仓库已有服务；
- 不要直接杀死未知进程；
- 无法安全启动时，将相关测试标记 `BLOCKED` 并说明原因。

后端至少设置：
```bash
cd /Users/zhouwentao/Desktop/manufacturing-agent/maestro
MAESTRO_DATA_DIR="$TEST_DATA_DIR" \
PRIVILEGED_API_TOKEN="<测试专用随机值>" \
.venv/bin/uvicorn maestro.main:app --host 127.0.0.1 --port 8000
```

前端：
```bash
cd /Users/zhouwentao/Desktop/manufacturing-agent/frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

等待 `GET http://127.0.0.1:8000/health` 成功后再测试。保存前后端日志。结束后只清理本次测试启动的进程和临时数据。

启动隔离后端后再次调用 `GET /skills`，确认它读取的是临时副本，并与开始前 Skill 清单一致。若为空或不一致，先排查快照路径，不得导入 docs Skill 补齐。

## 六、功能测试矩阵

### A. 启动与基础 UI

FT-01 服务和首页：
- `/health` 返回 `status=ok`。
- 首页显示 Maestro、会话栏、输入框、路由选择、模式选择。
- 检查 console、pageerror 和失败网络请求。
- 检查 `/settings/skills`、`/settings/connectors`、`/tasks` 可访问。

### B. 会话

FT-02：新建、重命名、切换、删除会话。
- 左侧列表同步更新。
- 切换会话不串消息。
- 删除不存在的会话返回 404。

FT-03：发送两轮消息后重启后端。
- 历史消息、标题和消息数仍存在。
- 首条消息的自动标题不得阻塞主回答。

### C. 排产

排产核心用例强制选择“排产”引擎，避免无 LLM 时自动路由澄清影响测试。

FT-04：
“把注塑线的订单 O001、O002、O003 排一下，尽量别拖期”

检查：
- route intent 为 planning；
- 订单号提取正确；
- 使用 `JobShopMakespan`；
- 只使用兼容产线；
- 任务有合法开始、结束和分配信息；
- 无重叠、负时长和订单丢失。

FT-05：
“给 SMT贴片订单 O004 排产，按交期优先”

检查使用 `SimpleDispatch`，且 O004 只能进入 L3。

FT-06：
“只允许 L4 生产订单 O001”

必须返回不可行或兼容性失败，不得把 O001 排到 L4。

### D. 调度、齐套与 ActionGate

强制选择“调度”引擎。

Mock 数据事实：
- WO-101 对应 O001，缺 M-002。
- WO-102 对应 O002，缺 M-003。
- WO-103 对应 O004，缺 M-005。
- WO-104 对应 O005，物料齐套。
- WO-123 对应 O003，缺 M-002。
- M-002 为采购在途。
- M-003 卡在质量检验。
- M-005 为采购在途。

FT-07：发送“检查 WO-101、WO-104 的齐套情况”。结果必须与上述事实一致。

FT-08：发送“检查 WO-102 为什么缺料”。必须识别 M-003 和质量检验环节。

FT-09：发送“下发 WO-101”。必须被未齐套前置断言阻止，不得产生成功写操作。

FT-10：发送“检查并下发已经齐套的 WO-104”。
- LLM 可用时，应先查询事实，再产生 pending action；
- 确认前不得执行；
- 确认后状态为 executed；
- 重复确认不得重复执行。
- LLM 不可用时，验证降级齐套总览，并结合自动化测试验证 ActionGate；真实 Agent 生成动作部分标记 `BLOCKED`。

FT-11：产生一个待确认动作并拒绝。
- 状态变为 rejected；
- adapter 写操作不得执行；
- audit 中有拒绝记录。

权限特别检查：
- 文件写入可在 auto 模式自动执行；
- MES/ERP/WMS 生产写操作即使在 auto 模式也必须确认；
- 如果 UI 文案与实际策略不一致，记录为文案/行为偏差。

### E. SSE 与交互

检查 `POST /chat/stream`：
- progress 可出现多次；
- route 结构正确；
- token 可拼接为完整回答；
- scheduling/skill 运行有 context；
- 有待确认动作时出现 actions；
- 最终有 done；失败时有 error；
- SSE frame 使用真实空行分隔。

测试停止生成：
- 点击停止后请求中止；
- 停止按钮恢复为发送按钮；
- 不产生重复 assistant 消息；
- 后续仍可发送。

自动模式输入“3号线那批单有问题，处理下”：
- 低置信时显示澄清卡；
- 选择后恢复原始请求并通过 `/chat/clarify` 续流；
- 如果真实模型高置信直接路由，记录实际行为，不按文案逐字判断。

### F. 查询和知识库

无 LLM/Embedding 时，强制查询引擎发送：
“当前有哪些订单和待下发任务令？”

应返回确定性的基础数据摘要，明确说明降级，不得伪造来源。

知识库 CRUD：
- 上传包含唯一事实 `TEST-FACT-7319` 的 UTF-8 Markdown；
- 列表、改名、替换、删除正确；
- 删除不存在文档返回 404；
- 不支持格式返回 415；
- 超过 10MB 返回 413。

若 Embedding 和 LLM 可用：
- 询问 `TEST-FACT-7319`；
- 回答必须使用文档事实并带真实 source；
- 删除后不得继续引用已删除文档。

### G. 附件

通过 UI 添加 txt/csv/json/md 附件并发送。
- `/chat/stream` 请求中的 message、attachments、skill_ids 可同时存在；
- 小于 1MB 可添加；
- 超过 1MB 显示错误且不发送；
- 每轮最多 10 个；
- 重复文件名处理一致；
- 发送后附件清空；
- 文件名换行符不得破坏提示词边界。

### H. 已导入 Skill

本节只能使用隔离副本中、测试开始前已经存在的 Skill。禁止导入任何新 Skill。

H1. 清单与扩展中心展示：
- `GET /skills` 的 name 集合与测试开始前清单一致；
- `/settings/skills` 的“已安装”列表正确显示这些 Skill；
- Composer 的 Skill 菜单能搜索和选择它们；
- 不应凭空出现未安装 Skill。

H2. 动态选择测试对象：
- 从现有 Skill 中优先选择一个 `user_invocable=true` 且不依赖不可用外部服务的 Skill，记为 `SKILL_BASIC`；
- 如果存在带附件的 Skill，再选择一个记为 `SKILL_ATTACHMENT`；
- 如果存在包含脚本、写工具或高风险工具的 Skill，再选择一个记为 `SKILL_GUARDED`；
- 选择依据必须来自 `/skills` 元数据和临时副本中的包内容；
- 不要硬编码某个 Skill 必然存在；
- 没有满足条件的 Skill 时，对应子用例标记 `BLOCKED`，不得创建或导入替代 Skill。

H3. 基础调用：
- 在 Composer 选择 `SKILL_BASIC`；
- 发送与它的 description/when_to_use 匹配的请求；
- 请求必须携带实际 Skill name 组成的 `skill_ids`；
- 已选 Skill 必须拥有本轮路由，不能被默认引擎污染；
- SSE context 的 engine 为 `skill`；
- context 中的 `skill_ids`、`skill_names` 与选择一致；
- 回复符合 Skill 目标且不超出 allowed_tools；
- 发送后 UI 清空本轮 Skill 选择。

H4. 多 Skill：
- 如果至少有两个互补且可安全调用的已安装 Skill，选择两个同时发送请求；
- 检查 skill_ids 顺序、上下文合并、文件命名空间和最终 context；
- 不得调用未选 Skill；
- 如果没有合适组合，标记 `BLOCKED`。

H5. 附件与 Skill：
- 如果存在 `SKILL_ATTACHMENT`，验证它只能读取自身允许的附件；
- 路径穿越和跨 Skill 读取必须被阻止；
- 二进制或截断结果应明确标记；
- 同一请求同时携带 Skill 和用户附件时，两者都不应丢失。

H6. 信任与脚本安全：
- 如果存在 `SKILL_GUARDED`，所有测试只作用于临时 SkillStore；
- 先记录当前 trust 和 package_sha256；
- 未信任脚本不得执行；
- 信任请求必须 `acknowledged_script_execution=true`；
- 信任必须绑定当前 package_sha256；
- 错误 hash 返回冲突；
- 通过修改临时副本或使用受控 API 更新方式模拟包 hash 变化时，旧信任必须失效；
- 撤销信任后不能继续执行；
- Skill 已信任也不能绕过具体写操作的 ActionGate；
- 禁止对真实 SkillStore 执行信任、撤销或删除。

H7. allowed_tools 与权限：
- 实际工具调用不得超出该 Skill 的 allowed_tools；
- 未知工具应明确失败；
- 写工具在 plan 模式产生 pending，不得直接执行；
- auto 模式也不能绕过生产系统写操作确认；
- 工具白名单、前置条件、ActionGate 和 audit 都必须有证据。

H8. 删除测试：
- 只有确认后端连接的是 `$TEST_DATA_DIR/skills` 时，才允许删除临时副本中的一个非关键 Skill；
- 删除后 `/skills`、扩展中心和 Composer 菜单同步更新；
- 不存在 Skill 删除返回 404；
- 删除不得影响真实 SkillStore；
- 测试结束前再次只读检查真实 SkillStore 的 name 集合和文件 hash，必须与测试开始前一致。

明确不执行以下旧方案：
- 不使用 `docs/demo-skills/quick-hello.md`；
- 不使用 `docs/demo-skills/capacity-report.md`；
- 不调用 `/skills/import` 导入 docs 文件；
- 不从 SkillHub 安装 Skill 作为测试样本。

### I. 模型配置

只在隔离数据目录测试：
- GET `/models`；
- PUT 一个测试 provider；
- POST `/admin/reload-model`；
- `/health` 中 llm_available 与实际配置一致；
- 热更新不要求进程重启；
- 不记录真实 API Key。

### J. 管理权限

对以下写接口测试无 token、错误 token、正确 token：
- Skill trust/revoke/delete（仅临时副本）；
- `/mcp/servers`；
- `/extension-catalog/sync`；
- 扩展连接器添加。

无 token或错误 token 必须返回 401，且不得改变持久化状态。

由于禁止导入新 Skill，`/skills/import` 只通过已有自动化测试和源码契约确认，不在端到端阶段上传任何 Skill 包。

### K. MCP

测试：
- GET `/mcp/servers`；
- 添加隔离配置；
- secret env 响应脱敏；
- 重名返回 409；
- 过期 expected_revision 返回 409；
- 不存在连接器返回 404；
- 非 stdio transport 返回 422；
- 不存在 command 的 test 返回结构化失败，后端不崩溃；
- connect/disconnect 后 revision 和状态正确；
- 删除后工具注册表刷新。

没有可用真实 MCP Server 时，成功连接场景标记 `BLOCKED`，但配置 CRUD、错误处理、权限和脱敏仍必须完成。

### L. 扩展中心

测试 `/settings/skills` 和 `/settings/connectors`：
- 已安装 Skill 展示、搜索、详情、信任状态；
- 连接器搜索、添加、更新预览和 revision 冲突；
- 同步状态和外部网络错误提示。

注意：本轮禁止从推荐或 SkillHub 安装 Skill。可以浏览和验证目录只读展示，但不能点击安装。连接器测试仍可在隔离数据目录执行。

### M. 事件和审计

POST `/events`：
```json
{
  "type": "material_shortage_warning",
  "payload": {
    "wo_id": "WO-123",
    "source": "functional-test"
  }
}
```

检查：
- 返回 queued=true 和 event_id；
- 等待事件消费，单次等待不超过 10 秒；
- audit 出现 `engine_wakeup:material_shortage_warning`；
- LLM 可用时检查齐套、归因和待确认动作；
- LLM 不可用时检查确定性降级，不得伪造已催料。

再注入设备报警：
```json
{
  "type": "equipment_alarm",
  "payload": {
    "line_id": "L2",
    "description": "功能测试：锁模压力异常",
    "affected_wo_ids": ["WO-102"]
  }
}
```

检查报警进入调度路径，任何通知或状态写入仍需授权。

检查 `/audit/timeline`：
- route 显示为 route；
- 工具调用显示为 tool_call；
- 支持 session_id 过滤；
- authz、params、result 可追踪；
- 不泄露 secret。

### N. Observation

优先通过已有自动化测试和可构造的 Agent/API 场景验证：
- 大观察返回 observation_ref、总数、字段、预览；
- GET `/observations/{ref}` 支持 offset、limit、keys；
- 不存在或被淘汰的 ref 返回 404；
- 小结果保持 inline；
- UI 点击后才懒加载详情。

## 七、接口契约检查

对实际注册路由至少覆盖：
- 正常请求；
- 缺失必填字段；
- 错误字段类型；
- 不存在资源；
- 权限失败（适用时）。

重点检查：
- `/chat`
- `/chat/stream`
- `/chat/clarify`
- `/chat/confirm`
- `/scheduling/execute`
- `/sessions` 和 messages
- `/knowledge`
- `/skills`，但不得导入新 Skill
- `/models`
- `/mcp/servers`
- `/extension-catalog`
- `/events`
- `/audit`
- `/audit/timeline`
- `/pending`
- `/observations/{ref}`
- `/health`

记录代码与 `docs/api-contract/api-contract-v2.md` 的偏差，不修改契约。

## 八、证据与报告

浏览器测试优先使用 Playwright。每个关键流程至少保留：
- 开始状态截图；
- 关键中间状态截图；
- 最终状态截图；
- browser console error 和 pageerror；
- 失败请求与响应；
- 对应后端日志。

创建：
`test-results/functional-test-<timestamp>/`

只在该目录写测试产物：
- `report.md`
- `defects.md`
- `summary.json`
- `screenshots/`
- `api-evidence/`
- `logs/`

`report.md` 必须包含：
1. 测试时间、commit、工作区是否 dirty。
2. macOS、Python、Node、npm、浏览器版本。
3. 测试环境与隔离数据目录。
4. 自动化测试结果。
5. 功能测试矩阵。
6. 每个用例状态：`PASS / FAIL / BLOCKED / NOT_RUN`。
7. 每个用例的实际结果、证据路径和耗时。
8. 未测试项及原因。
9. 文档与实现偏差。
10. 测试前已导入 Skill 清单、实际选用 Skill 及选择原因。
11. 真实 SkillStore 测试前后完整性校验结果。
12. 总体发布建议：`Go / Go with known issues / No-Go`。

`defects.md` 中每个缺陷必须包含：
- 缺陷 ID、标题、严重级别；
- 环境和前置条件；
- 最小复现步骤；
- 预期和实际结果；
- 截图、请求响应和日志；
- 是否稳定复现；
- 影响范围；
- 初步怀疑的源码文件和行号；
- 不直接修复。

`summary.json` 至少包含：
```json
{
  "automated": {
    "backend_passed": 0,
    "backend_failed": 0,
    "frontend_passed": 0,
    "frontend_failed": 0,
    "lint": "PASS|FAIL",
    "build": "PASS|FAIL",
    "electron": "PASS|FAIL|BLOCKED"
  },
  "functional": {
    "passed": 0,
    "failed": 0,
    "blocked": 0,
    "not_run": 0
  },
  "defects": {
    "blocker": 0,
    "critical": 0,
    "major": 0,
    "minor": 0
  },
  "skills": {
    "preexisting_count": 0,
    "tested_names": [],
    "real_store_unchanged": true
  },
  "recommendation": "Go|Go with known issues|No-Go"
}
```

## 九、完成标准

- 不仅运行已有单元测试。
- 所有 P0 场景都有明确状态和证据。
- Skill 测试只使用测试前已经导入的 Skill。
- 未从 docs、网络、扩展目录或临时文件导入任何 Skill。
- 真实 SkillStore 测试前后完全一致。
- 所有 FAIL 都有最小复现步骤。
- 所有 BLOCKED 都有阻塞证据。
- 没有修改业务源码。
- 没有泄露密钥。
- 测试进程已清理。

最终向我输出：
1. 一句话总体结论；
2. 通过、失败、阻塞和未运行数量；
3. 最严重的 5 个问题；
4. 实际测试过的已导入 Skill 名称；
5. `report.md`、`defects.md`、`summary.json` 的绝对路径；
6. `git diff --stat`，证明除 `test-results` 外没有产生源码修改；
7. 真实 SkillStore 测试前后未变化的校验结论。
```
