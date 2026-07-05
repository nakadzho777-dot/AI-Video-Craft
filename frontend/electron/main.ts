import { app, BrowserWindow, dialog, ipcMain } from 'electron'
import crypto from 'node:crypto'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// ライセンス検証用の公開鍵（ビルド時に AIVC_LICENSE_PUBLIC_KEY から埋め込み）
const LICENSE_PUBLIC_KEY = __LICENSE_PUBLIC_KEY__

// Ed25519 SPKI DER ヘッダ（12バイト固定）
const SPKI_ED25519_PREFIX = Buffer.from('302a300506032b6570032100', 'hex')

function b64urlToBuf(s: string): Buffer {
  const pad = '='.repeat((4 - (s.length % 4)) % 4)
  return Buffer.from(s.replace(/-/g, '+').replace(/_/g, '/') + pad, 'base64')
}

// オフラインでの署名ライセンス検証（バックエンド不要）
function verifyLicenseToken(token: string): {
  valid: boolean
  payload: any | null
} {
  try {
    const parts = String(token).trim().split('.')
    if (parts.length !== 3 || parts[0] !== 'AIVC1') {
      return { valid: false, payload: null }
    }
    const [, bodyB64, sigB64] = parts
    const der = Buffer.concat([SPKI_ED25519_PREFIX, b64urlToBuf(LICENSE_PUBLIC_KEY)])
    const pub = crypto.createPublicKey({ key: der, format: 'der', type: 'spki' })
    const ok = crypto.verify(
      null,
      Buffer.from(`AIVC1.${bodyB64}`, 'ascii'),
      pub,
      b64urlToBuf(sigB64),
    )
    if (!ok) return { valid: false, payload: null }
    const payload = JSON.parse(b64urlToBuf(bodyB64).toString('utf8'))
    // 期限チェック（サブスク）
    if (payload.exp && payload.exp * 1000 < Date.now()) {
      return { valid: false, payload }
    }
    return { valid: true, payload }
  } catch {
    return { valid: false, payload: null }
  }
}

// vite-plugin-electron が注入する開発サーバ URL
const DEV_SERVER_URL = process.env.VITE_DEV_SERVER_URL

function createWindow() {
  const win = new BrowserWindow({
    width: 1320,
    height: 860,
    minWidth: 980,
    minHeight: 640,
    title: 'AI VideoCraft',
    // カスタムタイトルバーのためフレームレス化
    frame: false,
    backgroundColor: '#08080d',
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.mjs'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  // ちらつき防止（描画準備後に表示）
  win.once('ready-to-show', () => win.show())

  if (DEV_SERVER_URL) {
    win.loadURL(DEV_SERVER_URL)
  } else {
    win.loadFile(path.join(__dirname, '../dist/index.html'))
  }
}

// --- カスタムタイトルバーのウィンドウ操作 ---
ipcMain.on('window:minimize', (e) => {
  BrowserWindow.fromWebContents(e.sender)?.minimize()
})
ipcMain.on('window:toggle-maximize', (e) => {
  const w = BrowserWindow.fromWebContents(e.sender)
  if (!w) return
  w.isMaximized() ? w.unmaximize() : w.maximize()
})
ipcMain.on('window:close', (e) => {
  BrowserWindow.fromWebContents(e.sender)?.close()
})

// --- オフライン ライセンス検証 ---
ipcMain.handle('license:verify', (_e, token: string) => verifyLicenseToken(token))

// --- 動画ファイル選択ダイアログ ---
ipcMain.handle('dialog:open-video', async (e) => {
  const win = BrowserWindow.fromWebContents(e.sender)
  const result = await dialog.showOpenDialog(win!, {
    title: '動画を読み込む',
    properties: ['openFile'],
    filters: [
      { name: '動画', extensions: ['mp4', 'mov', 'mkv', 'webm', 'avi', 'm4v'] },
      { name: 'すべてのファイル', extensions: ['*'] },
    ],
  })
  if (result.canceled || result.filePaths.length === 0) return null
  return result.filePaths[0]
})

app.whenReady().then(() => {
  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})
