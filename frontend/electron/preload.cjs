// Preload: runs in an isolated context with access to a safe subset of Electron.
// Exposes a tiny read-only bridge so the renderer can detect the desktop shell.
const { contextBridge } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  isElectron: true,
  platform: process.platform,
});
