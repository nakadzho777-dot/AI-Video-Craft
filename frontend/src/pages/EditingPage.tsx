import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type {
  ProbeResponse,
  Project,
  ProviderInfo,
  SilenceRange,
  SuggestResponse,
} from '../types'

function fmt(sec: number): string {
  const s = Math.max(0, Math.round(sec))
  const m = Math.floor(s / 60)
  return `${m}:${String(s % 60).padStart(2, '0')}`
}

const canBrowse = () => !!window.videocraft?.openVideoDialog

export default function EditingPage() {
  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [provider, setProvider] = useState('')
  const [models, setModels] = useState<string[]>([])
  const [model, setModel] = useState('')
  const [projects, setProjects] = useState<Project[]>([])

  const [videoPath, setVideoPath] = useState('')
  const [probe, setProbe] = useState<ProbeResponse | null>(null)
  const [duration, setDuration] = useState<number>(0)
  const [projectId, setProjectId] = useState<number | ''>('')
  const [goal, setGoal] = useState<'auto' | 'improve' | 'short'>('auto')
  const [script, setScript] = useState('')

  const [result, setResult] = useState<SuggestResponse | null>(null)
  const [silence, setSilence] = useState<SilenceRange[] | null>(null)
  const [busy, setBusy] = useState<'' | 'probe' | 'suggest' | 'silence'>('')
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

  async function browse() {
    const p = await window.videocraft?.openVideoDialog?.()
    if (p) setVideoPath(p)
  }

  async function loadVideo() {
    if (!videoPath.trim() || busy) return
    setBusy('probe')
    setError(null)
    setProbe(null)
    setSilence(null)
    try {
      const info = await api.probeVideo(videoPath.trim())
      setProbe(info)
      setDuration(Math.round(info.duration_sec))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy('')
    }
  }

  async function suggest() {
    if (busy) return
    setBusy('suggest')
    setError(null)
    setResult(null)
    try {
      const res = await api.suggestEdit({
        duration_sec: duration || undefined,
        script: script.trim() || undefined,
        goal,
        provider,
        model: model || undefined,
        project_id: projectId === '' ? null : projectId,
      })
      setResult(res)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy('')
    }
  }

  async function findSilence() {
    if (!videoPath.trim() || busy) return
    setBusy('silence')
    setError(null)
    try {
      setSilence(await api.detectSilence(videoPath.trim()))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy('')
    }
  }

  const sug = result?.suggestion

  return (
    <div className="page">
      <h1>
        <span className="gradient-text">編集支援</span>
      </h1>
      <p className="subtitle">
        動画を読み込み、AIがカット・テロップ・BGM・ショート化を提案します。
      </p>

      {/* 動画読み込み */}
      <section className="card">
        <h2>🎞️ 動画を読み込む</h2>
        <div className="row">
          <input
            className="input"
            placeholder="動画ファイルのパス（例: C:\videos\demo.mp4）"
            value={videoPath}
            onChange={(e) => setVideoPath(e.target.value)}
          />
          {canBrowse() && (
            <button className="btn ghost" onClick={browse}>
              参照…
            </button>
          )}
          <button className="btn" onClick={loadVideo} disabled={busy === 'probe'}>
            {busy === 'probe' ? '読込中…' : '読み込む'}
          </button>
        </div>
        {probe && (
          <div className="media-info">
            <span className="media-chip">⏱ {fmt(probe.duration_sec)}</span>
            {probe.width && probe.height && (
              <span className="media-chip">
                🖥 {probe.width}×{probe.height}
              </span>
            )}
            <button
              className="btn ghost sm"
              onClick={findSilence}
              disabled={busy === 'silence'}
            >
              {busy === 'silence' ? '検出中…' : '🔇 無音検出'}
            </button>
          </div>
        )}
        {silence && (
          <div className="silence-box">
            <div className="field-label">無音区間（カット候補） {silence.length} 件</div>
            {silence.length === 0 ? (
              <p className="muted">無音区間は見つかりませんでした。</p>
            ) : (
              <ul className="silence-list">
                {silence.map((s, i) => (
                  <li key={i}>
                    <span className="mono">
                      {fmt(s.start_sec)} → {fmt(s.end_sec)}
                    </span>
                    <span className="muted">{s.duration_sec.toFixed(1)}秒</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </section>

      {/* 条件 + 生成 */}
      <section className="card">
        <h2>✂️ AI編集提案</h2>
        <div className="plan-form-grid">
          <label>
            動画の長さ（秒）
            <input
              className="input"
              type="number"
              min={0}
              value={duration || ''}
              onChange={(e) => setDuration(Number(e.target.value))}
              placeholder="読み込むと自動入力"
            />
          </label>
          <label>
            目的
            <select value={goal} onChange={(e) => setGoal(e.target.value as any)}>
              <option value="auto">おまかせ</option>
              <option value="improve">通常動画を改善</option>
              <option value="short">ショート動画化</option>
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
        <textarea
          className="input"
          rows={3}
          placeholder="台本・文字起こし（任意・あると提案精度が上がります）"
          value={script}
          onChange={(e) => setScript(e.target.value)}
        />
        {error && <div className="banner error">{error}</div>}
        <button className="btn primary" onClick={suggest} disabled={busy === 'suggest'}>
          {busy === 'suggest' ? '生成中…' : 'AI編集提案を生成'}
        </button>
      </section>

      {sug && (
        <section className="edit-result">
          <div className="plan-badges">
            {result?.saved_to_project && (
              <span className="badge ok">プロジェクトに保存済み</span>
            )}
            <span className="muted">
              {result?.provider} / {result?.model}
            </span>
          </div>

          <div className="card">
            <h2>✂️ カット提案 <span className="muted">{sug.cuts.length}件</span></h2>
            {sug.cuts.length === 0 ? (
              <p className="muted">なし</p>
            ) : (
              <ul className="cut-list">
                {sug.cuts.map((c, i) => (
                  <li key={i}>
                    <span className="mono cut-time">
                      {fmt(c.start_sec)}–{fmt(c.end_sec)}
                    </span>
                    <span>{c.reason}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="card">
            <h2>💬 テロップ提案 <span className="muted">{sug.telops.length}件</span></h2>
            {sug.telops.length === 0 ? (
              <p className="muted">なし</p>
            ) : (
              <ul className="telop-list">
                {sug.telops.map((t, i) => (
                  <li key={i}>
                    <span className="mono telop-time">{fmt(t.time_sec)}</span>
                    <span>{t.text}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="edit-two-col">
            <div className="card">
              <h2>🎵 BGM候補</h2>
              <div className="chip-row">
                {sug.bgm_suggestions.map((b, i) => (
                  <span key={i} className="chip">
                    {b}
                  </span>
                ))}
              </div>
            </div>
            <div className="card">
              <h2>⚡ テンポ改善</h2>
              <ul className="tip-list">
                {sug.tempo_tips.map((t, i) => (
                  <li key={i}>{t}</li>
                ))}
              </ul>
            </div>
          </div>

          {sug.short_plan && (
            <div className="card short-card">
              <h2>📱 ショート動画化案</h2>
              <div className="plan-badges">
                <span className="badge ok">
                  {sug.short_plan.vertical ? '縦動画' : '横動画'}
                </span>
                <span className="muted">
                  目標 {sug.short_plan.target_duration_sec} 秒
                </span>
              </div>
              <ul className="cut-list">
                {sug.short_plan.segments.map((s, i) => (
                  <li key={i}>
                    <span className="mono cut-time">
                      {fmt(s.start_sec)}–{fmt(s.end_sec)}
                    </span>
                    <span>{s.reason}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}
    </div>
  )
}
