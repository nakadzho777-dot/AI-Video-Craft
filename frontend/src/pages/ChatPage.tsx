import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { ChatTurn, ProviderInfo } from '../types'

export default function ChatPage() {
  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [provider, setProvider] = useState<string>('')
  const [models, setModels] = useState<string[]>([])
  const [model, setModel] = useState<string>('')
  const [messages, setMessages] = useState<ChatTurn[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.listProviders().then((ps) => {
      setProviders(ps)
      const first = ps.find((p) => p.configured) ?? ps[0]
      if (first) setProvider(first.id)
    })
  }, [])

  useEffect(() => {
    if (!provider) return
    setModel('')
    api
      .listModels(provider)
      .then((ms) => {
        setModels(ms)
        setModel(ms[0] ?? '')
      })
      .catch(() => setModels([]))
  }, [provider])

  async function send() {
    if (!input.trim() || busy) return
    const next = [...messages, { role: 'user' as const, content: input.trim() }]
    setMessages(next)
    setInput('')
    setBusy(true)
    setError(null)
    try {
      const res = await api.chat({ provider, model: model || undefined, messages: next })
      setMessages([...next, { role: 'assistant', content: res.text }])
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="page chat-page">
      <h1>
        <span className="gradient-text">AIチャット</span>
      </h1>
      <p className="subtitle">
        「このツールの紹介動画を作って」のように話しかけて制作を進めます。
      </p>

      <div className="chat-toolbar">
        <label>
          プロバイダー
          <select value={provider} onChange={(e) => setProvider(e.target.value)}>
            {providers.map((p) => (
              <option key={p.id} value={p.id}>
                {p.display_name} {p.configured ? '' : '（未設定）'}
              </option>
            ))}
          </select>
        </label>
        <label>
          モデル
          <select value={model} onChange={(e) => setModel(e.target.value)}>
            {models.length === 0 && <option value="">（モデルなし）</option>}
            {models.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="chat-log">
        {messages.length === 0 && (
          <div className="empty" style={{ margin: 'auto', border: 'none' }}>
            <div className="empty-icon">💬</div>
            メッセージを送信して制作を始めましょう。
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`bubble ${m.role}`}>
            {m.content}
          </div>
        ))}
        {busy && <div className="bubble assistant muted">生成中…</div>}
      </div>

      {error && <div className="banner error">{error}</div>}

      <div className="chat-input-row">
        <textarea
          className="input"
          rows={2}
          placeholder="メッセージを入力（Enterで送信 / Shift+Enterで改行）"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              send()
            }
          }}
        />
        <button className="btn primary" onClick={send} disabled={busy}>
          送信
        </button>
      </div>
    </div>
  )
}
