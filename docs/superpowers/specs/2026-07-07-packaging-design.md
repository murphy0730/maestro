# 桌面应用打包方案设计（Windows + macOS）

- 日期：2026-07-07
- 状态：设计已确认，待实现计划
- 适用范围：把 `maestro`（Python FastAPI 后端）+ `frontend`（React/Electron 壳）打包为 Windows 与 macOS 可运行的桌面应用

## 1. 目标与非目标

### 目标
- 产出一个**自包含**的桌面应用：双击即用，用户无需自行安装 Python 或启动后端。
- 支持 **macOS（仅 arm64）** 与 **Windows（x64）**。
- Windows 安装器允许**用户选择安装目录**。
- 公开对外分发：macOS 经 Apple 公证、Windows 经代码签名。
- 首次运行起降级模式；用户在应用内配置 LLM/Embedding 供应商后恢复完整能力。

### 非目标（v1）
- 自动更新（electron-updater）。设计不阻挡后续接入，但 v1 不实现；分发方式 = 从 GitHub Release 下载新版手动重装。
- macOS x64 / Universal 构建。
- Windows arm64 构建。
- EV 证书 / 远程签名服务（v1 用 OV 证书，接受 SmartScreen 信誉累积期）。
- 密钥用 OS keychain 加密存储（`safeStorage`），v1 明文存于用户数据目录。
- 内置 LLM/Embedding 模型或离线嵌入；后端仍走外部 `EMBED_*` 接口。

## 2. 关键决策

| 决策点 | 选择 | 理由 |
|---|---|---|
| 后端打包方式 | **PyInstaller onefolder 侧车** | 真正自包含、无需用户装 Python；与现有 electron-builder 无缝衔接 |
| 构建环境 | **GitHub Actions**（macos-14 arm64 + windows-latest x64） | 可复现、签名密钥托管于 secrets；PyInstaller 不能跨 OS 编译 |
| 自动更新 | **v1 不做** | 带后端侧车的自动更新复杂度高；分发走 Release 下载 |
| API key 处理 | **不打包密钥**，应用内多供应商配置 | 公开分发的二进制不得硬编码密钥 |
| 配置入口 | **复用左下角 ⚙️ 设置 Popover**，新增「LLM / Embedding 供应商…」菜单项 | 前端已有设置按钮，仅加菜单项 |
| 后端配置模型 | **后端零改动**，Electron 在 spawn 时把「当前生效」供应商解析为扁平 `LLM_*`/`EMBED_*` env | 多供应商是前端 + userData 的事，后端永远只见一个已解析供应商 |
| mac 架构 | **仅 arm64** | 覆盖当前 ~95% Mac；省一条 intel CI job |
| Windows 安装 | **NSIS `oneClick:false` + `allowToChangeInstallationDirectory:true`，perMachine** | 直接满足「选安装目录」诉求；装 Program Files、需提权 |

## 3. 运行时架构：侧车布局 + 进程生命周期

### 3.1 应用内布局（electron-builder `extraResources`）
PyInstaller 以 `onefolder` 冻结后端，产出 `MaestroBackend`（mac）/ `MaestroBackend.exe`（win）+ `_internal/` 依赖树，经 `extraResources` 复制进安装包：
- macOS：`Maestro.app/Contents/Resources/backend/`
- Windows：`<安装目录>/resources/backend/`

运行时 `main.cjs` 通过 `process.resourcesPath` 定位 `<resources>/backend/MaestroBackend(.exe)`。

### 3.2 端口握手（不写死 8000）
8000 可能被占用。Electron 启动时挑一个空闲 TCP 端口，经环境变量 `MAESTRO_BACKEND_PORT` 传给后端子进程；后端 `config.py` 读取该 env 并绑定 `127.0.0.1`（仅本机）。同时 preload 经 `electronAPI.backendBaseUrl` 暴露 `http://127.0.0.1:{port}`；`api/index.ts` 的 baseURL 优先取它，回退到现有 `VITE_API_BASE_URL`。动态端口对前端透明。

### 3.3 就绪握手 + 启动屏
`app.whenReady()` 后先 spawn 后端，轮询 `GET /health`（~15s 超时，200ms 间隔），期间显示无边框启动窗（"Maestro 正在准备…"）。就绪后创建主窗加载前端；超时则弹错误对话框并退出。

### 3.4 单实例 + 生命周期
- `app.requestSingleInstanceLock()`：第二次启动只聚焦已有窗口，避免重复拉起后端。
- macOS：`window-all-closed` 不退出（标准行为），后端随应用驻留；Cmd-Q 触发 `before-quit`。
- Windows/Linux：`window-all-closed` 退出。
- `before-quit` → 对子进程先 `SIGTERM`，2s 宽限后 `SIGKILL`，确保不留僵尸 uvicorn。

### 3.5 改动面
- `electron/main.cjs`：后端 spawn/就绪/关闭、单实例锁、启动窗（~+80 行）。
- `electron/preload.cjs`：暴露 `backendBaseUrl`（~+3 行）。
- `api/index.ts`：baseURL 优先读 `window.electronAPI?.backendBaseUrl`（~+5 行）。
- `maestro/.../config.py`：`port` 读 `MAESTRO_BACKEND_PORT`，绑定改 `127.0.0.1`（~+5 行）。

## 4. 数据目录与多供应商配置

### 4.1 运行时数据搬到 userData
后端经 `MAESTRO_DATA_DIR` 把会话/知识/向量库写到 `app.getPath('userData')`：
- macOS：`~/Library/Application Support/Maestro`
- Windows：`%APPDATA%\Maestro`

后端 `config.py`、`session_store.py`、chroma/skills 路径全部以该 env 为根（未设置时回退现状 `data/`，CLI/dev 不受影响）。升级重装时 userData 默认保留 → 会话、知识库、配置不丢；卸载不主动清 userData（NSIS 默认行为）。

### 4.2 配置入口（复用左下角设置按钮）
`Sidebar.tsx` 左下角已有 ⚙️ 设置按钮，点开 `Popover`，当前仅有「外观」分组。在 Popover 内新增「**模型**」分组 + 菜单项「**LLM / Embedding 供应商…**」，点击打开 Settings Modal（复用现有 Modal 原语）。Modal 分两栏：
- **LLM 供应商**：列表 + 「添加供应商」；每条含 `名称 / base_url / api_key / model`，可编辑、删除、设为当前生效。无生效项 → 降级模式。
- **Embedding 供应商**：同结构 + 设为当前生效。无生效项 → 嵌入路由层禁用（即现有 `EMBED_MODEL` 为空的行为）。

### 4.3 数据模型：`userData/providers.json`
```jsonc
{
  "llm": {
    "providers": [
      { "id": "p1", "name": "DeepSeek", "base_url": "https://api.deepseek.com", "api_key": "sk-…", "model": "deepseek-chat" }
    ],
    "active_id": "p1"
  },
  "embedding": {
    "providers": [
      { "id": "e1", "name": "OpenAI", "base_url": "https://api.openai.com/v1", "api_key": "sk-…", "model": "text-embedding-3-small" }
    ],
    "active_id": "e1"   // null/缺省 → 禁用嵌入
  }
}
```

### 4.4 后端 LLM/Embedding 读取零改动
后端仍只读扁平的 `LLM_*` / `EMBED_*` env（pydantic-settings 现状不变，直接从进程环境变量读取，**不经过任何 .env 文件**）。Electron 在 spawn 后端时，把「当前生效」的供应商解析成 `LLM_BASE_URL/LLM_API_KEY/LLM_MODEL` 与 `EMBED_BASE_URL/EMBED_API_KEY/EMBED_MODEL` 作为子进程环境变量注入。多供应商是纯前端 + userData 的事，后端永远只看到一个已解析的供应商。切换生效项 / 增删改 → 写 `providers.json` → 提示「应用并重启后端」→ 重建子进程 + 重新握手 + 前端 reload。

### 4.5 首运行
不做独立首运行弹窗：降级模式直接进应用，左下角给一次性提示「尚未配置 LLM 供应商，点左下角设置添加」。填好生效项即恢复完整能力。

### 4.6 密钥存储（v1 取舍）
v1 明文存于 `userData/providers.json`（仅当前 OS 用户可读）。后续用 Electron `safeStorage`（OS keychain 加密）逐条加密 `api_key`，列为推荐后续项，不进 v1。

### 4.7 改动面
- 后端 `config.py` 读 `MAESTRO_DATA_DIR`/`MAESTRO_BACKEND_PORT`、各数据路径以此为根（~20 行，**不碰** LLM/EMBED 读取——后者由 Electron 作进程环境变量注入，无需 env 文件）。
- 前端 Settings Modal + providers CRUD + `Sidebar.tsx` 菜单项（~250 行）。
- `main.cjs` spawn 时解析生效供应商注入 env、改配置后重启后端（~70 行）。

## 5. 构建流水线（PyInstaller + electron-builder + GitHub Actions）

### 5.1 新增后端入口（冻结用）
`maestro/src/maestro/sidecar_entry.py`（~30 行）：从 env 读 `MAESTRO_BACKEND_PORT`，`from maestro.main import app` 后 `uvicorn.run(app, host="127.0.0.1", port=port, workers=1, reload=False)`。stdout/stderr 由 Electron 重定向到 `userData/backend.log` 供排障。这是 PyInstaller 的 entrypoint（不用 `cli`，那是交互式）。

### 5.2 PyInstaller（onefolder）
spec `maestro/maestro_backend.spec`，关键项：
- `--onedir`（启动快、原生库好排查；不用 onefile）
- `--collect-all ortools`、`--collect-all chromadb`、`--collect-all onnxruntime`
- `--hidden-import` fastapi/uvicorn/pydantic 相关
- 产物名 `MaestroBackend`（mac）/ `MaestroBackend.exe`（win），输出到 `maestro/dist/backend/`
- mac/win 均 `--windowed`（无控制台窗）

`pyproject.toml` 加 `[project.optional-dependencies] packaging = ["pyinstaller>=6"]`。

### 5.3 electron-builder 配置改动（`frontend/package.json` 的 `build`）
新增 `extraResources` 把冻结产物复制进包：
```jsonc
"extraResources": [
  { "from": "../maestro/dist/backend", "to": "backend", "filter": ["**/*"] }
]
```
（不在 asar 内 → 原生 exe 直接收录。）`files` 维持 `dist/**`、`electron/**`。

### 5.4 GitHub Actions 矩阵（两条 job）
- `build-mac-arm64`（macos-14）→ `Maestro-{ver}-arm64.dmg`
- `build-win-x64`（windows-latest）→ `Maestro-Setup-{ver}.exe`

每条 job：装 Python 3.12 + Node → `uv pip install -e ".[dev,packaging]"` → 跑 PyInstaller → 跑 `smoke_backend`（见 §7）→ `npm ci` → `npm run electron:build` → 签名/公证（§6）→ upload-artifact。tag 推送时再跑一个 release job 把产物挂到 GitHub Release（无自动更新 → 分发即从 Release 下载）。

## 6. 签名 / 公证 + Windows 选安装目录

### 6.1 macOS：签名 + 公证（Apple Developer ID）
所需密钥（放 Actions secrets）：`MAC_CERT_P12`（base64）、`MAC_CERT_PASSWORD`、`APPLE_ID`、`APPLE_APP_SPECIFIC_PASSWORD`、`APPLE_TEAM_ID`。electron-builder 读 `CSC_LINK`/`CSC_KEY_PASSWORD` + `notarize.teamId` 自动签名并提交 notarytool、装订票据。

### 6.2 PyInstaller 产物的深签名（关键难点）
electron-builder 默认只签 Electron 壳，`extraResources` 里的后端 `MaestroBackend` + `_internal/*.dylib/*.so` 不会被签 → Gatekeeper 仍拦。故在 electron-builder 组装前加一步深签名：
```
codesign --deep --force --options runtime --sign "Developer ID Application: <name>" \
  maestro/dist/backend
```
配 `build/entitlements.mac.plist`（含 `com.apple.security.cs.disable-library-validation`，因第三方原生库非我方签名）。装包后 `codesign --verify --deep --strict` 验证一遍。

### 6.3 Windows：代码签名 + SmartScreen 现实
所需密钥：`WIN_CSC_LINK`（.pfx base64）、`WIN_CSC_KEY_PASSWORD`。electron-builder 用 `CSC_LINK`/`CSC_KEY_PASSWORD` 签 NSIS exe。
**诚实提示**：v1 用 OV 证书在 CI 内直接签，新应用仍会触发 SmartScreen「不识别」直到信誉累积；EV 证书可即时免拦但需硬件 token，CI 里要走远程签名服务（Azure Trusted Signing / SignPath）。EV 列为后续项，v1 用 OV。

### 6.4 Windows 选安装目录（核心诉求）
`package.json` 的 `build.win` 与新增 `build.nsis`：
```jsonc
"win": {
  "target": ["nsis"],
  "signingHashAlgorithms": ["sha256"]
},
"nsis": {
  "oneClick": false,                          // 标准向导，非一键安装
  "perMachine": true,                         // 装到 Program Files，需提权
  "allowToChangeInstallationDirectory": true, // ← 目录选择器（Browse 改路径）
  "allowElevation": true,
  "uninstallDisplayName": "Maestro"
}
```
`oneClick:false` + `allowToChangeInstallationDirectory:true` → 安装器出现「Destination Folder」步骤，用户可 Browse 改目录。`perMachine:true` 默认装 `C:\Program Files\Maestro`。后端运行时数据已在 §4 搬到 `%APPDATA%\Maestro`（用户可写），故安装目录本身只读无碍。

### 6.5 改动面
- `entitlements.mac.plist`（新文件，~10 行）。
- `package.json` 的 `win`/`nsis`/`mac.notarize`/`extraResources` 字段（~25 行）。
- CI 加深签名 + 验证 step（~15 行 YAML）。

## 7. 测试与验证

按目标驱动，每个目标给出可执行验证。

- **G1 — 冻结后端可独立启动**：脚本 `scripts/smoke_backend.{sh,ps1}` 直接跑冻结产物（`MAESTRO_BACKEND_PORT=9xxx`）→ `curl /health` 应 200 → 发一条降级 `/chat` 应正常返回。启动 <5s 且无 `ModuleNotFoundError`/`Library not loaded`。**在 CI 里 PyInstaller 之后、electron-builder 之前跑**，冻结构回归即时失败。最高性价比自动门。
- **G2 — 打包应用启动链路**（手动，每平台一台干净机器）：双击 → 启动屏 → 后端就绪 → 主窗加载 → 首屏可用；`process.resourcesPath/backend/` 存在冻结产物；日志落 `userData/backend.log`。
- **G3 — 供应商配置闭环**（手动）：降级态 → 加 LLM 供应商 → 后端重启握手 → 真实 LLM 对话成功；加 embedding 供应商 → 嵌入路由层启用；切换生效项触发重启。
- **G4 — 数据持久**（手动）：建会话/传知识 → 退出 → 重启 → 数据仍在 `userData`。
- **G5 — 干净退出**（手动）：退出后 Activity Monitor / 任务管理器无残留 `MaestroBackend`/`uvicorn`。
- **G6 — 签名/安装器**（手动）：mac `xcrun stapler validate Maestro.app` 通过、首运行无 Gatekeeper 拦截；win 安装向导出现 Destination Folder 可改目录、装到所选目录、开始菜单快捷方式正常、卸载器移除应用（保留 userData）。
- **G7 — CI 产出**：打 tag → 两条 job 全绿 → GitHub Release 挂 2 个产物。

**自动 vs 手动**：自动（CI 门）= G1 `smoke_backend` + 现有 `pytest`/`npm test`；手动（发版前清单，每平台干净机）= G2–G6。GUI 启动链路不强求自动化。

## 8. 风险

- **PyInstaller 原生库调参**：首次构建需磨合 `--collect-all` 列表；G1 `smoke_backend` 兜底，缺库即失败。
- **chromadb 运行时是否拉默认 onnx 模型**：后端用的是外部 `EMBED_*` 接口、chromadb 仅作向量库，理论上不需要；G1 验证，必要时加 `--collect-all onnxruntime` 并把模型缓存指向 `userData`。
- **Windows SmartScreen 信誉累积期**：OV 证书固有现象，非缺陷；EV/远程签名为后续项。
- **macOS 深签名遗漏**：若 `--deep` 仍漏签个别 `.dylib`，公证会失败；CI 的 `codesign --verify --deep --strict` + 公证步骤会暴露。
- **包体偏大**（~150–300MB）：可接受范围，后续可考虑压缩 `_internal` 或精简 chromadb 依赖。

## 9. 后续项（不在 v1）

- 自动更新（electron-updater + 后端版本同步）。
- `safeStorage` 加密 `api_key`。
- EV 证书 / 远程签名服务（Azure Trusted Signing / SignPath）即时免 SmartScreen。
- macOS x64 / Universal、Windows arm64。
- 包体瘦身。
