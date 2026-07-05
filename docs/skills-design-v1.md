# Skill 技能模块设计 v1

> 状态:设计定稿,未实现。参考 Claude Code Skills 体系("Prompt 即能力"),结合本平台"一个平台 / 三个引擎 / 一个入口"架构裁剪。
> 关联文档:`api-contract-v2.md`(实现后追加端点小节)、`scheduling-platform-design-v3.md`。

## 1. 背景与目标

平台的三个引擎(Planning / Scheduling / Query)覆盖通用排产场景,但工厂侧存在大量**长尾、流程化、可用自然语言描述的任务**(产能日报、瓶颈分析、换线检查清单等),不值得为每个写死一个引擎或策略。

参考 Claude Code 的 Skills 设计,引入**技能(Skill)**:一个 Markdown 文件(或 zip 包)= YAML frontmatter(元数据)+ prompt 正文(能力本体)。非程序员可通过编写结构化 Markdown 为平台扩展能力,平台通过声明式配置与既有护栏(工具白名单、ActionGate、审计、循环守卫)保证可控。

**Skill 与 Command 统一**:两者是同一种模块,区别只在触发通道——`user_invocable` 控制能否被用户显式调用,`disable_model_invocation` 控制能否被意图路由自动匹配。数据模型统一,本期前台只实现选择器通道,斜杠命令(`/技能名` 补全)留后续。

核心设计原则(与全仓库一致):
- **渐进式披露**:路由层只见 `description`(LLM 分类候选)与 `when_to_use`(embedding 种子句);SKILL.md 正文只在技能被执行时从磁盘读取;zip 附属文件由 agent 通过 `read_skill_file` 工具按需读取。
- **复用不新造**:执行复用 `AgentLoop`(ReAct),持久化对齐 `SessionStore` 范式,上传对齐 `/knowledge` multipart 模式,路由扩展现有三层意图路由。
- **零新增依赖**:frontmatter 手写解析(`---` 分割 + `yaml.safe_load`),zip 用 stdlib `zipfile`;前端不引入弹窗库。
- **如实告知不臆造**:所有 degraded 路径明确定义(见 §6)。

## 2. SKILL.md 规范

### 2.1 文件格式

```markdown
---
name: capacity-report
display_name: 产能日报
description: 汇总当日订单/任务令/齐套数据，生成产能与瓶颈分析报告
when_to_use:
  - 给我出一份今天的产能报告
  - 分析一下最近的产线瓶颈
allowed_tools: [query_orders, query_work_orders, check_kitting]
user_invocable: true
disable_model_invocation: false
version: "1.0"
author: 周文涛
---
你是产能分析技能的执行体。步骤：
1. 用 query_work_orders 拉取今日任务令…
（正文即 system prompt）
```

### 2.2 frontmatter 字段(共 10 个)

| 字段 | 类型 | 必填 | 校验 | 说明 |
|---|---|---|---|---|
| `name` | str | ✅ | `^[a-z][a-z0-9-]{1,31}$`,全局唯一 | 即 skill_id,兼作落盘目录名与 URL 段,不另造 ID |
| `display_name` | str | ❌(默认=name) | ≤32 字符 | 中文显示名(name 必须 ASCII,制造业用户需要中文) |
| `description` | str | ✅ | 1~200 字符 | 路由层描述:注入 LLM 分类候选 + 前端列表简介 |
| `when_to_use` | list[str] | ❌(默认 []) | ≤10 条,每条 ≤100 字符 | embedding 路由种子例句(对齐 `routing_examples.yaml` 机制);缺省则只走 LLM 分类层 |
| `allowed_tools` | list[str] | ❌(默认=`QUERY_READONLY_TOOLS`) | 必须 ⊆ `ToolRegistry.names()`,导入时校验 | 默认只读安全;允许写工具——写操作仍被 precondition + ActionGate 双护栏兜底 |
| `user_invocable` | bool | ❌(默认 true) | — | false 则不出现在前端选择器;为斜杠命令预留 |
| `disable_model_invocation` | bool | ❌(默认 false) | — | true 则不进 embedding 向量 / LLM 候选,仅显式调用 |
| `tool_preconditions` | dict[str, list[str]] | ❌(默认 {}) | key ⊆ `allowed_tools`,value 中断言名 ⊆ 平台命名断言表 | 技能级前置断言:给指定工具**追加**平台内置命名断言(如 `dispatch_ready`);**只能收紧、不能放松**——工具自带断言与 ActionGate 无条件保留,三道防线叠加。技能包只声明名字,断言实现永远是平台代码(禁止上传代码执行) |
| `version` | str | ❌ | ≤16 字符 | 纯展示 |
| `author` | str | ❌ | ≤32 字符 | 纯展示 |

```yaml
# tool_preconditions 示例（写操作技能）
allowed_tools: [check_kitting, dispatch_work_order]
tool_preconditions:
  dispatch_work_order: [dispatch_ready]
```

**刻意不采纳的 Claude Code 字段**:`model`(平台单 LLM 配置)、`context`/`agent`(无子代理体系)、`hooks`/`mcp`(无此机制)、`license`/`metadata`(内网单机部署无意义)、`max_steps`(统一用 `Settings.react_max_steps`,不给技能包突破循环护栏的口子)。

### 2.3 技能包格式与校验规则

支持两种上传格式,后端统一落盘为目录:

- **单 `.md` 文件**:整个文件即 SKILL.md,无附属文件。
- **`.zip` 包**:根级(或唯一顶层目录内,自动归一化)必须有 `SKILL.md`;其余为附属文件(参考资料、模板等),由 agent 经 `read_skill_file` 工具按需读取。

导入校验(任一失败 → `SkillValidationError` → HTTP 422,错误消息说明具体原因):

1. zip 安全:拒绝含 `..` / 绝对路径 / 符号链接的条目;成员数 ≤50;解压后总大小 ≤10MB(防 zip bomb,与 `_MAX_UPLOAD_BYTES` 一致)。
2. frontmatter 必须以 `---` 开头且 `yaml.safe_load` 解析为 dict。
3. 必填字段齐全且各字段满足上表约束。
4. 正文非空(strip 后 ≥1 字符)且 ≤32KB(system prompt 注入上限)。
5. `allowed_tools` 中任一名字未在 `ToolRegistry` 注册 → 422,消息列出未知工具名。
6. `tool_preconditions` 中:key 不在 `allowed_tools` 内,或断言名不在平台命名断言表内 → 422,消息列出非法项。

其他 HTTP 错误语义:name 重复 → 409;上传超 10MB → 413;后缀非 `.zip`/`.md` → 415。

## 3. 后端架构

### 3.1 模块布局(新包 `skills/`,与三引擎平级)

```
src/scheduling_platform/skills/
├── __init__.py
├── schemas.py   # SkillValidationError；SkillFrontmatter(BaseModel + field_validator)；
│                # SkillMeta(SkillFrontmatter) 追加 file_count / bytes / added_at
├── parser.py    # parse_skill_md(text) -> (SkillFrontmatter, body)
│                # extract_package(data, filename) -> (fm, body, attachments: dict[str, bytes])
│                # validate_allowed_tools(fm, registered, default) -> list[str]
├── store.py     # SkillStore：落盘 + catalog + 路由数据供给（见 3.2）
└── engine.py    # SkillEngine：组装 AgentLoop 执行技能（见 3.3）
```

不放 `foundation/` 的理由:skills 依赖 foundation(LLM/tools/audit)并复用 `engines/scheduling/agent_loop.py`,foundation 不能反向依赖引擎。

**SkillStore 与 SkillRegistry 合并为一个类**:单进程、JSON 文件背书、量级小(几十个技能),拆两层只会引入同步问题;与 `SessionStore` / `KnowledgeIngestor` 的"单类 = catalog + 落盘"范式一致。

### 3.2 SkillStore(持久化,对齐 SessionStore 范式)

```
data/skills/index.json                 # list[SkillMeta]，按 added_at 倒序
data/skills/{name}/SKILL.md
data/skills/{name}/<附属文件相对路径>
```

```python
class SkillStore:
    def __init__(self, base_dir): ...          # mkdir + _load_index + threading.Lock
    version: int                                # save/delete 自增，供 EmbeddingRouter 缓存失效
    def list_all(self) -> list[SkillMeta]
    def get(self, name) -> SkillMeta | None
    def get_body(self, name) -> str             # 执行时才读盘 = 渐进式披露
    def save(self, meta, body, attachments)     # name 已存在抛 KeyError → 409
    def delete(self, name) -> bool              # rmtree 技能目录 + 更新索引
    def read_attachment(self, name, rel_path, max_bytes=65536) -> dict
                                                # resolve 后必须位于技能目录内（防穿越）
    # 路由数据供给
    def routable(self) -> list[SkillMeta]       # 过滤 disable_model_invocation
    def routing_examples(self) -> dict[str, list[str]]   # {"skill:{name}": when_to_use}
```

配置:`config.py` 新增 `skills_dir`(默认 `data/skills`,gitignored)。

### 3.3 SkillEngine(执行,复用 AgentLoop)

技能 = system prompt(前导语 + SKILL.md 正文)+ 工具白名单(`allowed_tools`)。每次调用新建 `AgentLoop`(构造零成本),天然继承:双重白名单强制(`to_openai_tools` 过滤 + `_handle_call` 复查)、precondition 断言、ActionGate 授权、卡死检测、审计。

```python
class SkillEngine:
    def __init__(self, llm, tools, pending, audit, store, settings,
                 named_preconditions: dict[str, Precondition]): ...

    async def handle(self, skill_id, message, session_id,
                     history=None, on_progress=None) -> EngineResponse:
        # meta 不存在 → 如实回复"技能不存在或已被删除"
        # llm 不可用 → 如实回复"LLM 未配置，技能暂不可用"
        # meta.file_count > 0 时白名单自动追加 "read_skill_file"
        # extra = {tool: [named_preconditions[n] for n in names]
        #          for tool, names in meta.tool_preconditions.items()}
        # AgentLoop(llm, tools, pending, audit,
        #           SKILL_PREAMBLE + store.get_body(skill_id),
        #           allowed, settings.react_max_steps,
        #           extra_preconditions=extra).run(message, history, on_progress)
```

不实现 `Engine` ABC(签名多一个 skill_id,硬套抽象反而别扭;Orchestrator 直接持有具体类型,与 QueryEngine 同待遇)。

`read_skill_file(skill_name, path)` 在 `bootstrap.py` 注册为 `kind="read"` 工具,handler 闭包调 `store.read_attachment`——附属文件由此进入渐进式披露链路。

**技能级前置断言(tool_preconditions)的落地**:
- **命名断言表**:bootstrap 构造 `named_preconditions: dict[str, Precondition]`(平台内置断言实名化,首批注册 `dispatch_ready` = `make_dispatch_precondition(...)`、`expedite_valid` = `make_expedite_precondition(...)`),挂到 `Platform` 字段,供导入端点校验与 SkillEngine 消费。不新建 Registry 类——量级小,普通 dict 足够(简单优先)。
- **AgentLoop 扩展**:`__init__` 加可选参数 `extra_preconditions: dict[str, list[Precondition]] | None = None`;`_handle_call` 在工具自带 precondition 检查**之后**依次执行该工具的追加断言,任一失败即拦截并把 reason 回喂 ReAct(与现有 blocked 路径同构)。缺省 None 时行为与现状完全一致,调度引擎零感知。
- **安全不变量**:追加断言只叠加、不替换——工具在 bootstrap 挂的内置断言、ActionGate 人工确认均不受技能影响;恶意技能包最多只能让自己更受限。

### 3.4 意图路由:第四类 "skill" 路由

`RouteDecision`(`orchestrator/schemas.py`)扩展:

```python
intent: Literal["planning", "scheduling", "query", "ambiguous", "skill"]
skill_id: str | None = None
```

三层路由各自的扩展:

| 层 | 改动 |
|---|---|
| ① embedding | `EmbeddingRouter` 持有 SkillStore 引用;`routing_examples()` 批量 embed 为 `"skill:{name}"` 类目向量,按 `store.version` 失效缓存(导入/删除后下次 classify 自动重嵌);技能分数与种子意图分数合并排序 |
| ② LLM 分类 | `CLASSIFY_SYSTEM` 常量不动;`_classify_system()` 动态拼接技能候选块(`- {name}: {description}`)。无技能时输出与现状逐字节一致。`llm.classify` 注入 `RouteDecision.model_json_schema()`,新枚举值与 `skill_id` 字段自动可填,classify 本身零改动。返回 intent="skill" 时校验 skill_id ∈ routable 名集,否则降 ambiguous(reason 注明"LLM 选择了不存在的技能") |
| ③ 澄清 | 不变(澄清选项维持三引擎,不加技能——技能靠前两层或显式调用) |

`Orchestrator` 扩展:
- `handle()` 加 `skill_id: str | None = None` 参数;最前面加 forced 分支(前端选定技能 → `RouteDecision(intent="skill", skill_id=…, route_method="forced", confidence=1.0)`,跳过路由)。
- `_gate_and_dispatch` 门控元组加 `"skill"`;`_dispatch` 加 skill 分支 → `skill_engine.handle(...)`。
- `_record_route` 结果加 `skill_id`(审计时间线可见)。
- **不调 `memory.set_engine`**:技能不拥有 Context Panel,会话粘性引擎保持不变。

### 3.5 HTTP 端点(`main.py`,照 /knowledge 模式)

| 端点 | 说明 |
|---|---|
| `GET /skills` | `{"skills": [SkillMeta…]}` |
| `POST /skills/import` | multipart UploadFile;流程:大小 → 后缀 → `extract_package` → `validate_allowed_tools` → `store.save`;错误 413/415/422/409 |
| `DELETE /skills/{name}` | 404 或 `{"deleted": true, "name": …}` |

- `ChatRequest` / `ChatStreamRequest` 加 `skill_id: str | None = None`,透传 `orchestrator.handle`。
- SSE `route` 帧(`_contract_route`)payload 加 `skill_id` 字段(非技能路由为 null);`intent: "skill"` 原样透出。
- **不做 PATCH 启停**:启停语义由文件内 `user_invocable` / `disable_model_invocation` 表达,运行时开关会引入"文件说 A、状态说 B"的双事实源。删除/重导入足够,有真实需求再加。

## 4. 前端架构

### 4.1 组件与文件

```
src/api/skills.ts                                        # listSkills / importSkill(apiUpload 带进度) / deleteSkill
src/components/ui/Modal.tsx                              # 最小居中弹窗原语（新建，仓库此前无 Modal）
src/features/orchestrator/skills/SkillMenu.tsx           # 技能 chip + Popover（搜索 + 列表 + 导入入口）
src/features/orchestrator/skills/SkillImportModal.tsx    # 导入弹窗（拖拽/点击上传）
```

### 4.2 交互设计

**技能 chip**(Composer 工具条,插在 mode chip 后、`flex-1` spacer 前,与 route/mode chip 平齐):
- 复用现有 chip 类名工厂;图标 `Sparkles`;文案 = 选中技能的 display_name 或「技能」。
- `OpenMenu` 联合类型加 `'skill'`;放在 toolbarRef 容器内,现有 outside-click / Escape 逻辑零改动。

**SkillMenu Popover**(`absolute bottom-full` 上弹,`w-[260px]`):
- 顶部搜索框(样式对齐 Composer textarea:`bg-transparent text-body-sm placeholder:text-text-tertiary`),本地 state 按 name / display_name / description 过滤。
- 列表行照 ROUTE_OPTS 两行结构:显示名(`text-body-sm font-semibold`)+ description 截断(`text-[11px] text-text-tertiary`),选中显示 Check。
- 首行「不使用技能」清除项;底部分隔线 + 「导入技能…」入口;空态「暂无技能,点击下方导入」。
- 只展示 `user_invocable !== false` 的技能。

**SkillImportModal**(用户明确要求弹框,新建 Modal 原语而非 Popover 内切视图):
- Modal:`fixed inset-0 z-[60]` + `bg-black/50` scrim + 面板(`rounded-xl border-border-default bg-surface-raised shadow-popover`);Escape / 背景点击 / 标题栏 X 关闭。
- 拖拽区照 `features/query/knowledge/UploadZone.tsx` 模式(dragging state + onDragOver/Leave/Drop + 隐藏 `<input accept=".zip,.md">`),文案「拖拽 .zip / .md 技能包到此,或点击选择」。
- 客户端预检后缀;`useImportSkill` mutation + `UploadProgress` 进度条。
- 失败(413/415/422/409)统一展示 **「技能包不符合规范:{后端 detail}」**(复用 `knowledge/shared.ts` 的 `errMessage` / `extOf`)。
- 成功:invalidate 列表、关闭弹窗、自动选中新技能。

### 4.3 状态与透传

- 选中技能放 `Workspace.tsx` local state(对齐 route/mode):`useState<SkillMeta | null>`。
- **互斥规则**:选中技能 → `setRoute('auto')`;选定非 auto 引擎 → `setSkill(null)`(避免"既指定引擎又指定技能"歧义)。
- 透传链:Workspace `onSend` → `useOrchestrator.send(text, engine, skillId)` → `useStreamingChat.send` → 请求体 `skill_id`(`ChatStreamRequest` 类型透传,`api/chat.ts` 无需改)。

### 4.4 数据层与视觉

- 三层范式照 knowledge:`api/skills.ts` → `queryKeys.skills.list()` → `hooks.ts`(`useSkills` / `useImportSkill` / `useDeleteSkill`)→ `api/index.ts` re-export;MSW `fixtures.ts` + `handlers.ts` 照 knowledge 上传 handler 模板。
- `types/api.ts`:`SkillMeta` / `SkillListResponse`;`IntentType`、`RouteEngine` 加 `'skill'`;`RouteDecision` / `ChatStreamRequest` 加 `skill_id?`。
- `ROUTE_META` 加 `skill` 条目,**全部复用 accent token 家族**(`bg-accent` / `text-accent` / `bg-accent-bg` / `border-accent-border` / `shadow-glow-accent`),零新增 token,类名写全串。理由:accent 是"AI/live"语义,技能是平台的 AI 扩展能力;沿用 uncertain(琥珀警示色)会传达错误情绪。消息流 route badge 自动生效,v1 只显示「技能」徽章。

## 5. 契约扩展

`docs/api-contract-v2.md` 直接追加(活契约,本次全为增量、无破坏性修改,不开 v3):

1. 端点总览表加 `GET /skills` / `POST /skills/import` / `DELETE /skills/{name}` 三行。
2. §1:`/chat` 与 `/chat/stream` 请求体新增可选 `skill_id`;`route` 帧 `intent` 枚举加 `"skill"`、payload 加 `skill_id`。
3. 新小节「技能模块 (Skills)」:SkillMeta 形状、multipart 约定、413/415/422/409 错误语义,frontmatter 规范链接本文档。

## 6. Degraded 模式(如实告知不臆造)

| 场景 | 行为 |
|---|---|
| LLM 未配置,显式调用技能 | 回复「LLM 未配置,技能暂不可用」 |
| LLM 未配置,自动路由 | 降级路径不变(ambiguous → 澄清),技能仅剩显式通道 |
| embedding 未配置 | 技能 `when_to_use` 不参与第①层,LLM 分类层候选仍生效 |
| LLM 分类返回不存在的 skill_id | 降为 ambiguous(confidence=0,reason 注明),触发澄清 |
| 技能被删后再调用 | 回复「技能 X 不存在或已被删除」 |
| 技能 prompt 请求白名单外工具 | AgentLoop 现有护栏拦截(blocked),观察内容如实呈现 |
| 技能级前置断言不满足 | 与工具自带断言同构:拦截写操作,reason 回喂 ReAct,由其换思路或如实说明 |

## 7. 实施阶段(每阶段可验证)

| 阶段 | 内容 | 检查点 |
|---|---|---|
| 1 解析与存储 | `skills/schemas+parser+store` + `tests/test_skills.py`(frontmatter 非法态、zip 穿越/缺 SKILL.md/顶层目录归一化、未知工具名/断言名、tool_preconditions key 越界 allowed_tools、落盘重启重载) | `pytest tests/test_skills.py` |
| 2 HTTP + bootstrap | `config.skills_dir`、bootstrap 装配(store/engine/`read_skill_file`/`named_preconditions`)、Platform 字段、三端点 | `pytest`;`curl -F "file=@demo.md" :8000/skills/import` |
| 3 执行 + 路由 | SkillEngine、AgentLoop `extra_preconditions` 参数、RouteDecision 枚举、EmbeddingRouter 动态向量、`_classify_system` 候选拼接、Orchestrator forced/dispatch 分支、`_contract_route`。测试照 test_router.py FakeLLM 范式(forced / LLM 命中 / 选不存在技能降级 / embedding 层 / degraded / 白名单强制 / 技能断言拦截写工具且不影响无技能路径) | `pytest`;curl `/chat/stream` 观察 route 帧 `intent:"skill"` |
| 4 前端 | 类型 → api → hooks → MSW → Modal → SkillMenu → SkillImportModal → Composer/Workspace 接线 → ROUTE_META → 透传链 + 组件/hook 测试 | `npm test && npm run lint && npm run build`;MSW 模式手动走查 |
| 5 契约与联调 | api-contract-v2 追加;`./restart.sh` 端到端:导入 → 选中 → 发送 → route 帧 skill → ReAct 执行 → 审计时间线含 skill_id | 手动验收 |

## 8. 遗留到后续版本

- 斜杠命令:输入框 `/` 前缀补全菜单(数据模型已就绪,`user_invocable` 字段本期即消费)。
- 技能市场 / 推荐(参考 WorkBuddy):内置技能目录、按任务描述找技能、AI 生成技能。
- 技能启停开关(若"删除/重导入"被证明不够用)。
- `context: fork` 式隔离执行(需先有子代理体系)。
