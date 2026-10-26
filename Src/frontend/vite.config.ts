import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: { host: '127.0.0.1', port: 5173, strictPort: true,
    proxy: { '/api': 'http://127.0.0.1:8000', '/livez': 'http://127.0.0.1:8000' } },
  test: { environment: 'node', include: ['tests/**/*.test.ts'] },
})
