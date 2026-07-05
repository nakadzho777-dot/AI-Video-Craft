import { useState } from 'react'

// クリップボードへコピーするボタン。投稿テキストの貼り付け用。
export default function CopyButton({
  text,
  label = 'コピー',
}: {
  text: string
  label?: string
}) {
  const [copied, setCopied] = useState(false)

  async function copy() {
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      // フォールバック（古い環境）
      const ta = document.createElement('textarea')
      ta.value = text
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
    }
    setCopied(true)
    setTimeout(() => setCopied(false), 1600)
  }

  return (
    <button className={`copy-btn ${copied ? 'copied' : ''}`} onClick={copy}>
      {copied ? '✓ コピー済み' : `⧉ ${label}`}
    </button>
  )
}
