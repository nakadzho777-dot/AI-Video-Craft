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
    getDeviceId: () => Promise<string>
    openExternal: (url: string) => Promise<boolean>
    openPath: (filePath: string) => Promise<boolean>
    showItemInFolder: (filePath: string) => Promise<boolean>
    openVideoDialog: () => Promise<string | null>
    openFileDialog: (kind: string) => Promise<string | null>
    openFolderDialog: () => Promise<string | null>
    openRecWindow: () => Promise<string>
    closeRecWindow: () => Promise<boolean>
    screenRecord: {
      save: (data: ArrayBuffer, name: string) => Promise<string | null>
      listSources: () => Promise<
        { id: string; name: string; kind: 'screen' | 'window' }[]
      >
      setSource: (id: string | null) => Promise<boolean>
    }
    verifyLicense: (
      token: string,
    ) => Promise<{ valid: boolean; payload: any | null }>
    appVersion: () => Promise<string>
    update: {
      onStatus: (cb: (s: UpdateStatus) => void) => () => void
      check: () => Promise<UpdateStatus>
      install: () => void
    }
  }
}

interface UpdateStatus {
  state:
    | 'checking'
    | 'available'
    | 'latest'
    | 'downloading'
    | 'downloaded'
    | 'error'
    | 'dev'
  version?: string
  percent?: number
  message?: string
}
