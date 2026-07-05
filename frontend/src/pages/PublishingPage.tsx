import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { Project, ProviderInfo, PublishResponse } from '../types'
import CopyButton from '../components/CopyButton'

export default function PublishingPage() {
  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [provider, setProvider] = useState('')
  const [models, setModels] = useState<string[]>([])
  const [model, setModel] = useState('')
  const [projects, setProjects] = useState<Project[]>([])

  const [projectId, setProjectId] = useState<number | ''>('')
  const [topic, setTopic] = useState('')
  const [notes, setNotes] = useState('')

  const [result, setResult] = useState<PublishResponse | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.listProviders().then((ps) => {
      setProviders(ps)
      const first = ps.find((p) => p.configured) ?? ps[0]
      if (first) setProvider(first.id)
    })
    api.listProjects().then(setProjects)
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

  async function generate() {
    if (busy) return
    if (projectId === '' && !topic.trim()) {
      setError('プロジェクトを選ぶか、テーマを入力してください。')
      return
    }
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const res = await api.generatePublish({
        topic: topic.trim() || undefined,
        notes: notes.trim() || undefined,
        provider,
        model: model || undefined,
        project_id: projectId === '' ? null : projectId,
      })
      setResult(res)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const pack = result?.pack

  return (
    <div className="page">
      <h1>
        <span className="gradient-text">投稿支援</span>
      </h1>
      <p className="subtitle">
        企画をもとに、YouTube・各SNS向けの投稿テキストを一括生成します。
      </p>

      <section className="card">
        <div className="plan-form-grid">
          <label>
            元にするプロジェクト
            <select
              value={projectId}
              onChange={(e) =>
                setProjectId(e.target.value === '' ? '' : Number(e.target.value))
              }
            >
              <option value="">指定しない（テーマから生成）</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.title}
                </option>
              ))}
            </select>
          </label>
          <label>
            テーマ（プロジェクト未指定時）
            <input
              className="input"
              placeholder="例: AI動画アプリの紹介"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
            />
          </label>
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
        <input
          className="input"
          placeholder="追加の要望（トーン・宣伝したい点など・任意）"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
        {error && <div className="banner error">{error}</div>}
        <button className="btn primary" onClick={generate} disabled={busy}>
          {busy ? '生成中…' : '投稿テキストを生成'}
        </button>
      </section>

      {pack && (
        <section className="pub-result">
          <div className="plan-badges">
            {result?.saved_to_project && (
              <span className="badge ok">プロジェクトに保存済み</span>
            )}
            <span className="muted">
              {result?.provider} / {result?.model}
            </span>
          </div>

          {/* YouTube */}
          <div className="card pub-yt">
            <h2>▶️ YouTube タイトル候補</h2>
            <ul className="pub-titles">
              {pack.youtube_titles.map((t, i) => (
                <li key={i}>
                  <span>{t}</span>
                  <CopyButton text={t} />
                </li>
              ))}
            </ul>
          </div>

          <div className="card">
            <h2>
              📝 YouTube 説明欄
              <span className="h2-action">
                <CopyButton text={pack.youtube_description} />
              </span>
            </h2>
            <pre className="pub-text">{pack.youtube_description}</pre>
          </div>

          <div className="card">
            <h2>
              #️⃣ ハッシュタグ
              <span className="h2-action">
                <CopyButton text={pack.hashtags.join(' ')} label="全部コピー" />
              </span>
            </h2>
            <div className="chip-row">
              {pack.hashtags.map((h, i) => (
                <span key={i} className="chip">
                  {h}
                </span>
              ))}
            </div>
          </div>

          <div className="card">
            <h2>
              📌 固定コメント
              <span className="h2-action">
                <CopyButton text={pack.pinned_comment} />
              </span>
            </h2>
            <pre className="pub-text">{pack.pinned_comment}</pre>
          </div>

          {/* SNS */}
          <div className="pub-sns-grid">
            <SnsCard icon="𝕏" title="X（Twitter）" text={pack.x_post} cls="sns-x" />
            <SnsCard
              icon="📷"
              title="Instagram"
              text={pack.instagram_post}
              cls="sns-ig"
            />
            <SnsCard icon="🎵" title="TikTok" text={pack.tiktok_post} cls="sns-tt" />
            <SnsCard icon="🛍️" title="BOOTH" text={pack.booth_text} cls="sns-booth" />
          </div>
        </section>
      )}
    </div>
  )
}

function SnsCard({
  icon,
  title,
  text,
  cls,
}: {
  icon: string
  title: string
  text: string
  cls: string
}) {
  return (
    <div className={`card sns-card ${cls}`}>
      <h2>
        <span className="sns-icon">{icon}</span>
        {title}
        <span className="h2-action">
          <CopyButton text={text} />
        </span>
      </h2>
      <pre className="pub-text">{text}</pre>
    </div>
  )
}
