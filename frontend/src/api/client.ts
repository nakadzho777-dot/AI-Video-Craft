// バックエンド (FastAPI) との通信層。
// UI コンポーネントはこのクライアント経由でのみ API を呼ぶ。

import type {
  AuthResult,
  BillingConfig,
  ChatTurn,
  GuideRequest,
  GuideResponse,
  HealthInfo,
  KeygenResult,
  LicenseStatus,
  MarketingRequest,
  MarketingResponse,
  PlanRequest,
  PurchaseRequestResult,
  PlanResponse,
  ProbeResponse,
  Project,
  ProductionMode,
  MaterialMode,
  ProviderInfo,
  PublishRequest,
  PublishResponse,
  SigningInfo,
  SilenceRange,
  SuggestRequest,
  SuggestResponse,
  UsageInfo,
  UserInfo,
} from '../types'

// preload が公開する値。未定義（ブラウザ実行時）は既定 URL にフォールバック。
const BASE_URL =
  (window as any).videocraft?.backendBaseUrl ?? 'http://localhost:8756'

// --- 認証トークン（localStorage 永続化） ---
let authToken: string | null = localStorage.getItem('aivc_token')

export function setToken(token: string | null): void {
  authToken = token
  if (token) localStorage.setItem('aivc_token', token)
  else localStorage.removeItem('aivc_token')
}

export function getToken(): string | null {
  return authToken
}

// この端末の一意ID（ライセンス端末登録に使用）
export function getDeviceId(): string {
  let id = localStorage.getItem('aivc_device_id')
  if (!id) {
    id = crypto.randomUUID()
    localStorage.setItem('aivc_device_id', id)
  }
  return id
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (authToken) headers.Authorization = `Bearer ${authToken}`
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: { ...headers, ...(init?.headers as Record<string, string>) },
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail ?? detail
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const api = {
  health: () => request<HealthInfo>('/health'),
  usage: () => request<UsageInfo>('/settings/usage'),

  // --- auth ---
  register: (email: string, password: string, username?: string) =>
    request<AuthResult>('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, username }),
    }),
  login: (email: string, password: string) =>
    request<AuthResult>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  logout: () => request<{ ok: boolean }>('/auth/logout', { method: 'POST' }),
  me: () => request<UserInfo>('/auth/me'),

  // --- license ---
  licenseStatus: () => request<LicenseStatus>('/license/status'),
  redeemLicense: (license_key: string, device_name: string) =>
    request<LicenseStatus>('/license/redeem', {
      method: 'POST',
      body: JSON.stringify({
        license_key,
        device_id: getDeviceId(),
        device_name,
      }),
    }),
  releaseDevice: (device_id: string) =>
    request<LicenseStatus>('/license/devices/release', {
      method: 'POST',
      body: JSON.stringify({ device_id }),
    }),
  issueLicenses: (count: number, booth_order_number?: string) =>
    request<{ count: number; keys: string[] }>('/license/issue', {
      method: 'POST',
      body: JSON.stringify({ count, booth_order_number }),
    }),
  activateOffline: (license_token: string) =>
    request<LicenseStatus>('/license/activate-offline', {
      method: 'POST',
      body: JSON.stringify({ license_token }),
    }),
  signLicense: (email: string, kind: string, days: number) =>
    request<{ license_token: string; email: string }>('/license/sign', {
      method: 'POST',
      body: JSON.stringify({ email, kind, days }),
    }),
  offlineToken: () => request<{ token: string | null }>('/license/offline-token'),
  signingInfo: () => request<SigningInfo>('/license/signing-info'),
  generateKeypair: () =>
    request<KeygenResult>('/license/keygen', { method: 'POST' }),

  // --- billing (購入リクエスト / 決済) ---
  purchaseRequest: (plan: string, note?: string) =>
    request<PurchaseRequestResult>('/billing/purchase-request', {
      method: 'POST',
      body: JSON.stringify({ plan, note }),
    }),
  billingConfig: () => request<BillingConfig>('/billing/config'),
  checkout: (plan: string) =>
    request<{ checkout_url: string; session_id: string }>('/billing/checkout', {
      method: 'POST',
      body: JSON.stringify({ plan }),
    }),

  // --- projects ---
  listProjects: () => request<Project[]>('/projects'),
  createProject: (data: {
    title: string
    description?: string
    production_mode?: ProductionMode
    material_mode?: MaterialMode
  }) =>
    request<Project>('/projects', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  deleteProject: (id: number) =>
    request<void>(`/projects/${id}`, { method: 'DELETE' }),

  // --- ai ---
  listProviders: () => request<ProviderInfo[]>('/ai/providers'),
  listModels: (providerId: string) =>
    request<string[]>(`/ai/providers/${providerId}/models`),
  setApiKey: (providerId: string, apiKey: string) =>
    request(`/settings/ai/${providerId}/api-key`, {
      method: 'PUT',
      body: JSON.stringify({ api_key: apiKey }),
    }),
  chat: (data: { provider?: string; model?: string; messages: ChatTurn[] }) =>
    request<{ text: string; provider: string; model: string }>('/ai/chat', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // --- planning (AI企画) ---
  generatePlan: (data: PlanRequest) =>
    request<PlanResponse>('/planning/generate', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // --- recording (録画支援) ---
  generateGuide: (data: GuideRequest) =>
    request<GuideResponse>('/recording/guide', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // --- editing (編集支援) ---
  probeVideo: (input_path: string) =>
    request<ProbeResponse>('/editing/probe', {
      method: 'POST',
      body: JSON.stringify({ input_path }),
    }),
  suggestEdit: (data: SuggestRequest) =>
    request<SuggestResponse>('/editing/suggest', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  detectSilence: (input_path: string) =>
    request<SilenceRange[]>('/editing/silence', {
      method: 'POST',
      body: JSON.stringify({ input_path }),
    }),

  // --- publishing (投稿支援) ---
  generatePublish: (data: PublishRequest) =>
    request<PublishResponse>('/publishing/generate', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // --- marketing (宣伝AI・開発者専用) ---
  generateMarketing: (data: MarketingRequest) =>
    request<MarketingResponse>('/marketing/generate', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
}
