# Skill 技能模块设计 v2 — 代码现实对齐与实现定稿

> 状态:在 v1 基础上,经后端 12 项 + 前端 10 项代码核查后的实现定稿。
> **v1(`docs/skills/skills-design-v1.md`)为规范源**;v2 仅记录与代码现实的偏差对齐、三个实现分叉的决策、以及前置断言能力的落地确认。除下述 delta 外,v1 全文有效;v2 与 v1 冲突处以 v2 为准。
> 关联:v1、`../api-contract/api-contract-v2.md`、`../platform/scheduling-platform-design-v3.md`。
>
> 核查结论:**无架构阻塞**。`AgentLoop` 构造签名逐字一致、`RouteDecision`/`Orchestrator`/`bootstrap`/`main.py` 注入点齐全、前端 Composer/`ROUTE_META`/Workspace/数据层管线与 v1 描述一致。drift 全是局部措辞/token/命名,不影响结构。

## 1. 三个实现分叉的决策

| 分叉 | 选项 | 决策 |
|---|---|---|
| **A. EmbeddingRouter 缓存失效** | A1 `store.version` 拉式失效 / A2 推式回调 / A3 每次 classify 重嵌 | **A1**:`SkillStore.version: int`(save/delete 自增)+ `EmbeddingRouter` 记 `last_version`,`classify()` 入口比对、变了就 `_vectors=None` 重嵌。解耦干净,无双向依赖 |
| **B. LLM 分类 system prompt 装配** | B1 `_classify_system(skills)` 构造函数 / B2 调用处临时拼接 | **B1**:把 `router.py:24-43` 的 `CLASSIFY_SYSTEM` 常量改成 `_classify_system(skill_candidates: list[str]) -> str` 构造函数;无技能时输出与现状逐字节一致;skill_id 合法性校验加在 `IntentRouter.route()` 的 classify 返回之后(`router.py:121` 之后) |
| **C. SkillEngine 的 AgentLoop 生命周期** | C1 per-call 新建 / C2 单例可重配 | **C1**:per-call 新建 AgentLoop。每个技能 `system_prompt`+`allowed_tools` 不同,per-call 构造零成本且天然隔离;`SchedulingEngine` 复用单例是因其单 prompt 单白名单,场景不同 |

**确认(非分叉)**:SkillEngine 镜像 **`SchedulingEngine`**(走 `AgentLoop` 的 ReAct+precondition+ActionGate+循环守卫),**不是** `QueryEngine`(后者走 `llm.complete()` 内部工具循环、无写护栏)。v1 §3.3 选 AgentLoop 正确——技能可能含写工具,必须有护栏。

## 2. 与代码现实的偏差对齐(supersede v1)

| # | v1 措辞 | 代码现实 | v2 处置 |
|---|---|---|---|
| 1 | `bg-surface-raised`(Modal §4.2) | ❌ token 不存在;实际有 `surface-1/2/3/inset` | Modal 面板改 `bg-surface-1`(`border-border-default` / `shadow-popover` / `bg-black/50` scrim 均已验证) |
| 2 | `ROUTE_META.skill.fg = text-accent` | 现有 route 用 `text-{route}-fg` 模式;`RouteMeta` 接口必填 `leftBorder`(v1 漏列) | 改 `text-accent-fg`;补 `leftBorder: 'border-l-accent'`。完整条目:`{ zh:'技能', en:'skill', dot:'bg-accent', leftBorder:'border-l-accent', fg:'text-accent-fg', tintBg:'bg-accent-bg', border:'border-accent-border', glow:'shadow-glow-accent' }` |
| 3 | (前端疑) `RouteSource` 加 `'forced'` | 后端 `_SOURCE_MAP`(`main.py:103-109`)把 `route_method="forced"`→`source="command"` | **不必加** `'forced'`;后端不发 `source:"forced"`,前端 `RouteSource` 联合类型不变 |
| 4 | `useImportSkill` 命名 | knowledge 用 `useUploadKnowledge`(因其端点是 `POST /knowledge`) | 维持 `importSkill` / `useImportSkill`——技能端点是 `/skills/import`,"import" 与本模块自身命名一致(不是 knowledge 的 "upload" 镜像) |
| 5 | `UploadProgress` 复用 | 填充色硬编码 `bg-query`(`UploadProgress.tsx:9`) | 给 `UploadProgress` 加 `fillClassName` prop(默认 `bg-query`,knowledge 不动);SkillImportModal 传 `bg-accent` |
| 6 | `UploadZone` 镜像(隐藏 input) | 实际用 `onBrowse` 点击浏览,非隐藏 input | SkillImportModal 自建 `<input accept=".zip,.md">` 隐藏 input + 点击触发;拖拽 state 模式照 UploadZone |
| 7 | 图标 `Sparkles` | `WandSparkles` 已用于 "auto" 路由 | 维持 `Sparkles`(v1 选择);两者都在 lucide,若视觉混淆可后调 |
| 8 | `POST /skills/import` 状态码 | knowledge POST 返回 200 | 技能 **201**(创建命名资源并返回 SkillMeta);与 knowledge 200 不同可接受 |
| 9 | `_MAX_UPLOAD_BYTES` 在 config.py | 实为 `main.py:435` 模块常量 10MB | skills 复用该常量;zip-bomb "与之一致" 已验证 |
| 10 | `AuditLogger` | 类名是 `AuditLog`(`foundation/audit.py:26`) | v2 用 `AuditLog` |
| 11 | `preconditions.py` 在 foundation | 实在 `engines/scheduling/preconditions.py` | v1 §3.1 已正确指出(foundation 不能反向依赖引擎);v2 注明实际路径 |
| 12 | `AgentLoop.run(message,…)` | 首参名 `task`(`agent_loop.py:99`) | v2 用 `task`(位置调用不受影响) |
| 13 | "对齐 SessionStore 范式"含 version | SessionStore 无 version 字段(全仓库无先例) | 仅镜像 catalog+落盘+Lock 结构;version 是净新增机制(见分叉 A),非镜像已有模式 |
| 14 | `_classify_system()` / `_classify` | 均不存在(`CLASSIFY_SYSTEM` 是 `router.py:24-43` 模块常量,直接传给 `llm.classify`) | 见分叉 B |
| 15 | `EmbeddingRouter` 持 SkillStore 引用 | 当前构造器只收 `(llm, examples)`(`embedding_router.py:50`) | 加 SkillStore 引用 + version 失效(见分叉 A);`load_examples()` 仍读 `routing_examples.yaml`,技能 `when_to_use` 经 `routing_examples()` 合并 |

## 3. 前置断言能力(`tool_preconditions`)落地确认

v1 §2.2/§3.3 已写入技能级前置断言。核查确认可行,**无需改设计**,仅记录实现要点:

- **命名断言来源**:`engines/scheduling/preconditions.py` 的 `make_dispatch_precondition(kitting, adapter)`(`:17-49`)与 `make_expedite_precondition(kitting, followups)`(`:52-76`)均存在,返回 `Precondition` callable。bootstrap 构造 `named_preconditions: dict[str, Precondition]`(`{"dispatch_ready": …, "expedite_valid": …}`),闭包已绑定 kitting/adapter/followups,SkillEngine 查名即用。**普通 dict,不建 Registry 类**(简单优先)。
- **AgentLoop 插入点**:`agent_loop.py:212-221` 是工具自带 precondition 检查(`if tool.kind=="write" and tool.precondition is not None`)。`extra_preconditions: dict[str, list[Precondition]] | None = None` 加到 `AgentLoop.__init__`;`_handle_call` 在该块**之后**依次执行该工具的追加断言,任一失败即 blocked 回喂(与现有 blocked 路径同构)。缺省 None 行为不变,调度引擎零感知。
- **执行范围**:extra_preconditions 对技能在 `tool_preconditions` 中显式命名的工具执行(不限 write kind,因技能已声明);命名断言本身是自包含 callable,内部决定检查什么。安全不变量不变:**只叠加不替换**——内置断言与 ActionGate 人工确认均不受技能影响,恶意技能包最多只能让自己更受限。
- **导入校验**:`tool_preconditions` 的 key 不在 `allowed_tools` 内、或断言名不在 `named_preconditions` 名集内 → 422 列出非法项(v1 §2.3 规则 6,已对齐)。
- **`Precondition` 类型与精确插入行号**:实现时读 `engines/scheduling/preconditions.py` 的 `Precondition` 签名 + `agent_loop.py` 的 `_handle_call` 确认精确插入行;此处不锁定行号(代码会演进)。

## 4. 实施阶段(承 v1 §7,drift 并入)

| 阶段 | 内容 | 检查点 |
|---|---|---|
| 1 解析与存储 | `skills/schemas+parser+store` + `tests/test_skills.py`(frontmatter 非法态、zip 穿越/缺 SKILL.md/归一化、未知工具名/断言名、`tool_preconditions` key 越界 allowed_tools、落盘重启重载) | `pytest tests/test_skills.py` |
| 2 HTTP + bootstrap | `config.skills_dir`、bootstrap 装配(store/engine/`read_skill_file`/`named_preconditions`)、Platform 字段、三端点(§2 #8 用 201) | `pytest`;`curl -F "file=@demo.md" :8000/skills/import` |
| 3 执行 + 路由 | SkillEngine、AgentLoop `extra_preconditions`、RouteDecision 枚举、EmbeddingRouter 动态向量(分叉 A)、`_classify_system` 候选拼接(分叉 B)、Orchestrator forced/dispatch、`_contract_route`。测试照 `test_router.py` FakeLLM:forced / LLM 命中 / 选不存在技能降级 / embedding 层(conftest `_EMBED_VOCAB` 补技能判别词)/ degraded / 白名单强制 / 技能断言拦截写工具且不影响无技能路径 | `pytest`;curl `/chat/stream` 观察 route 帧 `intent:"skill"` |
| 4 前端 | 类型 → api → hooks → MSW → Modal(`bg-surface-1`)→ SkillMenu → SkillImportModal(`UploadProgress` 加 `fillClassName`)→ Composer/Workspace 接线 → `ROUTE_META`(`text-accent-fg`+`leftBorder`)→ 透传链 + 组件/hook 测试 | `npm test && npm run lint && npm run build`;`VITE_API_MOCKING=enabled npm run dev` 走查 |
| 5 契约与联调 | `../api-contract/api-contract-v2.md` 追加;附 demo `capacity-report.md` 技能;`./restart.sh` 端到端:导入 → 选中 → 发送 → route 帧 skill → ReAct 执行 → 审计时间线含 skill_id | 手动验收 |

附:本期随仓库附一个 demo `capacity-report.md`(对齐 v1 §2.1 示例),让端到端可走查。

## 5. 关键改动文件速查

- **后端**:`bootstrap.py`、`orchestrator/{schemas,router,embedding_router,orchestrator}.py`、`engines/scheduling/agent_loop.py`(`extra_preconditions`)、`main.py`、`config.py`、新包 `skills/`(schemas/parser/store/engine)。
- **前端**:`Composer.tsx`、`Workspace.tsx`、`api/{skills,hooks,queryKeys,index}.ts`、`types/{api,index}.ts`、`lib/routes.ts`、`mocks/api/{handlers,fixtures}.ts`、`components/ui/Modal.tsx`(新建)、`features/orchestrator/skills/`(新建)、`features/query/knowledge/UploadProgress.tsx`(加 `fillClassName` prop)。
