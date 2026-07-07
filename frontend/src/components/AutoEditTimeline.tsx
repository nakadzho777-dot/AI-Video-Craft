import { useEffect, useRef, useState } from 'react'

// 自動編集の「AIの編集風景」をタイムラインで見せる演出コンポーネント。
// - 実行中(busy): 走査ヘッドが左右に流れ「AIが編集中…」を表示。
// - 完了後: 再生ヘッドが左→右へ一度スイープし、通過点でカット/テロップが
//   ポンッと配置される（AIが順に編集を置いていくように見える）。

type Cut = { start_sec: number; end_sec: number }
type Telop = { time_sec: number; text: string }

type Ev =
  | { kind: 'cut'; t: number; end: number }
  | { kind: 'telop'; t: number; text: string }

export default function AutoEditTimeline({
  busy,
  duration,
  cuts,
  telops,
}: {
  busy: boolean
  duration: number
  cuts: Cut[]
  telops: Telop[]
}) {
  // 完了後のスイープ進捗（0..1）。busy 中は無効。
  const [sweep, setSweep] = useState(0)
  const rafRef = useRef<number | null>(null)
  const startRef = useRef<number>(0)

  const dur = Math.max(1, duration || 0)
  const events: Ev[] = [
    ...cuts.map((c) => ({ kind: 'cut' as const, t: c.start_sec, end: c.end_sec })),
    ...telops.map((t) => ({ kind: 'telop' as const, t: t.time_sec, text: t.text })),
  ].sort((a, b) => a.t - b.t)

  const hasPlan = !busy && (cuts.length > 0 || telops.length > 0)

  // 完了時に一度だけスイープ演出を走らせる
  useEffect(() => {
    if (!hasPlan) {
      setSweep(0)
      return
    }
    const SWEEP_MS = 3600
    startRef.current = 0
    const tick = (ts: number) => {
      if (!startRef.current) startRef.current = ts
      const p = Math.min(1, (ts - startRef.current) / SWEEP_MS)
      setSweep(p)
      if (p < 1) rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
    }
    // cuts/telops の内容が変わった時のみ再演出
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasPlan, cuts.length, telops.length])

  const headPct = sweep * 100

  if (!busy && !hasPlan) return null

  return (
    <div className={`autoedit-tl ${busy ? 'busy' : ''}`}>
      <div className="autoedit-tl-head">
        {busy ? (
          <>
            <span className="autoedit-spin" /> 🤖 AIが編集中… タイムラインを組み立てています
          </>
        ) : (
          <>
            🎬 AIの編集：カット {cuts.length}／テロップ {telops.length}
            {sweep >= 1 && <span className="autoedit-done"> ✓ 完了</span>}
          </>
        )}
      </div>

      <div className="autoedit-track">
        {/* カット区間（赤帯）: スイープが通過したら出現 */}
        {!busy &&
          cuts.map((c, i) => {
            const left = (Math.min(c.start_sec, dur) / dur) * 100
            const w = (Math.max(0, Math.min(c.end_sec, dur) - c.start_sec) / dur) * 100
            const shown = sweep * dur >= c.start_sec
            return (
              <div
                key={`c${i}`}
                className={`autoedit-cut ${shown ? 'show' : ''}`}
                style={{ left: `${left}%`, width: `${Math.max(0.6, w)}%` }}
                title={`カット ${c.start_sec.toFixed(1)}–${c.end_sec.toFixed(1)}秒`}
              />
            )
          })}

        {/* テロップマーカー: スイープ通過で pop */}
        {!busy &&
          telops.map((t, i) => {
            const left = (Math.min(t.time_sec, dur) / dur) * 100
            const shown = sweep * dur >= t.time_sec
            return (
              <div
                key={`t${i}`}
                className={`autoedit-telop ${shown ? 'show' : ''}`}
                style={{ left: `${left}%` }}
                title={t.text}
              >
                <span className="autoedit-telop-dot">🔤</span>
                <span className="autoedit-telop-text">{t.text}</span>
              </div>
            )
          })}

        {/* 再生/走査ヘッド */}
        <div
          className={`autoedit-head ${busy ? 'scan' : ''}`}
          style={busy ? undefined : { left: `${headPct}%` }}
        />
      </div>

      {!busy && events.length === 0 && (
        <div className="muted autoedit-empty">配置する編集はありませんでした。</div>
      )}
    </div>
  )
}
