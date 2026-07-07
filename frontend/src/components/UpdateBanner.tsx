import { useEffect, useState } from 'react'

// 自動更新の状態を表示するバナー。
// Electron(パッケージ版)でのみ意味を持つ（ブラウザ/devでは何も出ない）。
export default function UpdateBanner() {
  const [status, setStatus] = useState<UpdateStatus | null>(null)

  useEffect(() => {
    const off = window.videocraft?.update?.onStatus((s) => setStatus(s))
    return () => off?.()
  }, [])

  if (!status) return null

  if (status.state === 'downloading') {
    return (
      <div className="banner update">
        ⬇️ 新しいバージョン{status.version ? ` v${status.version}` : ''}
        をダウンロード中… {status.percent ?? 0}%
      </div>
    )
  }

  if (status.state === 'downloaded') {
    return (
      <div className="banner update ready">
        <span>
          ✅ アップデート{status.version ? ` v${status.version}` : ''}
          の準備ができました。
        </span>
        <button
          className="btn primary sm update-btn"
          onClick={() => window.videocraft?.update?.install()}
        >
          再起動して更新
        </button>
      </div>
    )
  }

  return null
}
