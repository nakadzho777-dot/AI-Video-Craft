import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// ブラウザ単体プレビュー用（Electron を起動しない）。
// UI の見た目確認や、ブラウザでの開発に使う。
export default defineConfig({
  plugins: [react()],
  server: { port: 5174 },
})
