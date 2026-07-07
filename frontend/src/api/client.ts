// バックエンド (FastAPI) との通信層。
// UI コンポーネントはこのクライアント経由でのみ API を呼ぶ。

import type {
  AutopilotPlan,
  AutopilotPlanRequest,
  AutopilotPlanResponse,
  AutopilotRunResponse,
  AutopilotVoice,
  AutoEditResponse,
  CharacterConfig,
  EditCut,
  EditOverlay,
  EditTelop,
  DurationSuggestion,
  ManualEditResponse,
  MaterialSearchResponse,
  DesktopPlan,
  DesktopPlanRequest,
  DesktopPlanResponse,
  YukkuriScript,
  YukkuriScriptRequest,
  YukkuriScriptResponse,
  YukkuriRenderResponse,
  BillingConfig,
  ChatTurn,
  GuideRequest,
  GuideResponse,
  HealthInfo,
  KeygenResult,
  LearnStyleRequest,
  LearnStyleResponse,
  LicenseStatus,
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
  ThumbSpec,
  UsageInfo,
  VideoPlan,
} from '../types'

// preload が公開する値。未定義（ブラウザ実行時）は既定 URL にフォールバック。
const BASE_URL =
  (window as any).videocraft?.backendBaseUrl ?? 'http://localhost:8756'

// --- デバイスID（PC単位の識別子）---
// Electron は userData に永続化された値、ブラウザは localStorage の UUID。
let DEVICE_ID = ''

export function getDeviceId(): string {
  return DEVICE_ID
}

export async function initDeviceId(): Promise<string> {
  if (DEVICE_ID) return DEVICE_ID
  const fromElectron = await (window as any).videocraft?.getDeviceId?.()
  if (fromElectron) {
    DEVICE_ID = fromElectron
    return DEVICE_ID
  }
  let id = localStorage.getItem('aivc_device_id')
  if (!id) {
    id = crypto.randomUUID()
    localStorage.setItem('aivc_device_id', id)
  }
  DEVICE_ID = id
  return id
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (DEVICE_ID) headers['X-Device-Id'] = DEVICE_ID
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

  // --- license（PC単位）---
  licenseStatus: () => request<LicenseStatus>('/license/status'),
  redeemLicense: (license_key: string) =>
    request<LicenseStatus>('/license/redeem', {
      method: 'POST',
      body: JSON.stringify({ license_key }),
    }),
  activateOffline: (license_token: string) =>
    request<LicenseStatus>('/license/activate-offline', {
      method: 'POST',
      body: JSON.stringify({ license_token }),
    }),
  signLicense: (device_id: string, kind: string, days: number) =>
    request<{ license_token: string; device_id: string }>('/license/sign', {
      method: 'POST',
      body: JSON.stringify({ device_id, kind, days }),
    }),
  offlineToken: () => request<{ token: string | null }>('/license/offline-token'),
  signingInfo: () => request<SigningInfo>('/license/signing-info'),
  generateKeypair: () =>
    request<KeygenResult>('/license/keygen', { method: 'POST' }),

  // --- billing (購入リクエスト / 決済) ---
  purchaseRequest: (plan: string, contact?: string, note?: string) =>
    request<PurchaseRequestResult>('/billing/purchase-request', {
      method: 'POST',
      body: JSON.stringify({ plan, contact, note }),
    }),
  billingConfig: () => request<BillingConfig>('/billing/config'),
  checkout: (plan: string) =>
    request<{ checkout_url: string; session_id: string }>('/billing/checkout', {
      method: 'POST',
      body: JSON.stringify({ plan }),
    }),
  // Webhookに頼らず session_id で決済を確認して Pro を発行する
  verifyCheckout: (session_id: string) =>
    request<{ paid: boolean; activated: boolean; plan: string }>(
      '/billing/verify',
      { method: 'POST', body: JSON.stringify({ session_id }) },
    ),

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
  savePlan: (project_id: number, plan: VideoPlan, notes = '') =>
    request<{ project_id: number; variation_count: number }>('/planning/save', {
      method: 'POST',
      body: JSON.stringify({ project_id, plan, notes }),
    }),
  suggestDurations: async (
    topic: string,
    notes: string,
    provider?: string,
    model?: string,
  ): Promise<DurationSuggestion> => {
    // 尺候補は「必ず出す」。バックエンド未起動・ネット不通・エラー等でも
    // ローカルの目安候補を返して、候補が出ないことをなくす。
    try {
      return await request<DurationSuggestion>('/planning/durations', {
        method: 'POST',
        body: JSON.stringify({ topic, notes, provider, model }),
      })
    } catch {
      return {
        video_sec: 240,
        short_sec: 45,
        note: 'AIに繋がらなかったため、目安の候補を表示しています。',
        record_video_sec: 312,
        record_short_sec: 63,
      }
    }
  },
  setProjectTarget: (id: number, target_duration_sec: number) =>
    request<Project>(`/projects/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ target_duration_sec }),
    }),

  // --- recording (録画支援) ---
  generateGuide: (data: GuideRequest) =>
    request<GuideResponse>('/recording/guide', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // --- autopilot (AI自動撮影: ブラウザ自動操作＋TTS) ---
  autopilotVoices: () =>
    request<{ voices: AutopilotVoice[] }>('/autopilot/voices'),
  autopilotPlan: (data: AutopilotPlanRequest) =>
    request<AutopilotPlanResponse>('/autopilot/plan', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  autopilotRun: (
    plan: AutopilotPlan,
    voice: string,
    subtitles = true,
    yukkuri = false,
    yukkuri_name = '霊夢',
    allowed_urls: string[] = [],
    token = '',
    yukkuri_avatar = '',
    yukkuri_show = true,
    narrate = true,
  ) =>
    request<AutopilotRunResponse>('/autopilot/run', {
      method: 'POST',
      body: JSON.stringify({
        plan,
        voice,
        subtitles,
        yukkuri,
        yukkuri_name,
        yukkuri_avatar,
        yukkuri_show,
        allowed_urls,
        token,
        narrate,
      }),
    }),
  autopilotCancel: (token: string) =>
    request<{ cancelled: boolean }>('/autopilot/cancel', {
      method: 'POST',
      body: JSON.stringify({ token }),
    }),
  // デスクトップアプリ版
  desktopWindows: () =>
    request<{ windows: string[] }>('/autopilot/desktop/windows'),
  desktopPlan: (data: DesktopPlanRequest) =>
    request<DesktopPlanResponse>('/autopilot/desktop/plan', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  desktopRun: (
    plan: DesktopPlan,
    voice: string,
    subtitles = true,
    token = '',
    narrate = true,
  ) =>
    request<AutopilotRunResponse>('/autopilot/desktop/run', {
      method: 'POST',
      body: JSON.stringify({ plan, voice, subtitles, token, narrate }),
    }),

  // --- ゆっくり解説 ---
  yukkuriConfig: () =>
    request<{
      voice_engine: string
      voices: { id: string; label: string }[]
      voicevox_available: boolean
      voicevox_download_url: string
      aquestalk_available: boolean
      aquestalk_dir: string
      aquestalk_download_url: string
    }>('/yukkuri/config'),
  yukkuriScript: (data: YukkuriScriptRequest) =>
    request<YukkuriScriptResponse>('/yukkuri/script', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  yukkuriRender: (script: YukkuriScript, chars: CharacterConfig) =>
    request<YukkuriRenderResponse>('/yukkuri/render', {
      method: 'POST',
      body: JSON.stringify({ script, chars }),
    }),
  yukkuriJikkyou: (
    base_video: string,
    script: YukkuriScript,
    chars: CharacterConfig,
    voice_a: string,
    voice_b: string,
    subtitles = true,
    keep_original_audio = true,
  ) =>
    request<YukkuriRenderResponse>('/yukkuri/jikkyou/render', {
      method: 'POST',
      body: JSON.stringify({
        base_video,
        script,
        chars,
        voice_a,
        voice_b,
        subtitles,
        keep_original_audio,
      }),
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
  learnStyle: (data: LearnStyleRequest) =>
    request<LearnStyleResponse>('/editing/learn-style', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  detectSilence: (input_path: string) =>
    request<SilenceRange[]>('/editing/silence', {
      method: 'POST',
      body: JSON.stringify({ input_path }),
    }),
  autoEdit: (
    input_path: string,
    instructions: string,
    provider?: string,
    model?: string,
    has_subtitles = false,
    vertical = false,
    edit_heavy = false,
  ) =>
    request<AutoEditResponse>('/editing/auto', {
      method: 'POST',
      body: JSON.stringify({
        input_path,
        instructions,
        provider,
        model,
        has_subtitles,
        vertical,
        edit_heavy,
      }),
    }),
  applyEdit: (data: {
    input_path: string
    cuts: EditCut[]
    telops: EditTelop[]
    vertical?: boolean
    volume?: number
    mute?: boolean
    bgm?: string
    bgm_volume?: number
    overlays?: EditOverlay[]
    has_subtitles?: boolean
    speed?: number
    vfilter?: string
    fade_in?: number
    fade_out?: number
  }) =>
    request<ManualEditResponse>('/editing/apply', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  searchMaterials: (query: string) =>
    request<MaterialSearchResponse>('/editing/materials', {
      method: 'POST',
      body: JSON.stringify({ query }),
    }),
  timelineThumbnails: (input_path: string, count = 12) =>
    request<{ frames: string[] }>('/editing/thumbnails', {
      method: 'POST',
      body: JSON.stringify({ input_path, count }),
    }),
  detectMaterials: (folder: string) =>
    request<{
      audio: { path: string; name: string }[]
      images: { path: string; name: string }[]
    }>('/editing/detect-materials', {
      method: 'POST',
      body: JSON.stringify({ folder }),
    }),

  // --- publishing (投稿支援) ---
  generatePublish: (data: PublishRequest) =>
    request<PublishResponse>('/publishing/generate', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // --- サムネイル作業場 ---
  thumbnailScene: (video_path: string, time_sec: number) =>
    request<{ image_path: string }>('/publishing/thumbnail/scene', {
      method: 'POST',
      body: JSON.stringify({ video_path, time_sec }),
    }),
  thumbnailSuggest: (data: {
    topic?: string
    notes?: string
    video_analysis?: string
    provider?: string
    model?: string
  }) =>
    request<{ title: string; subtitle: string }>(
      '/publishing/thumbnail/suggest',
      { method: 'POST', body: JSON.stringify(data) },
    ),
  thumbnailGenerate: (data: {
    prompt: string
    provider?: string
    model?: string
  }) =>
    request<{ image_path: string; warning: string }>(
      '/publishing/thumbnail/generate',
      { method: 'POST', body: JSON.stringify(data) },
    ),
  thumbnailRender: (spec: ThumbSpec) =>
    request<{ image_path: string }>('/publishing/thumbnail/render', {
      method: 'POST',
      body: JSON.stringify(spec),
    }),
}
