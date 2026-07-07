import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { ProviderInfo, UsageInfo } from '../types'
import LicenseCard from '../components/LicenseCard'

export default function SettingsPage({
  onPlanChanged,
}: {
  onPlanChanged?: () => void
}) {
  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [keys, setKeys] = useState<Record<string, string>>({})
  const [saved, setSaved] = useState<string | null>(null)
  const [models, setModels] = useState<Record<string, string[]>>({})
  const [usage, setUsage] = useState<UsageInfo | null>(null)
  const [devMode, setDevMode] = useState(false)
  const [appVersion, setAppVersion] = useState<string | null>(null)
  const [updateMsg, setUpdateMsg] = useState<string | null>(null)

  const reload = () => api.listProviders().then(setProviders)

  useEffect(() => {
    reload()
    api.usage().then(setUsage).catch(() => {})
    api.health().then((h) => setDevMode(h.dev_mode)).catch(() => {})
    window.videocraft?.appVersion().then(setAppVersion).catch(() => {})
  }, [])

  async function checkUpdate() {
    setUpdateMsg('確認中…')
    const r = await window.videocraft?.update?.check()
    if (!r || r.state === 'dev') setUpdateMsg('開発モードでは更新確認は無効です。')
    else if (r.state === 'latest') setUpdateMsg('最新版を使用中です。')
    else if (r.state === 'available') setUpdateMsg('新しいバージョンが見つかりました。ダウンロードします…')
    else if (r.state === 'error') setUpdateMsg('更新確認に失敗しました。')
    else setUpdateMsg(null)
  }

  const isPro = usage?.plan === 'pro'

  async function saveKey(id: string) {
    await api.setApiKey(id, keys[id] ?? '')
    setSaved(id)
    setTimeout(() => setSaved(null), 2000)
    reload()
  }

  async function checkModels(id: string) {
    try {
      const ms = await api.listModels(id)
      setModels((prev) => ({ ...prev, [id]: ms }))
    } catch {
      setModels((prev) => ({ ...prev, [id]: ['(取得失敗)'] }))
    }
  }

  return (
    <div className="page">
      <h1>
        <span className="gradient-text">設定</span>
      </h1>
      <p className="subtitle">プラン・制限の確認と、AI プロバイダーの設定を行います。</p>

      {usage && (
        <section className="card plan-card">
          <div className="provider-head">
            <h2>現在のプラン</h2>
            <span className={`badge ${isPro ? 'ok' : 'muted'}`}>
              {isPro ? 'Pro' : 'Free'}
            </span>
          </div>
          <ul className="limit-list">
            <LimitRow
              label="AI制作（1日）"
              value={
                usage.ai_runs_limit === null
                  ? '無制限'
                  : `${usage.ai_runs_today} / ${usage.ai_runs_limit} 回`
              }
            />
            <LimitRow
              label="プロジェクト数"
              value={
                usage.limits.max_projects === null
                  ? '無制限'
                  : `${usage.limits.max_projects} 件`
              }
            />
            <LimitRow
              label="書き出し解像度"
              value={
                usage.limits.max_resolution_p === null
                  ? '4K'
                  : `${usage.limits.max_resolution_p}p`
              }
            />
            <LimitRow
              label="動画の長さ"
              value={
                usage.limits.max_video_minutes === null
                  ? '無制限'
                  : `${usage.limits.max_video_minutes} 分`
              }
            />
            <LimitRow
              label="有料AI（OpenAI/Gemini/Claude）"
              value={usage.limits.paid_ai_allowed ? '利用可' : '利用不可'}
            />
            <LimitRow
              label="高度編集（縦動画化など）"
              value={usage.limits.advanced_editing ? '利用可' : '利用不可'}
            />
          </ul>
          {!isPro && (
            <p className="muted plan-note">
              Free版の制限です。Pro版で全機能が無制限になります。
            </p>
          )}
        </section>
      )}

      <LicenseCard
        devMode={devMode}
        onChanged={() => {
          api.usage().then(setUsage).catch(() => {})
          onPlanChanged?.()
        }}
      />

      <section className="card">
        <div className="provider-head">
          <h2>🔄 アプリの更新</h2>
          <span className="badge muted">
            v{appVersion ?? '—'}
          </span>
        </div>
        <p className="muted lic-intro">
          起動時に自動で最新版を確認し、あればダウンロードして次回起動時に適用します。
        </p>
        <div className="row">
          <button className="btn ghost" onClick={checkUpdate}>
            今すぐ更新を確認
          </button>
        </div>
        {updateMsg && <div className="lic-ok">{updateMsg}</div>}
      </section>

      {providers.map((p) => (
        <section className="card" key={p.id}>
          <div className="provider-head">
            <h2>{p.display_name}</h2>
            <span className={`badge ${p.configured ? 'ok' : 'muted'}`}>
              {p.configured ? '設定済み' : '未設定'}
            </span>
          </div>

          {p.kind === 'local' ? (
            <div>
              <p className="muted">
                ローカルで動作します。Ollama をインストールしてください。
              </p>
              {p.download_url && (
                <a className="link" href={p.download_url} target="_blank" rel="noreferrer">
                  Ollama ダウンロードページ ↗
                </a>
              )}
              <div className="row">
                <button className="btn ghost" onClick={() => checkModels(p.id)}>
                  モデル一覧を取得
                </button>
              </div>
            </div>
          ) : (
            <div>
              <div className="row">
                <input
                  className="input"
                  type="password"
                  placeholder="APIキーを入力"
                  value={keys[p.id] ?? ''}
                  onChange={(e) => setKeys({ ...keys, [p.id]: e.target.value })}
                />
                <button className="btn primary" onClick={() => saveKey(p.id)}>
                  {saved === p.id ? '保存しました' : '保存'}
                </button>
              </div>
              {p.api_key_help_url && (
                <a
                  className="link"
                  href={p.api_key_help_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  APIキー確認ページ ↗
                </a>
              )}
            </div>
          )}

          {models[p.id] && (
            <ul className="model-list">
              {models[p.id].map((m) => (
                <li key={m}>{m}</li>
              ))}
            </ul>
          )}
        </section>
      ))}
    </div>
  )
}

function LimitRow({ label, value }: { label: string; value: string }) {
  return (
    <li className="limit-row">
      <span className="limit-label">{label}</span>
      <span className="limit-value">{value}</span>
    </li>
  )
}
