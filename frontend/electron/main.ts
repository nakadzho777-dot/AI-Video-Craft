import {
  app,
  BrowserWindow,
  desktopCapturer,
  dialog,
  ipcMain,
  session,
  shell,
} from 'electron'
import { spawn } from 'node:child_process'
import crypto from 'node:crypto'
import { readFile, unlink, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import updaterPkg from 'electron-updater'
import ffmpegStatic from 'ffmpeg-static'

const { autoUpdater } = updaterPkg
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
      // ESM(.mjs) preload はサンドボックス下では読み込めない。
      // 信頼できる自アプリのみ読み込むため sandbox を無効化して preload を有効にする。
      sandbox: false,
    },
  })

  // ちらつき防止（描画準備後に表示）
  win.once('ready-to-show', () => {
    win.show()
    setupAutoUpdate(win)
  })

  // 外部リンク（Stripe決済・ヘルプ等）は既定ブラウザで開く。アプリ内遷移は禁止。
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:/.test(url)) shell.openExternal(url)
    return { action: 'deny' }
  })
  win.webContents.on('will-navigate', (e, url) => {
    const current = DEV_SERVER_URL ?? 'file://'
    if (!url.startsWith(current)) {
      e.preventDefault()
      if (/^https?:/.test(url)) shell.openExternal(url)
    }
  })

  if (DEV_SERVER_URL) {
    win.loadURL(DEV_SERVER_URL)
  } else {
    win.loadFile(path.join(__dirname, '../dist/index.html'))
  }
}

// --- 録画用の別ウィンドウ（AIVideoCraft自体を撮影するとき用）---
// 本体ウィンドウ（操作/警告オーバーレイ）と分けることで、AIの操作で本体の
// キャンセルが誘発されず、撮影対象を一意なタイトルで指定できる。
let recWin: BrowserWindow | null = null
const REC_WINDOW_TITLE = 'AI VideoCraft (録画用)'

ipcMain.handle('window:open-rec', () => {
  if (recWin && !recWin.isDestroyed()) {
    recWin.focus()
    return REC_WINDOW_TITLE
  }
  recWin = new BrowserWindow({
    width: 1180,
    height: 760,
    title: REC_WINDOW_TITLE,
    frame: false, // 本体と同じ見た目（カスタムタイトルバー）で撮影を綺麗に
    backgroundColor: '#08080d',
    show: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.mjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  })
  // ページ側の document.title で上書きされないよう固定（一意タイトル維持）
  recWin.on('page-title-updated', (e) => e.preventDefault())
  recWin.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:/.test(url)) shell.openExternal(url)
    return { action: 'deny' }
  })
  if (DEV_SERVER_URL) recWin.loadURL(DEV_SERVER_URL)
  else recWin.loadFile(path.join(__dirname, '../dist/index.html'))
  recWin.once('ready-to-show', () => recWin?.setTitle(REC_WINDOW_TITLE))
  recWin.on('closed', () => {
    recWin = null
  })
  return REC_WINDOW_TITLE
})

ipcMain.handle('window:close-rec', () => {
  if (recWin && !recWin.isDestroyed()) recWin.close()
  recWin = null
  return true
})

// --- 自動更新（electron-updater / GitHub Releases）---
let updateWired = false
function setupAutoUpdate(win: BrowserWindow) {
  // パッケージ済み（インストール版）でのみ動作。開発時は無効。
  if (!app.isPackaged) return

  const send = (status: Record<string, unknown>) =>
    win.webContents.send('update:status', status)

  if (!updateWired) {
    updateWired = true
    autoUpdater.autoDownload = true
    autoUpdater.on('checking-for-update', () => send({ state: 'checking' }))
    autoUpdater.on('update-available', (info) =>
      send({ state: 'available', version: info.version }),
    )
    autoUpdater.on('update-not-available', () => send({ state: 'latest' }))
    autoUpdater.on('download-progress', (p) =>
      send({ state: 'downloading', percent: Math.round(p.percent) }),
    )
    autoUpdater.on('update-downloaded', (info) =>
      send({ state: 'downloaded', version: info.version }),
    )
    autoUpdater.on('error', (e) =>
      send({ state: 'error', message: String(e?.message ?? e) }),
    )
  }
  autoUpdater.checkForUpdates().catch(() => {})
}

// 手動チェック / 再起動してインストール / バージョン取得
ipcMain.handle('update:check', () => {
  if (!app.isPackaged) return { state: 'dev' }
  return autoUpdater.checkForUpdates().catch((e) => ({
    state: 'error',
    message: String(e),
  }))
})
ipcMain.on('update:install', () => autoUpdater.quitAndInstall())
ipcMain.handle('app:version', () => app.getVersion())

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

// --- デバイスID（PC固有・userDataに永続化）---
ipcMain.handle('device:id', async () => {
  const file = path.join(app.getPath('userData'), 'device-id.txt')
  try {
    const id = (await readFile(file, 'utf8')).trim()
    if (id) return id
  } catch {
    /* 未作成 */
  }
  const id = crypto.randomUUID()
  await writeFile(file, id, 'utf8')
  return id
})

// --- オフライン ライセンス検証 ---
ipcMain.handle('license:verify', (_e, token: string) => verifyLicenseToken(token))

// --- 外部で URL を開く（Stripe決済 / メール送信など）---
ipcMain.handle('shell:open-external', (_e, url: string) => {
  if (typeof url === 'string' && /^(https?|mailto):/.test(url)) {
    shell.openExternal(url)
    return true
  }
  return false
})

// --- ローカルファイルを既定アプリで開く（生成した動画の再生）---
ipcMain.handle('shell:open-path', async (_e, filePath: string) => {
  if (typeof filePath !== 'string' || !filePath) return false
  const err = await shell.openPath(filePath)
  return err === '' // 空文字なら成功
})

// --- エクスプローラーでファイルを表示（フォルダを開いて選択）---
ipcMain.handle('shell:show-item', (_e, filePath: string) => {
  if (typeof filePath !== 'string' || !filePath) return false
  shell.showItemInFolder(filePath)
  return true
})

// 同梱 FFmpeg（asar 内は unpacked を参照）で WebM を MP4(H.264/AAC) に変換
function convertToMp4(webmPath: string, mp4Path: string): Promise<void> {
  const bin = String(ffmpegStatic).replace('app.asar', 'app.asar.unpacked')
  return new Promise((resolve, reject) => {
    const p = spawn(bin, [
      '-y', '-i', webmPath,
      '-c:v', 'libx264', '-preset', 'veryfast', '-pix_fmt', 'yuv420p',
      '-c:a', 'aac', '-movflags', '+faststart',
      mp4Path,
    ])
    let err = ''
    p.stderr.on('data', (d) => (err += d.toString()))
    p.on('error', reject)
    p.on('close', (code) =>
      code === 0 ? resolve() : reject(new Error(err.slice(-400) || 'ffmpeg failed')),
    )
  })
}

// --- 自動画面録画: 録画データを MP4 に変換して保存 ---
ipcMain.handle(
  'recording:save',
  async (e, data: ArrayBuffer, defaultName: string) => {
    const win = BrowserWindow.fromWebContents(e.sender)
    const { canceled, filePath } = await dialog.showSaveDialog(win!, {
      title: '録画を保存',
      defaultPath: defaultName || 'recording.mp4',
      filters: [
        { name: 'MP4 動画', extensions: ['mp4'] },
        { name: 'WebM 動画', extensions: ['webm'] },
      ],
    })
    if (canceled || !filePath) return null

    const buf = Buffer.from(data)
    // MP4 指定なら一時WebMを経由して変換、WebM指定ならそのまま保存
    if (!filePath.toLowerCase().endsWith('.mp4')) {
      await writeFile(filePath, buf)
      return filePath
    }
    const tmp = path.join(os.tmpdir(), `aivc_rec_${Date.now()}.webm`)
    await writeFile(tmp, buf)
    try {
      await convertToMp4(tmp, filePath)
      return filePath
    } catch {
      // 変換失敗時は WebM で保存（データは失わない）
      const fallback = filePath.replace(/\.mp4$/i, '') + '.webm'
      await writeFile(fallback, buf)
      return fallback
    } finally {
      unlink(tmp).catch(() => {})
    }
  },
)

// --- 素材ファイル選択ダイアログ（音声/画像）---
ipcMain.handle('dialog:open-file', async (e, kind: string) => {
  const win = BrowserWindow.fromWebContents(e.sender)
  const filters =
    kind === 'audio'
      ? [{ name: '音声', extensions: ['mp3', 'wav', 'm4a', 'aac', 'ogg', 'flac'] }]
      : kind === 'image'
        ? [{ name: '画像', extensions: ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'] }]
        : [{ name: 'すべてのファイル', extensions: ['*'] }]
  const r = await dialog.showOpenDialog(win!, {
    title: '素材を読み込む',
    properties: ['openFile'],
    filters,
  })
  if (r.canceled || r.filePaths.length === 0) return null
  return r.filePaths[0]
})

// --- フォルダ選択ダイアログ（ゆっくりボイスのインポート場所など）---
ipcMain.handle('dialog:open-folder', async (e) => {
  const win = BrowserWindow.fromWebContents(e.sender)
  const r = await dialog.showOpenDialog(win!, {
    title: 'フォルダを選ぶ',
    properties: ['openDirectory'],
  })
  if (r.canceled || r.filePaths.length === 0) return null
  return r.filePaths[0]
})

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

// --- 録画対象の選択（画面全体 or 特定ウィンドウ）---
// レンダラが選んだソースIDを覚えておき、getDisplayMedia 時にそれを返す。
let preferredSourceId: string | null = null

// 録画できる対象（画面＋ウィンドウ）の一覧を返す
// ※ Windows では thumbnailSize が 0x0 だとウィンドウ一覧が空で返ることがあるため、
//   小さめの非0サイズを指定する（名前つきで確実に列挙させる）。
ipcMain.handle('capture:list', async () => {
  try {
    const sources = await desktopCapturer.getSources({
      types: ['screen', 'window'],
      thumbnailSize: { width: 150, height: 150 },
      fetchWindowIcons: false,
    })
    return sources
      // 空名や自分の録画用ウィンドウ等の無題は除外しつつ返す
      .filter((s) => s.name && s.name.trim())
      .map((s) => ({
        id: s.id,
        name: s.name,
        kind: s.id.startsWith('screen') ? 'screen' : 'window',
      }))
  } catch {
    return []
  }
})

// 録画対象を選ぶ（null で画面全体に戻す）
ipcMain.handle('capture:set-source', (_e, id: string | null) => {
  preferredSourceId = id || null
  return true
})

app.whenReady().then(() => {
  // 録音のためマイク等のメディア権限を許可（信頼できる自アプリのみ読み込む前提）
  session.defaultSession.setPermissionRequestHandler((_wc, _permission, callback) => {
    callback(true)
  })

  // 画面録画: 選択中のソース（無ければプライマリ画面）を返し、システム音声(loopback)も提供。
  // 実際に音声を含めるかはレンダラの getDisplayMedia({audio}) 側で制御する。
  session.defaultSession.setDisplayMediaRequestHandler((_request, callback) => {
    desktopCapturer
      .getSources({ types: ['screen', 'window'] })
      .then((sources) => {
        const picked =
          (preferredSourceId &&
            sources.find((s) => s.id === preferredSourceId)) ||
          sources.find((s) => s.id.startsWith('screen')) ||
          sources[0]
        callback({ video: picked, audio: 'loopback' })
      })
      .catch(() => callback({}))
  })

  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})
