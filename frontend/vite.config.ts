import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// In development the API runs on the docker-compose host port (default 18010).
const apiTarget = process.env.HERBAGUARD_API_URL ?? 'http://127.0.0.1:18010'

// The proxy must outlast the browser's wait for /ai/ask (src/lib/ask.ts: 2 x 240 s backend
// attempts + 60 s margin = 540 s), otherwise it would cut a request the backend is still serving.
const proxyTimeoutMs = Number(process.env.HERBAGUARD_PROXY_TIMEOUT_MS ?? 600_000)

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: Number(process.env.HERBAGUARD_WEB_PORT ?? 5173),
    strictPort: Boolean(process.env.HERBAGUARD_WEB_PORT),
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
        timeout: proxyTimeoutMs, // incoming socket
        proxyTimeout: proxyTimeoutMs, // wait for the API's response
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
})
