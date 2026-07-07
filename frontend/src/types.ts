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
  target_duration_sec: number
  created_at: string
  updated_at: string
}

export interface DurationSuggestion {
  video_sec: number
  short_sec: number
  note: string
  record_video_sec: number
  record_short_sec: number
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

// ---- ライセンス（PC単位）----
export interface LicenseStatus {
  plan: 'free' | 'pro'
  device_id: string
  has_license: boolean
  license_key: string | null
  source: string | null
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
  style?: string
  provider?: string
  model?: string
  project_id?: number | null
}

export interface StyleProfile {
  creator: string
  summary: string
  pacing: string
  cut_style: string
  telop_style: string
  sound_style: string
  transitions: string
  hook_style: string
  keywords: string[]
}

export interface LearnStyleRequest {
  reference_url?: string
  creator?: string
  notes?: string
  provider?: string
  model?: string
}

export interface LearnStyleResponse {
  style: StyleProfile
  provider: string
  model: string
  source: string
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
  video_path?: string
  provider?: string
  model?: string
  project_id?: number | null
}

export interface PublishResponse {
  pack: PublishPack
  provider: string
  model: string
  saved_to_project: number | null
  video_analysis?: string
}


// --- AI自動撮影（autopilot: ブラウザ自動操作＋AIナレーション）---
export type AutopilotActionKind =
  | 'goto'
  | 'click'
  | 'fill'
  | 'press'
  | 'scroll'
  | 'wait'

export interface AutopilotStep {
  title: string
  action: AutopilotActionKind
  target: string
  value: string
  narration: string
}

export interface AutopilotPlan {
  title: string
  url: string
  steps: AutopilotStep[]
}

export interface AutopilotPlanRequest {
  url: string
  urls?: string[]
  topic?: string
  notes?: string
  instructions?: string
  style?: 'normal' | 'kaisetsu' | 'jikkyou'
  provider?: string
  model?: string
}

export interface AutopilotPlanResponse {
  plan: AutopilotPlan
  provider: string
  model: string
}

export interface AutopilotRunResponse {
  video_path: string
  duration_sec: number
  steps_run: number
  warnings: string[]
}

export interface AutopilotVoice {
  id: string
  label: string
}

// --- AI自動撮影（デスクトップアプリ版）---
export interface DesktopPlan {
  title: string
  window_title: string
  steps: AutopilotStep[]
}

export interface DesktopPlanRequest {
  window_title: string
  topic?: string
  notes?: string
  instructions?: string
  provider?: string
  model?: string
}

export interface DesktopPlanResponse {
  plan: DesktopPlan
  provider: string
  model: string
}

// --- ゆっくり解説（2キャラ掛け合い解説動画）---
export interface YukkuriLine {
  speaker: 'a' | 'b'
  text: string
}

export interface YukkuriScript {
  title: string
  lines: YukkuriLine[]
}

export interface ThumbText {
  text: string
  x: number
  y: number
  size: number
  color: string
  stroke: string
  stroke_width: number
  bold: boolean
  align: 'left' | 'center' | 'right'
}

export interface ThumbSpec {
  width: number
  height: number
  base_kind: 'scene' | 'image' | 'gradient' | 'ai'
  image_path: string
  video_path: string
  scene_time: number
  color_a: string
  color_b: string
  darken: number
  texts: ThumbText[]
}

export interface CharacterConfig {
  single?: boolean
  name_a: string
  name_b: string
  voice_a: string
  voice_b: string
  show_chars?: boolean
  avatar_a?: string
  avatar_b?: string
}

export interface YukkuriScriptRequest {
  topic: string
  notes?: string
  instructions?: string
  mode?: 'kaisetsu' | 'jikkyou'
  target_sec?: number
  speakers?: number
  name_a?: string
  name_b?: string
  provider?: string
  model?: string
}

export interface YukkuriScriptResponse {
  script: YukkuriScript
  provider: string
  model: string
}

export interface YukkuriRenderResponse {
  video_path: string
  duration_sec: number
  lines: number
  voice_engine: string
  warnings: string[]
}

// --- 動画編集（自動 / 手動）---
export interface MaterialSource {
  site: string
  url: string
}
export interface MaterialSuggestion {
  kind: string
  kind_label: string
  query: string
  reason: string
  sources: MaterialSource[]
}
export interface AutoEditPlan {
  summary: string
  remove_silence: boolean
  cuts: CutSuggestion[]
  telops: TelopSuggestion[]
  materials: MaterialSuggestion[]
}
export interface AutoEditResponse {
  output_path: string
  duration_sec: number
  original_sec: number
  plan: AutoEditPlan
  warnings: string[]
}
export interface EditCut {
  start_sec: number
  end_sec: number
}
export interface EditTelop {
  time_sec: number
  text: string
  size?: number
  color?: string
  stroke?: string
  x?: number
  y?: number | null
  bold?: boolean
  anim?: 'none' | 'fade' | 'pop' | 'slide'
}
export interface EditOverlay {
  image: string
  start_sec: number
  end_sec: number
  position: string
}
export interface ManualEditResponse {
  output_path: string
  duration_sec: number
}
export interface MaterialSearchResponse {
  materials: MaterialSuggestion[]
}
