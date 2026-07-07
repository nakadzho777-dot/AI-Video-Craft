import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { handoff, sendToEditing } from '../handoff'
import RecordingStudio from '../components/RecordingStudio'
import YukkuriPage from './YukkuriPage'
import type {
  AutopilotPlan,
  AutopilotRunResponse,
  AutopilotVoice,
  DesktopPlan,
  DurationSuggestion,
  GuideResponse,
  Project,
  ProviderInfo,
  RecordingStep,
  StepKind,
} from '../types'

// AI自動撮影の操作ラベル/アイコン
const AP_LABEL: Record<string, string> = {
  goto: 'ページ移動',
  click: 'クリック',
  fill: '入力',
  press: 'キー',
  scroll: 'スクロール',
  wait: '待機',
}
const AP_ICON: Record<string, string> = {
  goto: '🌐',
  click: '🖱️',
  fill: '⌨️',
  press: '⏎',
  scroll: '📜',
  wait: '⏱️',
}

// AI VideoCraft 自体を撮影する時に開く別ウィンドウのタイトル（main.ts と一致）
const REC_WINDOW_TITLE = 'AI VideoCraft (録画用)'


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

  // 尺の候補（生成前に動画用/ショート用を提案）
  const [durSug, setDurSug] = useState<DurationSuggestion | null>(null)
  const [durBusy, setDurBusy] = useState(false)
  const [targetMsg, setTargetMsg] = useState<string | null>(null)

  async function suggestDur() {
    if (durBusy) return
    setDurBusy(true)
    setError(null)
    try {
      const s = await api.suggestDurations(
        (apTopic || topic).trim(),
        (apInstructions || notes).trim(),
        provider,
        model || undefined,
      )
      setDurSug(s)
    } catch {
      // client 側でフォールバック済みだが二重の保険で必ず候補を出す
      setDurSug({
        video_sec: 240,
        short_sec: 45,
        note: 'AIに繋がらなかったため、目安の候補を表示しています。',
        record_video_sec: 312,
        record_short_sec: 63,
      })
    } finally {
      setDurBusy(false)
    }
  }

  async function pickTarget(sec: number, label: string) {
    if (projectId !== '') {
      try {
        await api.setProjectTarget(Number(projectId), sec)
        setTargetMsg(`目標尺を ${sec}秒（${label}）に設定しました。編集にも共有されます。`)
      } catch (e) {
        setError((e as Error).message)
      }
    } else {
      setTargetMsg(
        `目標尺 ${sec}秒（${label}）。プロジェクトを選ぶと編集にも共有できます。`,
      )
    }
  }

  // ステップ実行モード
  const [runIdx, setRunIdx] = useState<number | null>(null)
  const [remaining, setRemaining] = useState(0)
  const nextRef = useRef<() => void>(() => {})

  // 自動画面録画（音声つき）
  const canRecord = !!window.videocraft?.screenRecord
  const recRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null) // 画面
  const micStreamRef = useRef<MediaStream | null>(null) // マイク
  const audioCtxRef = useRef<AudioContext | null>(null) // ミックス用
  const micGainRef = useRef<GainNode | null>(null) // マイク音量
  const sysGainRef = useRef<GainNode | null>(null) // システム音量
  const chunksRef = useRef<Blob[]>([])
  const previewRef = useRef<HTMLVideoElement>(null) // ライブプレビュー
  const [recording, setRecording] = useState(false)
  const [savedPath, setSavedPath] = useState<string | null>(null)
  const [micOn, setMicOn] = useState(true)
  const [sysAudioOn, setSysAudioOn] = useState(false)
  const [micVol, setMicVol] = useState(1) // 0〜2（100%基準）
  const [sysVol, setSysVol] = useState(1)
  // ※録画対象の選択は録画スタジオ(RecordingStudio)側に一本化（重複UIを削除）

  // スタジオ内タブ（タブ以外は画面全体を使う）
  const [recTab, setRecTab] = useState<'studio' | 'auto' | 'yukkuri'>('studio')

  // AI自動撮影・ゆっくり動画（統合）: 方式（映像ソース）
  const [genSource, setGenSource] = useState<'web' | 'desktop' | 'yukkuri'>('web')
  const [apMode, setApMode] = useState<'web' | 'desktop'>('web')

  function setSource(s: 'web' | 'desktop' | 'yukkuri') {
    setGenSource(s)
    if (s !== 'yukkuri') {
      setApMode(s)
      setApPlan(null)
      setApResult(null)
      setApError(null)
      if (s === 'desktop') loadWindows()
    }
  }
  const [apUrl, setApUrl] = useState('')
  const [apWindow, setApWindow] = useState('') // 対象ウィンドウ（デスクトップ）
  const [apWindows, setApWindows] = useState<string[]>([])
  // AI VideoCraft 自体を撮影（別ウィンドウを開いてそこを撮る）
  const [apSelfRec, setApSelfRec] = useState(false)
  const [apTopic, setApTopic] = useState('')
  const [apInstructions, setApInstructions] = useState('') // 手順の指示
  const [apVoice, setApVoice] = useState('ja-JP-NanamiNeural')
  const [apVoices, setApVoices] = useState<AutopilotVoice[]>([])
  const [apPlan, setApPlan] = useState<AutopilotPlan | DesktopPlan | null>(null)
  const [apResult, setApResult] = useState<AutopilotRunResponse | null>(null)
  const [apBusy, setApBusy] = useState<'' | 'plan' | 'run'>('')
  const [apError, setApError] = useState<string | null>(null)
  const [apSubs, setApSubs] = useState(true) // ナレーションを字幕で焼き込む
  const [apUrls, setApUrls] = useState<string[]>([]) // 追加のページ（複数URL）
  const [apConfirm, setApConfirm] = useState(false) // 実行前の確認ダイアログ
  const apTokenRef = useRef('') // キャンセル用トークン
  const [apCancelling, setApCancelling] = useState(false)

  // デスクトップ: 開いているウィンドウ一覧を取得
  function loadWindows() {
    api
      .desktopWindows()
      .then((r) => {
        setApWindows(r.windows)
        if (r.windows[0] && !apWindow) setApWindow(r.windows[0])
      })
      .catch(() => {})
  }

  // 録画中でもリアルタイムに音量を反映
  function changeMicVol(v: number) {
    setMicVol(v)
    if (micGainRef.current) micGainRef.current.gain.value = v
  }
  function changeSysVol(v: number) {
    setSysVol(v)
    if (sysGainRef.current) sysGainRef.current.gain.value = v
  }

  function cleanupStreams() {
    streamRef.current?.getTracks().forEach((t) => t.stop())
    micStreamRef.current?.getTracks().forEach((t) => t.stop())
    audioCtxRef.current?.close().catch(() => {})
    streamRef.current = null
    micStreamRef.current = null
    audioCtxRef.current = null
    micGainRef.current = null
    sysGainRef.current = null
  }

  async function startRecording(): Promise<boolean> {
    setSavedPath(null)
    setError(null)
    try {
      // 画面（＋任意でシステム音声）。cursor:'motion' で静止時はカーソルを映さない
      const display = await navigator.mediaDevices.getDisplayMedia({
        video: { cursor: 'motion' } as MediaTrackConstraints,
        audio: sysAudioOn,
      })
      streamRef.current = display

      // 音声ソース（システム音声 / マイク）をゲイン付きで集める
      const audioInputs: {
        stream: MediaStream
        vol: number
        assign: (g: GainNode) => void
      }[] = []
      if (sysAudioOn && display.getAudioTracks().length > 0) {
        audioInputs.push({
          stream: new MediaStream(display.getAudioTracks()),
          vol: sysVol,
          assign: (g) => (sysGainRef.current = g),
        })
      }
      if (micOn) {
        const mic = await navigator.mediaDevices.getUserMedia({ audio: true })
        micStreamRef.current = mic
        audioInputs.push({
          stream: mic,
          vol: micVol,
          assign: (g) => (micGainRef.current = g),
        })
      }

      // 映像 + 音声（各ソースをゲイン経由でミックスして1トラックに）
      const tracks: MediaStreamTrack[] = [display.getVideoTracks()[0]]
      if (audioInputs.length > 0) {
        const ctx = new AudioContext()
        audioCtxRef.current = ctx
        const dest = ctx.createMediaStreamDestination()
        for (const inp of audioInputs) {
          const src = ctx.createMediaStreamSource(inp.stream)
          const gain = ctx.createGain()
          gain.gain.value = inp.vol
          src.connect(gain).connect(dest)
          inp.assign(gain)
        }
        tracks.push(dest.stream.getAudioTracks()[0])
      }
      const finalStream = new MediaStream(tracks)

      chunksRef.current = []
      const mime = MediaRecorder.isTypeSupported('video/webm;codecs=vp9,opus')
        ? 'video/webm;codecs=vp9,opus'
        : 'video/webm'
      const rec = new MediaRecorder(finalStream, { mimeType: mime })
      rec.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }
      rec.onstop = async () => {
        const blob = new Blob(chunksRef.current, { type: 'video/webm' })
        const buf = await blob.arrayBuffer()
        const name = `AIVideoCraft_${Date.now()}.mp4`
        const p = await window.videocraft?.screenRecord?.save(buf, name)
        setSavedPath(p ?? null)
        if (p) window.videocraft?.showItemInFolder?.(p) // 保存先を自動で開く
        cleanupStreams()
      }
      // OS側で共有を止めた場合も停止
      display.getVideoTracks()[0].addEventListener('ended', () => stopRecording())
      rec.start()
      recRef.current = rec
      setRecording(true)
      return true
    } catch (e) {
      cleanupStreams()
      setError('画面録画を開始できませんでした: ' + (e as Error).message)
      return false
    }
  }

  function stopRecording() {
    if (recRef.current && recRef.current.state !== 'inactive') {
      recRef.current.stop()
    }
    recRef.current = null
    setRecording(false)
  }

  async function startAutoRecord() {
    const ok = await startRecording()
    if (ok) setRunIdx(0)
  }

  function finishRun() {
    if (recording) stopRecording() // 停止→保存ダイアログ
    setRunIdx(null)
  }

  useEffect(() => {
    api.listProviders().then((ps) => {
      setProviders(ps)
      const first = ps.find((p) => p.configured) ?? ps[0]
      if (first) setProvider(first.id)
    })
    api.listProjects().then(setProjects)
    api
      .autopilotVoices()
      .then((r) => {
        setApVoices(r.voices)
        if (r.voices[0]) setApVoice(r.voices[0].id)
      })
      .catch(() => {})
    // AI企画から「録画支援へ送る」で渡された企画を反映
    if (handoff.recordingPlan) {
      const rp = handoff.recordingPlan
      handoff.recordingPlan = undefined
      if (rp.topic) {
        setTopic(rp.topic)
        setApTopic(rp.topic)
      }
      if (rp.instructions) {
        setNotes(rp.instructions)
        setApInstructions(rp.instructions)
      }
      if (rp.target_duration_sec) setTargetMsg(
        `AI企画から目標尺 約${Math.round(rp.target_duration_sec)}秒 を引き継ぎました。`,
      )
    }
  }, [])

  async function genAutoPlan() {
    if (apBusy) return
    if (apMode === 'web' && !apUrl.trim()) {
      setApError('対象サイトのURLを入力してください。')
      return
    }
    if (apMode === 'desktop' && !apSelfRec && !apWindow.trim()) {
      setApError('対象のアプリ（ウィンドウ）を選んでください。')
      return
    }
    setApBusy('plan')
    setApError(null)
    setApResult(null)
    try {
      if (apMode === 'web') {
        const allUrls = [apUrl.trim(), ...apUrls.map((u) => u.trim())].filter(
          Boolean,
        )
        const res = await api.autopilotPlan({
          url: apUrl.trim(),
          urls: allUrls,
          topic: apTopic.trim() || undefined,
          instructions: apInstructions.trim() || undefined,
          provider,
          model: model || undefined,
        })
        setApPlan(res.plan)
      } else {
        const res = await api.desktopPlan({
          window_title: apSelfRec ? REC_WINDOW_TITLE : apWindow,
          topic: apTopic.trim() || undefined,
          instructions: apInstructions.trim() || undefined,
          provider,
          model: model || undefined,
        })
        setApPlan(res.plan)
      }
    } catch (e) {
      setApError((e as Error).message)
    } finally {
      setApBusy('')
    }
  }

  // 確認ダイアログを開く
  function requestRun() {
    if (apBusy || !apPlan) return
    setApConfirm(true)
  }

  // 実行中の自動操作をキャンセル
  function cancelRun() {
    if (apBusy !== 'run' || apCancelling) return
    setApCancelling(true)
    api.autopilotCancel(apTokenRef.current).catch(() => {})
  }

  // 自動操作中は「Escキーでキャンセル」。
  // ※以前は「どれか入力」でキャンセルしていたが、AIVideoCraft自身を撮影/操作すると
  //   AIのクリックや入力が自己キャンセルを誘発するため、Escキー限定にする。
  useEffect(() => {
    if (apBusy !== 'run') return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') cancelRun()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apBusy, apCancelling])

  async function runAuto() {
    if (apBusy || !apPlan) return
    const token =
      (window.crypto?.randomUUID?.() as string) || String(Math.random())
    apTokenRef.current = token
    setApCancelling(false)
    setApBusy('run')
    setApError(null)
    setApResult(null)
    // AI VideoCraft 自体を撮る場合は、別ウィンドウを開いてそこを撮影対象にする
    let openedRecWin = false
    try {
      const allUrls = [apUrl.trim(), ...apUrls.map((u) => u.trim())].filter(
        Boolean,
      )
      let res
      if (apMode === 'web') {
        res = await api.autopilotRun(
          apPlan as AutopilotPlan,
          apVoice,
          apSubs,
          false,
          '霊夢',
          allUrls,
          token,
        )
      } else {
        if (apSelfRec) {
          await window.videocraft?.openRecWindow?.() // 撮影用の別ウィンドウを開く
          openedRecWin = true
          await new Promise((r) => setTimeout(r, 1600)) // 表示を待つ
        }
        res = await api.desktopRun(
          apPlan as DesktopPlan,
          apVoice,
          apSubs,
          token,
        )
      }
      setApResult(res)
      if (res.video_path) window.videocraft?.showItemInFolder?.(res.video_path)
    } catch (e) {
      setApError((e as Error).message)
    } finally {
      setApBusy('')
      if (openedRecWin) window.videocraft?.closeRecWindow?.() // 撮影用ウィンドウを閉じる
    }
  }

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

  // 録画中は画面ストリームをプレビューに映す
  useEffect(() => {
    const v = previewRef.current
    if (recording && v && streamRef.current) {
      v.srcObject = streamRef.current
      v.play?.().catch(() => {})
    } else if (v) {
      v.srcObject = null
    }
  }, [recording])

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
          <button className="btn ghost" onClick={finishRun}>
            ← {recording ? '録画停止して保存' : 'ガイド終了'}
          </button>
          <span className="muted">
            {recording && <span className="rec-dot">● REC</span>} ステップ{' '}
            {runIdx + 1} / {steps.length}
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

        {recording && (micOn || sysAudioOn) && (
          <div className="runner-vol">
            {micOn && (
              <VolumeRow label="🎤 マイク" value={micVol} onChange={changeMicVol} />
            )}
            {sysAudioOn && (
              <VolumeRow label="🔊 システム" value={sysVol} onChange={changeSysVol} />
            )}
          </div>
        )}

        <div className="runner-controls">
          <button
            className="btn ghost"
            disabled={runIdx === 0}
            onClick={() => setRunIdx((i) => Math.max(0, (i ?? 0) - 1))}
          >
            前へ
          </button>
          {isLast ? (
            <button className="btn primary" onClick={finishRun}>
              {recording ? '完了して保存 🎬' : '完了 🎉'}
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
    <div className="page studio-page">
      <h1>
        <span className="gradient-text">録画スタジオ</span>
      </h1>
      <p className="subtitle">
        OBS風の録画スタジオ・AI自動撮影・ゆっくり動画。タブで切り替えて、画面全体を使って制作できます。
      </p>

      <div className="studio-tabs">
        <button
          className={`studio-tab ${recTab === 'studio' ? 'active' : ''}`}
          onClick={() => setRecTab('studio')}
        >
          🎬 スタジオ録画
        </button>
        <button
          className={`studio-tab ${recTab === 'auto' ? 'active' : ''}`}
          onClick={() => setRecTab('auto')}
        >
          🤖 AI自動撮影
        </button>
        <button
          className={`studio-tab ${recTab === 'yukkuri' ? 'active' : ''}`}
          onClick={() => setRecTab('yukkuri')}
        >
          🗣️ ゆっくり動画
        </button>
      </div>

      {/* OBS風 録画スタジオ（ウェブカメラ合成・音声ミキサー・オーバーレイ） */}
      {recTab === 'studio' && <RecordingStudio />}

      {/* AI自動撮影（ブラウザ自動操作＋AIナレーション） */}
      {recTab === 'auto' && (
        <>
      <section className="card autostudio-card">
        <h2>🤖 AI自動撮影</h2>
        <p className="muted lic-intro">
          AIにブラウザ/アプリを自動操作させて録画します。手順を書けばその通りに、空欄ならAIが構成します。
          （ゆっくり解説・実況は上の「🗣️ ゆっくり動画」タブから）
        </p>

        {/* 方式（映像ソース）切替 */}
        <div className="ap-mode">
          <button
            className={`ap-mode-btn ${genSource === 'web' ? 'active' : ''}`}
            onClick={() => setSource('web')}
          >
            🌐 ブラウザ自動操作
          </button>
          <button
            className={`ap-mode-btn ${genSource === 'desktop' ? 'active' : ''}`}
            onClick={() => setSource('desktop')}
          >
            🖥️ アプリ自動操作
          </button>
        </div>

        {genSource !== 'yukkuri' && (
          <>
            {apMode === 'web' ? (
              <>
                <input
                  className="input"
                  placeholder="対象サイトのURL（例: https://example.com）"
                  value={apUrl}
                  onChange={(e) => setApUrl(e.target.value)}
                />
            {apUrls.map((u, i) => (
              <div className="row edit-row" key={i}>
                <input
                  className="input"
                  placeholder="追加ページのURL（AIがこの範囲で行き来します）"
                  value={u}
                  onChange={(e) => {
                    const n = [...apUrls]
                    n[i] = e.target.value
                    setApUrls(n)
                  }}
                />
                <button
                  className="btn ghost sm"
                  onClick={() => setApUrls(apUrls.filter((_, j) => j !== i))}
                >
                  ✕
                </button>
              </div>
            ))}
            <button
              className="btn ghost sm"
              onClick={() => setApUrls([...apUrls, ''])}
            >
              ＋ ページを追加（複数指定でAIが移動）
            </button>
          </>
        ) : (
          <>
            <label className="check">
              <input
                type="checkbox"
                checked={apSelfRec}
                onChange={(e) => setApSelfRec(e.target.checked)}
              />
              🖥️ AI VideoCraft 自体を撮影する（別ウィンドウを自動で開いて撮影し、終了後に閉じる）
            </label>
            {!apSelfRec && (
              <>
                <div className="row">
                  <select
                    className="input"
                    value={apWindow}
                    onChange={(e) => setApWindow(e.target.value)}
                  >
                    {apWindows.length === 0 && (
                      <option value="">（開いているアプリがありません）</option>
                    )}
                    {apWindows.map((w) => (
                      <option key={w} value={w}>
                        {w}
                      </option>
                    ))}
                  </select>
                  <button className="btn ghost" onClick={loadWindows}>
                    🔄 更新
                  </button>
                </div>
                <p className="muted vol-hint">
                  撮影したいアプリを起動して「更新」で選択してください。録画中はそのウィンドウを最前面に表示しておいてください。
                </p>
              </>
            )}
            {apSelfRec && (
              <p className="muted vol-hint">
                「② 自動撮影を実行」を押すと、AI VideoCraft をもう一つ別ウィンドウで開き、
                そのウィンドウをAIが操作しながら撮影します（本体ウィンドウは操作されません）。終了後に自動で閉じます。
              </p>
            )}
          </>
        )}
        <div className="plan-form-grid">
          <label>
            テーマ（任意）
            <input
              className="input"
              placeholder="例: このサービスの使い方紹介"
              value={apTopic}
              onChange={(e) => setApTopic(e.target.value)}
            />
          </label>
          <label>
            ナレーション音声
            <select value={apVoice} onChange={(e) => setApVoice(e.target.value)}>
              {apVoices.length === 0 && <option value={apVoice}>標準</option>}
              {apVoices.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        {/* 尺の候補（テーマの下に配置）*/}
        <div className="dur-box dur-panel">
          <button className="btn ghost" onClick={suggestDur} disabled={durBusy}>
            {durBusy ? '尺を計算中…' : '📏 尺の候補を出す（動画用 / ショート用）'}
          </button>
          {durSug && (
            <div className="dur-cands">
              <div className="dur-card">
                <div className="dur-title">🎬 動画用</div>
                <div className="dur-sec">{durSug.video_sec}秒</div>
                <div className="muted dur-rec">
                  録画目安 {durSug.record_video_sec}秒（カット分を見込む）
                </div>
                <button
                  className="btn ghost sm"
                  onClick={() => pickTarget(durSug.video_sec, '動画用')}
                >
                  この尺を採用
                </button>
              </div>
              <div className="dur-card">
                <div className="dur-title">📱 ショート用</div>
                <div className="dur-sec">{durSug.short_sec}秒</div>
                <div className="muted dur-rec">
                  録画目安 {durSug.record_short_sec}秒（カット分を見込む）
                </div>
                <button
                  className="btn ghost sm"
                  onClick={() => pickTarget(durSug.short_sec, 'ショート用')}
                >
                  この尺を採用
                </button>
              </div>
            </div>
          )}
          {durSug?.note && <p className="muted vol-hint">💡 {durSug.note}</p>}
          {targetMsg && <div className="lic-ok">{targetMsg}</div>}
        </div>

        <textarea
          className="input"
          rows={3}
          placeholder={
            apMode === 'web'
              ? 'AIへの手順の指示（任意・1行に1つ）\n例）トップページを紹介 / 「Learn more」をクリック / 開いたページを説明'
              : 'AIへの手順の指示（任意・1行に1つ）\n例）メニューの「ファイル」を開く / ツールバーを紹介 / 使い方を説明'
          }
          value={apInstructions}
          onChange={(e) => setApInstructions(e.target.value)}
        />
        <p className="muted vol-hint">
          🎬 手順を書くと、その通りにAIが操作・解説して録画します。空欄ならAIが自動で構成します。
        </p>

        <label className="check">
          <input
            type="checkbox"
            checked={apSubs}
            onChange={(e) => setApSubs(e.target.checked)}
          />
          🔤 ナレーションを字幕で表示（動画に焼き込み）
        </label>
        <p className="muted vol-hint">
          🗣️ ゆっくり解説・実況（キャラ＋声）にしたい場合は、上の「方式」で「ゆっくり動画」を選んでください。
        </p>

        <div className="run-actions">
          <button className="btn" onClick={genAutoPlan} disabled={apBusy !== ''}>
            {apBusy === 'plan' ? '台本を生成中…' : '① 台本を生成'}
          </button>
          {apPlan && (
            <button
              className="btn primary"
              onClick={requestRun}
              disabled={apBusy !== ''}
            >
              {apBusy === 'run' ? '🎬 撮影中…' : '② 自動撮影を実行'}
            </button>
          )}
        </div>

        {/* 実行前の確認ダイアログ */}
        {apConfirm && (
          <div className="modal-backdrop" onClick={() => setApConfirm(false)}>
            <div className="modal-card" onClick={(e) => e.stopPropagation()}>
              <h3>🤖 自動撮影を開始します</h3>
              <ul className="confirm-list">
                <li>
                  ✋ <b>操作はできません</b>：撮影中はAIが自動で操作します。あなたは操作しないでください。
                </li>
                <li>
                  🛑 <b>キャンセル方法</b>：撮影中に<b>Esc キー</b>を押すと即座に中止します。
                </li>
                <li>
                  🔒 <b>安全</b>：
                  {apMode === 'web'
                    ? '指定したページ以外は開きません。'
                    : '指定したウィンドウのみを操作・録画します。'}
                </li>
              </ul>
              <div className="run-actions">
                <button
                  className="btn primary"
                  onClick={() => {
                    setApConfirm(false)
                    runAuto()
                  }}
                >
                  開始する
                </button>
                <button className="btn ghost" onClick={() => setApConfirm(false)}>
                  やめる
                </button>
              </div>
            </div>
          </div>
        )}

        {/* 操作中の警告オーバーレイ（Escキーでキャンセル）。
            デスクトップ撮影時は、この画面自体が録画に映り込まないよう表示しない。 */}
        {apBusy === 'run' && apMode !== 'desktop' && (
          <div className="ai-overlay">
            <div className="ai-overlay-inner">
              <div className="ai-overlay-spin" />
              <div className="ai-overlay-title">
                {apCancelling ? '⏹ キャンセル中…' : '🤖 AIが操作・撮影中'}
              </div>
              <div className="ai-overlay-sub">
                {apCancelling
                  ? 'まもなく停止します…'
                  : '操作しないでください。中止するには Esc キーを押してください。'}
              </div>
            </div>
          </div>
        )}

        {apError && <div className="banner error">{apError}</div>}
        {apBusy === 'run' && (
          <p className="muted rec-note">
            ブラウザ操作・録画・ナレーション合成を実行中です（30秒〜数分かかります）…
          </p>
        )}

        {apPlan && (
          <div className="ap-plan">
            <div className="field-label">
              台本：{apPlan.title || (apMode === 'web' ? apUrl : apWindow)}（
              {apPlan.steps.length}ステップ）
            </div>
            <ol className="step-list">
              {apPlan.steps.map((s, i) => (
                <li key={i} className="step-row">
                  <div className="step-num">{i + 1}</div>
                  <div className="step-kind k-action">
                    <span>{AP_ICON[s.action] ?? '•'}</span>
                    {AP_LABEL[s.action] ?? s.action}
                  </div>
                  <div className="step-body">
                    <div className="step-title">
                      {s.target || s.title || AP_LABEL[s.action]}
                      {s.value && <span className="muted"> → {s.value}</span>}
                    </div>
                    <div className="step-instruction muted">🗣 {s.narration}</div>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        )}

        {apResult && (
          <div className="ap-result lic-ok">
            🎬 動画を作成しました（約{Math.round(apResult.duration_sec)}秒 /{' '}
            {apResult.steps_run}ステップ）
            <div className="run-actions">
              <button
                className="btn ghost sm"
                onClick={() => window.videocraft?.openPath?.(apResult.video_path)}
              >
                ▶ 再生
              </button>
              <button
                className="btn ghost sm"
                onClick={() =>
                  window.videocraft?.showItemInFolder?.(apResult.video_path)
                }
              >
                📁 フォルダを開く
              </button>
              <button
                className="btn primary sm"
                onClick={() => sendToEditing(apResult.video_path)}
              >
                ✂️ 編集スタジオへ送る
              </button>
            </div>
            <div className="muted ap-path">{apResult.video_path}</div>
            {apResult.warnings.length > 0 && (
              <ul className="ap-warn">
                {apResult.warnings.map((w, i) => (
                  <li key={i}>⚠️ {w}</li>
                ))}
              </ul>
            )}
          </div>
        )}
          {/* 録画ガイド（手動録画の手順をAIが作成）＋ AI設定（自動撮影と共通）*/}
          <div className="field-label" style={{ marginTop: 12 }}>
            📋 録画ガイドを作る（手動録画用の手順をAIが作成／AI設定は自動撮影と共通）
          </div>
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
          </>
        )}
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

          {canRecord && (
            <div className="audio-opts">
              <label className="check">
                <input
                  type="checkbox"
                  checked={micOn}
                  onChange={(e) => setMicOn(e.target.checked)}
                />
                🎤 マイク音声（ナレーション）
              </label>
              <label className="check">
                <input
                  type="checkbox"
                  checked={sysAudioOn}
                  onChange={(e) => setSysAudioOn(e.target.checked)}
                />
                🔊 システム音声（PCの音）
              </label>
            </div>
          )}
          {canRecord && (micOn || sysAudioOn) && (
            <div className="vol-rows">
              {micOn && (
                <VolumeRow
                  label="🎤 マイク音量"
                  value={micVol}
                  onChange={changeMicVol}
                />
              )}
              {sysAudioOn && (
                <VolumeRow
                  label="🔊 システム音量"
                  value={sysVol}
                  onChange={changeSysVol}
                />
              )}
              {micOn && sysAudioOn && (
                <p className="muted vol-hint">
                  ナレーションを主役にするならマイクを大きめ・システムを小さめに。
                </p>
              )}
            </div>
          )}
          <div className="run-actions">
            <button className="btn ghost run-btn" onClick={() => setRunIdx(0)}>
              ▶ ガイドを開始（手動録画）
            </button>
            {canRecord && (
              <button className="btn primary run-btn" onClick={startAutoRecord}>
                🔴 自動録画で撮影
              </button>
            )}
          </div>
          {canRecord ? (
            <p className="muted rec-note">
              「自動録画で撮影」を押すと、アプリが画面録画を開始しガイドに沿って進行、
              完了時に停止して動画ファイルを保存します（録画の操作は不要）。
            </p>
          ) : (
            <p className="muted rec-note">
              自動録画はデスクトップアプリ版で利用できます。
            </p>
          )}
          {savedPath && (
            <div className="lic-ok">
              録画を保存しました：{savedPath}
              <div className="run-actions">
                <button
                  className="btn primary sm"
                  onClick={() => sendToEditing(savedPath)}
                >
                  ✂️ 編集スタジオへ送る
                </button>
              </div>
            </div>
          )}

          <ol className="step-list">
            {steps.map((s, i) => (
              <StepRow key={i} step={s} index={i} />
            ))}
          </ol>
        </section>
      )}
        </>
      )}

      {recTab === 'yukkuri' && <YukkuriPage />}
    </div>
  )
}

function VolumeRow({
  label,
  value,
  onChange,
}: {
  label: string
  value: number
  onChange: (v: number) => void
}) {
  return (
    <div className="vol-row">
      <span className="vol-label">{label}</span>
      <input
        type="range"
        min={0}
        max={2}
        step={0.05}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="vol-slider"
      />
      <span className="vol-val">{Math.round(value * 100)}%</span>
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
