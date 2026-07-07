import { useEffect, useState } from 'react'
import { api, getDeviceId } from '../api/client'
import type {
  BillingConfig,
  KeygenResult,
  LicenseStatus,
  SigningInfo,
} from '../types'
import CopyButton from './CopyButton'

function fmtDate(iso: string | null): string {
  if (!iso) return ''
  return iso.slice(0, 10)
}

export default function LicenseCard({
  devMode,
  onChanged,
}: {
  devMode: boolean
  onChanged?: () => void
}) {
  const [status, setStatus] = useState<LicenseStatus | null>(null)
  const [token, setToken] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [ok, setOk] = useState<string | null>(null)

  // 販売者: 署名発行（購入者のデバイスIDに紐づけ）
  const [signDevice, setSignDevice] = useState('')
  const [signKind, setSignKind] = useState<'perpetual' | 'subscription'>('perpetual')
  const [signDays, setSignDays] = useState(365)
  const [signedToken, setSignedToken] = useState('')

  // 販売者: 鍵の状態・本番鍵生成
  const [signing, setSigning] = useState<SigningInfo | null>(null)
  const [genKeys, setGenKeys] = useState<KeygenResult | null>(null)

  // 買い手: 購入リクエスト / 決済
  const [buyPlan, setBuyPlan] = useState<'perpetual' | 'subscription'>('perpetual')
  const [buyContact, setBuyContact] = useState('')
  const [buyMsg, setBuyMsg] = useState<string | null>(null)
  const [billing, setBilling] = useState<BillingConfig | null>(null)

  // Stripe決済ページ等は既定ブラウザで開く（アプリ内遷移させない）
  function openExternal(url: string) {
    if (window.videocraft?.openExternal) window.videocraft.openExternal(url)
    else window.open(url, '_blank', 'noopener')
  }

  // 直近の決済セッション（ポーリング/手動確認で使う）
  const [pendingSession, setPendingSession] = useState<string | null>(null)
  const [verifying, setVerifying] = useState(false)

  // 決済が完了したか確認する。session_id があれば Stripe に直接確認して
  // （Webhook無しでも）Pro を発行する。戻り値: Pro になったか。
  async function checkPro(sessionId?: string | null): Promise<boolean> {
    try {
      if (sessionId) {
        const v = await api.verifyCheckout(sessionId)
        if (v.plan === 'pro') {
          const s = await api.licenseStatus()
          setStatus(s)
          return true
        }
        return false
      }
      const s = await api.licenseStatus()
      setStatus(s)
      return s.plan === 'pro'
    } catch {
      return false
    }
  }

  // 決済完了を検知するまで一定間隔でポーリング
  function pollForPro(sessionId?: string | null) {
    let tries = 0
    const timer = setInterval(async () => {
      tries += 1
      if (await checkPro(sessionId)) {
        setBuyMsg('決済を確認しました。Pro版が有効になりました。')
        setPendingSession(null)
        onChanged?.()
        clearInterval(timer)
        return
      }
      if (tries >= 45) clearInterval(timer) // 最大 ~3分
    }, 4000)
  }

  // 手動での「支払いを確認」（ポーリングが時間切れした場合の保険）
  async function verifyNow() {
    if (verifying) return
    setVerifying(true)
    setError(null)
    try {
      const done = await checkPro(pendingSession)
      if (done) {
        setBuyMsg('決済を確認しました。Pro版が有効になりました。')
        setPendingSession(null)
        onChanged?.()
      } else {
        setBuyMsg('まだ決済が確認できません。支払い完了後、少し待ってからもう一度お試しください。')
      }
    } finally {
      setVerifying(false)
    }
  }

  async function checkout() {
    setBuyMsg(null)
    setError(null)
    try {
      const r = await api.checkout(buyPlan)
      setPendingSession(r.session_id)
      openExternal(r.checkout_url) // ブラウザで決済ページを開く
      setBuyMsg('ブラウザで決済ページを開きました。支払いが完了するとこの画面が自動的にPro版に切り替わります。')
      pollForPro(r.session_id)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function requestPurchase() {
    setBuyMsg(null)
    setError(null)
    try {
      const r = await api.purchaseRequest(buyPlan, buyContact.trim())
      if (r.sent) {
        setBuyMsg(`販売者（${r.notify_email}）に購入リクエストを送信しました。ライセンスが届くまでお待ちください。`)
      } else {
        // SMTP未設定: 買い手のメールソフトを開く
        openExternal(r.mailto)
        setBuyMsg(`メールソフトを開きました。宛先（${r.notify_email}）にそのまま送信してください。`)
      }
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const load = () => api.licenseStatus().then(setStatus).catch(() => {})
  useEffect(() => {
    load()
    api.billingConfig().then(setBilling).catch(() => {})
    if (devMode) api.signingInfo().then(setSigning).catch(() => {})
  }, [devMode])

  async function activate() {
    if (!token.trim() || busy) return
    setBusy(true)
    setError(null)
    setOk(null)
    try {
      const s = await api.activateOffline(token.trim())
      setStatus(s)
      setToken('')
      setOk('ライセンスを有効化しました。Pro版が利用できます。')
      onChanged?.()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function sign() {
    setError(null)
    try {
      const r = await api.signLicense(signDevice.trim(), signKind, signDays)
      setSignedToken(r.license_token)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const isPro = status?.plan === 'pro'

  return (
    <section className="card license-card">
      <div className="provider-head">
        <h2>🔑 ライセンス</h2>
        <span className={`badge ${isPro ? 'ok' : 'muted'}`}>
          {isPro ? 'Pro 有効' : 'Free'}
        </span>
      </div>

      {status?.has_license && isPro ? (
        <div>
          <div className="lic-key-row">
            <span className="lic-plan-label">
              {status.kind === 'subscription' ? '📅 サブスクリプション' : '♾️ 買い切り'}
            </span>
            <span className="muted">
              {status.kind === 'subscription' && status.expires_at
                ? `${fmtDate(status.expires_at)} まで有効`
                : '無期限'}
            </span>
          </div>
          <p className="muted lic-note">
            🖥️ このPC（{getDeviceId().slice(0, 8)}）で有効です。
          </p>
          {status.kind === 'subscription' && (
            <p className="muted lic-note">
              期限が切れると自動的にFreeに戻ります。更新版のライセンスで再有効化してください。
            </p>
          )}
        </div>
      ) : (
        <div>
          {/* 購入（決済 or リクエスト） */}
          <div className="buy-box">
            <div className="field-label">Pro版を購入</div>
            <div className="row">
              <select
                value={buyPlan}
                onChange={(e) => setBuyPlan(e.target.value as any)}
              >
                <option value="perpetual">買い切り（無期限）</option>
                <option value="subscription">サブスク（期間制）</option>
              </select>
              {billing?.stripe_enabled ? (
                <button className="btn primary buy-btn" onClick={checkout}>
                  決済して購入
                </button>
              ) : (
                <button className="btn primary buy-btn" onClick={requestPurchase}>
                  購入をリクエスト
                </button>
              )}
            </div>
            {!billing?.stripe_enabled && (
              <>
                <div className="field-label">連絡先（返信用・任意）</div>
                <input
                  className="input"
                  placeholder="メールアドレス等（ライセンスの受け取り先）"
                  value={buyContact}
                  onChange={(e) => setBuyContact(e.target.value)}
                />
                <div className="device-box">
                  <span className="muted">このPCのID</span>
                  <code className="device-code">{getDeviceId()}</code>
                  <CopyButton text={getDeviceId()} />
                </div>
              </>
            )}
            {buyMsg && <div className="lic-ok">{buyMsg}</div>}
            {pendingSession && billing?.stripe_enabled && (
              <button
                className="btn ghost buy-verify"
                onClick={verifyNow}
                disabled={verifying}
              >
                {verifying ? '確認中…' : '支払いが完了したのに切り替わらない場合はこちら（支払いを確認）'}
              </button>
            )}
            <p className="muted lic-note">
              {billing?.stripe_enabled
                ? '決済が完了すると、このPCで自動的にPro版が有効になります。'
                : 'このPCのIDと一緒に販売者へ通知が届きます。入金確認後、このPC専用のライセンスが届きます。'}
            </p>
          </div>

          {/* オフライン有効化 */}
          <div className="activate-box">
            <div className="field-label">受け取ったライセンスを有効化</div>
            <textarea
              className="input"
              rows={3}
              placeholder="AIVC1.xxxxx.xxxxx"
              value={token}
              onChange={(e) => setToken(e.target.value)}
            />
            <button className="btn primary" onClick={activate} disabled={busy}>
              {busy ? '確認中…' : 'オフライン有効化'}
            </button>
          </div>
        </div>
      )}

      {error && <div className="banner error">{error}</div>}
      {ok && <div className="lic-ok">{ok}</div>}

      {devMode && signing?.using_dev_public_key && (
        <div className="key-warning">
          ⚠️ 現在は<b>同梱DEV鍵</b>で署名/検証しています。実販売の前に下の「本番鍵を生成」で
          自分の鍵へ差し替えてください（差し替えないと第三者が偽造できます）。
        </div>
      )}

      {devMode && (
        <div className="issue-box">
          <div className="field-label">
            <span className="dev-badge">DEV</span> 署名ライセンス発行（販売者用）
          </div>
          <div className="plan-form-grid">
            <label>
              購入者のデバイスID
              <input
                className="input"
                placeholder="購入リクエストに記載のデバイスID"
                value={signDevice}
                onChange={(e) => setSignDevice(e.target.value)}
              />
            </label>
            <label>
              種別
              <select
                value={signKind}
                onChange={(e) => setSignKind(e.target.value as any)}
              >
                <option value="perpetual">買い切り（無期限）</option>
                <option value="subscription">サブスク（期限あり）</option>
              </select>
            </label>
            {signKind === 'subscription' && (
              <label>
                有効日数
                <input
                  className="input"
                  type="number"
                  min={1}
                  value={signDays}
                  onChange={(e) => setSignDays(Number(e.target.value) || 1)}
                />
              </label>
            )}
          </div>
          <button className="btn ghost" onClick={sign}>
            署名して発行
          </button>
          {signedToken && (
            <div className="issued-keys">
              <div className="field-label">
                発行済みライセンス（購入者へメール送付）
                <CopyButton text={signedToken} />
              </div>
              <pre className="keys-pre">{signedToken}</pre>
            </div>
          )}
          <p className="muted lic-note">
            秘密鍵は環境変数 AIVC_LICENSE_PRIVATE_KEY で設定します（未設定時は同梱DEV鍵）。
          </p>

          <div className="keygen-box">
            <div className="field-label">本番鍵の生成（実販売用に差し替え）</div>
            <button
              className="btn ghost"
              onClick={async () => setGenKeys(await api.generateKeypair())}
            >
              本番鍵を生成
            </button>
            {genKeys && (
              <div className="genkeys">
                <div className="genkey-row">
                  <div className="field-label">
                    公開鍵（配布アプリに設定）
                    <CopyButton
                      text={`AIVC_LICENSE_PUBLIC_KEY=${genKeys.public_key}`}
                    />
                  </div>
                  <pre className="keys-pre">{genKeys.public_key}</pre>
                </div>
                <div className="genkey-row">
                  <div className="field-label">
                    秘密鍵（署名する端末だけに設定・一度きり表示）
                    <CopyButton
                      text={`AIVC_LICENSE_PRIVATE_KEY=${genKeys.private_key}`}
                    />
                  </div>
                  <pre className="keys-pre danger-key">{genKeys.private_key}</pre>
                </div>
                <p className="muted lic-note">{genKeys.instructions.note}</p>
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  )
}
