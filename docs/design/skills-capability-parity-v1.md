# Skill 能力补齐设计 v1 — 对齐 Claude Code 的四项缺口

> 状态:**草案(非定稿)**。方向已定,但开工前须先解决 §1 的 4 项 P0/P1 blocker;在此之前**不视为"无架构阻塞"**。
> 目标:在**不破坏现有安全属性**(白名单 + 前置断言 + ActionGate + 审计)的前提下,补齐 maestro 技能系统相对 Claude Code 的四项能力:①渐进披露 ②可执行脚本 ③技能嵌套 ④正文上限。
> 关联:`../skills/skills-design-v1.md`(规范源)、`../skills/skills-design-v2.md`(代码现实对齐)、`../platform/scheduling-platform-design-v3.md`。
> 核查基线:`skills/{engine,store,parser,schemas}.py`、`engines/scheduling/{agent_loop,tool_executor,termination,preconditions}.py`、`foundation/tools/{registry,builtin}.py`、`foundation/authz.py`、`orchestrator/router.py`、`bootstrap.py` 已逐一核查。

## 0. 现状基线(三级披露骨架已存在,但零件不安全)

| 级别 | Claude Code | maestro 现状 | 缺口 |
|---|---|---|---|
| L1 目录 | 全技能 metadata 常驻 | `router.py:87` `routable()`、`store.routing_examples()`,仅**路由时**可见 | 运行中的技能看不到别的技能与附件清单 |
| L2 正文 | 触发时加载 | `engine.py:104` 整份注入(≤32KB) | 整份塞入;硬上限;**多技能拼接后总量无上限** |
| L3 附件 | 按需读 | `read_skill_file(skill_name, path)`(`bootstrap.py:203`) | 无法发现文件;**`skill_name` 可传任意值,跨技能越权读取** |

## 1. 开工前 blocker(P0/P1,必须先解决)

以下问题在原草案中被遗漏,直接影响安全正确性,**开工前逐条落实**。

### B-1(P0)#2 subprocess `-I` 不是沙箱

`sys.executable -I` 只隔离 Python 环境变量与 site,**进程仍以后端账户权限运行**:可读宿主文件、访问网络、`fork` 子进程;`subprocess.timeout` 也未必杀掉**后代进程**。人工确认与内网部署**不构成隔离**。

**处置(二选一)**:
- **(a) 延期**:#2 延到具备**真正隔离**的方案(容器 / nsjail / seccomp)再做;本期不实现 `run_skill_script`。
- **(b) 明确改名"受信任脚本执行"**(不叫"沙箱"),且硬性要求全部满足:独立**低权限账户**运行、**只读挂载**技能目录、**禁网**(netns / 防火墙)、**资源与进程组限制**(`setsid` + 超时按**进程组**整组 kill、rlimit/cgroup)、**脚本 SHA-256 审批**(见 B-2)。任一条不满足则回退到 (a)。

**结论**:#2 视为**独立安全专项**,不作为普通"能力补齐"随 #1/#3 一起推进。

### B-2(P1)文件/脚本缺"当前技能"作用域

`read_skill_file(skill_name, path)`(`bootstrap.py:203`)接受**任意 `skill_name`**,handler 直接读 store。白名单只限制**工具名**,不限制**参数**,故任一技能都能读/执行**其他技能包**的内容。新增 `list_skill_files`/`run_skill_script` 若沿用同接口会放大此越权。

**处置**:
- 工具签名**去掉 `skill_name`**,改为"当前技能附件"接口:`read_skill_file(path)`、`list_skill_files()`、`run_skill_script(script, args)`。
- 允许访问的 skill ID 由**调用上下文**携带(见 B-4 的 invocation context),不由 LLM 传参。
- 嵌套子技能只能访问**自己的附件**与**自己声明的脚本**;`read_skill_file` 现有的路径越界校验(`store.read_attachment` `is_relative_to`)保留。
- `read_skill_file` 需同步改造(现有它是有 `skill_name` 的旧接口),这是**先决重构**,不是纯新增。

### B-3(P1)`kind="write"` 不自动经 ActionGate

`SkillEngine.handle`(`engine.py:107`)构造 `AgentLoop` 时**未注入 `permissions`/`confirm_resolver`**;`ToolExecutor` 仅在显式注入 `PermissionEngine` 时才做权限评估(`tool_executor.py:86`),`kind="write"` 单独只会跑**已挂载的前置断言**(`:112`)。现有写工具是在 **handler 内部显式** `gate.request()`(`builtin.py:162`;`authz.py:98` 的 `ActionGate.request`,`auto` 级直接执行 `executor()`)。

**处置**:
- `run_skill_script` **必须在 handler 内调用 `gate.request(...)`**,与 `send_expedite_message` 同构。
- 其 `action_type` 在 AuthZ 策略中定为**所有模式都 `requires_confirmation`**;否则 `auto` 模式下未知写动作可直接执行(`authz.py:112`)。
- 待确认时**记录并执行同一份内容快照或 SHA-256**,避免确认后源文件被替换(TOCTOU)。

### B-4(P1)嵌套工具会被并发执行

`invoke_skill` 定为 `aux` 后,`ToolExecutor.parallelizable`(`tool_executor.py:44`)对 `read`/`aux` 返回 True,多个调用被 `asyncio.gather` 并行(`agent_loop.py:141`)。共享的 `visited`/`remaining_steps` 产生竞争、预算可超支;`contextvar` **不能替代并发同步**。

**处置**:
- `Tool` 增 `parallelizable: bool = True` 字段;`ToolExecutor.parallelizable(name)` 改为 `tool.parallelizable and tool.kind in ("read","aux")`。`invoke_skill`、`run_skill_script` 设 `parallelizable=False`,强制串行。(此为 registry/executor 的跨切面小改,惠及未来所有"不可并行"工具。)
- **预算语义**:定义为"**全链路 LLM 请求数(含 forced final / retry)**",由带**锁**的 invocation context **原子扣减**;不是每循环 `max_steps`,也不靠 contextvar 裸读写。

## 2. 决策记录(两处实质分叉,已定)

| 分叉 | 决策 | 理由 |
|---|---|---|
| **A. #2 脚本执行形态** | 真执行 `.py`,但**收窄为受信任脚本执行 + 独立安全专项**(见 B-1) | 用例需任意计算;但 `-I` 非隔离,不能作为普通能力补齐 |
| **B. #3 子技能工具白名单** | 子技能用**自己声明的 `allowed_tools`** | 安全由全局写护栏兜底(B-3 修正后),嵌套不放大危险动作;交集会无谓限制组合 |

**贯穿不变量**:技能包最多让**自己**更受限或更啰嗦,**永不**绕过权限引擎、写前置断言、ActionGate 人工确认与审计。四项改动全部保持此不变量——B-2/B-3 正是为守住它而补。

## 3. 实施顺序(据 blocker 重排)

```
#4 正文上限 + 合并总量上限        — 0.5~1 天,先做
#1 渐进披露 (作用域化附件接口)    — 1~1.5 天(含 read_skill_file 去 skill_name 重构)
#3 技能嵌套                       — 补齐"串行 + 共享预算原子扣减"后再做
#2 受信任脚本执行                 — 独立安全专项,满足 B-1(b) 或延期
```

各项自带单测,做完一项验一项。#2/#3 各自独立分支。

---

## 4. 逐项设计

### #4 正文上限 + 合并总量上限

**问题**:`parser.py:9` `_BODY_MAX = 32*1024` 硬编码;多技能在 `engine.py:97` 直接拼接正文,单包 128KB 组合时**放大且无总上限**。

**落点**:
- `config.py` 增 `skill_body_max_bytes`(单包)与 `skill_prompt_max_bytes`(**合并后渲染进 system prompt 的总量上限**)。
- `parse_skill_md(text, max_bytes)`、`extract_package(..., max_bytes)` 透传单包上限;`routes/skills.py` 用 `settings.skill_body_max_bytes`。
- `SkillEngine.handle` 拼接后校验合并总量,超 `skill_prompt_max_bytes` → 明确报错(而非静默截断)。

**注意**:不再用"32KB≈8k tokens"这种近似——**中文的 token/字节比与英文不同**,以字节上限为准,token 估算仅作参考。默认值靠 #1 引导瘦身而非一味调大。

**验收**:单包 32KB<x<上限 成功、超限 422;多技能合并超 `skill_prompt_max_bytes` 时明确报错;既有测试全绿。

---

### #1 渐进披露:作用域化附件接口 + L2 瘦身

**目标**:运行中的技能能发现并按需读**自己**的附件,正文只留索引。**含 B-2 的作用域重构**。

**落点**:
1. `SkillStore` 增 `list_attachments(name) -> list[dict]`,字段明确为 **`{path, size_bytes}`**(是大小,**不是内容**)。
2. 附件接口**去 `skill_name`**(B-2):`read_skill_file(path)` / `list_skill_files()`,当前技能 ID 由 invocation context 提供;`read_skill_file` 是**先决重构**(改现有有 `skill_name` 的实现)。
3. **路径安全**:`path` 是用户/LLM 输入,须规范化相对路径、拒绝控制字符、限长;保留 `store.read_attachment` 的 `is_relative_to` 越界校验。
4. **注入安全**:文件清单以**结构化/转义**形式注入 prompt(路径来自技能包,也当不可信文本处理),不裸拼进自然语言。
5. `SkillEngine.handle`:`file_count>0` 时把 `list_skill_files`/`read_skill_file` 追加进白名单并注入清单。
6. 文档约定:长 SOP/表格放附件,正文留"何时读哪个文件"。

**不做"全技能目录常驻"**:技能由路由触发,router 已见全部 description;常驻目录属过度设计,跨技能发现由 #3 覆盖。

**验收**:带 `reference/x.md` 的技能能据清单读到内容;传他技能路径/越界路径/控制字符被拒;无附件技能白名单不含这两个工具。

---

### #3 技能嵌套:`invoke_skill`(有界 + 串行)

**目标**:技能循环内可调另一技能(depth),不只是 breadth 合并。**依赖 B-4 的串行 + 共享预算。**

**落点**:
1. **抽出可复用入口**:`engine.py:52` `handle` 现直接 new `AgentLoop`;抽出 `_run(skill_ids, message, history, on_progress, ctx)`,`ctx: SkillInvocationContext` 带 `depth`、`visited: set[str]`、`remaining_budget`、**`Lock`**。
2. **`invoke_skill(skill_id, task)` 工具**,`kind="aux"` 且 **`parallelizable=False`**(B-4)。handler 闭包持 `skill_engine` 与 ctx。
3. **有界护栏**:
   - `depth > settings.skill_max_depth`(默认 2)→ 拒绝。
   - `skill_id in visited`(含祖先链)→ 拒绝,防环。
   - **全链路 LLM 请求预算**:`ctx` 在**锁内原子扣减**(含 forced final / retry 计数);耗尽即停。不用每循环 `max_steps`,不靠裸 contextvar。
   - `disable_model_invocation=True` 的技能不可被 `invoke_skill` 调用。
   - `user_invocable` 约束只作用于 `source="user"` 顶层;嵌套视为 `source="route"`。
4. **不提权(决策 B)**:子技能用自己声明的 `allowed_tools`;安全由全局写护栏兜底(B-3 修正后含 ActionGate)。子技能只能访问**自己的**附件/脚本(B-2)。
5. 观测 = 子技能 `answer` + `stop_reason`,回喂父循环。

**config**:`skill_max_depth: int = 2`;全链路预算(建议复用/新增一个"总请求数"上限)。

**验收**:A 调 `invoke_skill("B",…)`→B 回结论;A→B→A 第二次被环检测拒;depth 3 被拒;**并发多个 invoke_skill 时预算不超支**(串行 + 原子扣减);子技能 dispatch 仍走 ActionGate。

---

### #2 受信任脚本执行(独立安全专项,默认关闭)

**定位**:**不是**普通能力补齐,是独立安全项目。`-I` 非沙箱(B-1),仅在满足**真正隔离**要求时才实现,否则延期。**不使用"沙箱"一词**。

**前置硬要求(B-1(b),缺一即延期)**:独立低权限账户、只读挂载技能目录、禁网、进程组超时整组 kill、资源限制(rlimit/cgroup)、脚本 SHA-256 审批快照。

**落点(满足前置后)**:
1. `schemas.py` `SkillFrontmatter` 增 `scripts: list[str] = []`(声明式白名单);未声明的附件永不可执行。
2. 导入校验:`scripts` 路径须存在、扩展名 ∈ 允许集(先仅 `.py`),否则 422。
3. `run_skill_script(script, args)` 工具(**去 `skill_name`**,B-2;`kind="write"`,`parallelizable=False`):
   - handler 内**显式 `gate.request(...)`**(B-3),`action_type` 全模式 `requires_confirmation`。
   - 执行**确认时的内容快照/SHA-256**(B-3,防 TOCTOU)。
   - 隔离执行(前置硬要求),捕获 stdout/stderr 作观测,超时按**进程组**kill。
   - 输出走 `observation_max_bytes` 截断/离线(`tool_executor.py:160`)。
4. 总开关:`settings.skill_scripts_enabled: bool = False`(默认关闭,工具不注册)。
5. **诚实局限**:未达前置硬要求前,本功能**不上线**;人工确认/内网**不等于**隔离。

**config**:`skill_scripts_enabled: bool = False`、`skill_script_timeout: int = 10`。

**验收**:满足隔离前置后——声明的 `scripts` 经 ActionGate 确认后执行、快照一致;未声明附件/他技能脚本被拒;禁网/只读/整组超时 kill 生效;开关关闭时工具不存在。

---

## 5. 文件改动清单(据 blocker 更新)

| 文件 | #1 | #2 | #3 | #4 | blocker |
|---|:-:|:-:|:-:|:-:|---|
| `config.py` | | ✅ 开关/超时 | ✅ 深度/预算 | ✅ body/合并上限 | |
| `foundation/tools/registry.py` | | | | | ✅ `Tool.parallelizable`(B-4) |
| `engines/scheduling/tool_executor.py` | | | | | ✅ `parallelizable` 判定改造(B-4) |
| `skills/schemas.py` | | ✅ `scripts` | | | |
| `skills/parser.py` | | ✅ 校验 scripts | | ✅ 上限透传 | |
| `skills/store.py` | ✅ `list_attachments`(size_bytes) | ✅ 脚本快照/hash | | | ✅ 路径规范化(B-2) |
| `skills/engine.py` | ✅ 注清单/白名单 | | ✅ 重构 + ctx+Lock | ✅ 合并上限校验 | ✅ 作用域 ctx(B-2) |
| `foundation/tools/builtin.py` | ✅ `list_skill_files`(去 skill_name) | ✅ `run_skill_script`(gate.request) | ✅ `invoke_skill`(不可并行) | | ✅ `read_skill_file` 去 skill_name(B-2) |
| `bootstrap.py` | ✅ 注册 + 注入 ctx | ✅ 注册 + 门控 | ✅ 注入 engine | | |
| `api/routes/skills.py` | | | | ✅ 传上限 | |
| `foundation/authz.py`(策略) | | ✅ script 动作定级 requires_confirmation | | | ✅(B-3) |
| `tests/` | ✅ | ✅ | ✅ | ✅ | ✅ 越权/并发/gate 用例 |
