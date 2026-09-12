import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // In development Vite proxies /api to the FastAPI process, so the browser
    // only ever talks to one origin and CORS never comes up. In production the
    // same job is done by whatever web server serves these static files.
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
  build: { outDir: 'dist', sourcemap: false },
})
