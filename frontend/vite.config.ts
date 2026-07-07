import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import electron from 'vite-plugin-electron'
import renderer from 'vite-plugin-electron-renderer'

// Electron のメイン / preload をビルドしつつ Vite で React をホストする。
// 接続先URLとライセンス公開鍵は「ビルド時」に環境変数から埋め込む:
//   AIVC_BACKEND_URL         例) https://api.example.com
//   AIVC_LICENSE_PUBLIC_KEY  本番の公開鍵（未指定なら同梱DEV鍵）
export default defineConfig(({ mode }) => {
  const fileEnv = loadEnv(mode, process.cwd(), '')
  const pick = (k: string, def: string) =>
    process.env[k] || fileEnv[k] || def

  const BACKEND_URL = pick('AIVC_BACKEND_URL', 'http://localhost:8756')
  const LICENSE_PUBLIC_KEY = pick(
    'AIVC_LICENSE_PUBLIC_KEY',
    '493hT-FNwLPTA7008x5C-WfEbkbjKCoG-sn8sg4BRKI',
  )

  // 埋め込む定数。renderer だけでなく electron main/preload のビルドにも渡す。
  const injected = {
    __BACKEND_URL__: JSON.stringify(BACKEND_URL),
    __LICENSE_PUBLIC_KEY__: JSON.stringify(LICENSE_PUBLIC_KEY),
  }

  return {
    define: injected,
    plugins: [
      react(),
      electron([
        {
          // メインプロセス
          entry: 'electron/main.ts',
          vite: {
            define: injected,
            build: {
              // electron-updater / ffmpeg-static は実行時読み込み（バンドルしない）
              rollupOptions: { external: ['electron-updater', 'ffmpeg-static'] },
            },
          },
        },
        {
          // preload（コンテキスト分離ブリッジ）
          // Electron の ESM preload は .mjs 拡張子が必須のため明示的に出力名を指定
          entry: 'electron/preload.ts',
          onstart(args) {
            args.reload()
          },
          vite: {
            define: injected,
            build: {
              rollupOptions: {
                output: { entryFileNames: '[name].mjs' },
              },
            },
          },
        },
      ]),
      renderer(),
    ],
    server: {
      port: 5173,
    },
  }
})
