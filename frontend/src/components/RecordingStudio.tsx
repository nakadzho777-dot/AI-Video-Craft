import { useEffect, useRef, useState } from 'react'

// OBS風 録画スタジオ：画面＋ウェブカメラ(PIP)＋テキスト/画像オーバーレイを
// canvasで合成し、マイク/システム音声をミキサー(メーター付き)でまとめて録画する。

const W = 1280
const H = 720

type TextOverlay = {
  id: number
  text: string
  x: number // 0..1
  y: number // 0..1
  size: number
  color: string
  stroke: string
}
type ImgOverlay = { id: number; img: HTMLImageElement; x: number; y: number; w: number }
type PipPos = 'tr' | 'tl' | 'br' | 'bl'
type WebcamMode = 'off' | 'pip' | 'full'
type Scene = {
  id: number
  name: string
  webcamMode: WebcamMode
  pipPos: PipPos
  pipSize: number
  screenOn: boolean
  texts: TextOverlay[]
  imgs: ImgOverlay[]
}

function fmtClock(sec: number): string {
  const m = Math.floor(sec / 60)
  return `${m}:${String(sec % 60).padStart(2, '0')}`
}

let _oid = 1

export default function RecordingStudio() {
  const canRecord = !!window.videocraft?.screenRecord

  const [sources, setSources] = useState<
    { id: string; name: string; kind: 'screen' | 'window' }[]
  >([])
  const [sourceId, setSourceId] = useState('') // '' = 画面全体
  const [selfRec, setSelfRec] = useState(false) // AI VideoCraft 本体を撮影
  const [webcamMode, setWebcamMode] = useState<WebcamMode>('off')
  const [screenOn, setScreenOn] = useState(true)
  const [micOn, setMicOn] = useState(true)
  const [sysOn, setSysOn] = useState(false)
  const [micVol, setMicVol] = useState(1)
  const [sysVol, setSysVol] = useState(0.7)
  const [pipPos, setPipPos] = useState<PipPos>('br')
  const [pipSize, setPipSize] = useState(24) // 幅の%
  const [texts, setTexts] = useState<TextOverlay[]>([])
  const [imgs, setImgs] = useState<ImgOverlay[]>([])
  const [newText, setNewText] = useState('')

  const [preview, setPreview] = useState(false)
  const [recording, setRecording] = useState(false)
  const [paused, setPaused] = useState(false)
  const [scenes, setScenes] = useState<Scene[]>([])
  const [newSceneName, setNewSceneName] = useState('')
  const [recSec, setRecSec] = useState(0)
  const [savedPath, setSavedPath] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [micLevel, setMicLevel] = useState(0)
  const [sysLevel, setSysLevel] = useState(0)

  const canvasRef = useRef<HTMLCanvasElement>(null)
  const screenVideoRef = useRef<HTMLVideoElement>(null)
  const webcamVideoRef = useRef<HTMLVideoElement>(null)
  const screenStreamRef = useRef<MediaStream | null>(null)
  const webcamStreamRef = useRef<MediaStream | null>(null)
  const micStreamRef = useRef<MediaStream | null>(null)
  const audioCtxRef = useRef<AudioContext | null>(null)
  const micGainRef = useRef<GainNode | null>(null)
  const sysGainRef = useRef<GainNode | null>(null)
  const micAnaRef = useRef<AnalyserNode | null>(null)
  const sysAnaRef = useRef<AnalyserNode | null>(null)
  const destRef = useRef<MediaStreamAudioDestinationNode | null>(null)
  const rafRef = useRef<number | null>(null)
  const meterTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const recTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const recRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const selfRecOpenRef = useRef(false) // 撮影用ウィンドウを開いたか

  // RAF から最新値を読むための ref
  const textsRef = useRef(texts)
  const imgsRef = useRef(imgs)
  const pipRef = useRef({
    pos: pipPos,
    size: pipSize,
    mode: webcamMode,
    screen: screenOn,
  })
  useEffect(() => {
    textsRef.current = texts
  }, [texts])
  useEffect(() => {
    imgsRef.current = imgs
  }, [imgs])
  useEffect(() => {
    pipRef.current = {
      pos: pipPos,
      size: pipSize,
      mode: webcamMode,
      screen: screenOn,
    }
  }, [pipPos, pipSize, webcamMode, screenOn])

  useEffect(() => {
    loadSources()
    return () => stopPreview()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function loadSources() {
    window.videocraft?.screenRecord
      ?.listSources?.()
      .then(setSources)
      .catch(() => {})
  }

  function pipXY(pos: PipPos, pw: number, ph: number): [number, number] {
    const m = 24
    switch (pos) {
      case 'tl':
        return [m, m]
      case 'tr':
        return [W - pw - m, m]
      case 'bl':
        return [m, H - ph - m]
      default:
        return [W - pw - m, H - ph - m]
    }
  }

  function drawCover(
    ctx: CanvasRenderingContext2D,
    v: HTMLVideoElement,
  ) {
    const vw = v.videoWidth
    const vh = v.videoHeight
    if (!vw || !vh) return
    const scale = Math.max(W / vw, H / vh)
    const dw = vw * scale
    const dh = vh * scale
    ctx.drawImage(v, (W - dw) / 2, (H - dh) / 2, dw, dh)
  }

  function level(ana: AnalyserNode | null): number {
    if (!ana) return 0
    const buf = new Uint8Array(ana.fftSize)
    ana.getByteTimeDomainData(buf)
    let sum = 0
    for (let i = 0; i < buf.length; i++) {
      const x = (buf[i] - 128) / 128
      sum += x * x
    }
    return Math.min(1, Math.sqrt(sum / buf.length) * 3)
  }

  function startLoop() {
    const canvas = canvasRef.current
    const ctx = canvas?.getContext('2d')
    if (!ctx) return
    const draw = () => {
      ctx.fillStyle = '#05050c'
      ctx.fillRect(0, 0, W, H)
      const sv = screenVideoRef.current
      const wv = webcamVideoRef.current
      const pip = pipRef.current
      // 画面キャプチャ（screen ON のとき）
      if (pip.screen && sv) drawCover(ctx, sv)
      // ウェブカメラ: full=全面 / pip=隅
      if (pip.mode === 'full' && wv && wv.videoWidth) {
        drawCover(ctx, wv)
      } else if (pip.mode === 'pip' && wv && wv.videoWidth) {
        const pw = (W * pip.size) / 100
        const ph = pw * (wv.videoHeight / wv.videoWidth)
        const [px, py] = pipXY(pip.pos, pw, ph)
        ctx.drawImage(wv, px, py, pw, ph)
        ctx.strokeStyle = '#7c5cff'
        ctx.lineWidth = 4
        ctx.strokeRect(px, py, pw, ph)
      }
      for (const o of imgsRef.current) {
        const iw = o.w * W
        const ih = iw * (o.img.height / o.img.width)
        ctx.drawImage(o.img, o.x * W, o.y * H, iw, ih)
      }
      for (const t of textsRef.current) {
        ctx.font = `bold ${t.size}px Meiryo, "Segoe UI", sans-serif`
        ctx.textAlign = 'left'
        ctx.textBaseline = 'middle'
        ctx.lineJoin = 'round'
        ctx.lineWidth = Math.max(2, t.size / 6)
        ctx.strokeStyle = t.stroke
        ctx.strokeText(t.text, t.x * W, t.y * H)
        ctx.fillStyle = t.color
        ctx.fillText(t.text, t.x * W, t.y * H)
      }
      rafRef.current = requestAnimationFrame(draw)
    }
    rafRef.current = requestAnimationFrame(draw)
  }

  // ウェブカメラを（必要なら）取得する。シーン切替で後から使う場合にも呼ぶ
  async function ensureWebcam() {
    if (webcamStreamRef.current) return
    try {
      const cam = await navigator.mediaDevices.getUserMedia({ video: true })
      webcamStreamRef.current = cam
      if (webcamVideoRef.current) {
        webcamVideoRef.current.srcObject = cam
        await webcamVideoRef.current.play().catch(() => {})
      }
    } catch {
      setError('ウェブカメラを取得できませんでした。')
    }
  }

  async function startPreview() {
    setError(null)
    setSavedPath(null)
    try {
      if (selfRec) {
        // AI VideoCraft 本体を撮る: 別ウィンドウを開き、それを撮影対象にする
        await window.videocraft?.openRecWindow?.()
        selfRecOpenRef.current = true
        await new Promise((r) => setTimeout(r, 1400)) // 表示待ち
        const srcs = (await window.videocraft?.screenRecord?.listSources?.()) ?? []
        const rec =
          srcs.find((s) => /録画用/.test(s.name)) ??
          srcs.find((s) => /videocraft/i.test(s.name))
        await window.videocraft?.screenRecord?.setSource?.(rec?.id ?? null)
      } else {
        await window.videocraft?.screenRecord?.setSource?.(sourceId || null)
      }
      const screen = await navigator.mediaDevices.getDisplayMedia({
        // cursor:'motion' → 動かしている（＝操作中）ときだけカーソルを映す
        video: { cursor: 'motion' } as MediaTrackConstraints,
        audio: sysOn,
      })
      screenStreamRef.current = screen
      if (screenVideoRef.current) {
        screenVideoRef.current.srcObject = screen
        await screenVideoRef.current.play().catch(() => {})
      }
      screen.getVideoTracks()[0]?.addEventListener('ended', () => stopPreview())

      if (webcamMode !== 'off') await ensureWebcam()

      // 音声ミキサー
      const ctx = new AudioContext()
      audioCtxRef.current = ctx
      const dest = ctx.createMediaStreamDestination()
      destRef.current = dest
      if (sysOn && screen.getAudioTracks().length > 0) {
        const src = ctx.createMediaStreamSource(
          new MediaStream(screen.getAudioTracks()),
        )
        const g = ctx.createGain()
        g.gain.value = sysVol
        sysGainRef.current = g
        const ana = ctx.createAnalyser()
        ana.fftSize = 256
        sysAnaRef.current = ana
        src.connect(g)
        g.connect(dest)
        g.connect(ana)
      }
      if (micOn) {
        const mic = await navigator.mediaDevices.getUserMedia({ audio: true })
        micStreamRef.current = mic
        const src = ctx.createMediaStreamSource(mic)
        const g = ctx.createGain()
        g.gain.value = micVol
        micGainRef.current = g
        const ana = ctx.createAnalyser()
        ana.fftSize = 256
        micAnaRef.current = ana
        src.connect(g)
        g.connect(dest)
        g.connect(ana)
      }

      startLoop()
      meterTimerRef.current = setInterval(() => {
        setMicLevel(level(micAnaRef.current))
        setSysLevel(level(sysAnaRef.current))
      }, 90)
      setPreview(true)
    } catch (e) {
      stopPreview()
      setError('プレビューを開始できませんでした: ' + (e as Error).message)
    }
  }

  function stopPreview() {
    if (recording) stopRec()
    if (rafRef.current) cancelAnimationFrame(rafRef.current)
    if (meterTimerRef.current) clearInterval(meterTimerRef.current)
    rafRef.current = null
    meterTimerRef.current = null
    screenStreamRef.current?.getTracks().forEach((t) => t.stop())
    webcamStreamRef.current?.getTracks().forEach((t) => t.stop())
    micStreamRef.current?.getTracks().forEach((t) => t.stop())
    audioCtxRef.current?.close().catch(() => {})
    screenStreamRef.current = null
    webcamStreamRef.current = null
    micStreamRef.current = null
    audioCtxRef.current = null
    micGainRef.current = null
    sysGainRef.current = null
    micAnaRef.current = null
    sysAnaRef.current = null
    destRef.current = null
    if (selfRecOpenRef.current) {
      window.videocraft?.closeRecWindow?.() // 撮影用ウィンドウを閉じる
      selfRecOpenRef.current = false
    }
    setMicLevel(0)
    setSysLevel(0)
    setPreview(false)
  }

  function startRec() {
    const canvas = canvasRef.current
    if (!canvas || !preview) return
    try {
      const vstream = canvas.captureStream(30)
      const tracks: MediaStreamTrack[] = [...vstream.getVideoTracks()]
      if (destRef.current) tracks.push(...destRef.current.stream.getAudioTracks())
      const combined = new MediaStream(tracks)
      const mime = MediaRecorder.isTypeSupported('video/webm;codecs=vp9,opus')
        ? 'video/webm;codecs=vp9,opus'
        : 'video/webm'
      const rec = new MediaRecorder(combined, { mimeType: mime })
      chunksRef.current = []
      rec.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }
      rec.onstop = async () => {
        const blob = new Blob(chunksRef.current, { type: 'video/webm' })
        const buf = await blob.arrayBuffer()
        const name = `AIVideoCraft_studio_${Date.now()}.mp4`
        const p = await window.videocraft?.screenRecord?.save(buf, name)
        setSavedPath(p ?? null)
        if (p) window.videocraft?.showItemInFolder?.(p)
      }
      rec.start()
      recRef.current = rec
      setRecording(true)
      setRecSec(0)
      recTimerRef.current = setInterval(() => setRecSec((s) => s + 1), 1000)
    } catch (e) {
      setError('録画を開始できませんでした: ' + (e as Error).message)
    }
  }

  function stopRec() {
    if (recRef.current && recRef.current.state !== 'inactive') recRef.current.stop()
    recRef.current = null
    if (recTimerRef.current) clearInterval(recTimerRef.current)
    recTimerRef.current = null
    setRecording(false)
    setPaused(false)
  }

  function pauseResume() {
    const rec = recRef.current
    if (!rec) return
    if (rec.state === 'recording') {
      rec.pause()
      setPaused(true)
      if (recTimerRef.current) clearInterval(recTimerRef.current)
      recTimerRef.current = null
    } else if (rec.state === 'paused') {
      rec.resume()
      setPaused(false)
      recTimerRef.current = setInterval(() => setRecSec((s) => s + 1), 1000)
    }
  }

  // 現在の構成を「シーン」として保存
  function saveScene() {
    const name = newSceneName.trim() || `シーン ${scenes.length + 1}`
    setScenes((ss) => [
      ...ss,
      {
        id: _oid++,
        name,
        webcamMode,
        pipPos,
        pipSize,
        screenOn,
        texts: texts.map((t) => ({ ...t })),
        imgs: imgs.map((i) => ({ ...i })),
      },
    ])
    setNewSceneName('')
  }

  // 保存済みシーンを適用（録画を止めずに切替可能）
  async function applyScene(s: Scene) {
    if (s.webcamMode !== 'off') await ensureWebcam()
    setWebcamMode(s.webcamMode)
    setPipPos(s.pipPos)
    setPipSize(s.pipSize)
    setScreenOn(s.screenOn)
    setTexts(s.texts.map((t) => ({ ...t })))
    setImgs(s.imgs.map((i) => ({ ...i })))
  }

  function removeScene(id: number) {
    setScenes((ss) => ss.filter((s) => s.id !== id))
  }

  function changeMicVol(v: number) {
    setMicVol(v)
    if (micGainRef.current) micGainRef.current.gain.value = v
  }
  function changeSysVol(v: number) {
    setSysVol(v)
    if (sysGainRef.current) sysGainRef.current.gain.value = v
  }

  function addText() {
    if (!newText.trim()) return
    setTexts((ts) => [
      ...ts,
      {
        id: _oid++,
        text: newText.trim(),
        x: 0.1,
        y: 0.85,
        size: 56,
        color: '#ffffff',
        stroke: '#000000',
      },
    ])
    setNewText('')
  }
  async function addImage() {
    const p = await window.videocraft?.openFileDialog?.('image')
    if (!p) return
    const img = new Image()
    img.onload = () =>
      setImgs((xs) => [
        ...xs,
        { id: _oid++, img, x: 0.72, y: 0.06, w: 0.22 },
      ])
    img.src = 'file:///' + p.replace(/\\/g, '/').replace(/ /g, '%20')
  }

  if (!canRecord) {
    return (
      <section className="card">
        <h2>🎬 録画スタジオ（OBS風）</h2>
        <p className="muted">録画スタジオはデスクトップアプリ版で利用できます。</p>
      </section>
    )
  }

  return (
    <section className="card studio-card">
      <h2>🎬 録画スタジオ（OBS風）</h2>
      <p className="muted lic-intro">
        画面にウェブカメラ・テロップ・ロゴを重ねて録画できます。「プレビュー開始」で配置を確認し、「録画開始」で撮影します。
      </p>

      {/* 隠しビデオ（合成ソース） */}
      <video ref={screenVideoRef} muted playsInline style={{ display: 'none' }} />
      <video ref={webcamVideoRef} muted playsInline style={{ display: 'none' }} />

      <div className="studio-grid">
        {/* プレビュー */}
        <div className="studio-preview">
          <canvas
            ref={canvasRef}
            width={W}
            height={H}
            className="studio-canvas"
          />
          {!preview && <div className="studio-canvas-empty">プレビュー停止中</div>}
          {recording && (
            <div className={`studio-rec-badge${paused ? ' paused' : ''}`}>
              {paused ? '❚❚ 一時停止' : '● REC'} {fmtClock(recSec)}
            </div>
          )}
        </div>

        {/* コントロール */}
        <div className="studio-controls">
          <div className="field-label">映像ソース</div>
          <label className="check">
            <input
              type="checkbox"
              checked={selfRec}
              disabled={preview}
              onChange={(e) => setSelfRec(e.target.checked)}
            />
            🎬 AI VideoCraft 本体を録画（別ウィンドウを自動で開いて撮影）
          </label>
          {!selfRec && (
            <>
              <select
                className="input"
                value={sourceId}
                disabled={preview}
                onChange={(e) => setSourceId(e.target.value)}
              >
                <option value="">🖥️ 画面全体</option>
                {sources
                  .filter((s) => s.kind === 'window')
                  .map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
              </select>
              <button
                className="btn ghost sm"
                onClick={loadSources}
                disabled={preview}
              >
                🔄 一覧を更新
              </button>
            </>
          )}
          {selfRec && (
            <p className="muted vol-hint">
              「プレビュー開始」で AI VideoCraft をもう一つ別ウィンドウで開き、その画面を撮影対象にします（本体ウィンドウは映りません）。停止で自動的に閉じます。
            </p>
          )}

          <div className="field-label">ソース（合成）</div>
          <label className="check">
            <input
              type="checkbox"
              checked={screenOn}
              onChange={(e) => setScreenOn(e.target.checked)}
            />
            🖥️ 画面キャプチャを表示
          </label>
          <div className="field-label sm">🎥 ウェブカメラ</div>
          <div className="pill-row">
            {(['off', 'pip', 'full'] as WebcamMode[]).map((m) => (
              <button
                key={m}
                className={`pill ${webcamMode === m ? 'selected' : ''}`}
                onClick={async () => {
                  if (m !== 'off' && preview) await ensureWebcam()
                  setWebcamMode(m)
                }}
              >
                {{ off: 'なし', pip: 'PIP（隅）', full: '全面' }[m]}
              </button>
            ))}
          </div>
          <label className="check">
            <input
              type="checkbox"
              checked={micOn}
              disabled={preview}
              onChange={(e) => setMicOn(e.target.checked)}
            />
            🎤 マイク音声
          </label>
          <label className="check">
            <input
              type="checkbox"
              checked={sysOn}
              disabled={preview}
              onChange={(e) => setSysOn(e.target.checked)}
            />
            🔊 システム音声（PCの音）
          </label>

          {webcamMode === 'pip' && (
            <div className="studio-pip">
              <div className="field-label">カメラの位置・大きさ</div>
              <div className="pill-row">
                {(['tl', 'tr', 'bl', 'br'] as PipPos[]).map((p) => (
                  <button
                    key={p}
                    className={`pill ${pipPos === p ? 'selected' : ''}`}
                    onClick={() => setPipPos(p)}
                  >
                    {{ tl: '左上', tr: '右上', bl: '左下', br: '右下' }[p]}
                  </button>
                ))}
              </div>
              <label className="thumb-num">
                サイズ {pipSize}%
                <input
                  type="range"
                  min={12}
                  max={45}
                  value={pipSize}
                  onChange={(e) => setPipSize(Number(e.target.value))}
                />
              </label>
            </div>
          )}

          {/* 音声ミキサー＋メーター */}
          <div className="field-label">🎚️ 音声ミキサー</div>
          {micOn && (
            <div className="mixer-row">
              <span className="mixer-name">🎤 マイク</span>
              <div className="mixer-meter">
                <div
                  className="mixer-meter-fill"
                  style={{ width: `${Math.round(micLevel * 100)}%` }}
                />
              </div>
              <input
                type="range"
                min={0}
                max={2}
                step={0.05}
                value={micVol}
                onChange={(e) => changeMicVol(Number(e.target.value))}
              />
            </div>
          )}
          {sysOn && (
            <div className="mixer-row">
              <span className="mixer-name">🔊 システム</span>
              <div className="mixer-meter">
                <div
                  className="mixer-meter-fill"
                  style={{ width: `${Math.round(sysLevel * 100)}%` }}
                />
              </div>
              <input
                type="range"
                min={0}
                max={2}
                step={0.05}
                value={sysVol}
                onChange={(e) => changeSysVol(Number(e.target.value))}
              />
            </div>
          )}
          {!micOn && !sysOn && (
            <p className="muted vol-hint">音声ソースが選ばれていません。</p>
          )}

          {/* オーバーレイ */}
          <div className="field-label">🏷️ テロップ・ロゴを重ねる</div>
          <div className="row">
            <input
              className="input"
              placeholder="テロップの文字"
              value={newText}
              onChange={(e) => setNewText(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && addText()}
            />
            <button className="btn ghost sm" onClick={addText}>
              ＋文字
            </button>
            <button className="btn ghost sm" onClick={addImage}>
              🖼️ロゴ
            </button>
          </div>
          {(texts.length > 0 || imgs.length > 0) && (
            <div className="studio-overlay-list">
              {texts.map((t) => (
                <TextRow
                  key={t.id}
                  t={t}
                  onChange={(nt) =>
                    setTexts((ts) => ts.map((x) => (x.id === t.id ? nt : x)))
                  }
                  onRemove={() =>
                    setTexts((ts) => ts.filter((x) => x.id !== t.id))
                  }
                />
              ))}
              {imgs.map((o) => (
                <div className="studio-overlay-item" key={o.id}>
                  <span className="muted">🖼️ ロゴ</span>
                  <label className="thumb-num">
                    大きさ {Math.round(o.w * 100)}%
                    <input
                      type="range"
                      min={5}
                      max={50}
                      value={Math.round(o.w * 100)}
                      onChange={(e) =>
                        setImgs((xs) =>
                          xs.map((x) =>
                            x.id === o.id
                              ? { ...x, w: Number(e.target.value) / 100 }
                              : x,
                          ),
                        )
                      }
                    />
                  </label>
                  <button
                    className="btn ghost sm"
                    onClick={() =>
                      setImgs((xs) => xs.filter((x) => x.id !== o.id))
                    }
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* 🎬 シーン（構成の切替） */}
      <div className="studio-scenes">
        <div className="field-label">🎬 シーン（構成を保存して切替）</div>
        <div className="row">
          <input
            className="input"
            placeholder="シーン名（例：トーク / 画面共有）"
            value={newSceneName}
            onChange={(e) => setNewSceneName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && saveScene()}
          />
          <button className="btn ghost sm" onClick={saveScene}>
            ＋現在の構成を保存
          </button>
        </div>
        {scenes.length > 0 && (
          <div className="studio-scene-list">
            {scenes.map((s) => (
              <div className="studio-scene-chip" key={s.id}>
                <button className="pill" onClick={() => applyScene(s)}>
                  🎬 {s.name}
                </button>
                <button
                  className="scene-x"
                  onClick={() => removeScene(s.id)}
                  title="削除"
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        )}
        {scenes.length === 0 && (
          <p className="muted vol-hint">
            カメラ配置・テロップ・画面ON/OFFをシーンとして保存し、録画中でもワンタップで切替えられます。
          </p>
        )}
      </div>

      {error && <div className="banner error">{error}</div>}

      <div className="run-actions">
        {!preview ? (
          <button className="btn" onClick={startPreview}>
            ▶ プレビュー開始
          </button>
        ) : (
          <>
            {!recording ? (
              <button className="btn primary" onClick={startRec}>
                🔴 録画開始
              </button>
            ) : (
              <>
                <button className="btn ghost" onClick={pauseResume}>
                  {paused ? '▶ 再開' : '⏸ 一時停止'}
                </button>
                <button className="btn primary" onClick={stopRec}>
                  ⏹ 停止して保存
                </button>
              </>
            )}
            <button className="btn ghost" onClick={stopPreview}>
              プレビュー停止
            </button>
          </>
        )}
      </div>

      {savedPath && !recording && (
        <div className="lic-ok">
          録画を保存しました：{savedPath}
          <div className="run-actions">
            <button
              className="btn ghost sm"
              onClick={() => window.videocraft?.openPath?.(savedPath)}
            >
              ▶ 再生
            </button>
            <button
              className="btn ghost sm"
              onClick={() => window.videocraft?.showItemInFolder?.(savedPath)}
            >
              📁 フォルダを開く
            </button>
          </div>
        </div>
      )}
    </section>
  )
}

function TextRow({
  t,
  onChange,
  onRemove,
}: {
  t: TextOverlay
  onChange: (t: TextOverlay) => void
  onRemove: () => void
}) {
  return (
    <div className="studio-overlay-item">
      <input
        className="input sm"
        value={t.text}
        onChange={(e) => onChange({ ...t, text: e.target.value })}
      />
      <label className="thumb-color">
        色
        <input
          type="color"
          value={t.color}
          onChange={(e) => onChange({ ...t, color: e.target.value })}
        />
      </label>
      <label className="thumb-num">
        大 {t.size}
        <input
          type="range"
          min={24}
          max={120}
          value={t.size}
          onChange={(e) => onChange({ ...t, size: Number(e.target.value) })}
        />
      </label>
      <label className="thumb-num">
        横 {Math.round(t.x * 100)}%
        <input
          type="range"
          min={0}
          max={95}
          value={Math.round(t.x * 100)}
          onChange={(e) => onChange({ ...t, x: Number(e.target.value) / 100 })}
        />
      </label>
      <label className="thumb-num">
        縦 {Math.round(t.y * 100)}%
        <input
          type="range"
          min={5}
          max={98}
          value={Math.round(t.y * 100)}
          onChange={(e) => onChange({ ...t, y: Number(e.target.value) / 100 })}
        />
      </label>
      <button className="btn ghost sm" onClick={onRemove}>
        ✕
      </button>
    </div>
  )
}
