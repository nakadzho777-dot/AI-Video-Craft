// バックエンド API と共有する型定義

export type ProductionMode = 'auto' | 'assist' | 'manual'
export type MaterialMode = 'provide' | 'request'
export type ProjectStatus =
  | 'planning'
  | 'materials'
  | 'recording'
  | 'editing'
  | 'publishing'
  | 'done'

export interface Project {
  id: number
  title: string
  description: string
  production_mode: ProductionMode
  material_mode: MaterialMode
  status: ProjectStatus
  created_at: string
  updated_at: string
}

export interface ProviderInfo {
  id: string
  display_name: string
  kind: 'local' | 'apikey'
  download_url: string | null
  api_key_help_url: string | null
  configured: boolean
}

export interface ChatTurn {
  role: 'system' | 'user' | 'assistant'
  content: string
}

export interface HealthInfo {
  status: string
  version: string
  plan: 'free' | 'pro'
  ffmpeg_available: boolean
  dev_mode: boolean
}

export interface PlanLimits {
  max_projects: number | null
  ai_runs_per_day: number | null
  max_resolution_p: number | null
  max_video_minutes: number | null
  advanced_editing: boolean
  timeline_tracks: number | null
  paid_ai_allowed: boolean
}

export interface UsageInfo {
  plan: 'free' | 'pro'
  limits: PlanLimits
  ai_runs_today: number
  ai_runs_limit: number | null
  ai_runs_remaining: number | null
  license_kind: 'perpetual' | 'subscription' | null
  license_expires_at: string | null
  license_expires_in_days: number | null
}

export interface SigningInfo {
  using_dev_public_key: boolean
  using_dev_private_key: boolean
}

export interface KeygenResult {
  public_key: string
  private_key: string
  instructions: {
    public_env: string
    private_env: string
    note: string
  }
}

export interface PurchaseRequestResult {
  sent: boolean
  notify_email: string
  mailto: string
}

export interface BillingConfig {
  stripe_enabled: boolean
  perpetual_available: boolean
  subscription_available: boolean
}

// ---- 認証 / ライセンス ----
export interface UserInfo {
  id: number
  email: string
  username: string
  plan: 'free' | 'pro'
}

export interface AuthResult {
  token: string
  user: UserInfo
}

export interface LicenseDevice {
  device_id: string
  device_name: string
  registered_at: string
}

export interface LicenseStatus {
  plan: 'free' | 'pro'
  has_license: boolean
  license_key: string | null
  source: string | null
  max_devices: number | null
  devices: LicenseDevice[]
  kind: 'perpetual' | 'subscription' | null
  expires_at: string | null
}

// ---- AI企画 ----
export type VideoFormat = 'short' | 'long'

export interface PlanSection {
  name: string
  duration_sec: number
  description: string
}

export interface VideoPlan {
  topic: string
  format: VideoFormat
  titles: string[]
  target_duration_sec: number
  hook: string
  sections: PlanSection[]
  cta: string
  thumbnail_ideas: string[]
}

export interface PlanRequest {
  topic: string
  format?: 'short' | 'long' | 'auto'
  target_duration_sec?: number | null
  notes?: string
  provider?: string
  model?: string
  project_id?: number | null
}

export interface PlanResponse {
  plan: VideoPlan
  provider: string
  model: string
  saved_to_project: number | null
}

// ---- 録画支援 ----
export type StepKind = 'start' | 'show' | 'action' | 'say' | 'wait' | 'stop'

export interface RecordingStep {
  kind: StepKind
  title: string
  instruction: string
  duration_sec: number
}

export interface RecordingGuide {
  topic: string
  steps: RecordingStep[]
}

export interface GuideRequest {
  topic?: string
  notes?: string
  provider?: string
  model?: string
  project_id?: number | null
}

export interface GuideResponse {
  guide: RecordingGuide
  provider: string
  model: string
  saved_to_project: number | null
}

// ---- 編集支援 ----
export interface CutSuggestion {
  start_sec: number
  end_sec: number
  reason: string
}

export interface TelopSuggestion {
  time_sec: number
  text: string
}

export interface ShortPlan {
  target_duration_sec: number
  vertical: boolean
  segments: CutSuggestion[]
}

export interface EditSuggestion {
  cuts: CutSuggestion[]
  telops: TelopSuggestion[]
  bgm_suggestions: string[]
  tempo_tips: string[]
  short_plan: ShortPlan | null
}

export interface SuggestRequest {
  duration_sec?: number
  script?: string
  goal?: 'improve' | 'short' | 'auto'
  notes?: string
  provider?: string
  model?: string
  project_id?: number | null
}

export interface SuggestResponse {
  suggestion: EditSuggestion
  provider: string
  model: string
  saved_to_project: number | null
}

export interface ProbeResponse {
  duration_sec: number
  width: number | null
  height: number | null
}

export interface SilenceRange {
  start_sec: number
  end_sec: number
  duration_sec: number
}

// ---- 投稿支援 ----
export interface PublishPack {
  youtube_titles: string[]
  youtube_description: string
  hashtags: string[]
  pinned_comment: string
  booth_text: string
  x_post: string
  instagram_post: string
  tiktok_post: string
}

export interface PublishRequest {
  topic?: string
  notes?: string
  provider?: string
  model?: string
  project_id?: number | null
}

export interface PublishResponse {
  pack: PublishPack
  provider: string
  model: string
  saved_to_project: number | null
}

// ---- 宣伝AI（開発者専用） ----
export interface Article {
  title: string
  slug: string
  target_keyword: string
  meta_description: string
  keywords: string[]
  outline: string[]
  body_markdown: string
}

export interface MarketingRequest {
  topic: string
  keywords?: string[]
  count?: number
  tone?: string
  provider?: string
  model?: string
}

export interface MarketingResponse {
  articles: Article[]
  provider: string
  model: string
  requested: number
  generated: number
}
