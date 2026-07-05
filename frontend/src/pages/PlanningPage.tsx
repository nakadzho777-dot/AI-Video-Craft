import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { PlanResponse, Project, ProviderInfo } from '../types'

export default function PlanningPage() {
  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [provider, setProvider] = useState('')
  const [models, setModels] = useState<string[]>([])
  const [model, setModel] = useState('')
  const [projects, setProjects] = useState<Project[]>([])

  const [topic, setTopic] = useState('')
  const [format, setFormat] = useState<'auto' | 'short' | 'long'>('auto')
  const [notes, setNotes] = useState('')
  const [projectId, setProjectId] = useState<number | ''>('')

  const [result, setResult] = useState<PlanResponse | null>(null)
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
    if (!topic.trim() || busy) return
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const res = await api.generatePlan({
        topic: topic.trim(),
        format,
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

  const plan = result?.plan
  const sectionsTotal = plan?.sections.reduce((s, x) => s + x.duration_sec, 0) ?? 0

  return (
    <div className="page">
      <h1>
        <span className="gradient-text">AI企画</span>
      </h1>
      <p className="subtitle">
        テーマを入力すると、タイトル・構成・尺配分・掴み・CTA・サムネイル案を生成します。
      </p>

      <section className="card">
        <textarea
          className="input"
          rows={2}
          placeholder="動画のテーマ（例: このツールの紹介動画を作りたい）"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
        />

        <div className="plan-form-grid">
          <label>
            フォーマット
            <select value={format} onChange={(e) => setFormat(e.target.value as any)}>
              <option value="auto">おまかせ</option>
              <option value="short">ショート</option>
              <option value="long">通常</option>
            </select>
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
          <label>
            保存先プロジェクト
            <select
              value={projectId}
              onChange={(e) =>
                setProjectId(e.target.value === '' ? '' : Number(e.target.value))
              }
            >
              <option value="">保存しない</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.title}
                </option>
              ))}
            </select>
          </label>
        </div>

        <input
          className="input"
          placeholder="追加の要望（トーン、対象視聴者など・任意）"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />

        {error && <div className="banner error">{error}</div>}
        <button className="btn primary" onClick={generate} disabled={busy}>
          {busy ? '生成中…' : '企画を生成'}
        </button>
      </section>

      {plan && (
        <section className="plan-result">
          <div className="plan-badges">
            <span className="badge ok">
              {plan.format === 'short' ? 'ショート' : '通常'}
            </span>
            <span className="muted">目標尺 {plan.target_duration_sec} 秒</span>
            {result?.saved_to_project && (
              <span className="badge ok">プロジェクトに保存済み</span>
            )}
            <span className="muted">
              {result?.provider} / {result?.model}
            </span>
          </div>

          <div className="card">
            <h2>🏷️ タイトル候補</h2>
            <ol className="plan-titles">
              {plan.titles.map((t, i) => (
                <li key={i}>{t}</li>
              ))}
            </ol>
          </div>

          <div className="card">
            <h2>🎯 冒頭の掴み</h2>
            <p className="plan-hook">{plan.hook}</p>
          </div>

          <div className="card">
            <h2>
              🎬 構成 / 尺配分{' '}
              <span className="muted">（合計 {sectionsTotal} 秒）</span>
            </h2>
            <ul className="plan-sections">
              {plan.sections.map((s, i) => (
                <li key={i}>
                  <div className="plan-sec-head">
                    <span className="plan-sec-name">{s.name}</span>
                    <span className="plan-sec-dur">{s.duration_sec}秒</span>
                  </div>
                  <div className="muted">{s.description}</div>
                </li>
              ))}
            </ul>
          </div>

          <div className="card">
            <h2>📣 CTA</h2>
            <p className="cta-box">{plan.cta}</p>
          </div>

          <div className="card">
            <h2>🖼️ サムネイル案</h2>
            <ul className="plan-thumbs">
              {plan.thumbnail_ideas.map((t, i) => (
                <li key={i}>{t}</li>
              ))}
            </ul>
          </div>
        </section>
      )}
    </div>
  )
}
