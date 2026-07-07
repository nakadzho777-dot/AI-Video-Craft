import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type { EditCut, EditTelop } from '../types'

// CapCut風 編集タイムライン：プレビュー＋再生ヘッド、タイムライン上でカット/トリム、
// テロップの配置。cuts/telops は EditingPage と共有する。

function fileUrl(p: string): string {
  if (!p) return ''
  return 'file:///' + p.replace(/\\/g, '/').replace(/ /g, '%20').replace(/#/g, '%23')
}
function fmt(sec: number): string {
  const s = Math.max(0, sec)
  const m = Math.floor(s / 60)
  const ss = Math.floor(s % 60)
  return `${m}:${String(ss).padStart(2, '0')}`
}

export default function EditorTimeline({
  videoPath,
  duration,
  cuts,
  setCuts,
  telops,
  setTelops,
}: {
  videoPath: string
  duration: number
  cuts: EditCut[]
  setCuts: (c: EditCut[]) => void
  telops: EditTelop[]
  setTelops: (t: EditTelop[]) => void
}) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const trackRef = useRef<HTMLDivElement>(null)
  const previewRef = useRef<HTMLDivElement>(null)
  const [previewH, setPreviewH] = useState(240)
  const rafRef = useRef<number | null>(null)
  const dragRef = useRef<{ startT: number; moved: boolean } | null>(null)

  const [cur, setCur] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [thumbs, setThumbs] = useState<string[]>([])
  const [sel, setSel] = useState<{ a: number; b: number } | null>(null)
  const [skipCuts, setSkipCuts] = useState(true)
  const [newTelop, setNewTelop] = useState('')

  const dur = duration > 0 ? duration : 0
  const pct = (t: number) => (dur > 0 ? Math.max(0, Math.min(100, (t / dur) * 100)) : 0)

  // プレビュー高さを測ってテロップの見た目サイズを合わせる
  useEffect(() => {
    const el = previewRef.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(() => setPreviewH(el.clientHeight || 240))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  useEffect(() => {
    if (!videoPath || dur <= 0) return
    setThumbs([])
    api
      .timelineThumbnails(videoPath, 12)
      .then((r) => setThumbs(r.frames))
      .catch(() => setThumbs([]))
  }, [videoPath, dur])

  // 再生中は再生ヘッドを更新。skipCuts ON ならカット区間を飛ばして「編集後」を確認できる
  useEffect(() => {
    const v = videoRef.current
    if (!v) return
    const loop = () => {
      let t = v.currentTime
      if (skipCuts && !v.paused) {
        for (const c of cuts) {
          if (c.end_sec > c.start_sec && t >= c.start_sec - 0.02 && t < c.end_sec) {
            v.currentTime = c.end_sec
            t = c.end_sec
            break
          }
        }
      }
      setCur(t)
      rafRef.current = requestAnimationFrame(loop)
    }
    rafRef.current = requestAnimationFrame(loop)
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
    }
  }, [cuts, skipCuts])

  function togglePlay() {
    const v = videoRef.current
    if (!v) return
    if (v.paused) {
      v.play().catch(() => {})
      setPlaying(true)
    } else {
      v.pause()
      setPlaying(false)
    }
  }
  function seek(t: number) {
    const v = videoRef.current
    if (v) v.currentTime = Math.max(0, Math.min(dur, t))
    setCur(Math.max(0, Math.min(dur, t)))
  }

  function timeFromX(clientX: number): number {
    const el = trackRef.current
    if (!el || dur <= 0) return 0
    const r = el.getBoundingClientRect()
    return Math.max(0, Math.min(dur, ((clientX - r.left) / r.width) * dur))
  }

  function onTrackDown(e: React.PointerEvent) {
    if (dur <= 0) return
    const t0 = timeFromX(e.clientX)
    dragRef.current = { startT: t0, moved: false }
    setSel({ a: t0, b: t0 })
    const move = (ev: PointerEvent) => {
      if (!dragRef.current) return
      const t = timeFromX(ev.clientX)
      if (Math.abs(t - dragRef.current.startT) > 0.15) dragRef.current.moved = true
      setSel({ a: Math.min(dragRef.current.startT, t), b: Math.max(dragRef.current.startT, t) })
    }
    const up = (ev: PointerEvent) => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      const t = timeFromX(ev.clientX)
      if (!dragRef.current?.moved) {
        // ドラッグしていない＝クリック＝シーク
        setSel(null)
        seek(t)
      }
      dragRef.current = null
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }

  function deleteSelection() {
    if (!sel || sel.b - sel.a < 0.1) return
    setCuts([...cuts, { start_sec: +sel.a.toFixed(2), end_sec: +sel.b.toFixed(2) }])
    setSel(null)
  }
  function addTelop() {
    setTelops([
      ...telops,
      {
        time_sec: +cur.toFixed(2),
        text: newTelop.trim() || 'テロップ',
        size: 54,
        color: '#ffffff',
        stroke: '#000000',
        x: 0.5,
        y: 0.86,
        bold: true,
        anim: 'fade',
      },
    ])
    setNewTelop('')
  }
  const keptSec =
    dur - cuts.reduce((s, c) => s + Math.max(0, c.end_sec - c.start_sec), 0)

  if (!videoPath || dur <= 0) {
    return (
      <div className="tl-empty muted">
        動画を読み込むと、タイムラインで直感的にカット・テロップできます。
      </div>
    )
  }

  return (
    <div className="editor-timeline">
      {/* プレビュー */}
      <div className="tl-preview" ref={previewRef}>
        <video
          ref={videoRef}
          src={fileUrl(videoPath)}
          className="tl-video"
          onClick={togglePlay}
          onPause={() => setPlaying(false)}
          onPlay={() => setPlaying(true)}
        />
        {/* 再生位置のテロップを、色・大きさ・位置つきで疑似表示 */}
        {telops
          .filter((t) => cur >= t.time_sec && cur < t.time_sec + 2.8 && t.text.trim())
          .map((t, i) => {
            const fs = ((t.size ?? 54) / 720) * previewH
            return (
              <div
                key={i}
                className="tl-telop-preview"
                style={{
                  left: `${(t.x ?? 0.5) * 100}%`,
                  top: `${(t.y ?? 0.86) * 100}%`,
                  transform: 'translate(-50%, -50%)',
                  color: t.color ?? '#fff',
                  fontSize: `${Math.max(10, fs)}px`,
                  fontWeight: t.bold === false ? 400 : 800,
                  WebkitTextStroke: `${Math.max(1, fs / 9)}px ${t.stroke ?? '#000'}`,
                }}
              >
                {t.text}
              </div>
            )
          })}
      </div>

      <div className="tl-transport">
        <button className="btn ghost sm" onClick={togglePlay}>
          {playing ? '⏸' : '▶'}
        </button>
        <span className="muted tl-time">
          {fmt(cur)} / {fmt(dur)}
        </span>
        <label className="check tl-skip">
          <input
            type="checkbox"
            checked={skipCuts}
            onChange={(e) => setSkipCuts(e.target.checked)}
          />
          カットを飛ばして再生（編集後プレビュー）
        </label>
        <span className="muted">
          完成尺の目安: 約 {fmt(keptSec)}
        </span>
      </div>

      {/* タイムライン */}
      <div className="tl-track-wrap">
        <div className="tl-track" ref={trackRef} onPointerDown={onTrackDown}>
          <div className="tl-thumbs">
            {thumbs.length > 0
              ? thumbs.map((src, i) => (
                  <img key={i} src={src} alt="" draggable={false} />
                ))
              : null}
          </div>
          {/* カット区間 */}
          {cuts.map((c, i) => (
            <div
              key={i}
              className="tl-cut"
              style={{
                left: `${pct(c.start_sec)}%`,
                width: `${pct(c.end_sec) - pct(c.start_sec)}%`,
              }}
              title="クリックで削除を取り消し"
              onPointerDown={(e) => e.stopPropagation()}
              onClick={() => setCuts(cuts.filter((_, j) => j !== i))}
            >
              <span>✕カット</span>
            </div>
          ))}
          {/* 選択範囲 */}
          {sel && sel.b > sel.a && (
            <div
              className="tl-sel"
              style={{ left: `${pct(sel.a)}%`, width: `${pct(sel.b) - pct(sel.a)}%` }}
            />
          )}
          {/* テロップマーカー */}
          {telops.map((t, i) => (
            <div
              key={i}
              className="tl-telop-mark"
              style={{ left: `${pct(t.time_sec)}%` }}
              title={t.text}
              onPointerDown={(e) => e.stopPropagation()}
              onClick={() => seek(t.time_sec)}
            >
              🔤
            </div>
          ))}
          {/* 再生ヘッド */}
          <div className="tl-playhead" style={{ left: `${pct(cur)}%` }} />
        </div>
      </div>

      <div className="tl-actions">
        <button
          className="btn ghost sm"
          onClick={deleteSelection}
          disabled={!sel || sel.b - sel.a < 0.1}
        >
          ✂️ 選択範囲をカット
        </button>
        <input
          className="input sm"
          placeholder="テロップの文字"
          value={newTelop}
          onChange={(e) => setNewTelop(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && addTelop()}
        />
        <button className="btn ghost sm" onClick={addTelop}>
          🔤 再生位置にテロップ
        </button>
        <span className="muted tl-hint">
          タイムラインをドラッグ→「選択範囲をカット」／クリックでシーク
        </span>
      </div>
    </div>
  )
}
