import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': { target: 'http://localhost:8080', changeOrigin: true } },
  },
  build: {
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      output: {
        // Keep React and everything that imports it in one chunk; splitting recharts from
        // react caused the charts chunk to evaluate before React was defined in production.
        manualChunks(id) {
          if (id.includes('node_modules/maplibre-gl')) return 'maplibre'
          if (id.includes('node_modules')) return 'vendor'
        },
      },
    },
  },
})
