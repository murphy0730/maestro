// Preload: runs in an isolated context with access to a safe subset of Electron.
// Exposes a tiny read-only bridge so the renderer can detect the desktop shell,
// plus the providers IPC (read/write providers.json, backend-restart notifications).
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  isElectron: true,
  platform: process.platform,
  providers: {
    get: () => ipcRenderer.invoke('providers:get'),
    save: (config) => ipcRenderer.invoke('providers:save', config),
  },
  onBackendReconnecting: (cb) => {
    const listener = () => cb();
    ipcRenderer.on('backend:reconnecting', listener);
    return () => ipcRenderer.removeListener('backend:reconnecting', listener);
  },
});
