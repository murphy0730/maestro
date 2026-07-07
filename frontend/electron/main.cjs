// frontend/electron/main.cjs
// Electron main process. Runs the same React app as a cross-platform desktop
// shell AND lifecycle-manages the Python backend as a child process (sidecar).
//
// Modes (see Global Constraints):
//   - packaged            : load dist + spawn frozen MaestroBackend
//   - preview (MAESTRO_SIDECAR=1): load dist + spawn venv python -m sidecar_entry
//   - dev (electron:dev)  : load Vite DEV_URL, NO spawn (backend via ./restart.sh)
const { app, BrowserWindow, nativeTheme, shell, dialog, ipcMain } = require('electron');
const path = require('node:path');
const fs = require('node:fs');
const http = require('node:http');
const { spawn, execSync } = require('node:child_process');
const bc = require('./backend-config.cjs');

const isMac = process.platform === 'darwin';
const isSidecar = app.isPackaged || process.env.MAESTRO_SIDECAR === '1';
const isDevServer = !app.isPackaged && !isSidecar;
const DEV_URL = process.env.ELECTRON_RENDERER_URL || 'http://127.0.0.1:5173';

let backend = null; // { child, port }
let splash = null;
let quitting = false;

function userDataDir() {
  return app.getPath('userData');
}
function backendLogPath() {
  return path.join(userDataDir(), 'backend.log');
}

function backendBinary() {
  if (app.isPackaged) {
    const exe = process.platform === 'win32' ? 'MaestroBackend.exe' : 'MaestroBackend';
    return path.join(process.resourcesPath, 'backend', exe);
  }
  // preview: 仓库 venv 的 python 跑 sidecar_entry
  return process.platform === 'win32'
    ? path.join(__dirname, '..', '..', 'maestro', '.venv', 'Scripts', 'python.exe')
    : path.join(__dirname, '..', '..', 'maestro', '.venv', 'bin', 'python');
}

function backendArgs() {
  return app.isPackaged ? [] : ['-m', 'maestro.sidecar_entry'];
}

function buildBackendEnv(port) {
  const env = {
    ...process.env,
    MAESTRO_BACKEND_PORT: String(port),
    MAESTRO_DATA_DIR: userDataDir(),
  };
  // 把「当前生效」供应商解析为扁平 LLM_*/EMBED_* (后端零改动)
  const cfg = bc.readProviders(userDataDir());
  Object.assign(env, bc.resolveActiveEnv(cfg));
  return env;
}

function waitForHealth(port, timeoutMs) {
  return new Promise((resolve, reject) => {
    const deadline = Date.now() + timeoutMs;
    const tick = () => {
      const req = http.get(`http://127.0.0.1:${port}/health`, (res) => {
        res.resume();
        if (res.statusCode === 200) return resolve();
        if (Date.now() > deadline) return reject(new Error(`/health non-200 on ${port}`));
        setTimeout(tick, 200);
      });
      req.on('error', () => {
        if (Date.now() > deadline) return reject(new Error(`/health timeout on ${port}`));
        setTimeout(tick, 200);
      });
      req.setTimeout(500, () => req.destroy());
    };
    tick();
  });
}

async function startBackend() {
  fs.mkdirSync(userDataDir(), { recursive: true });
  const port = await bc.pickFreePort();
  const logStream = fs.createWriteStream(backendLogPath(), { flags: 'a' });
  const child = spawn(backendBinary(), backendArgs(), {
    env: buildBackendEnv(port),
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true, // Windows: hide the console-subsystem backend window (console=True exe)
  });
  child.stdout.pipe(logStream);
  child.stderr.pipe(logStream);
  child.on('exit', () => {
    if (backend && backend.child === child && !quitting) {
      // 非预期退出：主流程会在 health 超时或后续操作中暴露
    }
  });
  backend = { child, port };
  await waitForHealth(port, 60000);
  return backend;
}

function killChild(child) {
  try {
    if (process.platform === 'win32') execSync(`taskkill /pid ${child.pid} /T /F`);
    else child.kill('SIGTERM');
  } catch { /* best effort */ }
}

function stopBackendAsync() {
  return new Promise((resolve) => {
    if (!backend) return resolve();
    const { child } = backend;
    backend = null;
    let done = false;
    const finish = () => { if (!done) { done = true; resolve(); } };
    child.once('exit', finish);
    killChild(child);
    // 2s 宽限后 SIGKILL
    setTimeout(() => {
      if (!done) {
        try { if (process.platform !== 'win32') child.kill('SIGKILL'); } catch { /* noop */ }
        finish();
      }
    }, 2000);
  });
}

function createSplash() {
  splash = new BrowserWindow({
    width: 360, height: 220, frame: false, resizable: false,
    transparent: false, backgroundColor: '#f5f5f7', show: true,
    webPreferences: { contextIsolation: true },
  });
  splash.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(
    `<body style="margin:0;font-family:-apple-system,system-ui,sans-serif;background:#f5f5f7;height:100vh;display:flex;align-items:center;justify-content:center;color:#1a1a1e;font-size:14px;">Maestro 正在准备…</body>`
  ));
}

function createWindow(port) {
  const win = new BrowserWindow({
    width: 1440, height: 900, minWidth: 1024, minHeight: 680,
    backgroundColor: nativeTheme.shouldUseDarkColors ? '#1a1a1e' : '#f5f5f7',
    title: 'Maestro', autoHideMenuBar: true,
    ...(isMac && { titleBarStyle: 'hiddenInset', trafficLightPosition: { x: 18, y: 16 } }),
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  win.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('http')) { shell.openExternal(url); return { action: 'deny' }; }
    return { action: 'allow' };
  });

  if (isDevServer) {
    win.loadURL(DEV_URL);
    win.webContents.openDevTools({ mode: 'detach' });
  } else {
    win.loadFile(path.join(__dirname, '..', 'dist', 'index.html'), { query: { bp: String(port) } });
  }
}

// 供应商配置 IPC：读写 providers.json，保存后按新 env 重启后端 (Task 6 接线前端)
ipcMain.handle('providers:get', () => bc.readProviders(userDataDir()));

ipcMain.handle('providers:save', async (_e, config) => {
  bc.writeProviders(userDataDir(), config);
  await restartBackend();
  return { ok: true };
});

async function restartBackend() {
  for (const w of BrowserWindow.getAllWindows()) w.webContents.send('backend:reconnecting');
  await stopBackendAsync();
  await startBackend();
  for (const w of BrowserWindow.getAllWindows()) {
    w.loadFile(path.join(__dirname, '..', 'dist', 'index.html'), {
      query: { bp: String(backend.port) },
    });
  }
}

// 单实例锁：第二次启动只聚焦已有窗口，避免重复拉起后端
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    const wins = BrowserWindow.getAllWindows();
    if (wins.length) { if (wins[0].isMinimized()) wins[0].restore(); wins[0].focus(); }
  });

  app.whenReady().then(async () => {
    if (isSidecar) {
      createSplash();
      try {
        await startBackend();
      } catch (e) {
        splash?.destroy();
        dialog.showErrorBox('Maestro 启动失败', `后端未就绪: ${e.message}\n日志: ${backendLogPath()}`);
        app.quit();
        return;
      }
      splash?.destroy();
    }
    createWindow(backend?.port);
    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) createWindow(backend?.port);
    });
  });
}

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

// 优雅退出：SIGTERM → 2s → SIGKILL（见 stopBackendAsync）
app.on('before-quit', (e) => {
  if (quitting || !backend) return;
  e.preventDefault();
  quitting = true;
  stopBackendAsync().then(() => app.exit(0));
});
