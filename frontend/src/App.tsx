import { useEffect, useState } from 'react'
import { api, initDeviceId, getDeviceId } from './api/client'
import { handoff } from './handoff'
import type { HealthInfo, UsageInfo } from './types'
import TitleBar from './components/TitleBar'
import UpdateBanner from './components/UpdateBanner'
import Logo from './components/Logo'
import HomePage from './pages/HomePage'
import PlanningPage from './pages/PlanningPage'
import RecordingPage from './pages/RecordingPage'
import EditingPage from './pages/EditingPage'
import PublishingPage from './pages/PublishingPage'
import ChatPage from './pages/ChatPage'
import SettingsPage from './pages/SettingsPage'

type View =
  | 'home'
  | 'planning'
  | 'recording'
  | 'editing'
  | 'publishing'
  | 'chat'
  | 'settings'

type NavItem = {
  key: View
  label: string
  icon: string
  hint: string
  dev?: boolean
}

// プロジェクト作成後のガイド付きワークフロー（企画→録画→編集→投稿）
const WF_STEPS: { view: View; label: string; icon: string }[] = [
  { view: 'planning', label: '企画', icon: '💡' },
  { view: 'recording', label: '録画', icon: '🎥' },
  { view: 'editing', label: '編集', icon: '✂️' },
  { view: 'publishing', label: '投稿', icon: '🚀' },
]

const NAV: NavItem[] = [
  { key: 'home', label: 'プロジェクト', icon: '🎬', hint: '動画プロジェクト管理' },
  { key: 'planning', label: 'AI企画', icon: '💡', hint: '企画を自動生成' },
  { key: 'recording', label: '録画スタジオ', icon: '🎥', hint: '録画・自動撮影・ゆっくり' },
  { key: 'editing', label: '編集スタジオ', icon: '✂️', hint: 'AI編集・タイムライン' },
  { key: 'publishing', label: '投稿支援', icon: '🚀', hint: '投稿文を一括生成' },
  { key: 'chat', label: 'AIチャット', icon: '💬', hint: '対話で制作を進行' },
  { key: 'settings', label: '設定', icon: '⚙️', hint: 'AI・ライセンス設定' },
]

export default function App() {
  const [view, setView] = useState<View>('home')
  const [health, setHealth] = useState<HealthInfo | null>(null)
  const [usage, setUsage] = useState<UsageInfo | null>(null)
  const [offlineMode, setOfflineMode] = useState(false)
  const [ready, setReady] = useState(false)
  const [workflow, setWorkflow] = useState(false)

  // バックエンドに繋がらないとき: キャッシュ済みトークンをこのPCで検証してPro維持
  async function tryOfflineFallback(): Promise<boolean> {
    const token = localStorage.getItem('aivc_offline_token')
    const verify = window.videocraft?.verifyLicense
    if (!token || !verify) return false
    try {
      const res = await verify(token)
      if (res.valid && res.payload?.device === getDeviceId()) {
        setOfflineMode(true)
        setUsage({
          plan: 'pro',
          limits: {} as any,
          ai_runs_today: 0,
          ai_runs_limit: null,
          ai_runs_remaining: null,
          license_kind: res.payload.kind ?? null,
          license_expires_at: null,
          license_expires_in_days: null,
        })
        return true
      }
    } catch {
      /* ignore */
    }
    return false
  }

  const refreshUsage = () => {
    if (offlineMode) return
    api
      .usage()
      .then((u) => {
        setUsage(u)
        // オフライン用に署名トークンをキャッシュ
        api
          .offlineToken()
          .then((r) => {
            if (r.token) localStorage.setItem('aivc_offline_token', r.token)
            else localStorage.removeItem('aivc_offline_token')
          })
          .catch(() => {})
      })
      .catch(() => {
        tryOfflineFallback()
      })
  }

  // 起動時: デバイスID確定 → health / usage 取得
  useEffect(() => {
    initDeviceId().then(() => {
      setReady(true)
      api.health().then(setHealth).catch(() => {})
      refreshUsage()
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // AI利用状況は画面切替のたびに更新（生成後に残数へ反映するため）
  useEffect(() => {
    if (ready) refreshUsage()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view])

  // ページ間の「動画を送る」ナビゲーション（録画→編集→投稿）
  useEffect(() => {
    const onNav = (e: Event) => {
      const v = (e as CustomEvent).detail as View
      if (v) setView(v)
    }
    // プロジェクト作成後のガイド付きワークフロー開始
    const onWfStart = () => {
      setWorkflow(true)
      setView('planning')
    }
    window.addEventListener('aivc:navigate', onNav)
    window.addEventListener('aivc:workflow-start', onWfStart)
    return () => {
      window.removeEventListener('aivc:navigate', onNav)
      window.removeEventListener('aivc:workflow-start', onWfStart)
    }
  }, [])

  const wfIdx = WF_STEPS.findIndex((s) => s.view === view)

  // ワークフローで次のステップへ（スキップ/完了 共通のナビ）
  function wfAdvance() {
    if (wfIdx < 0) return
    if (wfIdx >= WF_STEPS.length - 1) {
      // 最後（投稿）で完了 → ワークフロー終了
      setWorkflow(false)
      handoff.workflowProjectId = undefined
      setView('home')
    } else {
      setView(WF_STEPS[wfIdx + 1].view)
    }
  }

  function wfExit() {
    setWorkflow(false)
    handoff.workflowProjectId = undefined
  }

  if (!ready) {
    return (
      <div className="app-shell">
        <div className="aurora" aria-hidden />
        <TitleBar />
      </div>
    )
  }

  return (
    <div className="app-shell">
      <div className="aurora" aria-hidden />
      <TitleBar />
      <UpdateBanner />

      <div className="app-body">
        <aside className="sidebar">
          <div className="brand">
            <div className="brand-badge">
              <Logo size={42} />
            </div>
            <div className="brand-text">
              <div className="brand-name">AI VideoCraft</div>
              <div className="brand-sub">v{health?.version ?? '0.1.0'}</div>
            </div>
          </div>

          <nav className="nav">
            {NAV.filter((n) => !n.dev || health?.dev_mode).map((n) => (
              <button
                key={n.key}
                className={`nav-item ${view === n.key ? 'active' : ''}`}
                onClick={() => setView(n.key)}
              >
                <span className="nav-icon">{n.icon}</span>
                <span className="nav-label">
                  {n.label}
                  {n.dev && <span className="nav-dev">DEV</span>}
                  <span className="nav-hint">{n.hint}</span>
                </span>
                <span className="nav-glow" aria-hidden />
              </button>
            ))}
          </nav>

          <div className="sidebar-footer">
            {health ? (
              <>
                <div className="device-row" title={getDeviceId()}>
                  <span className="device-ico">🖥️</span>
                  <span className="device-id">
                    このPC · {getDeviceId().slice(0, 8)}
                  </span>
                </div>
                <div className={`plan-chip ${usage?.plan ?? 'free'}`}>
                  <span className="plan-dot" />
                  {usage?.plan === 'pro' ? 'Pro プラン' : 'Free プラン'}
                </div>
                <div className="sys-row">
                  <span
                    className={`sys-dot ${health.ffmpeg_available ? 'ok' : 'warn'}`}
                  />
                  <span className="sys-text">
                    FFmpeg {health.ffmpeg_available ? '接続済み' : '未検出'}
                  </span>
                </div>
                {usage && usage.ai_runs_limit !== null && (
                  <div className="usage-box">
                    <div className="usage-head">
                      <span>本日のAI制作</span>
                      <span className="usage-count">
                        {usage.ai_runs_today}/{usage.ai_runs_limit}
                      </span>
                    </div>
                    <div className="usage-bar">
                      <div
                        className="usage-bar-fill"
                        style={{
                          width: `${Math.min(
                            100,
                            (usage.ai_runs_today / usage.ai_runs_limit) * 100,
                          )}%`,
                        }}
                      />
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="sys-row">
                <span className="sys-dot warn" />
                <span className="sys-text">接続確認中…</span>
              </div>
            )}
          </div>
        </aside>

        <main className="content">
          <div
            className={`content-inner${
              view === 'recording' || view === 'editing' ? ' wide' : ''
            }`}
          >
            {workflow && wfIdx >= 0 && (
              <div className="wf-bar">
                <div className="wf-steps">
                  {WF_STEPS.map((s, i) => (
                    <button
                      key={s.view}
                      className={`wf-step ${i === wfIdx ? 'active' : ''} ${
                        i < wfIdx ? 'done' : ''
                      }`}
                      onClick={() => setView(s.view)}
                    >
                      <span className="wf-num">{i < wfIdx ? '✓' : i + 1}</span>
                      {s.icon} {s.label}
                    </button>
                  ))}
                </div>
                <div className="wf-actions">
                  <button className="btn ghost sm" onClick={wfAdvance}>
                    スキップ →
                  </button>
                  <button className="btn primary sm" onClick={wfAdvance}>
                    {wfIdx === WF_STEPS.length - 1 ? '完了 🎉' : '完了して次へ →'}
                  </button>
                  <button
                    className="btn ghost sm"
                    onClick={wfExit}
                    title="ワークフローを終了"
                  >
                    ✕
                  </button>
                </div>
              </div>
            )}
            {offlineMode && (
              <div className="banner offline">
                📴 オフラインモード: キャッシュ済みライセンスでPro版を継続中です（一部機能はオンライン時のみ）。
              </div>
            )}
            {usage?.license_kind === 'subscription' &&
              usage.plan === 'pro' &&
              usage.license_expires_in_days !== null &&
              usage.license_expires_in_days <= 7 && (
                <div
                  className="banner reminder"
                  onClick={() => setView('settings')}
                >
                  ⏳ サブスクの有効期限が近づいています（残り
                  {usage.license_expires_in_days}日）。更新版のライセンスで再有効化してください。→ 設定
                </div>
              )}
            {usage?.license_kind === 'subscription' && usage.plan === 'free' && (
              <div
                className="banner reminder-expired"
                onClick={() => setView('settings')}
              >
                ⚠️ サブスクの有効期限が切れました。更新版のライセンスで再有効化するとPro版を継続できます。→ 設定
              </div>
            )}
            <div key={view} className="view-fade">
              {view === 'home' && <HomePage />}
              {view === 'planning' && <PlanningPage />}
              {view === 'recording' && <RecordingPage />}
              {view === 'editing' && <EditingPage />}
              {view === 'publishing' && <PublishingPage />}
              {view === 'chat' && <ChatPage />}
              {view === 'settings' && (
                <SettingsPage onPlanChanged={refreshUsage} />
              )}
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
