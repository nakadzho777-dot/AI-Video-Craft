import { useEffect, useState } from 'react'
import { api, setToken, getToken } from './api/client'
import type { HealthInfo, UsageInfo, UserInfo } from './types'
import TitleBar from './components/TitleBar'
import AuthScreen from './components/AuthScreen'
import HomePage from './pages/HomePage'
import PlanningPage from './pages/PlanningPage'
import RecordingPage from './pages/RecordingPage'
import EditingPage from './pages/EditingPage'
import MarketingPage from './pages/MarketingPage'
import PublishingPage from './pages/PublishingPage'
import ChatPage from './pages/ChatPage'
import SettingsPage from './pages/SettingsPage'

type View =
  | 'home'
  | 'planning'
  | 'recording'
  | 'editing'
  | 'marketing'
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

const NAV: NavItem[] = [
  { key: 'home', label: 'プロジェクト', icon: '🎬', hint: '動画プロジェクト管理' },
  { key: 'planning', label: 'AI企画', icon: '💡', hint: '企画を自動生成' },
  { key: 'recording', label: '録画支援', icon: '🎥', hint: '録画手順をガイド' },
  { key: 'editing', label: '編集支援', icon: '✂️', hint: 'AI編集提案・処理' },
  // 開発者専用（dev_mode のときだけ表示）
  { key: 'marketing', label: '宣伝AI', icon: '📣', hint: '記事・SEOを量産', dev: true },
  { key: 'publishing', label: '投稿支援', icon: '🚀', hint: '投稿文を一括生成' },
  { key: 'chat', label: 'AIチャット', icon: '💬', hint: '対話で制作を進行' },
  { key: 'settings', label: '設定', icon: '⚙️', hint: 'AI・ライセンス設定' },
]

export default function App() {
  const [view, setView] = useState<View>('home')
  const [health, setHealth] = useState<HealthInfo | null>(null)
  const [usage, setUsage] = useState<UsageInfo | null>(null)
  const [user, setUser] = useState<UserInfo | null>(null)
  const [authChecked, setAuthChecked] = useState(false)
  const [offlineMode, setOfflineMode] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // オンライン時: オフライン利用トークンとアカウントをキャッシュしておく
  function cacheForOffline(u: UserInfo) {
    localStorage.setItem('aivc_user', JSON.stringify(u))
    api
      .offlineToken()
      .then((r) => {
        if (r.token) localStorage.setItem('aivc_offline_token', r.token)
        else localStorage.removeItem('aivc_offline_token')
      })
      .catch(() => {})
  }

  // バックエンドに繋がらないとき: キャッシュ済みトークンをオフライン検証してPro維持
  async function tryOfflineFallback(): Promise<boolean> {
    const cachedUser = localStorage.getItem('aivc_user')
    const token = localStorage.getItem('aivc_offline_token')
    const verify = window.videocraft?.verifyLicense
    if (!cachedUser || !token || !verify) return false
    try {
      const res = await verify(token)
      const u: UserInfo = JSON.parse(cachedUser)
      if (res.valid && res.payload?.email === u.email.toLowerCase()) {
        setUser(u)
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

  useEffect(() => {
    api
      .health()
      .then(setHealth)
      .catch(() => {})
    if (getToken()) {
      api
        .me()
        .then((u) => {
          setUser(u)
          cacheForOffline(u)
        })
        .catch(async () => {
          // オフライン等で /auth/me 失敗 → キャッシュで継続を試みる
          const ok = await tryOfflineFallback()
          if (!ok) {
            setToken(null)
            setError('バックエンドに接続できません。')
          }
        })
        .finally(() => setAuthChecked(true))
    } else {
      setAuthChecked(true)
    }
  }, [])

  const refreshUsage = () => {
    if (user && !offlineMode) {
      api
        .usage()
        .then((u) => {
          setUsage(u)
          cacheForOffline(user)
        })
        .catch(() => {})
    }
  }

  // AI利用状況は画面切替のたびに更新（生成後に残数へ反映するため）
  useEffect(() => {
    refreshUsage()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, user])

  function logout() {
    api.logout().catch(() => {})
    setToken(null)
    setUser(null)
    setUsage(null)
    setOfflineMode(false)
    localStorage.removeItem('aivc_offline_token')
    localStorage.removeItem('aivc_user')
    setView('home')
  }

  // 認証チェック中 / 未ログインの表示
  if (!authChecked) {
    return (
      <div className="app-shell">
        <div className="aurora" aria-hidden />
        <TitleBar />
      </div>
    )
  }
  if (!user) {
    return (
      <div className="app-shell">
        <TitleBar />
        <AuthScreen
          onAuthed={(u) => {
            setUser(u)
            cacheForOffline(u)
          }}
        />
      </div>
    )
  }

  return (
    <div className="app-shell">
      <div className="aurora" aria-hidden />
      <TitleBar />

      <div className="app-body">
        <aside className="sidebar">
          <div className="brand">
            <div className="brand-badge">🎥</div>
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
                <div className="account-row">
                  <div className="account-info">
                    <div className="account-name">{user.username}</div>
                    <div className="account-email">{user.email}</div>
                  </div>
                  <button className="logout-btn" onClick={logout} title="ログアウト">
                    ⏻
                  </button>
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
          <div className="content-inner">
            {offlineMode && (
              <div className="banner offline">
                📴 オフラインモード: キャッシュ済みライセンスでPro版を継続中です（一部機能はオンライン時のみ）。
              </div>
            )}
            {error && <div className="banner error">{error}</div>}
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
              {view === 'marketing' && <MarketingPage />}
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
