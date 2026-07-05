import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type {
  GuideResponse,
  Project,
  ProviderInfo,
  RecordingStep,
  StepKind,
} from '../types'

const STEP_META: Record<StepKind, { icon: string; label: string; cls: string }> = {
  start: { icon: '⏺', label: '録画開始', cls: 'k-start' },
  show: { icon: '🖥️', label: '画面表示', cls: 'k-show' },
  action: { icon: '🖱️', label: '操作', cls: 'k-action' },
  say: { icon: '🗣️', label: 'ナレーション', cls: 'k-say' },
  wait: { icon: '⏱️', label: '待機', cls: 'k-wait' },
  stop: { icon: '⏹', label: '録画停止', cls: 'k-stop' },
}

export default function RecordingPage() {
  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [provider, setProvider] = useState('')
  const [models, setModels] = useState<string[]>([])
  const [model, setModel] = useState('')
  const [projects, setProjects] = useState<Project[]>([])

  const [projectId, setProjectId] = useState<number | ''>('')
  const [topic, setTopic] = useState('')
  const [notes, setNotes] = useState('')

  const [result, setResult] = useState<GuideResponse | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // ステップ実行モード
  const [runIdx, setRunIdx] = useState<number | null>(null)
  const [remaining, setRemaining] = useState(0)
  const nextRef = useRef<() => void>(() => {})

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

  const steps = result?.guide.steps ?? []
  nextRef.current = () =>
    setRunIdx((i) => (i === null ? i : Math.min(i + 1, steps.length - 1)))

  // wait ステップのカウントダウン（0で自動的に次へ）
  useEffect(() => {
    if (runIdx === null) return
    const step = steps[runIdx]
    if (!step || step.kind !== 'wait' || step.duration_sec <= 0) return
    setRemaining(step.duration_sec)
    const id = setInterval(() => {
      setRemaining((r) => {
        if (r <= 1) {
          clearInterval(id)
          setTimeout(() => nextRef.current(), 0)
          return 0
        }
        return r - 1
      })
    }, 1000)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runIdx])

  async function generate() {
    if (busy) return
    if (projectId === '' && !topic.trim()) {
      setError('プロジェクトを選ぶか、テーマを入力してください。')
      return
    }
    setBusy(true)
    setError(null)
    setResult(null)
    setRunIdx(null)
    try {
      const res = await api.generateGuide({
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

  // ---- ステップ実行モード ----
  if (runIdx !== null && steps.length > 0) {
    const step = steps[runIdx]
    const meta = STEP_META[step.kind]
    const isLast = runIdx === steps.length - 1
    const progress = ((runIdx + 1) / steps.length) * 100

    return (
      <div className="page">
        <div className="runner-head">
          <button className="btn ghost" onClick={() => setRunIdx(null)}>
            ← ガイド終了
          </button>
          <span className="muted">
            ステップ {runIdx + 1} / {steps.length}
          </span>
        </div>

        <div className="runner-progress">
          <div className="runner-progress-fill" style={{ width: `${progress}%` }} />
        </div>

        <div className={`runner-card ${meta.cls}`}>
          <div className="runner-kind">
            <span className="runner-kind-icon">{meta.icon}</span>
            {meta.label}
          </div>
          <h2 className="runner-title">{step.title}</h2>
          <p className="runner-instruction">{step.instruction}</p>

          {step.kind === 'wait' && step.duration_sec > 0 && (
            <div className="countdown">
              <div className="countdown-num">{remaining}</div>
              <div className="countdown-label">秒</div>
            </div>
          )}
        </div>

        <div className="runner-controls">
          <button
            className="btn ghost"
            disabled={runIdx === 0}
            onClick={() => setRunIdx((i) => Math.max(0, (i ?? 0) - 1))}
          >
            前へ
          </button>
          {isLast ? (
            <button className="btn primary" onClick={() => setRunIdx(null)}>
              完了 🎉
            </button>
          ) : (
            <button
              className="btn primary"
              onClick={() => setRunIdx((i) => Math.min(steps.length - 1, (i ?? 0) + 1))}
            >
              次へ →
            </button>
          )}
        </div>
      </div>
    )
  }

  // ---- 通常（生成 + 一覧）----
  const waitTotal = steps
    .filter((s) => s.kind === 'wait')
    .reduce((n, s) => n + s.duration_sec, 0)

  return (
    <div className="page">
      <h1>
        <span className="gradient-text">録画支援</span>
      </h1>
      <p className="subtitle">
        企画をもとに録画手順を生成し、ステップごとに撮影をガイドします。
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
            テーマ（プロジェクト未指定時）
            <input
              className="input"
              placeholder="例: アプリの使い方紹介"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
            />
          </label>
        </div>

        <input
          className="input"
          placeholder="追加の要望（撮影環境・強調したい操作など・任意）"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />

        {error && <div className="banner error">{error}</div>}
        <button className="btn primary" onClick={generate} disabled={busy}>
          {busy ? '生成中…' : '録画ガイドを生成'}
        </button>
      </section>

      {result && (
        <section>
          <div className="plan-badges">
            <span className="badge ok">{steps.length} ステップ</span>
            {waitTotal > 0 && <span className="muted">待機合計 {waitTotal} 秒</span>}
            {result.saved_to_project && (
              <span className="badge ok">プロジェクトに保存済み</span>
            )}
            <span className="muted">
              {result.provider} / {result.model}
            </span>
          </div>

          <button
            className="btn primary run-btn"
            onClick={() => setRunIdx(0)}
          >
            ▶ ガイドを開始
          </button>

          <ol className="step-list">
            {steps.map((s, i) => (
              <StepRow key={i} step={s} index={i} />
            ))}
          </ol>
        </section>
      )}
    </div>
  )
}

function StepRow({ step, index }: { step: RecordingStep; index: number }) {
  const meta = STEP_META[step.kind]
  return (
    <li className="step-row">
      <div className="step-num">{index + 1}</div>
      <div className={`step-kind ${meta.cls}`}>
        <span>{meta.icon}</span>
        {meta.label}
      </div>
      <div className="step-body">
        <div className="step-title">{step.title}</div>
        <div className="step-instruction muted">{step.instruction}</div>
      </div>
      {step.kind === 'wait' && step.duration_sec > 0 && (
        <div className="step-dur">{step.duration_sec}秒</div>
      )}
    </li>
  )
}
