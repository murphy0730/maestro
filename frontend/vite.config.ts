import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath, URL } from 'node:url';

export default defineConfig({
  // Relative base so built assets load under Electron's file:// as well as the web.
  base: './',
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    // Pin to IPv4 loopback so `wait-on` (electron:dev) and Electron connect
    // deterministically; Vite's default `localhost` may bind IPv6-only.
    host: '127.0.0.1',
    port: 5173,
    // Dev proxy: strip the /api/v1 prefix and forward to the FastAPI backend.
    // Keeps requests same-origin (no CORS) and preserves SSE streaming.
    proxy: {
      '/api/v1': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/v1/, ''),
      },
    },
  },
});
