import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { ThumbSpec, ThumbText } from '../types'

// Windowsパス → file URL（プレビュー表示用）
function fileUrl(p: string): string {
  if (!p) return ''
  return 'file:///' + p.replace(/\\/g, '/').replace(/ /g, '%20').replace(/#/g, '%23')
}

const DEFAULT_TITLE: ThumbText = {
  text: '',
  x: 0.5,
  y: 0.42,
  size: 120,
  color: '#ffffff',
  stroke: '#000000',
  stroke_width: 12,
  bold: true,
  align: 'center',
}
const DEFAULT_SUB: ThumbText = {
  text: '',
  x: 0.5,
  y: 0.82,
  size: 56,
  color: '#ffe14d',
  stroke: '#000000',
  stroke_width: 8,
  bold: true,
  align: 'center',
}

export default function ThumbnailStudio({
  videoPath,
  topic,
  notes,
  videoAnalysis,
  provider,
  model,
}: {
  videoPath: string
  topic: string
  notes: string
  videoAnalysis: string
  provider: string
  model: string
}) {
  const [baseKind, setBaseKind] = useState<ThumbSpec['base_kind']>('gradient')
  const [imagePath, setImagePath] = useState('')
  const [colorA, setColorA] = useState('#7c5cff')
  const [colorB, setColorB] = useState('#0b0b18')
  const [darken, setDarken] = useState(0.25)
  const [sceneTime, setSceneTime] = useState(1)
  const [duration, setDuration] = useState(0)
  const [aiPrompt, setAiPrompt] = useState('')

  const [title, setTitle] = useState<ThumbText>({ ...DEFAULT_TITLE })
  const [sub, setSub] = useState<ThumbText>({ ...DEFAULT_SUB })

  const [preview, setPreview] = useState('')
  const [busy, setBusy] = useState<'' | 'render' | 'scene' | 'ai' | 'auto'>('')
  const [msg, setMsg] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  // 動画の長さを取得（シーン選択スライダー用）
  useEffect(() => {
    if (!videoPath) return
    api
      .probeVideo(videoPath)
      .then((info) => {
        setDuration(Math.round(info.duration_sec))
        setSceneTime(Math.min(3, Math.max(1, Math.round(info.duration_sec / 2))))
      })
      .catch(() => setDuration(0))
  }, [videoPath])

  function buildSpec(): ThumbSpec {
    return {
      width: 1280,
      height: 720,
      base_kind: baseKind,
      image_path: imagePath,
      video_path: videoPath,
      scene_time: sceneTime,
      color_a: colorA,
      color_b: colorB,
      darken,
      texts: [title, sub],
    }
  }

  async function render(spec?: ThumbSpec) {
    setBusy('render')
    setError(null)
    try {
      const r = await api.thumbnailRender(spec ?? buildSpec())
      setPreview(r.image_path)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy('')
    }
  }

  async function useScene() {
    if (!videoPath) {
      setError('先に上の「動画を読み込む」で動画を指定してください。')
      return
    }
    setBusy('scene')
    setError(null)
    try {
      const r = await api.thumbnailScene(videoPath, sceneTime)
      setImagePath(r.image_path)
      setBaseKind('scene')
      setMsg('シーンをベースに取り込みました。')
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy('')
    }
  }

  async function importImage() {
    const p = await window.videocraft?.openFileDialog?.('image')
    if (!p) return
    setImagePath(p)
    setBaseKind('image')
    setMsg('画像を取り込みました。')
  }

  async function genImage() {
    if (!aiPrompt.trim()) {
      setError('生成したい画像の説明を入力してください。')
      return
    }
    setBusy('ai')
    setError(null)
    setMsg(null)
    try {
      const r = await api.thumbnailGenerate({
        prompt: aiPrompt.trim(),
        provider,
        model,
      })
      if (r.image_path) {
        setImagePath(r.image_path)
        setBaseKind('ai')
        setMsg('AIが背景画像を生成しました。')
      } else {
        setBaseKind('gradient')
        setMsg(r.warning || '画像生成に未対応のため、グラデ背景を使います。')
      }
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy('')
    }
  }

  // AIおまかせ: 文言をAIが提案 → 動画があればシーン、無ければグラデ → 描画
  async function autoMake() {
    setBusy('auto')
    setError(null)
    setMsg(null)
    try {
      const s = await api.thumbnailSuggest({
        topic,
        notes,
        video_analysis: videoAnalysis,
        provider,
        model,
      })
      const nt = { ...title, text: s.title || title.text }
      const ns = { ...sub, text: s.subtitle || sub.text }
      setTitle(nt)
      setSub(ns)
      let kind: ThumbSpec['base_kind'] = 'gradient'
      let img = imagePath
      if (videoPath) {
        try {
          const r = await api.thumbnailScene(videoPath, sceneTime)
          img = r.image_path
          kind = 'scene'
          setImagePath(img)
          setBaseKind('scene')
        } catch {
          /* シーン取得失敗時はグラデ */
        }
      }
      await render({
        width: 1280,
        height: 720,
        base_kind: kind,
        image_path: img,
        video_path: videoPath,
        scene_time: sceneTime,
        color_a: colorA,
        color_b: colorB,
        darken,
        texts: [nt, ns],
      })
      setMsg('AIがサムネの文言とベースを作りました。文字は下で微調整できます。')
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy('')
    }
  }

  const busyAny = busy !== ''

  return (
    <section className="card thumb-studio">
      <h2>🖼️ サムネイル作業場</h2>
      <p className="muted lic-intro">
        AIにおまかせ・シーンや画像から・完全手動、どれでもサムネを作れます（動画用・1280×720）。
      </p>

      <div className="run-actions">
        <button className="btn primary" onClick={autoMake} disabled={busyAny}>
          {busy === 'auto' ? '作成中…' : '🤖 AIにおまかせで作る'}
        </button>
      </div>

      {/* ベースの選び方 */}
      <div className="field-label">ベース（背景）</div>
      <div className="ap-mode thumb-base-modes">
        <button
          className={`ap-mode-btn ${baseKind === 'scene' ? 'active' : ''}`}
          onClick={() => setBaseKind('scene')}
        >
          🎞️ 動画のシーン
        </button>
        <button
          className={`ap-mode-btn ${baseKind === 'image' ? 'active' : ''}`}
          onClick={() => setBaseKind('image')}
        >
          🖼️ 画像インポート
        </button>
        <button
          className={`ap-mode-btn ${baseKind === 'ai' ? 'active' : ''}`}
          onClick={() => setBaseKind('ai')}
        >
          🤖 AI画像生成
        </button>
        <button
          className={`ap-mode-btn ${baseKind === 'gradient' ? 'active' : ''}`}
          onClick={() => setBaseKind('gradient')}
        >
          🎨 グラデ
        </button>
      </div>

      {baseKind === 'scene' && (
        <div className="thumb-scene">
          <div className="thumb-slider-row">
            <span className="muted">位置 {sceneTime}s</span>
            <input
              type="range"
              min={0}
              max={Math.max(1, duration)}
              value={sceneTime}
              onChange={(e) => setSceneTime(Number(e.target.value))}
            />
            <button className="btn ghost sm" onClick={useScene} disabled={busyAny}>
              {busy === 'scene' ? '取込中…' : 'このシーンを使う'}
            </button>
          </div>
          {!videoPath && (
            <p className="muted vol-hint">
              上の「🎞️ 動画を読み込む」で動画を指定するとシーンを選べます。
            </p>
          )}
        </div>
      )}
      {baseKind === 'image' && (
        <div className="row">
          <button className="btn ghost sm" onClick={importImage}>
            🖼️ 画像を選ぶ
          </button>
          <span className="muted ap-path">{imagePath || '（未選択）'}</span>
        </div>
      )}
      {baseKind === 'ai' && (
        <div className="thumb-ai">
          <div className="row">
            <input
              className="input"
              placeholder="生成したい背景の説明（例: 夜のネオン街、サイバー風の机とPC）"
              value={aiPrompt}
              onChange={(e) => setAiPrompt(e.target.value)}
            />
            <button className="btn ghost" onClick={genImage} disabled={busyAny}>
              {busy === 'ai' ? '生成中…' : '生成'}
            </button>
          </div>
          <p className="muted vol-hint">
            画像生成は Gemini など対応プロバイダーが必要です（未対応時はグラデ背景で代替）。
          </p>
        </div>
      )}
      {baseKind === 'gradient' && (
        <div className="row thumb-grad">
          <label className="thumb-color">
            上
            <input
              type="color"
              value={colorA}
              onChange={(e) => setColorA(e.target.value)}
            />
          </label>
          <label className="thumb-color">
            下
            <input
              type="color"
              value={colorB}
              onChange={(e) => setColorB(e.target.value)}
            />
          </label>
        </div>
      )}

      {/* 文字（作業場） */}
      <TextEditor label="大見出し" t={title} onChange={setTitle} multiline />
      <TextEditor label="補足（サブ）" t={sub} onChange={setSub} />

      <div className="thumb-slider-row">
        <span className="muted">暗さ {Math.round(darken * 100)}%</span>
        <input
          type="range"
          min={0}
          max={70}
          value={Math.round(darken * 100)}
          onChange={(e) => setDarken(Number(e.target.value) / 100)}
        />
        <span className="muted vol-hint">文字を読みやすくする暗幕</span>
      </div>

      <div className="run-actions">
        <button className="btn" onClick={() => render()} disabled={busyAny}>
          {busy === 'render' ? '描画中…' : '🔄 プレビュー更新'}
        </button>
        {preview && (
          <>
            <button
              className="btn ghost sm"
              onClick={() => window.videocraft?.openPath?.(preview)}
            >
              ▶ 開く
            </button>
            <button
              className="btn ghost sm"
              onClick={() => window.videocraft?.showItemInFolder?.(preview)}
            >
              📁 フォルダ
            </button>
          </>
        )}
      </div>

      {msg && <div className="lic-ok">{msg}</div>}
      {error && <div className="banner error">{error}</div>}

      {preview && (
        <div className="thumb-preview">
          <img src={fileUrl(preview)} alt="thumbnail preview" />
          <p className="muted ap-path">{preview}</p>
        </div>
      )}
    </section>
  )
}

function TextEditor({
  label,
  t,
  onChange,
  multiline,
}: {
  label: string
  t: ThumbText
  onChange: (t: ThumbText) => void
  multiline?: boolean
}) {
  const up = (patch: Partial<ThumbText>) => onChange({ ...t, ...patch })
  return (
    <div className="thumb-text-editor">
      <div className="field-label">{label}</div>
      {multiline ? (
        <textarea
          className="input"
          rows={2}
          placeholder="サムネの文字（改行OK）"
          value={t.text}
          onChange={(e) => up({ text: e.target.value })}
        />
      ) : (
        <input
          className="input"
          placeholder="サムネの文字"
          value={t.text}
          onChange={(e) => up({ text: e.target.value })}
        />
      )}
      <div className="thumb-text-controls">
        <label className="thumb-color">
          色
          <input
            type="color"
            value={t.color}
            onChange={(e) => up({ color: e.target.value })}
          />
        </label>
        <label className="thumb-num">
          サイズ {t.size}
          <input
            type="range"
            min={24}
            max={220}
            value={t.size}
            onChange={(e) => up({ size: Number(e.target.value) })}
          />
        </label>
        <label className="thumb-num">
          横 {Math.round(t.x * 100)}%
          <input
            type="range"
            min={0}
            max={100}
            value={Math.round(t.x * 100)}
            onChange={(e) => up({ x: Number(e.target.value) / 100 })}
          />
        </label>
        <label className="thumb-num">
          縦 {Math.round(t.y * 100)}%
          <input
            type="range"
            min={0}
            max={100}
            value={Math.round(t.y * 100)}
            onChange={(e) => up({ y: Number(e.target.value) / 100 })}
          />
        </label>
      </div>
    </div>
  )
}
