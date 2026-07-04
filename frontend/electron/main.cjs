// Electron main process. Runs the same React app as a cross-platform desktop
// shell. In dev it loads the Vite dev server (so HMR + the /api/v1 proxy work);
// when packaged it loads the built files from ../dist over file://.
const { app, BrowserWindow, nativeTheme, shell } = require('electron');
const path = require('node:path');

const isDev = !app.isPackaged;
const isMac = process.platform === 'darwin';
const DEV_URL = process.env.ELECTRON_RENDERER_URL || 'http://127.0.0.1:5173';

function createWindow() {
  const win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 680,
    // Anti-flash paint before the renderer loads. Best effort: follows the OS
    // appearance (the renderer's own persisted theme is applied first frame by
    // the inline script in index.html). Values = --bg-base light/dark tokens.
    backgroundColor: nativeTheme.shouldUseDarkColors ? '#1a1a1e' : '#f5f5f7',
    title: 'Maestro',
    autoHideMenuBar: true,
    // macOS: hide the titlebar, keep inset traffic lights; the renderer draws
    // a dedicated 44px drag strip (Layout.tsx) at the top and the lights are
    // vertically centered in it. App chrome starts below the strip.
    ...(isMac && {
      titleBarStyle: 'hiddenInset',
      trafficLightPosition: { x: 18, y: 16 },
    }),
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  // Open external (http/https) links in the OS browser, never inside the shell.
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('http')) {
      shell.openExternal(url);
      return { action: 'deny' };
    }
    return { action: 'allow' };
  });

  if (isDev) {
    win.loadURL(DEV_URL);
    win.webContents.openDevTools({ mode: 'detach' });
  } else {
    win.loadFile(path.join(__dirname, '..', 'dist', 'index.html'));
  }
}

app.whenReady().then(() => {
  createWindow();
  // macOS: re-create a window when the dock icon is clicked and none are open.
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

// Quit when all windows are closed, except on macOS (standard platform behavior).
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
