// vite.config.ts
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  build: {
    // beim „npm run build“ landet das Frontend dann in backend/static
    outDir: '../static',
    emptyOutDir: true,
    sourcemap: true,
  },
  server: {
    port: 3010,
    // alle API-Aufrufe auf Port 50505 forwarden
    proxy: {
      '/ask': {
        target: 'http://localhost:50505',
        changeOrigin: true,
      },
      '/chat': {
        target: 'http://localhost:50505',
        changeOrigin: true,
      },
      '/auth': {
        target: 'http://localhost:50505',
        changeOrigin: true,
      },
      '/conversation': {
        target: 'http://localhost:50505',
        changeOrigin: true,
      },
      '/history': {
        target: 'http://localhost:50505',
        changeOrigin: true,
      },
      '/admin': {
        target: 'http://localhost:50505',
        changeOrigin: true,
      },
      '/transcribe': {
        target: 'http://localhost:50505',
        changeOrigin: true,
      },
      '/frontend_settings': {
        target: 'http://localhost:50505',
        changeOrigin: true,
      },

    }
  }
})
