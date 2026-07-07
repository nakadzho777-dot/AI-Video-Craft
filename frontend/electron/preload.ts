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
  // PC固有のデバイスID
  getDeviceId: (): Promise<string> => ipcRenderer.invoke('device:id'),
  // 外部ブラウザで URL を開く（Stripe決済など）
  openExternal: (url: string): Promise<boolean> =>
    ipcRenderer.invoke('shell:open-external', url),
  // ローカルファイルを既定アプリで開く（生成した動画の再生）
  openPath: (filePath: string): Promise<boolean> =>
    ipcRenderer.invoke('shell:open-path', filePath),
  // エクスプローラーでファイルを表示
  showItemInFolder: (filePath: string): Promise<boolean> =>
    ipcRenderer.invoke('shell:show-item', filePath),
  // 動画ファイル選択ダイアログ（キャンセル時 null）
  openVideoDialog: (): Promise<string | null> =>
    ipcRenderer.invoke('dialog:open-video'),
  // 素材ファイル選択（kind: 'audio' | 'image'）
  openFileDialog: (kind: string): Promise<string | null> =>
    ipcRenderer.invoke('dialog:open-file', kind),
  // フォルダ選択（ゆっくりボイスのインポート場所など）
  openFolderDialog: (): Promise<string | null> =>
    ipcRenderer.invoke('dialog:open-folder'),
  // 録画用の別ウィンドウ（AIVideoCraft自体を撮影する用）。タイトルを返す
  openRecWindow: (): Promise<string> => ipcRenderer.invoke('window:open-rec'),
  closeRecWindow: (): Promise<boolean> => ipcRenderer.invoke('window:close-rec'),
  // 自動画面録画: 録画データを保存（キャンセル時 null）
  screenRecord: {
    save: (data: ArrayBuffer, name: string): Promise<string | null> =>
      ipcRenderer.invoke('recording:save', data, name),
    // 録画できる対象（画面＋ウィンドウ）一覧
    listSources: (): Promise<
      { id: string; name: string; kind: 'screen' | 'window' }[]
    > => ipcRenderer.invoke('capture:list'),
    // 録画対象を選ぶ（null で画面全体）
    setSource: (id: string | null): Promise<boolean> =>
      ipcRenderer.invoke('capture:set-source', id),
  },
  // オフラインでのライセンス検証（バックエンド不要）
  verifyLicense: (
    token: string,
  ): Promise<{ valid: boolean; payload: any | null }> =>
    ipcRenderer.invoke('license:verify', token),
  // 自動更新
  appVersion: (): Promise<string> => ipcRenderer.invoke('app:version'),
  update: {
    onStatus: (cb: (s: any) => void) => {
      const listener = (_e: unknown, s: any) => cb(s)
      ipcRenderer.on('update:status', listener)
      return () => ipcRenderer.removeListener('update:status', listener)
    },
    check: (): Promise<any> => ipcRenderer.invoke('update:check'),
    install: () => ipcRenderer.send('update:install'),
  },
})
