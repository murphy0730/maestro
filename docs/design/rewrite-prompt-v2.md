# 任务：基于 v2 设计稿完全重写 Maestro 前端

> 用途：直接复制本文件全文（或从「## 1. 目标」起）作为提示词，交给 Claude Code 执行前端重写。
> 依据设计稿：`docs/design/maestro-design-system-v2.html`（深空指挥舱 · DRAFT FOR REVIEW · 2026-07-23）

## 1. 目标
以 `docs/design/maestro-design-system-v2.html`（「深空指挥舱」，1307 行）为**唯一视觉与交互依据**，
完全重写 `frontend/` 的 UI 层。功能上做到「不丢能力」：现有已跑通的业务流程重写后必须全部仍然可用，
并在重写完成后做一次真实的端到端验证。

## 2. 先读设计稿
先完整阅读 `docs/design/maestro-design-system-v2.html`，它已包含 9 个章节：
01 设计概念与原则 / 02 色彩系统 / 03 字体排版 / 04 材质与效果 / 05 组件 /
06 界面设计稿 A–I / 07 动效规范 / 08 与代码的落地映射 / 09 交付验收清单。

其中 **08 节末尾的「实施顺序建议 ①–⑦」就是执行顺序，按它走**；
**09 节的验收清单是硬性验收标准**，重写完要逐条自查并给出结论。

界面稿 A–I 必须全部落地：
- A 主工作区·流式运行中（深空默认）
- B 主工作区·运行完成（极昼）
- C 空状态与建议
- D 会话侧栏：展开 264px ⇄ 折叠 56px
- E 详情栏三态：驻留 / 隐藏 / 全屏
- F 技能选择弹层（对话框上弹）
- G 技能管理
- H Electron 桌面端启动屏
- I 设置模态（侧栏左下入口，Esc / 点遮罩关闭）

## 3. 现状事实（不要凭 CLAUDE.md 猜，以下为实测）
- 前端：React 18 + Vite + TS + Tailwind 3 + TanStack Query + Zustand + react-router + lucide-react + react-markdown。
- 现有源码：`frontend/src/{api,components,features,pages,router,stores,lib,mocks,types}`。
  当前 `pages/Workspace.tsx`、`features/runtime/RunTrace.tsx`、`components/layout/TopBar.tsx` 等
  是极度压缩的骨架（单行超长语句），**可以整体重写，不要试图在它上面缝补**。
- 后端真实路由（`maestro/src/maestro/`，注意与旧文档不同）：
  - Runs：`POST /runs`、`GET /runs/{run_id}`、`GET /runs/{run_id}/stream`（SSE）、
    `POST /runs/{run_id}/approvals/{approval_id}`、`POST /runs/{run_id}/cancel`
  - Skills：`GET /skills`、`POST /skills/validate`、`POST /skills/import`、
    `POST|DELETE /skills/{name}/trust`、`DELETE /skills/{name}`
  - Sessions：`GET|POST /sessions`、`PATCH|DELETE /sessions/{session_id}`、`GET /sessions/{session_id}/messages`
  - Artifacts：`POST /artifacts`、`GET /artifacts/{artifact_id}`
- 前端 API 层（`src/api/`：client / hooks / runs / sessions / skills / artifacts / useRunStream）
  与类型层（`src/types/api/`）**已经与后端对齐，原则上保留，只在必要时增改**。
- 目前**没有 Playwright 配置**；已有 vitest 单测（`*.test.tsx` / `*.test.ts`）。
- Electron 壳在 `frontend/electron/`，`src/lib/platform.ts` 的 `isMacDesktop` 控制 44px 拖拽条。

## 4. 必须保留的功能（重写后逐条可用）
1. 会话：列表 / 新建 / 重命名 / 删除 / 切换 / 历史消息回填。
2. 运行：发起 run、SSE 流式 token 渲染、思考过程（ThinkingProcess）、步骤时间线、
   最终结果 Markdown 渲染、token 统计、升级原因（upgradeReason）、诊断信息（diagnostics）。
3. 断线恢复：切换会话时用 `active_run_id` 调 `restore()` 重挂流（现有 `useRunStream` 的 restore/recovered 语义不能丢）。
4. 审批：待确认动作卡片 → 确认 / 拒绝，带 `run_revision` 乐观并发；审批中禁用态。
5. 取消：运行中「停止」。
6. 技能：列表、多选挂载到本次运行、清空、导入（含校验）、信任 / 取消信任、删除。
7. 专家模式（expert）开关、附件上传。
8. Artifacts 查看。
9. 主题切换（接入已有 `stores/themeStore.ts`，补 UI）、个性化设置（`personalizationStore`）。
10. MSW 离线 mock（`VITE_API_MOCKING=enabled`）仍可跑通主流程。
11. Electron 桌面壳（macOS hiddenInset 拖拽区不塌）。

## 5. 范围与禁区
- **可以重写**：`frontend/src/` 下的 UI（components / features / pages / layout / index.css / tailwind.config.ts）。
- **谨慎改动**：`src/api/`、`src/types/`、`src/stores/` —— 只有当 UI 确有需要时才改，改了要同步更新对应单测。
- **不要改后端** `maestro/`。设计稿 08 节指出两个契约缺口：
  ① 模式选择器需要 `POST /runs` 增加 `mode` 字段（auto/planning/scheduling/query）；
  ② 会话列表的「消息数 / 最后预览」需要 `GET /sessions` 扩展字段。
  **遇到这两处先停下来问我**，不要擅自改后端；在我答复前按「前端先只展示标题与时间、模式选择器 UI 先做但暂不下发」实现。
- 不引入新的重型依赖；字体需要新增 `@fontsource` 的 Space Grotesk + JetBrains Mono（这个可以装）。

## 6. 硬性设计约束（来自设计稿，违反即返工）
- 语义 token 单一来源：只改 `src/index.css` 的 `:root` 变量值 + 少量新增变量，`tailwind.config.ts` 做镜像；
  组件里**只用语义类，禁止裸 hex**。新增变量至少包括 `--path-controlled`、`--mode-planning/scheduling/query`、
  `--glow-accent`、`--aurora`、`--grid-line`、`--data-1…6`。
- 双主题（深空 dark 默认 / 极昼 light）同构渲染，玻璃与边框在两主题都清晰。
- 一色一职：模式轴与授权轴不互借色；极光三色只做背景氛围，不进组件。
- 颜色非唯一指示：模式 / 状态一律配文字或图标。
- 图标全部 Lucide 线性 SVG（1.8px），**禁止 emoji 图标**。
- 圆角：按钮 6px / 徽标 4px / 卡片 12px / 容器 14–16px；过渡 150–250ms `cubic-bezier(.2,.8,.2,1)`；
  可点元素 `cursor:pointer`；焦点环可见。
- `prefers-reduced-motion` 一键停掉全部动效。
- 中文排版：字重 ≤ 500、字距 0、行长 ≤ 68 字符。
- 正文对比度 ≥ 4.5:1，极昼语义色 ≥ 4.9:1。

## 7. 端到端验证（重写完必须做，且要有证据）
分四层，逐层通过再进下一层：

**L1 静态**
```bash
cd frontend && npm run lint && npm run build && npm test
```
lint 必须 `--max-warnings 0` 通过；`tsc -b` 零错误；vitest 全绿（重写导致失效的测试要改成对应新结构的测试，不许删掉了事）。

**L2 真实后端联调**
```bash
./restart.sh all        # 后端 :8000 + 前端 :5173
```
确认 `frontend/.env.development` 仍是 `VITE_API_MOCKING=disabled`，即打真实后端。

**L3 浏览器逐项走查**（用 Chrome MCP 驱动 http://localhost:5173，每项截图留证）
按第 4 节的 11 条功能逐条实操，至少覆盖：
1. 冷启动 → 空状态（界面稿 C）显示正确
2. 新建会话 → 发消息 → SSE 流式 token 实时渲染 → 运行完成
3. 触发一个需确认的写操作 → 审批卡出现 → 确认执行 → 状态流转正确；再跑一次走「拒绝」
4. 运行中点「停止」→ 取消生效
5. 会话侧栏：新建 / 重命名 / 删除 / 切换；切回有活跃 run 的会话能恢复流
6. 侧栏折叠 264px ⇄ 56px；详情栏三态 驻留/隐藏/全屏 切换
7. 技能弹层：挂载多个技能 → 发起运行 → 清空；技能管理页导入 / 信任 / 删除
8. 主题切换 深空 ⇄ 极昼，全页面无失色、无对比度塌陷
9. 设置模态：入口 / Esc / 点遮罩关闭
10. 专家模式开关、附件上传
全程读 console 与 network，**不允许有报错或 4xx/5xx**。

**L4 离线与桌面**
- `VITE_API_MOCKING=enabled` 下 MSW 主流程仍跑通。
- `npm run electron:dev` 启动，检查启动屏（界面稿 H）与 macOS 拖拽条不与红绿灯冲突。

**最后交付一份验证报告**：逐条列「功能 / 验证方式 / 结果 / 证据」，
并对设计稿 09 节验收清单 8 项逐条给结论。**没验证过的不许写「已完成」，失败的如实写出来。**

## 8. 工作方式备注
- **不要使用 superpowers skill**（brainstorming / writing-plans / TDD 等一律不调用）。
- 前端设计相关可用 `ui-ux-pro-max`、`frontend-design`；这不是强制。
- 分阶段提交，每完成设计稿 08 节实施顺序的一步就跑一次 L1，别攒到最后。
- 本机 GateGuard 会让每个文件的**首次** Edit/Write 被拒一次，属正常现象，直接重试即可。
- 有歧义先问，不要猜着做；但除第 5 节点名的两个契约缺口外，其余判断自己拿主意，别频繁打断。
