# Skill Hub 与 MCP 连接器市场同步 — 实现计划

日期：2026-07-11  
范围：`maestro/`、`frontend/`、`docs/api-contract/api-contract-v2.md`  
目标：从审核过的官方或知名 GitHub 仓库同步技能与 MCP 连接器目录，每天北京时间 03:00 自动刷新；扩展中心支持搜索、来源标注、手动同步、安装/添加和更新。

## 0. 与 `extensions-center-design-v1.md` 的关系

本计划是扩展中心目录能力的**权威实现方案**，在目录（catalog）与远程安装范围内**取代** v1 设计文档的以下部分：

- 取代 v1 §7.2「连接器目录模型」与 §9「SkillHub 架构与 API」中的目录/远程安装设计。
- 以本计划的 `maestro/src/maestro/extensions/` 模块、`ExtensionCatalogStore` 与 `/extension-catalog/*` 路由为准，**不再**新建 v1 提出的 `skillhub/`、`connectors/` 目录，也不实现 `/skillhub/*`、`/mcp/catalog` 路由与两段式 `prepare-install` + `install_token` 流程。
- 用「安装时按固定 commit 重新下载并重新预检」替代 v1 的 `install_token` 绑定流：commit 固定 + 重新校验对「防止 Review 后包被替换」是等价且更简单的保证，不再引入一次性 Token 与临时包生命周期。

继续沿用 v1 中**已经落地**的 MCP 本地管理（`MCPConfigStore`、`SettingsJsonStore`、`/mcp/servers` 系列）和 Skill 本地生命周期（`SkillStore`、`validate_skill_package`、信任模型）。v1 §11 的安全基线尚未完整落地，其中 §11.1 privileged local/admin 认证是本计划阶段 0 的阻断项，不能视为已有能力。

v1 文档保留为背景与已实现部分的说明；两者冲突时以本计划为准。

## 1. 目标与非目标

### 1.1 目标

1. Skill Hub 不再依赖前端写死的 3 个技能，目录由后端持久化并通过 API 提供。
2. 连接器市场不再依赖前端写死的 3 个 MCP 模板，目录同样由后端提供。
3. 初始来源只允许平台代码中审核过的 GitHub 仓库与路径，不允许用户输入任意 URL。
4. 后端每天在 `Asia/Shanghai` 时区的 03:00 同步一次；管理员可手动同步全部来源或单个来源。
5. 市场支持按名称、描述、作者/组织、来源搜索，并显示来源仓库、许可证、版本/commit、最后同步时间和兼容性。
6. 已安装 Skill、已配置 MCP 与远程目录分离；同步目录不自动安装、更新、信任或启动任何扩展。
7. Skill 可手动安装和更新；MCP 可从市场模板添加，并在模板更新时手动更新非敏感配置。
8. 同步失败保留最后一次成功快照，不影响已安装 Skill、已配置 MCP 或聊天主流程。

### 1.2 非目标

- 首期不抓取任意网站，不运行通用网页爬虫。
- 首期不提供第三方投稿、评分、评论、排行榜或 AI 推荐。
- 首期不自动安装或自动更新 Skill/MCP。
- 首期不自动信任 Skill 脚本，不自动连接/启动 MCP Server。
- 首期不覆盖用户修改过的 MCP 参数、环境变量、Secret 或启用状态。
- 首期只支持现有 MCP `stdio` 能力；远程 HTTP/SSE MCP 等客户端支持后续单独设计。

## 2. 首批来源白名单

白名单是代码审查对象，定义在后端，不由前端或远程响应动态扩权。

### 2.1 Skill 来源

| source_id | 仓库 | 范围 | 默认状态 |
|---|---|---|---|
| `openai-skills-curated` | `openai/skills` | `skills/.curated/*/SKILL.md` | 启用 |
| `anthropics-skills` | `anthropics/skills` | 仅显式允许的技能子目录 | 启用 |

说明：

- OpenAI curated 目录可按目录发现，但每个包仍必须通过 Maestro 的兼容性预检。
- Anthropic 仓库结构或字段与 Maestro 不完全一致，因此首期使用路径 allowlist，不做“仓库里发现什么就全部上架”。
- 后续新增 `github/awesome-copilot` 等来源时必须单独提交配置、许可证评估和解析测试，不能仅在数据库中插入 URL。

### 2.2 MCP 来源

| source_id | 仓库 | 范围 | 默认状态 |
|---|---|---|---|
| `mcp-reference-servers` | `modelcontextprotocol/servers` | 生产用途的官方 reference servers；排除 `everything` 等测试 Server | 启用 |
| `github-mcp-server` | `github/github-mcp-server` | GitHub 官方 MCP Server | 启用 |
| `playwright-mcp` | `microsoft/playwright-mcp` | Microsoft 官方 Playwright MCP Server | 启用 |

MCP 仓库没有统一且稳定的 Maestro 配置格式。首期为每个来源实现小型、显式 adapter：从已知 manifest/package 文件读取版本与说明，再由本地审核过的模板生成 `command`、`args`、Secret 声明。禁止从 README 中抽取并直接执行任意 shell 命令。

## 3. 核心架构

```text
审核过的 GitHub 来源
        │ GitHub API / raw download（限域、限路径、限大小）
        ▼
CatalogSourceAdapter
        │ 解析 + 规范化 + 兼容性检查
        ▼
ExtensionCatalogStore ────── SyncRun 审计/状态
        │
        ├── GET /extension-catalog/skills ── Skill Hub
        └── GET /extension-catalog/connectors ── 连接器市场
                    │
          用户明确点击安装/添加/更新
                    ▼
          SkillStore / MCPConfigStore
```

关键边界：

- `ExtensionCatalogStore` 是“可发现目录”，不等同于本地安装状态。
- 已安装 Skill 继续由 `SkillStore` 管理；已配置 MCP 继续由 `MCPConfigStore` 管理。
- 目录项保存 GitHub 元数据和经过规范化的安装材料，但绝不因定时同步直接写入两个本地 Store。
- 安装/更新时必须重新下载指定 commit 的内容并重新校验，不能盲信目录缓存。

## 4. 后端数据模型

新增 `maestro/src/maestro/extensions/`：

```text
extensions/
├── __init__.py
├── schemas.py          # source/item/sync DTO
├── sources.py          # 代码内白名单定义
├── github_client.py    # GitHub API/raw 客户端，ETag/限流/超时
├── adapters.py         # Skill/MCP source adapters
├── catalog_store.py    # catalog.json + sync-runs.json 持久化
├── service.py          # 同步、安装、更新编排
└── scheduler.py        # 每日 03:00 调度
```

### 4.1 CatalogSource

```python
class CatalogSource(BaseModel):
    id: str
    kind: Literal["skill", "connector"]
    display_name: str
    owner: str
    repo: str
    ref: str = "main"
    source_url: HttpUrl
    trust_tier: Literal["official", "verified"]
    enabled: bool = True
```

API 只读返回来源；首期不提供创建/修改来源 API，避免把任意远程代码入口暴露给 UI。

### 4.2 CatalogSkill

```python
class CatalogSkill(BaseModel):
    catalog_id: str               # source_id:name
    name: str
    display_name: str
    description: str
    author: str | None
    license: str | None
    version: str | None
    source_id: str
    source_name: str
    source_url: str               # GitHub tree URL
    source_ref: str
    source_commit: str
    blob_sha: str | None
    etag: str | None
    package_sha256: str
    compatibility_status: Literal["ready", "degraded", "not_ready"]
    warnings: list[str]
    has_scripts: bool
    synced_at: datetime
    last_checked_at: datetime
    withdrawn: bool = False
    installable: bool
    install_block_reason: str | None
    installed: bool               # 查询时派生
    installed_sha256: str | None  # 查询时派生
    update_available: bool        # catalog hash != installed hash
```

`not_ready`、已撤回或许可证不在 allowlist 的项默认也进入目录，但 `installable=false`，“添加”按钮禁用并显示 `install_block_reason`，方便发现上游变化；它们不能进入安装流程。

### 4.3 CatalogConnector

```python
class CatalogConnector(BaseModel):
    catalog_id: str
    name: str
    display_name: str
    description: str
    author: str | None
    license: str | None
    version: str | None
    source_id: str
    source_name: str
    source_url: str
    source_ref: str
    source_commit: str
    blob_sha: str | None
    etag: str | None
    transport_type: Literal["stdio"]
    command: str
    args: list[str]
    env_schema: list[ConnectorEnvSpec]  # 只含变量名、说明、required/secret，不含值
    requirements: list[str]
    catalog_template_sha256: str
    synced_at: datetime
    last_checked_at: datetime
    withdrawn: bool = False
    installable: bool
    install_block_reason: str | None
    configured: bool
    configured_catalog_id: str | None
    configured_template_version: str | None
    update_available: bool
```

为准确比较 MCP 模板更新，给 `MCPServerSettings` 增加可选字段：

```python
catalog_id: str | None = None
catalog_version: str | None = None
catalog_template_sha256: str | None = None
```

旧配置加载时字段为空，保持向后兼容。

### 4.4 SyncRun

记录 `run_id`、触发方式（`scheduled/manual/startup_recovery`）、来源、开始/完成时间、状态、`discovered/sources_unchanged/items_unchanged/added/updated/withdrawn/failed` 计数、HTTP/解析错误摘要。来源级和条目级跳过分别计数，避免统计含糊。每个来源持久化 `last_synced_commit`、`last_checked_at`、`stale`、`last_error` 与 `validation_fingerprint`。保留最近 100 次，禁止保存 GitHub Token。

持久化模型包含同步内部字段（如 `blob_sha`、`etag`、`validation_fingerprint`）；API 响应可使用独立 DTO 隐藏不需要暴露的内部状态，但必须返回 UI 所需的 `withdrawn/installable/install_block_reason/last_checked_at`。

## 5. GitHub 同步规则

### 5.1 网络与凭证

- 新增可选环境变量 `GITHUB_TOKEN`；无 Token 时允许公共 API 降级运行。
- 仅访问 `api.github.com`、`raw.githubusercontent.com` 和白名单仓库。
- 请求设置连接/读取超时、响应体上限、重试上限；禁止重定向到非白名单域名。
- 优先使用 Git Trees API（`GET /repos/{owner}/{repo}/git/trees/{sha}?recursive=1`）一次拉取整棵目录树，再按需下载单个 blob，避免 per-file Contents API 在无 Token 的 60 次/小时预算下迅速耗尽。
- Git Trees API 返回 `truncated=true` 时，本次来源同步必须失败并保留旧快照；不得把不完整树中的缺失条目判定为上游删除。
- 使用 `ETag` / `If-None-Match` 与 blob SHA 比对做条目级短路；未变化的来源与条目均不重复下载、不重解析（详见 §5.5）。
- 每次同步先解析默认/配置 ref 对应 head commit SHA，目录项固定引用该 SHA，避免分支移动造成安装内容与展示内容不一致。
- 限流命中（403 rate limit / 429）时按 §5.4 部分失败处理：保留旧快照、状态页展示 reset 时间，不做高频重试。

### 5.2 Skill 同步

1. adapter 返回候选技能目录。
2. 下载 `SKILL.md` 及允许的附件；复用现有 ZIP 安全上限：成员数、总大小、路径穿越、符号链接。
3. 将远程目录组装为内存 ZIP。
4. 调用现有 `validate_skill_package()`，生成标准化元数据、工具映射、警告和兼容状态。
5. 计算 Maestro `package_sha256()` 并原子更新目录快照。
6. 同步不能调用 `SkillStore.save()`。

上游 Skill 请求 Maestro 未注册工具时标为 `not_ready`，不为了提高上架数量而放宽工具白名单。

### 5.3 MCP 同步

1. adapter 只读取审核过的 manifest/package 文件及固定路径 README 元数据。
2. 可执行模板来自本地 adapter，不接受远程 shell 文本。
3. package version 必须固定；模板中禁止 `@latest` 或无版本的 PyPI 包。
4. 对 `npx`、`uvx` 可执行文件和参数做 allowlist 校验；禁止 shell 控制符、重定向、命令替换和相对脚本执行。
5. Secret 仅声明变量名，例如 `GITHUB_PERSONAL_ACCESS_TOKEN`，目录永不保存 Secret 值。

### 5.4 原子快照与失效

- 每个来源成功后才用临时文件 + replace 更新该来源快照。
- 某来源失败时保留旧快照并标记 `stale=true`、`last_error`；其他来源继续同步。
- 上游删除的条目标记 `withdrawn=true`，保留 30 天用于解释已安装项来源；UI 不再允许新安装。
- 同步不删除、禁用或修改已安装扩展。

### 5.5 增量同步：GitHub 未更新则跳过

同步分两级短路。来源级短路必须同时验证 GitHub commit 与本地 `validation_fingerprint`；条目级短路也只跳过远程下载，本地验证规则发生变化时仍需重新计算兼容性。这是无 Token 限流预算下的主要节流手段，同时避免本地工具或安全策略升级后目录状态永久陈旧。

1. **来源级短路（source-level）**：每次同步先解析该来源当前 ref 的 head commit SHA，并计算当前 `validation_fingerprint`。只有 `head_commit == last_synced_commit`、指纹相同且来源非 `stale` 时，才跳过整个来源——不拉取文件树、不下载文件、不重算兼容性；SyncRun 增加 `sources_unchanged`，条目 `synced_at` 保持不变，同时更新来源 `last_checked_at`。
2. **条目级短路（item-level）**：来源 head commit 变了，不代表每个技能/连接器都变了。对每个候选条目比对子目录树/blob SHA 或 ETag。远程内容未变且验证指纹相同时，保留旧快照并增加 `items_unchanged`；只有真正变化的条目走完整下载、解析和预检。若验证指纹变化，则可复用安全的本地缓存包，但必须重新运行预检和安装许可判断，不得沿用旧兼容状态。

`validation_fingerprint` 至少覆盖：catalog schema 版本、source adapter 版本、已注册工具名、工具 alias、named preconditions、Skill 校验限制、许可证策略版本以及 MCP 本地模板版本。集合/映射先做稳定排序和规范 JSON 序列化再计算 SHA-256，保证相同配置跨进程得到相同指纹。任何一项变化都使旧兼容性缓存失效。

配套约束：

- catalog 快照按来源持久化 `last_synced_commit` 与 `validation_fingerprint`，每个条目持久化 `source_commit` 与 `blob_sha`/`etag`，作为下次短路依据。
- 首次同步（无任何快照）、`last_synced_commit` 缺失、或来源被标记 `stale`（上次失败）时，按全量处理，不走短路。
- 手动「立即同步」同样走增量短路；如需强制全量，提供显式 `force=true`（跳过 commit/ETag 比对），默认不强制。
- 来源级短路每源仅消耗 1 次 head-commit 查询，全部来源未变时一次定时同步的 API 开销为「来源数」次请求。

## 6. 每天 03:00 调度

新增配置：

```python
extension_catalog_sync_enabled: bool = True
extension_catalog_sync_time: str = "03:00"
extension_catalog_sync_timezone: str = "Asia/Shanghai"
extension_catalog_sync_jitter_seconds: int = 0
# catalog.json / sync-runs.json 落在运行时数据根下（默认 ~/.maestro/extensions/），gitignored；
# 遵循「env > settings.json > .env」的数据根解析，不写入仓库目录。
extension_catalog_data_dir: Path | None = None
```

调度器使用标准库 `zoneinfo` 计算“下一次本地 03:00”，不采用固定 `sleep(86400)`，避免时钟调整和夏令时问题。中国时区目前无夏令时，但实现不依赖这一事实。

启动语义：

- FastAPI lifespan 始终以 `asyncio.create_task` 创建 `catalog_sync_task`，关闭时 cancel 并等待退出。**首次/补偿同步一律在后台任务内执行，绝不在 lifespan 关键路径上 `await`**，以确保 GitHub 慢或不可达时不阻塞后端与 Electron 启动（复用现有 `bus_task`/`patrol_task` 的启动模式）。
- 若没有任何成功快照，启动后立即同步一次，以免首次使用看到空市场。
- 若已有快照但最近成功时间早于上一个应执行的 03:00，启动后执行一次补偿同步。
- 多进程部署首期明确要求单 worker；若未来使用多 worker，再增加文件锁/数据库租约。测试与 README 中写明该约束。
- 同一时刻只允许一个同步运行；手动同步遇到运行中任务返回现有 `run_id` 和 `status=running`，不重复启动。

## 7. API 契约

统一放在新路由 `maestro/src/maestro/api/routes/extensions.py`，保留现有 `/skills` 和 `/mcp/servers` 安装态接口。

```text
GET  /extension-catalog/sources
GET  /extension-catalog/status
POST /extension-catalog/sync
POST /extension-catalog/sources/{source_id}/sync

GET  /extension-catalog/skills?q=&source=&compatibility=&installed=&updates=&page=&page_size=
GET  /extension-catalog/skills/{catalog_id}
POST /extension-catalog/skills/{catalog_id}/install
POST /extension-catalog/skills/{catalog_id}/update

GET  /extension-catalog/connectors?q=&source=&configured=&updates=&page=&page_size=
GET  /extension-catalog/connectors/{catalog_id}
GET  /extension-catalog/connectors/{catalog_id}/update-preview?configured_name=
POST /extension-catalog/connectors/{catalog_id}/add
POST /extension-catalog/connectors/{catalog_id}/update
```

约定：

- 搜索由后端执行，大小写不敏感，覆盖 name/display_name/description/author/source_name。
- 列表默认按“官方优先、兼容优先、名称”排序；不伪造热度排序。
- `POST .../sync` 返回 `202 {run_id,status}`，状态通过 `/status` 查询；不让 HTTP 请求等待完整 GitHub 同步。
- 安装 Skill 前重新获取固定 commit 包并再次预检；重名但非同一 `catalog_id` 返回 409，不覆盖本地导入技能。
- Skill 更新采用 `SkillStore.replace()` 新方法原子替换；请求必须携带用户确认时看到的 `expected_package_sha256`，不匹配则返回 409 要求重新检查；更新后旧 hash 信任自动失效。
- MCP `add` 创建 `enabled=false` 配置；必要 Secret 缺失时也允许保存，但不能连接。
- MCP `update-preview` 是只读操作，返回 command/args/description/catalog 字段的更新前后 diff 及当前 `catalog_template_sha256`。
- MCP `update` 请求必须携带 `configured_name`、`expected_revision` 与用户确认时看到的 `expected_catalog_template_sha256`；任一值已变化则返回 409 要求重新预览。更新只修改 catalog 管理的 `command/args/description/catalog_*`，保留 env 值、Secret、enabled 和用户自定义 display_name。
- 所有变更接口（`install/update/add/sync`）都会写技能包或生成会启动本地进程的 MCP 配置，属 **privileged local/admin API**，必须遵循 v1 §11.1：Web 部署要求身份认证 + 管理员权限，Electron 使用受保护会话 Token，CORS 只允许受信前端来源。**Origin/Host 校验只是纵深防御，不能冒充身份认证**——不得仅依赖 `_require_local_origin()`。所有 privileged 操作写审计日志，记录来源、principal、目标 Hash 与结果。

建议错误码：400 参数错误、404 目录项不存在、409 名称冲突/同步运行中、422 不兼容或缺少必填配置、429 GitHub 限流、502 上游读取失败、503 尚无可用目录快照。

## 8. 前端实现

### 8.1 API 与类型

新增：

- `frontend/src/types/api/extensions.ts`
- `frontend/src/api/extensionCatalog.ts`
- `queryKeys.extensionCatalog.*`
- `useCatalogSources/useCatalogStatus/useCatalogSkills/useCatalogConnectors`
- `useSyncCatalog/useInstallCatalogSkill/useUpdateCatalogSkill`
- `useAddCatalogConnector/useUpdateCatalogConnector`

删除 `ExtensionCenterPage.tsx` 对 `CATALOG_SKILLS`、`CATALOG_CONNECTORS` 的依赖。完成迁移后删除 `frontend/src/features/extensions/catalog.ts` 及静态 ZIP；不在同一步顺手重构其他扩展中心组件。

### 8.2 Skill Hub

保留“已安装 / 推荐 / SkillHub”三个页签，但首期定义清楚：

- 已安装：现有 `/skills`。
- 推荐：目录中 `trust_tier=official`、`installable=true` 的确定性子集，按来源优先级与名称稳定排序后最多展示 12 个；不称为个性化推荐。
- SkillHub：全部未撤回目录项。

页面能力：

- 搜索框使用 URL `q`，300ms debounce 后请求后端。
- 来源筛选、兼容性筛选、“仅看可更新”。
- 卡片显示来源徽标、作者、版本、许可证、兼容性和更新时间。
- 详情抽屉显示 GitHub 来源链接、commit 短 SHA、所需工具、脚本、警告。
- 按钮状态：添加、安装中、已安装、更新、不可兼容、来源已撤回。
- “更新”先弹出版本/hash/权限差异，再确认；确认请求携带 `expected_package_sha256`。包含脚本的新版仍为未信任。

### 8.3 连接器市场

保留“已配置 / 推荐 / 连接器市场”：

- 搜索与来源/已配置/可更新筛选同 Skill Hub。
- 卡片显示来源、版本、运行时要求和所需 Secret 名称。
- “添加”打开预填表单，不直接保存和连接；用户可检查 command/args 并填写必要路径或 Secret。
- 保存后的默认 `enabled=false`；用户另行点击连接。
- “更新模板”先调用只读 `update-preview` 展示 command/args diff，明确标注哪些用户字段会保留；确认请求携带 preview 返回的模板 SHA 与配置 revision。
- 已配置但无法关联 catalog 的手工 MCP 继续正常显示，不出现错误的更新提示。

### 8.4 同步状态

两个市场页共用顶部状态：

```text
最后同步：今天 03:02 · 5 个来源正常（4 个未变化已跳过） · 1 个来源失败 [查看] [立即同步]
```

- “立即同步”触发全部来源；来源筛选详情可单独同步。
- 同步期间轮询 `/status`，完成后 invalidate 两类 catalog query。
- 失败展示来源级错误摘要和保留旧数据说明，不清空卡片。
- 只读 catalog 可按部署策略公开；“立即同步”、安装、添加和更新必须携带阶段 0 定义的 privileged 会话凭证。Origin/Host 只做纵深防御，不作为认证替代。

## 9. 分阶段实施任务

### 阶段 0：Privileged API 认证基线（阻断项）

目录 mutation 开发前先完成 v1 §11.1 的安全前置条件：

- 抽取统一的 privileged API 认证依赖，Web 部署校验身份与扩展管理权限，Electron 使用后端启动时生成的受保护会话 Token。
- CORS 从 `allow_origins=["*"]` 收紧为受信前端来源；Origin/Host 校验保留为纵深防御。
- 将现有 `/skills/import`、`DELETE /skills/{name}`、技能信任接口、`/mcp/servers` mutation、`/mcp/servers/test` 与后续 catalog mutation 纳入同一认证依赖。
- 只读 catalog 查询可按部署策略公开；已安装扩展详情若包含本地路径或配置摘要则保持受保护。
- 所有 privileged 操作写审计日志，记录 principal、来源、目标 hash 和结果，不记录 Token/Secret。

测试：无凭证、错误凭证、普通用户、管理员、Electron Token、伪造 Origin、无 Origin 直连、CORS 预检以及 Token 不出现在日志/API 响应中。

验收：未认证调用不能导入/删除/信任 Skill，不能测试/保存/连接 MCP，也不能触发同步或目录安装更新。阶段 0 未通过前，后续阶段最多开放只读 catalog API。

### 阶段 1：目录模型与持久化

改动：

- 新增 `extensions/schemas.py`、`sources.py`、`catalog_store.py`。
- `config.py` 增加目录路径与同步配置。
- 为 `MCPServerSettings` 增加可选 catalog 来源字段。

测试：

- catalog 原子保存、重启重载、损坏快照错误。
- 同 source/name 更新、撤回、保留旧快照。
- `validation_fingerprint` 变化使兼容性缓存失效。
- MCP 旧 settings.json 向后兼容。

验收：完全离线时可以用 fixture 构造并查询两类目录快照。

### 阶段 2：GitHub 客户端与来源 adapters

改动：

- 新增限域 GitHub 客户端、ETag 缓存。
- 实现 OpenAI/Anthropic Skill adapters。
- 实现 MCP reference/GitHub/Playwright adapters。
- Skill 复用现有 parser；MCP 增加命令模板安全校验。

测试全部 mock HTTP，不访问网络：

- 200、304、403 rate limit、404、超时、部分来源失败。
- Git Trees `truncated=true` 时来源失败且不撤回任何旧条目。
- ref 固定到 commit、重定向越域、响应超限。
- Skill 非法 ZIP/字段/未知工具变 `not_ready`。
- MCP 禁止 `latest`、shell 控制符和远程命令注入。

验收：fixture 同步生成稳定、可重复的 catalog JSON，任何远程内容均不能改变 MCP 可执行文件类型。

### 阶段 3：同步服务、调度与可观测性

改动：

- 新增 `service.py`、`scheduler.py`。
- 在 `bootstrap.py::build_platform()` 装配 catalog store/service/scheduler。
- 在 FastAPI lifespan 启停同步任务。
- 日志记录 source/run/count/duration，不记录 Token/Secret。

测试：

- 下一次 03:00 计算、跨日、补偿同步、首次启动同步。
- 来源级短路：head commit 与验证指纹均未变时不拉取文件树、不重算，记为 `sources_unchanged`。
- 条目级短路：来源 commit 变但某条目 blob/ETag 未变时不重下载、不重预检；仅变化条目走全量。
- 本地工具、alias、断言、校验限制、许可证或 adapter 版本变化时，即使 GitHub commit 未变也重新预检。
- `force=true` 手动同步跳过短路做全量；`stale` 来源不走短路。
- 并发手动/定时同步去重。
- 单来源失败不影响其他来源；失败保留旧快照。
- task cancel 可正常关闭。

验收：冻结时间测试证明北京时间每天只执行一次；重启漏跑时只补一次。

### 阶段 4：目录查询与同步 API

改动：

- 新增 `api/routes/extensions.py` 并注册 router。
- 实现来源、状态、分页搜索、筛选、手动同步。
- 更新 API contract。

测试：

- 查询组合、分页边界、URL 编码、空目录。
- 手动同步 202、运行中去重、未知 source 404。
- 所有 mutation 复用阶段 0 的 privileged 认证依赖；只读 catalog 按部署策略验证。

验收：curl 可查询来源、搜索两类目录并启动/观察一次同步。

### 阶段 5：Skill 安装与更新

改动：

- `SkillStore` 增加原子 `replace()`；不得用 delete + save 暴露中间空窗。
- 实现 catalog skill install/update。
- 安装记录 `catalog_id/source_commit`；可放入 `SkillMeta.extensions["catalog"]`，避免扩张顶层契约。

测试：

- 安装 ready/degraded；拒绝 not_ready/withdrawn。
- 固定 commit 下载内容变化时 hash 校验失败。
- `expected_package_sha256` 与当前目录不一致时返回 409，不执行更新。
- 本地同名冲突不覆盖。
- 更新成功、更新失败回滚、更新后信任失效。

验收：从目录安装后能在 Composer 选择并执行；上游新版本出现后可手动更新且旧信任无效。

### 阶段 6：MCP 添加与模板更新

改动：

- 实现 catalog connector add/update-preview/update。
- 复用 `MCPConfigStore` revision 乐观锁。
- 新增配置时强制 `enabled=false`。

测试：

- 预填配置、名称冲突、revision 冲突。
- Secret 不落 catalog，不由 API 回传。
- 更新保留 env/secret/enabled/display_name。
- preview 后模板 SHA 或 settings revision 变化时返回 409，不执行更新。
- 模板更新不启动进程；用户显式 connect 后才调用 manager。

验收：市场添加的 MCP 出现在“已配置”，保持未连接；填写必要参数后可走现有测试/连接流程。

### 阶段 7：前端 Skill Hub

改动：类型、API、hooks、搜索/筛选、来源徽标、同步状态、安装/更新确认。

测试：

- 搜索 debounce 与 query 参数。
- 来源/兼容性/更新筛选。
- 安装、409、not_ready、更新 diff、脚本信任提示。
- 同步轮询成功/部分失败。

验收：不再读取静态 `CATALOG_SKILLS`；刷新页面后目录、安装态和更新态一致。

### 阶段 8：前端连接器市场

改动：动态目录、搜索/筛选、来源、预填添加表单、模板 diff 更新。

测试：

- 添加不自动连接。
- 必要 Secret/路径提示。
- 模板更新保留用户字段。
- 手工连接器不被 catalog 状态污染。

验收：不再读取静态 `CATALOG_CONNECTORS`；官方来源与本地配置状态可清晰区分。

### 阶段 9：文档、打包与端到端验证

改动：

- 更新 `README.md`、`.env.example`、API contract。
- Electron/打包环境确认 GitHub 网络错误不会阻塞启动。
- 删除已被动态目录替代的静态 catalog ZIP。

验证命令：

```bash
cd maestro && pytest
cd frontend && npm test
cd frontend && npm run lint
cd frontend && npm run build
```

端到端场景：

1. 空数据目录启动，后台首次同步，市场出现两类官方目录。
2. 搜索 `pdf`、按 OpenAI 来源过滤、安装并执行 Skill。
3. fixture 模拟 Skill 新 commit，手动同步后出现“可更新”，更新后信任失效。
4. 搜索 filesystem MCP，添加后保持未连接，补充路径后手动连接。
5. fixture 模拟 MCP 模板新版本，更新 diff 保留用户路径/Secret。
6. GitHub 403/超时，UI 仍展示上次快照及失败来源。
7. 冻结到 02:59→03:00，自动同步只触发一次；服务重启补偿逻辑正确。
8. GitHub 内容不变但本地工具/许可证策略变化，目录兼容性重新计算。
9. 未认证请求无法触发同步、安装、更新、MCP 测试或连接；Electron 会话 Token 可完成授权操作。

## 10. 完成定义

- 后端市场目录完全替代前端硬编码目录。
- 所有启用来源均来自代码内审核白名单，并能显示 GitHub 来源链接与固定 commit。
- 北京时间每天 03:00 自动同步，支持全部与单来源手动同步；GitHub 未更新的来源与未变化的单个技能/连接器自动跳过，不做无谓下载与重解析。
- 本地验证指纹变化时，即使 GitHub commit 未变也会重新计算兼容性与安装许可。
- Skill Hub 和连接器市场均支持后端搜索、来源筛选、同步状态与更新提示。
- 同步永不自动安装、信任、修改已安装项、启动 MCP 或覆盖 Secret。
- Skill 更新原子且使旧 hash 信任失效；MCP 更新保留用户配置且默认不连接。
- 所有扩展 mutation 均经过 privileged API 认证，CORS 已收紧，Origin/Host 不能替代身份凭证。
- 上游失败不影响主应用和已有快照。
- 后端测试、前端测试、lint、build 全部通过，API contract 与 README 同步更新。

## 11. 风险与后续决策

1. **GitHub API 限流**：优先 ETag 与 Token；状态页显示 reset 时间，不做高频重试。
2. **上游结构变化**：每个 source adapter 独立测试；失败只冻结该来源旧快照。
3. **许可证**：目录显示许可证。首期**没有运行时管理员审核入口**（§4.1 不提供来源/条目变更 API），因此许可证 allowlist 与来源白名单同构、定义在代码内：未知或不在 allowlist 的许可证项可展示、可发现，但首期**永久不可安装**（按钮禁用并显示原因）。放行某个许可证是一次代码审查改动（等同新增来源），不通过 API 或数据库放行。
4. **依赖可用性**：MCP 市场只保证模板合法，不保证本机已安装 Node/uv；添加前展示 requirements，连接测试给出明确错误。
5. **多实例调度**：首期单 worker；扩展到多实例前必须引入跨进程租约，不能依赖进程内锁。
6. **网站 Feed**：本计划完成后可增加签名的 `/.well-known/maestro-extensions.json` adapter，但仍需来源白名单、固定 hash 与同等预检，不直接开放任意 URL。
