import { defineConfig, loadEnv } from 'vite'
import path from 'path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  // Strip /api suffix to get the bare backend origin for the dev proxy
  const apiTarget = (env.VITE_API_TARGET ?? 'https://abcdhtechnologiesbackend-production-bc91.up.railway.app/api')
    .replace(/\/api\/?$/, '')

  return {
  plugins: [
    react(),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  assetsInclude: ['**/*.svg', '**/*.csv'],
  // In dev: override VITE_API_TARGET to /api so requests go through the proxy (no CORS)
  // In production: VITE_API_TARGET from .env (full URL) is used as-is
  define: mode === 'development'
    ? { 'import.meta.env.VITE_API_TARGET': JSON.stringify('/api') }
    : {},
  server: {
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
        secure: true,
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
}
})
