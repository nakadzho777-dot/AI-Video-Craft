import { contextBridge, ipcRenderer } from 'electron'

// レンダラへ安全に公開する API。
// backendBaseUrl はビルド時に AIVC_BACKEND_URL から埋め込まれる（既定は localhost）。
contextBridge.exposeInMainWorld('videocraft', {
  backendBaseUrl: __BACKEND_URL__,
  versions: {
    node: process.versions.node,
    chrome: process.versions.chrome,
    electron: process.versions.electron,
  },
  // カスタムタイトルバーからのウィンドウ操作
  window: {
    minimize: () => ipcRenderer.send('window:minimize'),
    toggleMaximize: () => ipcRenderer.send('window:toggle-maximize'),
    close: () => ipcRenderer.send('window:close'),
  },
  // 動画ファイル選択ダイアログ（キャンセル時 null）
  openVideoDialog: (): Promise<string | null> =>
    ipcRenderer.invoke('dialog:open-video'),
  // オフラインでのライセンス検証（バックエンド不要）
  verifyLicense: (
    token: string,
  ): Promise<{ valid: boolean; payload: any | null }> =>
    ipcRenderer.invoke('license:verify', token),
})
