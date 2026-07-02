import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: '127.0.0.1',
    proxy: {
      // Dev: forward /api/* to the FastAPI api-server (override with
      // VITE_API_TARGET). The backend strips the /api prefix in-process,
      // so the same client code works in the built single-container image.
      '/api': {
        target: process.env.VITE_API_TARGET ?? 'http://127.0.0.1:8012',
        changeOrigin: true,
      },
    },
  },
  build: {
    target: 'es2022',
    sourcemap: true,
  },
})
