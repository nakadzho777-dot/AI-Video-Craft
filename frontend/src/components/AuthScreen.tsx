import { useState } from 'react'
import { api, setToken } from '../api/client'
import type { UserInfo } from '../types'

export default function AuthScreen({
  onAuthed,
}: {
  onAuthed: (user: UserInfo) => void
}) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [username, setUsername] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit() {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      const res =
        mode === 'login'
          ? await api.login(email.trim(), password)
          : await api.register(email.trim(), password, username.trim() || undefined)
      setToken(res.token)
      onAuthed(res.user)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth-screen">
      <div className="aurora" aria-hidden />
      <div className="auth-card">
        <div className="auth-brand">
          <div className="brand-badge">🎥</div>
          <div className="brand-name">AI VideoCraft</div>
        </div>
        <div className="auth-tabs">
          <button
            className={mode === 'login' ? 'active' : ''}
            onClick={() => setMode('login')}
          >
            ログイン
          </button>
          <button
            className={mode === 'register' ? 'active' : ''}
            onClick={() => setMode('register')}
          >
            新規登録
          </button>
        </div>

        {mode === 'register' && (
          <input
            className="input"
            placeholder="ユーザー名（任意）"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
        )}
        <input
          className="input"
          type="email"
          placeholder="メールアドレス"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <input
          className="input"
          type="password"
          placeholder="パスワード（8文字以上）"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && submit()}
        />

        {error && <div className="banner error">{error}</div>}
        <button className="btn primary auth-submit" onClick={submit} disabled={busy}>
          {busy ? '処理中…' : mode === 'login' ? 'ログイン' : 'アカウント作成'}
        </button>

        <p className="auth-note muted">
          アカウントごとにプロジェクトと利用状況を保持します。
          Pro版はBOOTHで購入したライセンスキーで有効化できます。
        </p>
      </div>
    </div>
  )
}
