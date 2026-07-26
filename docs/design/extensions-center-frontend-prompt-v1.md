# 扩展中心前台实现提示词 v1（可直接粘给 Claude Code）

> 日期：2026-07-26
> 配套设计稿：`docs/design/extensions-center-ui-v1.html`（交互式静态稿，打开即可点）
> 上位设计文档：`docs/design/extensions-center-design-v1.md`（产品意图）与
> `docs/design/extensions-center-design-v2.md`（MCP 实现现状勘误，**以 v2 与代码为准**）
> 视觉基准：`docs/design/maestro-design-system-v2.html`、`frontend/src/index.css`、`frontend/tailwind.config.ts`

---

## 任务

把左下角「技能·连接器管理」入口从当前的 `SkillManagerModal` 弹窗，升级为**全宽扩展中心页面**：
保留左侧 `SessionSidebar`，中间会话区 + 右侧 RunTrace 全部替换为扩展中心；左侧点击任意会话或「新建任务」时自动退出扩展中心回到对话。页面内含「技能 / 连接器」两个同级 Tab，支持增删改查。交互与视觉以 `extensions-center-ui-v1.html` 为准。

## 当前代码事实（已核实，不要重新发明）

- 入口：`frontend/src/components/layout/SessionSidebar.tsx:291-315`（展开态）与 `:121-129`（折叠 rail），回调 `onOpenSkills`，现在在 `frontend/src/pages/Workspace.tsx:284` 打开 `SkillManagerModal`。
- 路由：`frontend/src/router/index.tsx` 只有 `/` → `Workspace`（Electron 用 hashRouter）。
- 布局：`frontend/src/components/layout/Layout.tsx`（props: sidebar/topBar/conversation）；RunTrace 不在 Layout 内，由 `Workspace.tsx:302-372` 拼在 conversation slot 旁边。
- 技能 API（已实现，直接复用）：`frontend/src/api/skills.ts` — `listSkills` GET `/skills`、`validateSkill` POST `/skills/validate`、`importSkill` POST `/skills/import`、`trustSkill`/`revokeSkillTrust`、`deleteSkill`；类型在 `types/api/skills.ts`（`SkillMeta`/`SkillTrustStatus`/`SkillValidationReport`）。
- 连接器 API（已实现范围见 v2 文档）：`frontend/src/api/mcp.ts` — `listMcpServers` GET `/mcp/servers`、`upsertMcpServer` PUT `/mcp/servers/{name}`、`deleteMcpServer`、`reconnectMcpServer` POST `.../reconnect`；类型在 `types/api/mcp.ts`。**没有** test/connect/disconnect 独立端点、没有 `/mcp/catalog`、没有 SkillHub catalog。
- hooks：`frontend/src/api/hooks.ts`（`useSkills`、`useMcpServers`、`useUpsertMcpServer`、`useDeleteMcpServer`、`useReconnectMcpServer`，queryKey 内联 `['skills']` / `['mcp-servers']`）；TanStack Query 已在 `main.tsx` 就位。
- 现有弹窗可拆取复用：`features/orchestrator/skills/SkillImportModal.tsx`（validate→import 流程）、`features/settings/McpSettings.tsx`（ServerForm 字段与 hooks 用法）。
- 样式：`index.css` 语义 token（`--bg-*` `--surface-*` `--text-*` `--border-*` `--status-*` `--accent*`）+ `tailwind.config.ts` 映射；spacing 有 `sidebar:264px`、`sidebar-rail:56px`、`context-panel:308px`。组件习惯：语义 token 类 + 任意值原子类混用。
- 注意 bug：`McpSettings.tsx` 用了不存在的 `text-status-danger`，应为 `text-status-error`，顺手修掉。

## 硬性设计决策（不讨价）

1. **走独立路由，不做大弹窗**：`/settings/skills`、`/settings/connectors`（Electron hashRouter 同构）。点击 Sidebar 会话 → `navigate('/')` 天然实现「自动关闭」；可刷新、可前进后退。
2. **保留 Sidebar，替换整个右侧**：进入扩展中心后卸载 TopBar 会话信息 / Conversation / Composer / RunTrace。
3. **双 Tab 同级**：Header 内「技能 | 连接器」分段切换 = 两个路由互跳；技能域子导航「推荐 / SkillHub / 已安装」，连接器域「推荐 / 可用连接器 / 已配置」，子导航与 `?tab=` query 同步。
4. **只用语义 token，禁止 raw hex**；accent 复用现有 `--accent`（cyan），不新创品牌色；状态用 `status-success/warning/error`；阴影只给 Drawer/Modal/Popover，列表行用 1px 分隔线，不堆卡片阴影。
5. **范围对齐后端现状（本迭代只做有真实 API 的部分）**：
   - 技能：已安装列表（搜索/筛选/排序）、详情 Drawer、本地导入（validate→import，含警告展示）、信任/取消信任、删除。
   - 连接器：已配置列表（状态点/工具数/来源 managed 标识）、新增/编辑 Drawer（stdio 表单 + env 表格 + secret 三态）、删除（确认 Modal，按钮文案写清「删除连接器」）、重连。
   - 「推荐 / SkillHub / 可用连接器」三个浏览视图：**不伪造后端**。做成 `features/extensions/catalog/staticCatalog.ts` 本地静态目录（数据结构与未来 `/skillhub` `/mcp/catalog` 响应同形），安装按钮只对已安装项显示状态，未安装项点击只打开详情并标注「远程安装将在 SkillHub 接入后开放」；也可以整段用 feature flag `VITE_EXTENSION_CATALOG=off` 隐藏，默认 off。两种都行，选定一种写在 PR 描述里。
6. **危险操作显式确认**：卸载技能 / 删除连接器必须 Modal 二次确认，按钮写动作不写「确定」；MCP 删除前说明工具池影响（见设计稿文案）。
7. **managed 配置只读**：`McpServer` 若带 managed/editable 语义（后端字段为准），UI 禁用编辑/删除并提示「由环境管理」。
8. **不改后端 API**；发现缺字段时在前端类型层做兼容（可选字段 + 默认值），并在 PR 中列出「希望后端补充的字段清单」，不擅自 mock 出不存在的语义。
9. `SkillManagerModal` 与设置弹窗里的 `McpSettings` 迁移到新页面后**删除旧代码**；Composer 的 `SkillMenu` 保持轻量选择器不动，仅把底部「导入技能」跳转到 `/settings/skills?import=1`（打开导入 Drawer）。
10. a11y：Tab 用 `role=tablist/tab/tabpanel`；Drawer 捕获焦点、Esc 关闭、关闭后焦点回触发元素；状态不只用颜色（图标+文本）；异步态 `aria-live=polite`。

## 建议实现路径

### Step 1 — Shell 与路由（先做小步重构）

- 新增路由 `/settings/skills`、`/settings/connectors`，挂到现有 router。
- 最小改法：`Workspace.tsx` 目前持有 Sidebar 全部回调。把 Sidebar 渲染与 `useWorkspaceSessions`、会话回调、主题、折叠状态上移到新的 `components/layout/AppShell.tsx`（路由层共享），`/` 渲染 Workspace 内容，`/settings/*` 渲染扩展中心；若评估后风险大，允许过渡方案：扩展中心页自己再渲染一次 `SessionSidebar`（复用同一组件与回调 props），但必须保证 Sidebar 组件零复制，仅调用点复制，并在代码注释标记 `TODO(shell): 收敛到 AppShell`。
- Sidebar 入口 `onOpenSkills` 改为 `navigate('/settings/skills')`；在扩展中心路由下该入口呈选中态。Sidebar 其余部分（新建会话按钮、搜索会话输入框、会话分组列表、折叠 rail）**保持现状不改**。

### Step 2 — 扩展中心骨架

新增目录 `frontend/src/features/extensions/`：

```
ExtensionCenterLayout.tsx    // Header（标题+域 Tab+搜索+已安装计数+主按钮）+ <Outlet/>
ExtensionDomainTabs.tsx      // 技能 | 连接器
ExtensionSubTabs.tsx         // 推荐 / SkillHub|可用连接器 / 已安装|已配置（与 ?tab= 同步）
ExtensionDetailDrawer.tsx    // 右侧 480px Drawer 通用壳（mask 只盖内容区，不盖 Sidebar）
skills/SkillsPage.tsx        // 子路由内容：推荐(静态目录) / 已安装
skills/SkillInstalledList.tsx / SkillListRow.tsx
skills/SkillDetailDrawer.tsx // 简介/when_to_use/能力/工具/文件/包信息/危险操作
skills/SkillImportDrawer.tsx // 复用 validate→import 逻辑（从 SkillImportModal 抽 hook）
connectors/ConnectorsPage.tsx
connectors/ConnectorListRow.tsx
connectors/ConnectorEditorDrawer.tsx  // stdio 表单 + env 表格 + secret 三态
connectors/ConnectorDetailDrawer.tsx
catalog/staticCatalog.ts     // 静态演示目录（feature flag 控制）
```

- 状态：服务器状态全部走 TanStack Query（复用/扩展 `api/hooks.ts`，queryKey 收敛为 `['extensions','skills',...]` / `['extensions','mcp',...]` 并保留旧 key 兼容或让 Composer 共用同一 key）；浏览状态（tab/q/筛选）写 URL query；表单草稿用组件本地 state。**不新增 zustand store**。
- 视觉：参照 `extensions-center-ui-v1.html`——Header 56px、域 Tab 分段控件、子 Tab 2px 下划线指示、卡片 `rounded-xl border hover:translateY(-2px)`、状态点 6px + glow、Badge mono 大写、Drawer 480px、删除 Modal 400px。全部映射到现有 token，不抄设计稿里的 hex 值。

### Step 3 — 功能接线

- 已安装技能：列表 = `useSkills()`；筛选「全部/可用/需要处理/含脚本」前端派生（`SkillTrustStatus` + validator 字段）；「有更新」本次不做（无来源元数据），UI 预留但不渲染。
- 导入：从 `SkillImportModal` 抽 `useSkillPackageImport()`（validate→import→invalidate `['skills']`），`SkillImportDrawer` 与 Composer 的 Modal 共用；warnings 必须先展示再允许确认。
- 信任/取消信任/删除：复用现有 API 函数；删除前 Modal 确认。
- 连接器：列表 = `useMcpServers()`；新增/编辑 = `useUpsertMcpServer`；删除 = `useDeleteMcpServer`；重连 = `useReconnectMcpServer`。操作中的短暂态（saving/reconnecting）用本地 state 在原行内切换，不弹全局 loading。
- 错误处理沿用 `ApiError`（403 特权 token 提示参考 `McpSettings.tsx:26-28`）。

### Step 4 — 收尾

- 删除 `SkillManagerModal`、`McpSettings`（及 SettingsModal 中的「系统集成」节）；`SkillMenu` 底部「导入技能」改跳转。
- mocks：`mocks/api/handlers.ts` 增补已安装技能多条 fixture 与 mcp servers fixture，支撑组件测试。
- 测试（Vitest + Testing Library）：
  - 从 Sidebar 入口可导航到两个路由；扩展中心打开时 Conversation/Composer/RunTrace 不存在。
  - 域 Tab、子 Tab、搜索与 URL query 同步。
  - 技能：导入流程（validate 有 warning 时必须确认后才 import）、信任切换、删除确认后调用 DELETE 并刷新列表。
  - 连接器：新增/编辑提交 PUT、删除确认、reconnect 调用；managed 行禁用编辑/删除。
  - Drawer：Esc 关闭、焦点返回触发元素。
  - 跑通 `Workspace.test.tsx` 既有用例无回归。

## 验收标准（对照设计稿逐项过）

1. 左下角「技能·连接器管理」→ 中右全宽扩展中心；Sidebar 点会话/新建任务自动返回 `/`。
2. 技能、连接器双 Tab；技能有「已安装」真实 CRUD + 导入 + 信任管理；连接器有「已配置」真实 CRUD + 重连。
3. 刷新 / 前进后退不丢页面与子 Tab 状态（URL query）。
4. 全站无新增 raw hex；light/dark 两主题正常；`prefers-reduced-motion` 下动画关闭。
5. 危险操作均有显式确认；Secret 不回显。
6. `npm run test`（或仓库既有命令）全绿；`npm run build` 通过。

## 明确不做（写进 PR 描述防 scope creep）

- SkillHub 真实远程目录与两段式安装（等后端 `/skillhub`，见 v1 文档 §9）。
- `/mcp/catalog`、测试连接、connect/disconnect 独立端点（等后端补，见 v2 文档 §2）。
- MCP resources、SSE/HTTP 传输。
- 「有更新」检测（等安装来源元数据）。
