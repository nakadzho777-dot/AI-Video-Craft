/// <reference types="vite/client" />

// ビルド時に vite.config.ts の define で注入される定数
declare const __BACKEND_URL__: string
declare const __LICENSE_PUBLIC_KEY__: string

interface Window {
  videocraft?: {
    backendBaseUrl: string
    versions: { node: string; chrome: string; electron: string }
    window: {
      minimize: () => void
      toggleMaximize: () => void
      close: () => void
    }
    openVideoDialog: () => Promise<string | null>
    verifyLicense: (
      token: string,
    ) => Promise<{ valid: boolean; payload: any | null }>
  }
}
