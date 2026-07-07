import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { sendToEditing } from '../handoff'
import type {
  DurationSuggestion,
  ProviderInfo,
  YukkuriRenderResponse,
  YukkuriScript,
} from '../types'

// 立ち絵・キャラ画像の無料素材サイト（各サイトの規約を要確認）
const MATERIAL_SITES: { label: string; url: string }[] = [
  { label: 'ニコニ・コモンズ', url: 'https://commons.nicovideo.jp/' },
  { label: 'きつねゆっくり(nicotalk)', url: 'https://www.nicotalk.com/charasozai.html' },
  { label: 'いらすとや', url: 'https://www.irasutoya.com/' },
  { label: 'Pixabay', url: 'https://pixabay.com/ja/' },
]

export default function YukkuriPage() {
  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [provider, setProvider] = useState('')
  const [models, setModels] = useState<string[]>([])
  const [model, setModel] = useState('')

  const [topic, setTopic] = useState('')
  const [instructions, setInstructions] = useState('')
  const [speakers, setSpeakers] = useState(2) // 1=一人 / 2=掛け合い
  const [nameA, setNameA] = useState('アカリ')
  const [nameB, setNameB] = useState('ソウ')
  const [voiceA, setVoiceA] = useState('ja-JP-NanamiNeural')
  const [voiceB, setVoiceB] = useState('ja-JP-KeitaNeural')

  // キャラのプリセット（名前＋声をまとめて設定）
  const PRESETS: {
    label: string
    a: [string, string]
    b: [string, string]
  }[] = [
    { label: 'アカリ & ソウ（標準）', a: ['アカリ', 'ja-JP-NanamiNeural'], b: ['ソウ', 'ja-JP-KeitaNeural'] },
    { label: '霊夢 & 魔理沙（ゆっくり）', a: ['霊夢', 'ja-JP-NanamiNeural'], b: ['魔理沙', 'ja-JP-KeitaNeural'] },
    { label: 'ずんだもん & めたん（VOICEVOX）', a: ['ずんだもん', 'vv:3'], b: ['四国めたん', 'vv:2'] },
  ]
  function applyPreset(idx: number) {
    const p = PRESETS[idx]
    if (!p) return
    setNameA(p.a[0])
    setVoiceA(p.a[1])
    setNameB(p.b[0])
    setVoiceB(p.b[1])
  }
  const [voices, setVoices] = useState<{ id: string; label: string }[]>([])
  const [engine, setEngine] = useState('edge-tts')
  const [vvAvailable, setVvAvailable] = useState(false)
  const [vvUrl, setVvUrl] = useState('')
  // ゆっくりボイス（AquesTalk）の入手先とインポート場所
  const [aqAvailable, setAqAvailable] = useState(false)
  const [aqDir, setAqDir] = useState('')
  const [aqUrl, setAqUrl] = useState('')
  // キャラの見た目: 丸顔（名前アイコン）/ 立ち絵（画像）/ 非表示
  const [charLook, setCharLook] = useState<'circle' | 'tachie' | 'hide'>('circle')
  const [avatarA, setAvatarA] = useState('')
  const [avatarB, setAvatarB] = useState('')

  async function pickAvatar(which: 'a' | 'b') {
    const p = await window.videocraft?.openFileDialog?.('image')
    if (!p) return
    if (which === 'a') setAvatarA(p)
    else setAvatarB(p)
    setCharLook('tachie')
  }

  // 解説 or 実況
  const [mode, setMode] = useState<'kaisetsu' | 'jikkyou'>('kaisetsu')
  const [baseVideo, setBaseVideo] = useState('')
  const [baseDuration, setBaseDuration] = useState(0)
  const [subtitles, setSubtitles] = useState(true)

  // 元動画の作り方: インポート / ブラウザ自動録画 / アプリ自動録画
  const [baseSrc, setBaseSrc] = useState<
    'import' | 'web' | 'desktop' | 'self'
  >('import')
  const [recUrl, setRecUrl] = useState('')
  const [recWindow, setRecWindow] = useState('')
  const [recWindows, setRecWindows] = useState<string[]>([])
  const [recBusy, setRecBusy] = useState(false)
  const recTokenRef = useRef('')
  const recTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  // 録画の残り予定時間（カウントダウン表示用）
  const [recRemain, setRecRemain] = useState(0)
  const [recTotal, setRecTotal] = useState(0)
  // 尺の候補
  const [durSug, setDurSug] = useState<DurationSuggestion | null>(null)
  const [durBusy, setDurBusy] = useState(false)
  const [target, setTarget] = useState(0) // 採用した目標尺（秒）
  const [targetMsg, setTargetMsg] = useState<string | null>(null)

  async function suggestDur() {
    if (durBusy) return
    // テーマ未入力でも候補は必ず出す（空でもクライアントが目安候補を返す）
    setDurBusy(true)
    setError(null)
    try {
      const s = await api.suggestDurations(
        topic.trim(),
        instructions.trim(),
        provider,
        model || undefined,
      )
      setDurSug(s)
    } catch {
      // 念のため（client 側でフォールバック済みだが二重の保険）
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
  function pickTarget(sec: number, label: string) {
    setTarget(sec)
    setTargetMsg(`目標尺を${label}の約${sec}秒にしました。`)
  }

  function startRecCountdown(seconds: number) {
    const total = Math.max(1, Math.round(seconds))
    setRecTotal(total)
    setRecRemain(total)
    if (recTimerRef.current) clearInterval(recTimerRef.current)
    recTimerRef.current = setInterval(() => {
      setRecRemain((r) => (r > 1 ? r - 1 : 1))
    }, 1000)
  }
  function stopRecCountdown() {
    if (recTimerRef.current) {
      clearInterval(recTimerRef.current)
      recTimerRef.current = null
    }
    setRecRemain(0)
  }

  function loadRecWindows() {
    api
      .desktopWindows()
      .then((r) => {
        setRecWindows(r.windows)
        if (r.windows[0] && !recWindow) setRecWindow(r.windows[0])
      })
      .catch(() => {})
  }

  // AIに自動操作で元動画を録画させる（ナレーションなし＝ゆっくりの声を後で重ねる）。
  // 録画した動画のパスを返す。録画中は全画面オーバーレイで操作をブロックする。
  async function autoRecordBase(): Promise<string> {
    const isSelf = baseSrc === 'self'
    if (baseSrc === 'web' && !recUrl.trim()) {
      throw new Error('録画するページのURLを入力してください。')
    }
    if (baseSrc === 'desktop' && !recWindow.trim()) {
      throw new Error('録画するアプリを選んでください。')
    }
    setRecBusy(true)
    const token =
      (crypto as { randomUUID?: () => string }).randomUUID?.() ??
      String(Date.now())
    recTokenRef.current = token
    let openedRecWin = false
    try {
      let videoPath = ''
      if (baseSrc === 'web') {
        const p = await api.autopilotPlan({
          url: recUrl.trim(),
          urls: [recUrl.trim()],
          topic: topic.trim() || undefined,
          instructions: instructions.trim() || undefined,
          provider,
          model: model || undefined,
        })
        startRecCountdown((p.plan.steps?.length ?? 5) * 7)
        const res = await api.autopilotRun(
          p.plan,
          voiceA,
          false, // 字幕なし
          false, // ゆっくり重ねない（後段で重ねる）
          '霊夢',
          [recUrl.trim()],
          token,
          '',
          true,
          false, // narrate=false（ナレーションなしの素材録画）
        )
        videoPath = res.video_path
      } else {
        // AIVideoCraft自体を撮るときは、別ウィンドウを開いてそこを対象にする
        let winTitle = recWindow
        if (isSelf) {
          winTitle =
            (await window.videocraft?.openRecWindow?.()) ?? recWindow
          openedRecWin = true
          await new Promise((r) => setTimeout(r, 1600)) // 表示待ち
        }
        const p = await api.desktopPlan({
          window_title: winTitle,
          topic: topic.trim() || undefined,
          instructions: instructions.trim() || undefined,
          provider,
          model: model || undefined,
        })
        startRecCountdown((p.plan.steps?.length ?? 5) * 7)
        const res = await api.desktopRun(p.plan, voiceA, false, token, false)
        videoPath = res.video_path
      }
      setBaseVideo(videoPath)
      try {
        const info = await api.probeVideo(videoPath)
        setBaseDuration(Math.round(info.duration_sec))
      } catch {
        setBaseDuration(0)
      }
      return videoPath
    } finally {
      stopRecCountdown()
      setRecBusy(false)
      if (openedRecWin) window.videocraft?.closeRecWindow?.() // 撮影用ウィンドウを閉じる
    }
  }

  function cancelRec() {
    if (!recBusy) return
    api.autopilotCancel(recTokenRef.current).catch(() => {})
  }

  // 録画中は「何かキーを押すとキャンセル」＋操作をオーバーレイでブロック
  useEffect(() => {
    if (!recBusy) return
    const onInput = () => cancelRec()
    window.addEventListener('keydown', onInput)
    window.addEventListener('mousedown', onInput)
    return () => {
      window.removeEventListener('keydown', onInput)
      window.removeEventListener('mousedown', onInput)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recBusy])

  async function pickBaseVideo() {
    const p = await window.videocraft?.openVideoDialog?.()
    if (!p) return
    setBaseVideo(p)
    try {
      const info = await api.probeVideo(p)
      setBaseDuration(Math.round(info.duration_sec))
    } catch {
      setBaseDuration(0)
    }
  }

  const [script, setScript] = useState<YukkuriScript | null>(null)
  const [result, setResult] = useState<YukkuriRenderResponse | null>(null)
  const [busy, setBusy] = useState<'' | 'script' | 'render'>('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.listProviders().then((ps) => {
      setProviders(ps)
      const first = ps.find((p) => p.configured) ?? ps[0]
      if (first) setProvider(first.id)
    })
    api
      .yukkuriConfig()
      .then((c) => {
        setVoices(c.voices)
        setEngine(c.voice_engine)
        setVvAvailable(c.voicevox_available)
        setVvUrl(c.voicevox_download_url)
        setAqAvailable(c.aquestalk_available)
        setAqDir(c.aquestalk_dir)
        setAqUrl(c.aquestalk_download_url)
      })
      .catch(() => {})
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

  async function genScript() {
    if (busy) return
    if (!topic.trim()) {
      setError('テーマを入力してください。')
      return
    }
    // 実況でインポート元動画を使う場合のみ、この段階で動画が必要。
    // 自動録画（web/desktop）は「②動画を生成」時に撮影するので、ここでは不要。
    if (mode === 'jikkyou' && baseSrc === 'import' && !baseVideo) {
      setError('実況を乗せる元動画を選んでください。')
      return
    }
    setBusy('script')
    setError(null)
    setResult(null)
    try {
      const res = await api.yukkuriScript({
        topic: topic.trim(),
        instructions: instructions.trim() || undefined,
        mode,
        target_sec: baseVideo ? baseDuration : target || undefined,
        speakers,
        name_a: nameA,
        name_b: nameB,
        provider,
        model: model || undefined,
      })
      setScript(res.script)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy('')
    }
  }

  async function renderVideo() {
    if (busy || recBusy || !script) return
    // 自動録画ソースでまだ撮影していなければ、先にAIが自動撮影する（統合）
    let base = baseVideo
    if (
      !base &&
      (baseSrc === 'web' || baseSrc === 'desktop' || baseSrc === 'self')
    ) {
      if (
        !window.confirm(
          'この後、AIが自動で画面を操作して撮影します。撮影中はこの画面の操作をブロックします（何かキーを押すと中止）。開始しますか？',
        )
      )
        return
      try {
        base = await autoRecordBase()
      } catch (e) {
        setError((e as Error).message)
        return
      }
      if (!base) return
    }
    setBusy('render')
    setError(null)
    setResult(null)
    try {
      const chars = {
        name_a: nameA,
        name_b: nameB,
        voice_a: voiceA,
        voice_b: voiceB,
        single: speakers === 1,
        show_chars: charLook !== 'hide',
        avatar_a: charLook === 'tachie' ? avatarA : '',
        avatar_b: charLook === 'tachie' ? avatarB : '',
      }
      const res = base
        ? await api.yukkuriJikkyou(
            base,
            script,
            chars,
            voiceA,
            voiceB,
            subtitles,
            // 自動録画のベースは無音なので実況の声だけを使う（インポート動画のみ元音を残す）
            baseSrc === 'import',
          )
        : await api.yukkuriRender(script, chars)
      setResult(res)
      if (res.video_path) window.videocraft?.showItemInFolder?.(res.video_path)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy('')
    }
  }

  return (
    <div className="yk-embed">
      {/* 撮影中は全画面オーバーレイで操作をブロック＋残り予定時間＋何かキーで中止 */}
      {recBusy && (
        <div
          className="rec-block-overlay"
          onMouseDown={cancelRec}
          role="button"
          tabIndex={0}
        >
          <div className="rec-block-inner">
            <div className="ai-overlay-spin" />
            <div className="rec-block-title">🤖 AIが自動で撮影中です</div>
            <div className="rec-block-time">
              残り 約 {recRemain} 秒
              <span className="rec-block-sub">（予定）</span>
            </div>
            <div className="gen-progress">
              <div
                className="gen-progress-fill"
                style={{
                  width: `${recTotal > 0 ? Math.min(98, ((recTotal - recRemain) / recTotal) * 100) : 5}%`,
                }}
              />
            </div>
            <div className="rec-block-note">
              PC の操作はブロック中です。中止するには
              <b>何かキーを押す</b>か、この画面をクリックしてください。
            </div>
          </div>
        </div>
      )}
      <h2 className="section-title">
        🗣️ <span className="gradient-text">ゆっくり解説・実況</span>
      </h2>
      <p className="subtitle">
        2キャラ（または1人）の掛け合いをAIが作り、音声＋字幕つきの動画にします。解説はゼロから、実況は元動画に重ねます。
      </p>

      <section className="card">
        {/* 解説 / 実況 モード切替 */}
        <div className="ap-mode">
          <button
            className={`ap-mode-btn ${mode === 'kaisetsu' ? 'active' : ''}`}
            onClick={() => {
              setMode('kaisetsu')
              setScript(null)
              setResult(null)
            }}
          >
            🗣️ ゆっくり解説（ゼロから）
          </button>
          <button
            className={`ap-mode-btn ${mode === 'jikkyou' ? 'active' : ''}`}
            onClick={() => {
              setMode('jikkyou')
              setScript(null)
              setResult(null)
            }}
          >
            🎮 ゆっくり実況（動画に重ねる）
          </button>
        </div>

        <div className="field-label">
          {mode === 'jikkyou'
            ? '実況を乗せる元動画（必須）'
            : '元動画（任意）— 入れると解説を動画に重ねます'}
          {baseVideo && (
            <button
              className="btn ghost sm"
              onClick={() => {
                setBaseVideo('')
                setBaseDuration(0)
              }}
            >
              クリア
            </button>
          )}
        </div>
        {/* 元動画の作り方: インポート / ブラウザ自動録画 / アプリ自動録画 */}
        <div className="ap-mode ap-mode-3">
          <button
            className={`ap-mode-btn ${baseSrc === 'import' ? 'active' : ''}`}
            onClick={() => setBaseSrc('import')}
          >
            📁 インポート
          </button>
          <button
            className={`ap-mode-btn ${baseSrc === 'web' ? 'active' : ''}`}
            onClick={() => setBaseSrc('web')}
          >
            🌐 ブラウザ自動録画
          </button>
          <button
            className={`ap-mode-btn ${baseSrc === 'desktop' ? 'active' : ''}`}
            onClick={() => {
              setBaseSrc('desktop')
              loadRecWindows()
            }}
          >
            🖥️ アプリ自動録画
          </button>
          <button
            className={`ap-mode-btn ${baseSrc === 'self' ? 'active' : ''}`}
            onClick={() => setBaseSrc('self')}
          >
            🎬 AI VideoCraft自体
          </button>
        </div>

        {baseSrc === 'import' && (
          <div className="row">
            <input
              className="input"
              placeholder="動画ファイルのパス（空なら解説はゼロから生成）"
              value={baseVideo}
              onChange={(e) => setBaseVideo(e.target.value)}
            />
            <button className="btn ghost" onClick={pickBaseVideo}>
              参照…
            </button>
          </div>
        )}
        {baseSrc === 'web' && (
          <>
            <input
              className="input"
              placeholder="録画するページのURL（例: https://example.com）"
              value={recUrl}
              onChange={(e) => setRecUrl(e.target.value)}
            />
            <p className="muted vol-hint">
              下の「② 撮影して動画を生成」を押すと、AIがこのページを自動録画してから動画にします。
            </p>
          </>
        )}
        {baseSrc === 'desktop' && (
          <>
            <div className="row">
              <select
                className="input"
                value={recWindow}
                onChange={(e) => setRecWindow(e.target.value)}
              >
                {recWindows.length === 0 && (
                  <option value="">（開いているアプリがありません）</option>
                )}
                {recWindows.map((w) => (
                  <option key={w} value={w}>
                    {w}
                  </option>
                ))}
              </select>
              <button className="btn ghost" onClick={loadRecWindows}>
                🔄 更新
              </button>
            </div>
            <p className="muted vol-hint">
              下の「② 撮影して動画を生成」を押すと、AIがこのアプリを自動録画してから動画にします。
            </p>
          </>
        )}
        {baseSrc === 'self' && (
          <p className="muted vol-hint">
            🎬 下の「② 撮影して動画を生成」を押すと、AI VideoCraft をもう一つ別ウィンドウで自動的に開き、
            そのウィンドウをAIが操作しながら撮影します（本体ウィンドウは操作されません）。撮影後は自動で閉じ、
            その映像にゆっくりキャラ＋音声を重ねて動画にします。
          </p>
        )}
        {baseVideo && (
          <p className="muted ap-path">📹 元動画: {baseVideo}</p>
        )}
        {baseDuration > 0 && (
          <p className="muted vol-hint">
            長さ約{baseDuration}秒。これに合わせて声の量を調整します。
          </p>
        )}

        <div className="plan-form-grid">
          <label>
            テーマ
            <input
              className="input"
              placeholder="例: AI動画制作ツールの使い方"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
            />
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
        </div>

        {/* 尺の候補（テーマの下）*/}
        <div className="dur-box dur-panel">
          <button className="btn ghost" onClick={suggestDur} disabled={durBusy}>
            {durBusy ? '尺を計算中…' : '📏 尺の候補を出す（動画用 / ショート用）'}
          </button>
          {durSug && (
            <div className="dur-cands">
              <div className="dur-card">
                <div className="dur-title">🎬 動画用</div>
                <div className="dur-sec">{durSug.video_sec}秒</div>
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

        {/* 人数 ＋ プリセット */}
        <div className="row" style={{ alignItems: 'center', flexWrap: 'wrap' }}>
          <div className="ap-mode" style={{ marginBottom: 0, flex: '0 0 auto' }}>
            <button
              className={`ap-mode-btn ${speakers === 2 ? 'active' : ''}`}
              onClick={() => setSpeakers(2)}
            >
              👥 掛け合い（2人）
            </button>
            <button
              className={`ap-mode-btn ${speakers === 1 ? 'active' : ''}`}
              onClick={() => setSpeakers(1)}
            >
              🧍 ひとり語り（1人）
            </button>
          </div>
          <select
            className="input"
            defaultValue=""
            onChange={(e) => {
              applyPreset(Number(e.target.value))
              e.target.value = ''
            }}
            style={{ flex: '1 1 200px' }}
          >
            <option value="">キャラのプリセットを選ぶ…</option>
            {PRESETS.map((p, i) => (
              <option key={i} value={i}>
                {p.label}
              </option>
            ))}
          </select>
        </div>

        <div className="yk-chars">
          <div className="yk-char yk-a">
            <div className="field-label">
              {speakers === 1 ? '🔵 キャラ' : '🔵 聞き手キャラ'}
            </div>
            <input
              className="input"
              value={nameA}
              onChange={(e) => setNameA(e.target.value)}
            />
            <select value={voiceA} onChange={(e) => setVoiceA(e.target.value)}>
              {voices.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.label}
                </option>
              ))}
            </select>
          </div>
          {speakers === 2 && (
            <div className="yk-char yk-b">
              <div className="field-label">🟣 解説役キャラ</div>
              <input
                className="input"
                value={nameB}
                onChange={(e) => setNameB(e.target.value)}
              />
              <select value={voiceB} onChange={(e) => setVoiceB(e.target.value)}>
                {voices.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.label}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        {/* キャラの見た目（丸顔 / 立ち絵 / 非表示）*/}
        <div className="field-label">キャラの見た目</div>
        <div className="ap-mode ap-mode-3">
          <button
            className={`ap-mode-btn ${charLook === 'circle' ? 'active' : ''}`}
            onClick={() => setCharLook('circle')}
          >
            🟢 丸顔（名前アイコン）
          </button>
          <button
            className={`ap-mode-btn ${charLook === 'tachie' ? 'active' : ''}`}
            onClick={() => setCharLook('tachie')}
          >
            🧍 立ち絵（画像）
          </button>
          <button
            className={`ap-mode-btn ${charLook === 'hide' ? 'active' : ''}`}
            onClick={() => setCharLook('hide')}
          >
            🚫 表示しない
          </button>
        </div>
        {charLook === 'tachie' && (
          <div className="tachie-box">
            <div className="row">
              <button className="btn ghost sm" onClick={() => pickAvatar('a')}>
                🖼️ {speakers === 1 ? 'キャラ' : '聞き手'}の立ち絵を選ぶ
              </button>
              <span className="muted ap-path">{avatarA || '（未選択＝丸顔）'}</span>
            </div>
            {speakers === 2 && (
              <div className="row">
                <button className="btn ghost sm" onClick={() => pickAvatar('b')}>
                  🖼️ 解説役の立ち絵を選ぶ
                </button>
                <span className="muted ap-path">{avatarB || '（未選択＝丸顔）'}</span>
              </div>
            )}
            <p className="muted vol-hint">
              透過PNG推奨。立ち絵の無料素材（各サイトの利用規約をご確認ください）:{' '}
              {MATERIAL_SITES.map((m, i) => (
                <span key={m.url}>
                  {i > 0 && ' / '}
                  <a
                    href="#"
                    onClick={(e) => {
                      e.preventDefault()
                      window.videocraft?.openExternal?.(m.url)
                    }}
                  >
                    {m.label}
                  </a>
                </span>
              ))}
            </p>
          </div>
        )}

        {/* ゆっくりボイスの導入（VOICEVOX / AquesTalk）*/}
        <div className="vv-note">
          {vvAvailable ? (
            <span className="badge ok">
              🎙️ VOICEVOX 接続中 — 多数のキャラ声が使えます
            </span>
          ) : (
            <span className="muted">
              💡 もっと多くの声（ずんだもん等・無料/商用可）を使うには VOICEVOX を導入してください。{' '}
              <a
                href="#"
                onClick={(e) => {
                  e.preventDefault()
                  if (vvUrl) window.videocraft?.openExternal?.(vvUrl)
                }}
              >
                VOICEVOXをダウンロード（{vvUrl}）
              </a>
              。起動後にこの画面を開き直すと声が増えます。
            </span>
          )}
          <div className="aq-row">
            {aqAvailable ? (
              <span className="badge ok">
                🗣️ ゆっくりボイス(AquesTalk) 検出済み: {aqDir}
              </span>
            ) : (
              <span className="muted">
                🗣️ 本物のゆっくり声（AquesTalk）は、PCに入っていれば自動で検出して使います（未検出）。{' '}
                <a
                  href="#"
                  onClick={(e) => {
                    e.preventDefault()
                    if (aqUrl) window.videocraft?.openExternal?.(aqUrl)
                  }}
                >
                  AquesTalkの入手先（{aqUrl}）
                </a>
              </span>
            )}
          </div>
        </div>

        <textarea
          className="input"
          rows={2}
          placeholder="入れてほしい内容・流れ（任意）"
          value={instructions}
          onChange={(e) => setInstructions(e.target.value)}
        />
        {mode === 'jikkyou' && (
          <label className="check">
            <input
              type="checkbox"
              checked={subtitles}
              onChange={(e) => setSubtitles(e.target.checked)}
            />
            🔤 実況セリフを字幕で表示
          </label>
        )}

        {error && <div className="banner error">{error}</div>}
        <div className="run-actions">
          <button
            className="btn"
            onClick={genScript}
            disabled={busy !== '' || recBusy}
          >
            {busy === 'script' ? '台本を生成中…' : '① 台本を生成'}
          </button>
          {script && (
            <button
              className="btn primary"
              onClick={renderVideo}
              disabled={busy !== '' || recBusy}
            >
              {busy === 'render'
                ? '🎬 動画を生成中…'
                : recBusy
                  ? '🎬 撮影中…'
                  : !baseVideo &&
                      (baseSrc === 'web' ||
                        baseSrc === 'desktop' ||
                        baseSrc === 'self')
                    ? '② 撮影して動画を生成'
                    : '② 動画を生成'}
            </button>
          )}
        </div>
        {busy === 'render' && (
          <div className="gen-progress-row">
            <div className="gen-progress indeterminate">
              <div className="gen-progress-fill" />
            </div>
            <p className="muted vol-hint">
              🎬 動画を作成しています…（音声合成・キャラ合成・字幕焼き込み）
            </p>
          </div>
        )}
        <p className="muted vol-hint">
          音声エンジン: {engine === 'aquestalk' ? 'AquesTalk（ゆっくり声）' : 'edge-tts（自然な合成音声）'}
          {busy === 'render' && ' — 生成には少し時間がかかります…'}
        </p>
      </section>

      {script && (
        <section className="card">
          <div className="field-label">
            台本：{script.title}（{script.lines.length}セリフ）
          </div>
          <div className="yk-script">
            {script.lines.map((l, i) => (
              <div
                key={i}
                className={`yk-line ${l.speaker === 'a' ? 'yk-line-a' : 'yk-line-b'}`}
              >
                <span className="yk-name">
                  {l.speaker === 'a' ? nameA : nameB}
                </span>
                <span className="yk-text">{l.text}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {result && (
        <section className="card">
          <div className="lic-ok">
            🎬 動画を作成しました（約{Math.round(result.duration_sec)}秒 /{' '}
            {result.lines}セリフ・音声: {result.voice_engine}）
          </div>
          <div className="run-actions">
            <button
              className="btn ghost sm"
              onClick={() => window.videocraft?.openPath?.(result.video_path)}
            >
              ▶ 再生
            </button>
            <button
              className="btn ghost sm"
              onClick={() =>
                window.videocraft?.showItemInFolder?.(result.video_path)
              }
            >
              📁 フォルダを開く
            </button>
            <button
              className="btn primary sm"
              onClick={() => sendToEditing(result.video_path)}
            >
              ✂️ 編集スタジオへ送る
            </button>
          </div>
          <div className="muted ap-path">{result.video_path}</div>
          {result.warnings.length > 0 && (
            <ul className="ap-warn">
              {result.warnings.map((w, i) => (
                <li key={i}>⚠️ {w}</li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  )
}
