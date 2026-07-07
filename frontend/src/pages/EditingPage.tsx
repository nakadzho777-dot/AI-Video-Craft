import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { handoff, sendToPublishing } from '../handoff'
import EditorTimeline from '../components/EditorTimeline'
import AutoEditTimeline from '../components/AutoEditTimeline'
import type {
  AutoEditResponse,
  EditCut,
  EditOverlay,
  EditTelop,
  ManualEditResponse,
  MaterialSuggestion,
  ProbeResponse,
  Project,
  ProviderInfo,
  SilenceRange,
  StyleProfile,
  SuggestResponse,
} from '../types'

function fmt(sec: number): string {
  const s = Math.max(0, Math.round(sec))
  const m = Math.floor(s / 60)
  return `${m}:${String(s % 60).padStart(2, '0')}`
}

// スタイルプロファイルを提案APIへ渡すテキストに変換
function styleToText(p: StyleProfile): string {
  return [
    p.creator && `参考: ${p.creator}`,
    p.summary && `要約: ${p.summary}`,
    p.pacing && `テンポ: ${p.pacing}`,
    p.cut_style && `カット: ${p.cut_style}`,
    p.telop_style && `テロップ: ${p.telop_style}`,
    p.sound_style && `音: ${p.sound_style}`,
    p.transitions && `トランジション: ${p.transitions}`,
    p.hook_style && `掴み: ${p.hook_style}`,
  ]
    .filter(Boolean)
    .join(' / ')
}

const canBrowse = () => !!window.videocraft?.openVideoDialog

export default function EditingPage() {
  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [provider, setProvider] = useState('')
  const [models, setModels] = useState<string[]>([])
  const [model, setModel] = useState('')
  const [projects, setProjects] = useState<Project[]>([])

  // スタジオ内タブ（タブ以外は画面全体を使う）
  const [editTab, setEditTab] = useState<'edit' | 'auto' | 'assets'>('edit')

  const [videoPath, setVideoPath] = useState('')
  const [probe, setProbe] = useState<ProbeResponse | null>(null)
  const [duration, setDuration] = useState<number>(0)
  const [projectId, setProjectId] = useState<number | ''>('')
  const [goal, setGoal] = useState<'auto' | 'improve' | 'short'>('auto')
  const [script, setScript] = useState('')

  const [result, setResult] = useState<SuggestResponse | null>(null)
  const [silence, setSilence] = useState<SilenceRange[] | null>(null)
  const [busy, setBusy] = useState<'' | 'probe' | 'suggest' | 'silence' | 'style'>('')
  const [error, setError] = useState<string | null>(null)

  // 編集スタイル学習
  const [styleUrl, setStyleUrl] = useState('')
  const [styleCreator, setStyleCreator] = useState('')
  const [styleNotes, setStyleNotes] = useState('')
  const [style, setStyle] = useState<StyleProfile | null>(null)

  // 自動編集
  const [autoInstr, setAutoInstr] = useState('無音をカットして、要点にテロップを入れて')
  const [autoResult, setAutoResult] = useState<AutoEditResponse | null>(null)
  // 字幕がある動画→テロップを上寄せ（被り回避）
  const [hasSubs, setHasSubs] = useState(false)
  // 自動編集で縦動画化（ショート・1080x1920）
  const [autoVertical, setAutoVertical] = useState(false)
  // 編集多め（テロップ・記号・素材を多くして「しゃべるだけ」を回避）
  const [editHeavy, setEditHeavy] = useState(true)
  // 再生速度・色フィルタ・フェード（トランジション）
  const [speed, setSpeed] = useState(1)
  const [vfilter, setVfilter] = useState('none')
  const [fadeIn, setFadeIn] = useState(false)
  const [fadeOut, setFadeOut] = useState(false)
  // 推奨素材のDL→検出→再編集
  const [matFolder, setMatFolder] = useState('')
  const [detAudio, setDetAudio] = useState<{ path: string; name: string }[]>([])
  const [detImages, setDetImages] = useState<{ path: string; name: string }[]>([])
  const [pickAudio, setPickAudio] = useState('')
  const [pickImages, setPickImages] = useState<string[]>([])
  const [reediting, setReediting] = useState(false)
  const [reeditOut, setReeditOut] = useState<string | null>(null)
  // 手動編集
  const [cuts, setCuts] = useState<EditCut[]>([])
  const [telops, setTelops] = useState<EditTelop[]>([])
  const [vertical, setVertical] = useState(false)
  const [volume, setVolume] = useState(1)
  const [mute, setMute] = useState(false)
  const [bgm, setBgm] = useState('')
  const [bgmVol, setBgmVol] = useState(0.3)
  const [overlays, setOverlays] = useState<EditOverlay[]>([])
  const [manualResult, setManualResult] = useState<ManualEditResponse | null>(null)

  async function pickBgm() {
    const p = await window.videocraft?.openFileDialog?.('audio')
    if (p) setBgm(p)
  }
  async function addOverlay() {
    const p = await window.videocraft?.openFileDialog?.('image')
    if (p)
      setOverlays([
        ...overlays,
        { image: p, start_sec: 0, end_sec: duration || 0, position: 'tr' },
      ])
  }
  // 素材検索
  const [matQuery, setMatQuery] = useState('')
  const [materials, setMaterials] = useState<MaterialSuggestion[] | null>(null)
  const [editBusy, setEditBusy] = useState<'' | 'auto' | 'manual' | 'mat'>('')

  const openExt = (url: string) => window.videocraft?.openExternal?.(url)
  const openFile = (p: string) => window.videocraft?.openPath?.(p)

  async function runAutoEdit() {
    if (editBusy || !videoPath.trim()) {
      if (!videoPath.trim()) setError('先に動画を読み込んでください。')
      return
    }
    setEditBusy('auto')
    setError(null)
    setAutoResult(null)
    try {
      const target =
        projects.find((p) => p.id === projectId)?.target_duration_sec || 0
      const instr =
        target > 0
          ? `${autoInstr.trim()}\n完成尺を約${Math.round(target)}秒に近づけて`
          : autoInstr.trim()
      const r = await api.autoEdit(
        videoPath.trim(),
        instr,
        provider,
        model || undefined,
        hasSubs,
        autoVertical,
        editHeavy,
      )
      setAutoResult(r)
      setReeditOut(null)
      if (r.output_path) window.videocraft?.showItemInFolder?.(r.output_path)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setEditBusy('')
    }
  }

  // 素材フォルダを選ぶ（ダウンロードした素材の置き場）→ その場で検出
  async function pickMatFolder() {
    const f = await window.videocraft?.openFolderDialog?.()
    if (!f) return
    setMatFolder(f)
    await detectMats(f)
  }
  // フォルダを走査してダウンロード済み素材（音声/画像）を検出
  async function detectMats(folder?: string) {
    const f = folder ?? matFolder
    if (!f) return
    setError(null)
    try {
      const r = await api.detectMaterials(f)
      setDetAudio(r.audio)
      setDetImages(r.images)
      setPickAudio(r.audio[0]?.path ?? '')
      setPickImages([])
      if (!r.audio.length && !r.images.length) {
        setError('このフォルダに音声/画像素材が見つかりませんでした。')
      }
    } catch (e) {
      setError((e as Error).message)
    }
  }
  // 検出した素材を、自動編集の出力に重ねて再編集
  async function reEditWithMaterials() {
    if (!autoResult || reediting) return
    setReediting(true)
    setError(null)
    setReeditOut(null)
    try {
      const r = await api.applyEdit({
        input_path: autoResult.output_path,
        cuts: [],
        telops: [],
        bgm: pickAudio || undefined,
        bgm_volume: bgmVol,
        overlays: pickImages.map((img, i) => ({
          image: img,
          start_sec: 0,
          end_sec: 0,
          position: i % 2 === 0 ? 'tr' : 'tl',
        })),
        has_subtitles: hasSubs,
      })
      setReeditOut(r.output_path)
      if (r.output_path) window.videocraft?.showItemInFolder?.(r.output_path)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setReediting(false)
    }
  }

  async function applyManual() {
    if (editBusy || !videoPath.trim()) {
      if (!videoPath.trim()) setError('先に動画を読み込んでください。')
      return
    }
    setEditBusy('manual')
    setError(null)
    setManualResult(null)
    try {
      const r = await api.applyEdit({
        input_path: videoPath.trim(),
        cuts: cuts.filter((c) => c.end_sec > c.start_sec),
        telops: telops.filter((t) => t.text.trim()),
        vertical,
        volume,
        mute,
        bgm: bgm || undefined,
        bgm_volume: bgmVol,
        overlays: overlays.filter((o) => o.image),
        has_subtitles: hasSubs,
        speed,
        vfilter,
        fade_in: fadeIn ? 0.6 : 0,
        fade_out: fadeOut ? 0.6 : 0,
      })
      setManualResult(r)
      if (r.output_path) window.videocraft?.showItemInFolder?.(r.output_path)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setEditBusy('')
    }
  }

  async function searchMat() {
    if (editBusy) return
    setEditBusy('mat')
    try {
      const r = await api.searchMaterials(matQuery.trim())
      setMaterials(r.materials)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setEditBusy('')
    }
  }

  useEffect(() => {
    api.listProviders().then((ps) => {
      setProviders(ps)
      const first = ps.find((p) => p.configured) ?? ps[0]
      if (first) setProvider(first.id)
    })
    api.listProjects().then(setProjects)
    // 録画支援から「編集支援へ送る」で渡された動画を読み込む
    if (handoff.editingVideo) {
      const p = handoff.editingVideo
      handoff.editingVideo = undefined
      setVideoPath(p)
      api
        .probeVideo(p)
        .then((info) => {
          setProbe(info)
          setDuration(Math.round(info.duration_sec))
        })
        .catch(() => {})
    }
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

  async function learnStyle() {
    if (busy) return
    if (!styleUrl.trim() && !styleCreator.trim() && !styleNotes.trim()) {
      setError('参考URL・クリエイター名・特徴のいずれかを入力してください。')
      return
    }
    setBusy('style')
    setError(null)
    try {
      const res = await api.learnStyle({
        reference_url: styleUrl.trim() || undefined,
        creator: styleCreator.trim() || undefined,
        notes: styleNotes.trim() || undefined,
        provider,
        model: model || undefined,
      })
      setStyle(res.style)
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
        style: style ? styleToText(style) : undefined,
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
        <span className="gradient-text">編集スタジオ</span>
      </h1>
      <p className="subtitle">
        タイムライン・自動編集・手動編集・素材・スタイル学習を、ここにすべて集約しました。
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
        {probe && videoPath && (
          <video
            className="edit-preview"
            controls
            src={
              'file:///' +
              encodeURI(videoPath.trim().replace(/\\/g, '/')).replace(
                /#/g,
                '%23',
              )
            }
          />
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
            {/* テンポ判定 → カット編集の推奨 */}
            {(() => {
              const total = silence.reduce((n, s) => n + s.duration_sec, 0)
              const ratio = duration > 0 ? total / duration : 0
              if (ratio < 0.12 && duration < 180) return null
              return (
                <div className="banner reminder tempo-rec">
                  ⏱️ {ratio >= 0.12
                    ? `間（無音）が全体の約${Math.round(ratio * 100)}%あります。`
                    : '尺が長めです。'}
                  テンポを上げるにカット編集がおすすめです。
                  <button
                    className="btn ghost sm"
                    onClick={() => {
                      setAutoInstr('無音をカットしてテンポよく、要点にテロップ')
                    }}
                  >
                    🤖 自動でカット編集
                  </button>
                  <span className="muted">
                    または下の「✂️ 手動編集」で調整できます。
                  </span>
                </div>
              )
            })()}
          </div>
        )}
      </section>

      <div className="studio-tabs">
        <button
          className={`studio-tab ${editTab === 'edit' ? 'active' : ''}`}
          onClick={() => setEditTab('edit')}
        >
          ✂️ 編集（タイムライン）
        </button>
        <button
          className={`studio-tab ${editTab === 'auto' ? 'active' : ''}`}
          onClick={() => setEditTab('auto')}
        >
          🤖 自動編集
        </button>
        <button
          className={`studio-tab ${editTab === 'assets' ? 'active' : ''}`}
          onClick={() => setEditTab('assets')}
        >
          🎯 素材・スタイル・AI提案
        </button>
      </div>

      {/* 自動編集 */}
      {editTab === 'auto' && (
      <section className="card autostudio-card">
        <h2>🤖 自動編集（指示でおまかせ）</h2>
        <p className="muted lic-intro">
          読み込んだ動画に対し、指示どおりにAIが編集案を作り、無音カット＋テロップを自動で適用します。
          必要な無料素材があればURLも表示します。
        </p>
        {(() => {
          const t =
            projects.find((p) => p.id === projectId)?.target_duration_sec || 0
          return t > 0 ? (
            <div className="lic-ok">
              🎯 目標尺 {Math.round(t)}秒（録画で設定）に近づけて編集します
            </div>
          ) : null
        })()}
        <textarea
          className="input"
          rows={2}
          placeholder="編集の指示（例: 無音をカットしてテンポよく、要点にテロップ、BGMも）"
          value={autoInstr}
          onChange={(e) => setAutoInstr(e.target.value)}
        />
        <label className="check">
          <input
            type="checkbox"
            checked={hasSubs}
            onChange={(e) => setHasSubs(e.target.checked)}
          />
          🔤 この動画には字幕がある（テロップを上に置いて字幕と被らせない）
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={autoVertical}
            onChange={(e) => setAutoVertical(e.target.checked)}
          />
          📱 縦動画化する（ショート向け・1080×1920）
        </label>
        <label className="check">
          <input
            type="checkbox"
            checked={editHeavy}
            onChange={(e) => setEditHeavy(e.target.checked)}
          />
          🎬 編集多め（しゃべるだけにしない：テロップ・記号を多め＋差し込む画像素材も提案）
        </label>
        <button
          className="btn primary"
          onClick={runAutoEdit}
          disabled={editBusy !== ''}
        >
          {editBusy === 'auto' ? '編集中…（少し時間がかかります）' : '🤖 自動編集を実行'}
        </button>

        {/* AIの編集風景をタイムラインで流す（実行中は走査／完了後は配置演出） */}
        <AutoEditTimeline
          busy={editBusy === 'auto'}
          duration={autoResult?.original_sec || duration}
          cuts={autoResult?.plan.cuts ?? []}
          telops={autoResult?.plan.telops ?? []}
        />

        {autoResult && (
          <div className="ap-result lic-ok">
            🎬 完成：{Math.round(autoResult.original_sec)}秒 →{' '}
            {Math.round(autoResult.duration_sec)}秒
            <div className="muted" style={{ marginTop: 4 }}>
              {autoResult.plan.summary}（テロップ{autoResult.plan.telops.length}件・
              無音カット{autoResult.plan.remove_silence ? 'あり' : 'なし'}）
            </div>
            <div className="run-actions">
              <button
                className="btn ghost sm"
                onClick={() => openFile(autoResult.output_path)}
              >
                ▶ 再生
              </button>
              <button
                className="btn ghost sm"
                onClick={() =>
                  window.videocraft?.showItemInFolder?.(autoResult.output_path)
                }
              >
                📁 フォルダ
              </button>
              <button
                className="btn primary sm"
                onClick={() => sendToPublishing(autoResult.output_path)}
              >
                🚀 投稿支援へ送る
              </button>
            </div>
            {autoResult.plan.materials.length > 0 && (
              <div className="mat-box">
                <div className="field-label">おすすめ無料素材（クリックでサイトを開く→DL）</div>
                {autoResult.plan.materials.map((m, i) => (
                  <MaterialRow key={i} m={m} onOpen={openExt} />
                ))}
              </div>
            )}
            <div className="muted ap-path">{autoResult.output_path}</div>

            {/* 素材をDL→検出→再編集 */}
            <div className="reedit-box">
              <div className="field-label">
                📥 ダウンロードした素材を入れて再編集
              </div>
              <p className="muted vol-hint">
                上のリンクから素材フォルダに保存し、そのフォルダを選ぶと検出します。
              </p>
              <div className="row">
                <button className="btn ghost sm" onClick={pickMatFolder}>
                  📂 素材フォルダを選ぶ
                </button>
                {matFolder && (
                  <button
                    className="btn ghost sm"
                    onClick={() => detectMats()}
                  >
                    🔄 再検出
                  </button>
                )}
                <span className="muted ap-path">{matFolder || '（未選択）'}</span>
              </div>

              {detAudio.length > 0 && (
                <div className="mat-detect">
                  <div className="field-label">🎵 BGM/効果音（1つ選択）</div>
                  {detAudio.map((a) => (
                    <label className="check" key={a.path}>
                      <input
                        type="radio"
                        name="reedit-audio"
                        checked={pickAudio === a.path}
                        onChange={() => setPickAudio(a.path)}
                      />
                      {a.name}
                    </label>
                  ))}
                  <label className="check">
                    <input
                      type="radio"
                      name="reedit-audio"
                      checked={pickAudio === ''}
                      onChange={() => setPickAudio('')}
                    />
                    （BGMなし）
                  </label>
                </div>
              )}
              {detImages.length > 0 && (
                <div className="mat-detect">
                  <div className="field-label">🖼️ 画像（重ねるものを選択）</div>
                  {detImages.map((im) => (
                    <label className="check" key={im.path}>
                      <input
                        type="checkbox"
                        checked={pickImages.includes(im.path)}
                        onChange={(e) =>
                          setPickImages((prev) =>
                            e.target.checked
                              ? [...prev, im.path]
                              : prev.filter((p) => p !== im.path),
                          )
                        }
                      />
                      {im.name}
                    </label>
                  ))}
                </div>
              )}
              {(detAudio.length > 0 || detImages.length > 0) && (
                <button
                  className="btn primary sm"
                  onClick={reEditWithMaterials}
                  disabled={reediting}
                  style={{ marginTop: 8 }}
                >
                  {reediting ? '再編集中…' : '🔁 素材を入れて再編集'}
                </button>
              )}
              {reeditOut && (
                <div className="ap-result lic-ok" style={{ marginTop: 8 }}>
                  🎬 素材入り完成
                  <div className="run-actions">
                    <button
                      className="btn ghost sm"
                      onClick={() => openFile(reeditOut)}
                    >
                      ▶ 再生
                    </button>
                    <button
                      className="btn ghost sm"
                      onClick={() =>
                        window.videocraft?.showItemInFolder?.(reeditOut)
                      }
                    >
                      📁 フォルダ
                    </button>
                    <button
                      className="btn primary sm"
                      onClick={() => sendToPublishing(reeditOut)}
                    >
                      🚀 投稿支援へ送る
                    </button>
                  </div>
                  <div className="muted ap-path">{reeditOut}</div>
                </div>
              )}
            </div>
          </div>
        )}
      </section>
      )}

      {/* 手動編集 */}
      {editTab === 'edit' && (
      <section className="card">
        <h2>✂️ 手動編集（タイムライン）</h2>
        <p className="muted lic-intro">
          プレビューを見ながらタイムラインでカット・テロップを配置し、下の設定で仕上げます。
        </p>

        {/* CapCut風タイムライン（cuts/telops を共有） */}
        <EditorTimeline
          videoPath={videoPath}
          duration={duration}
          cuts={cuts}
          setCuts={setCuts}
          telops={telops}
          setTelops={setTelops}
        />

        <div className="field-label">
          ✂️ カット（削除する区間）
          <button
            className="btn ghost sm"
            onClick={() =>
              setCuts([...cuts, { start_sec: 0, end_sec: duration || 1 }])
            }
          >
            ＋追加
          </button>
        </div>
        {cuts.map((c, i) => (
          <div className="row edit-row" key={i}>
            <input
              className="input sm-num"
              type="number"
              value={c.start_sec}
              onChange={(e) => {
                const n = [...cuts]
                n[i] = { ...c, start_sec: Number(e.target.value) }
                setCuts(n)
              }}
            />
            <span className="muted">〜</span>
            <input
              className="input sm-num"
              type="number"
              value={c.end_sec}
              onChange={(e) => {
                const n = [...cuts]
                n[i] = { ...c, end_sec: Number(e.target.value) }
                setCuts(n)
              }}
            />
            <span className="muted">秒</span>
            <button
              className="btn ghost sm"
              onClick={() => setCuts(cuts.filter((_, j) => j !== i))}
            >
              ✕
            </button>
          </div>
        ))}

        <div className="field-label" style={{ marginTop: 10 }}>
          💬 テロップ（色・大きさ・位置・アニメ）
          <button
            className="btn ghost sm"
            onClick={() =>
              setTelops([
                ...telops,
                {
                  time_sec: 0,
                  text: '',
                  size: 54,
                  color: '#ffffff',
                  stroke: '#000000',
                  x: 0.5,
                  y: 0.86,
                  bold: true,
                  anim: 'fade',
                },
              ])
            }
          >
            ＋追加
          </button>
        </div>
        {telops.map((t, i) => {
          const up = (patch: Partial<EditTelop>) => {
            const n = [...telops]
            n[i] = { ...t, ...patch }
            setTelops(n)
          }
          return (
            <div className="telop-edit" key={i}>
              <div className="row edit-row">
                <input
                  className="input sm-num"
                  type="number"
                  value={t.time_sec}
                  onChange={(e) => up({ time_sec: Number(e.target.value) })}
                />
                <span className="muted">秒</span>
                <input
                  className="input"
                  placeholder="テロップ文言"
                  value={t.text}
                  onChange={(e) => up({ text: e.target.value })}
                />
                <button
                  className="btn ghost sm"
                  onClick={() => setTelops(telops.filter((_, j) => j !== i))}
                >
                  ✕
                </button>
              </div>
              <div className="telop-style-row">
                <label className="thumb-color">
                  色
                  <input
                    type="color"
                    value={t.color ?? '#ffffff'}
                    onChange={(e) => up({ color: e.target.value })}
                  />
                </label>
                <label className="thumb-color">
                  縁
                  <input
                    type="color"
                    value={t.stroke ?? '#000000'}
                    onChange={(e) => up({ stroke: e.target.value })}
                  />
                </label>
                <label className="thumb-num">
                  大 {t.size ?? 54}
                  <input
                    type="range"
                    min={24}
                    max={140}
                    value={t.size ?? 54}
                    onChange={(e) => up({ size: Number(e.target.value) })}
                  />
                </label>
                <label className="thumb-num">
                  横 {Math.round((t.x ?? 0.5) * 100)}%
                  <input
                    type="range"
                    min={0}
                    max={100}
                    value={Math.round((t.x ?? 0.5) * 100)}
                    onChange={(e) => up({ x: Number(e.target.value) / 100 })}
                  />
                </label>
                <label className="thumb-num">
                  縦 {Math.round((t.y ?? 0.86) * 100)}%
                  <input
                    type="range"
                    min={5}
                    max={98}
                    value={Math.round((t.y ?? 0.86) * 100)}
                    onChange={(e) => up({ y: Number(e.target.value) / 100 })}
                  />
                </label>
                <label className="thumb-num">
                  アニメ
                  <select
                    value={t.anim ?? 'fade'}
                    onChange={(e) =>
                      up({ anim: e.target.value as EditTelop['anim'] })
                    }
                  >
                    <option value="none">なし</option>
                    <option value="fade">フェード</option>
                    <option value="pop">ポップ</option>
                    <option value="slide">スライド</option>
                  </select>
                </label>
              </div>
            </div>
          )
        })}

        <div className="audio-opts" style={{ marginTop: 10 }}>
          <label className="check">
            <input
              type="checkbox"
              checked={vertical}
              onChange={(e) => setVertical(e.target.checked)}
            />
            📱 縦動画化（9:16）
          </label>
          <label className="check">
            <input
              type="checkbox"
              checked={mute}
              onChange={(e) => setMute(e.target.checked)}
            />
            🔇 音声を消す
          </label>
        </div>
        {!mute && (
          <div className="vol-rows">
            <VolumeRow2 label="🔊 音量" value={volume} onChange={setVolume} />
          </div>
        )}

        {/* 再生速度・フィルタ・トランジション */}
        <div className="field-label" style={{ marginTop: 10 }}>
          🎞️ 速度・フィルタ・トランジション
        </div>
        <div className="fx-row">
          <label className="thumb-num">
            再生速度 {speed}x
            <input
              type="range"
              min={0.5}
              max={2}
              step={0.25}
              value={speed}
              onChange={(e) => setSpeed(Number(e.target.value))}
            />
          </label>
          <label className="thumb-num">
            色フィルタ
            <select value={vfilter} onChange={(e) => setVfilter(e.target.value)}>
              <option value="none">なし</option>
              <option value="vivid">ビビッド</option>
              <option value="mono">モノクロ</option>
              <option value="warm">暖色</option>
              <option value="cool">寒色</option>
              <option value="retro">レトロ</option>
              <option value="bright">明るく</option>
              <option value="cinema">シネマ</option>
            </select>
          </label>
          <label className="check">
            <input
              type="checkbox"
              checked={fadeIn}
              onChange={(e) => setFadeIn(e.target.checked)}
            />
            冒頭フェードイン
          </label>
          <label className="check">
            <input
              type="checkbox"
              checked={fadeOut}
              onChange={(e) => setFadeOut(e.target.checked)}
            />
            末尾フェードアウト
          </label>
        </div>

        {/* 素材インポート */}
        <div className="field-label" style={{ marginTop: 12 }}>
          📥 素材をインポート
        </div>
        <div className="row">
          <button className="btn ghost" onClick={pickBgm}>
            🎵 BGMを読み込む
          </button>
          {bgm && (
            <>
              <span className="muted mat-file">{bgm.split(/[\\/]/).pop()}</span>
              <button className="btn ghost sm" onClick={() => setBgm('')}>
                ✕
              </button>
            </>
          )}
          <button className="btn ghost" onClick={addOverlay}>
            🖼️ 画像を追加
          </button>
        </div>
        {bgm && (
          <div className="vol-rows">
            <VolumeRow2 label="🎵 BGM音量" value={bgmVol} onChange={setBgmVol} />
          </div>
        )}
        {overlays.map((o, i) => (
          <div className="row edit-row" key={i}>
            <span className="muted mat-file">{o.image.split(/[\\/]/).pop()}</span>
            <input
              className="input sm-num"
              type="number"
              value={o.start_sec}
              onChange={(e) => {
                const n = [...overlays]
                n[i] = { ...o, start_sec: Number(e.target.value) }
                setOverlays(n)
              }}
            />
            <span className="muted">〜</span>
            <input
              className="input sm-num"
              type="number"
              value={o.end_sec}
              onChange={(e) => {
                const n = [...overlays]
                n[i] = { ...o, end_sec: Number(e.target.value) }
                setOverlays(n)
              }}
            />
            <select
              value={o.position}
              onChange={(e) => {
                const n = [...overlays]
                n[i] = { ...o, position: e.target.value }
                setOverlays(n)
              }}
            >
              <option value="tr">右上</option>
              <option value="tl">左上</option>
              <option value="br">右下</option>
              <option value="bl">左下</option>
              <option value="center">中央</option>
            </select>
            <button
              className="btn ghost sm"
              onClick={() => setOverlays(overlays.filter((_, j) => j !== i))}
            >
              ✕
            </button>
          </div>
        ))}

        <label className="check">
          <input
            type="checkbox"
            checked={hasSubs}
            onChange={(e) => setHasSubs(e.target.checked)}
          />
          🔤 この動画には字幕がある（テロップを上に置いて字幕と被らせない）
        </label>
        <button
          className="btn primary"
          onClick={applyManual}
          disabled={editBusy !== ''}
          style={{ marginTop: 12 }}
        >
          {editBusy === 'manual' ? '適用中…' : '✂️ 編集を適用'}
        </button>
        {manualResult && (
          <div className="ap-result lic-ok">
            🎬 完成（{Math.round(manualResult.duration_sec)}秒）
            <div className="run-actions">
              <button
                className="btn ghost sm"
                onClick={() => openFile(manualResult.output_path)}
              >
                ▶ 再生
              </button>
              <button
                className="btn ghost sm"
                onClick={() =>
                  window.videocraft?.showItemInFolder?.(manualResult.output_path)
                }
              >
                📁 フォルダ
              </button>
              <button
                className="btn primary sm"
                onClick={() => sendToPublishing(manualResult.output_path)}
              >
                🚀 投稿支援へ送る
              </button>
            </div>
            <div className="muted ap-path">{manualResult.output_path}</div>
          </div>
        )}

        {/* 素材検索 */}
        <div className="mat-search">
          <div className="field-label">🔎 素材を探す（無料サイトのURLを表示）</div>
          <div className="row">
            <input
              className="input"
              placeholder="キーワード（例: 明るいBGM、拍手、カフェ）"
              value={matQuery}
              onChange={(e) => setMatQuery(e.target.value)}
            />
            <button className="btn" onClick={searchMat} disabled={editBusy !== ''}>
              {editBusy === 'mat' ? '検索中…' : '探す'}
            </button>
          </div>
          {materials && (
            <div className="mat-box">
              {materials.map((m, i) => (
                <MaterialRow key={i} m={m} onOpen={openExt} />
              ))}
            </div>
          )}
        </div>
      </section>
      )}

      {editTab === 'assets' && (
      <>
      {/* 編集スタイル学習 */}
      <section className="card style-card">
        <h2>🎯 好きな人の編集スタイルを学習</h2>
        <p className="muted lic-intro">
          参考にしたいYouTube動画のURLやクリエイター名、好きな編集の特徴を入れると、
          そのスタイルを学習して以降の提案に反映します。
        </p>
        <input
          className="input"
          placeholder="参考動画のURL（YouTube等・任意）"
          value={styleUrl}
          onChange={(e) => setStyleUrl(e.target.value)}
        />
        <div className="row">
          <input
            className="input"
            placeholder="クリエイター/チャンネル名（任意）"
            value={styleCreator}
            onChange={(e) => setStyleCreator(e.target.value)}
          />
          <button className="btn" onClick={learnStyle} disabled={busy === 'style'}>
            {busy === 'style' ? '学習中…' : 'スタイルを学習'}
          </button>
        </div>
        <input
          className="input"
          placeholder="好きな編集の特徴（例: テンポ速い・大きいテロップ・効果音多め）"
          value={styleNotes}
          onChange={(e) => setStyleNotes(e.target.value)}
        />
        {style && (
          <div className="style-profile">
            <div className="style-head">
              <span className="badge ok">
                学習済み{style.creator ? `：${style.creator}` : ''}
              </span>
              <button className="copy-btn" onClick={() => setStyle(null)}>
                クリア
              </button>
            </div>
            <p className="style-summary">{style.summary}</p>
            <ul className="style-traits">
              {style.pacing && <li>⚡ テンポ：{style.pacing}</li>}
              {style.cut_style && <li>✂️ カット：{style.cut_style}</li>}
              {style.telop_style && <li>💬 テロップ：{style.telop_style}</li>}
              {style.sound_style && <li>🎵 音：{style.sound_style}</li>}
              {style.hook_style && <li>🎯 掴み：{style.hook_style}</li>}
            </ul>
            <div className="chip-row">
              {style.keywords.map((k, i) => (
                <span key={i} className="chip">
                  {k}
                </span>
              ))}
            </div>
          </div>
        )}
      </section>

      {/* 条件 + 生成 */}
      <section className="card">
        <h2>
          ✂️ AI編集提案
          {style && <span className="badge ok style-applied">スタイル適用中</span>}
        </h2>
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
      </>
      )}
    </div>
  )
}

function MaterialRow({
  m,
  onOpen,
}: {
  m: MaterialSuggestion
  onOpen: (url: string) => void
}) {
  return (
    <div className="mat-row">
      <span className="mat-kind">{m.kind_label}</span>
      {m.query && <span className="muted">「{m.query}」</span>}
      <span className="mat-links">
        {m.sources.map((s, i) => (
          <button
            key={i}
            className="btn ghost sm"
            onClick={() => onOpen(s.url)}
            title={s.url}
          >
            {s.site}
          </button>
        ))}
      </span>
    </div>
  )
}

function VolumeRow2({
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
