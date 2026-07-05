import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { MaterialMode, ProductionMode, Project } from '../types'

const PRODUCTION_MODES: { value: ProductionMode; label: string; desc: string }[] = [
  { value: 'auto', label: 'AIおまかせ', desc: 'AIが企画〜投稿準備まで主導' },
  { value: 'assist', label: 'AIサポート', desc: 'ユーザーが制作しAIが改善' },
  { value: 'manual', label: '手動制作', desc: '自分で制作・必要時のみAI' },
]

const MATERIAL_MODES: { value: MaterialMode; label: string }[] = [
  { value: 'provide', label: '素材を渡す' },
  { value: 'request', label: 'AIが素材を要求' },
]

export default function HomePage() {
  const [projects, setProjects] = useState<Project[]>([])
  const [title, setTitle] = useState('')
  const [production, setProduction] = useState<ProductionMode>('auto')
  const [material, setMaterial] = useState<MaterialMode>('request')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const reload = () => api.listProjects().then(setProjects).catch(() => {})

  useEffect(() => {
    reload()
  }, [])

  async function create() {
    if (!title.trim()) return
    setLoading(true)
    setError(null)
    try {
      await api.createProject({
        title: title.trim(),
        production_mode: production,
        material_mode: material,
      })
      setTitle('')
      await reload()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  async function remove(id: number) {
    await api.deleteProject(id)
    reload()
  }

  return (
    <div className="page">
      <h1>
        <span className="gradient-text">プロジェクト</span>
      </h1>
      <p className="subtitle">動画1本ごとにプロジェクトを作成します。</p>

      <section className="card">
        <h2>✨ 新規プロジェクト</h2>
        <input
          className="input"
          placeholder="動画タイトル（例: このツールの紹介動画）"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && create()}
        />

        <div className="field-label">制作モード</div>
        <div className="mode-grid">
          {PRODUCTION_MODES.map((m) => (
            <button
              key={m.value}
              className={`mode-card ${production === m.value ? 'selected' : ''}`}
              onClick={() => setProduction(m.value)}
            >
              <div className="mode-title">{m.label}</div>
              <div className="mode-desc">{m.desc}</div>
            </button>
          ))}
        </div>

        <div className="field-label">素材モード</div>
        <div className="pill-row">
          {MATERIAL_MODES.map((m) => (
            <button
              key={m.value}
              className={`pill ${material === m.value ? 'selected' : ''}`}
              onClick={() => setMaterial(m.value)}
            >
              {m.label}
            </button>
          ))}
        </div>

        {error && <div className="banner error">{error}</div>}
        <button className="btn primary" onClick={create} disabled={loading}>
          {loading ? '作成中…' : 'プロジェクトを作成'}
        </button>
      </section>

      <section>
        <h2>📁 プロジェクト一覧（{projects.length}）</h2>
        {projects.length === 0 ? (
          <div className="empty">
            <div className="empty-icon">🎞️</div>
            まだプロジェクトがありません。
            <br />
            上のフォームから最初の動画を作りましょう。
          </div>
        ) : (
          <ul className="project-list">
            {projects.map((p) => (
              <li key={p.id} className="project-item">
                <div>
                  <div className="project-title">{p.title}</div>
                  <div className="project-meta">
                    {PRODUCTION_MODES.find((m) => m.value === p.production_mode)
                      ?.label ?? p.production_mode}
                    <span className="status-tag">{p.status}</span>
                  </div>
                </div>
                <button className="btn ghost" onClick={() => remove(p.id)}>
                  削除
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
