import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { handoff, sendToRecording } from '../handoff'
import type { PlanResponse, Project, ProviderInfo } from '../types'

const FORMATS: { value: 'long' | 'short' | 'auto'; label: string }[] = [
  { value: 'long', label: '🎬 動画用（通常）' },
  { value: 'short', label: '📱 ショート用' },
  { value: 'auto', label: '✨ おまかせ' },
]

export default function PlanningPage() {
  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [provider, setProvider] = useState('')
  const [models, setModels] = useState<string[]>([])
  const [model, setModel] = useState('')
  const [projects, setProjects] = useState<Project[]>([])

  const [topic, setTopic] = useState('')
  const [format, setFormat] = useState<'auto' | 'short' | 'long'>('long')
  const [notes, setNotes] = useState('')
  const [projectId, setProjectId] = useState<number | ''>('')

  const [result, setResult] = useState<PlanResponse | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [savedMsg, setSavedMsg] = useState<string | null>(null)

  useEffect(() => {
    api.listProviders().then((ps) => {
      setProviders(ps)
      const first = ps.find((p) => p.configured) ?? ps[0]
      if (first) setProvider(first.id)
    })
    api.listProjects().then(setProjects)
    // ワークフロー中は対象プロジェクトを保存先に自動選択
    if (handoff.workflowProjectId) setProjectId(handoff.workflowProjectId)
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
    setSavedMsg(null)
    try {
      const res = await api.generatePlan({
        topic: topic.trim(),
        format,
        notes: notes.trim() || undefined,
        provider,
        model: model || undefined,
        // 同プロジェクト・同テーマの過去案があれば別バリエーションにさせる
        project_id: projectId === '' ? null : projectId,
      })
      setResult(res)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  // 「決定」してプロジェクトへ保存（履歴にも追記）
  async function decideAndSave() {
    if (!result?.plan || saving) return
    if (projectId === '') {
      setError('保存先プロジェクトを選んでください（この企画を決定して保存します）。')
      return
    }
    setSaving(true)
    setError(null)
    try {
      const r = await api.savePlan(projectId, result.plan, notes.trim())
      setSavedMsg(
        `プロジェクトに保存しました（このテーマで${r.variation_count}案目）。次に同じ条件で生成すると別バリエーションになります。`,
      )
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  // 企画を録画支援へ送る（テーマ・構成を引き継ぐ）
  function sendPlanToVideo() {
    if (!result?.plan) return
    const p = result.plan
    const instructions = [
      p.hook && `掴み: ${p.hook}`,
      ...p.sections.map((s) => `${s.name}: ${s.description}`),
    ]
      .filter(Boolean)
      .join('\n')
    sendToRecording({
      topic: p.topic || topic.trim(),
      instructions,
      target_duration_sec: p.target_duration_sec,
    })
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

        <div className="field-label">種類（動画用 / ショート用）</div>
        <div className="ap-mode ap-mode-3">
          {FORMATS.map((f) => (
            <button
              key={f.value}
              className={`ap-mode-btn ${format === f.value ? 'active' : ''}`}
              onClick={() => setFormat(f.value)}
            >
              {f.label}
            </button>
          ))}
        </div>

        <div className="plan-form-grid">
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
              {plan.format === 'short' ? '📱 ショート用' : '🎬 動画用'}
            </span>
            <span className="muted">目標尺 {plan.target_duration_sec} 秒</span>
            <span className="muted">
              {result?.provider} / {result?.model}
            </span>
          </div>

          {/* 決定して保存 ＋ 録画支援へ送る */}
          <div className="run-actions plan-actions">
            <button
              className="btn primary"
              onClick={decideAndSave}
              disabled={saving}
            >
              {saving ? '保存中…' : '💾 この企画を決定して保存'}
            </button>
            <button className="btn" onClick={sendPlanToVideo}>
              🎥 録画支援へ送る
            </button>
          </div>
          {savedMsg && <div className="lic-ok">{savedMsg}</div>}

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
