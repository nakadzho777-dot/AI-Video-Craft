// ページ間でデータ（動画ファイル・企画）を受け渡すための簡易ハンドオフ。
// 録画支援 → 編集支援、編集支援 → 投稿支援、AI企画 → 録画支援 に「送る」ために使う。
export type RecordingPlan = {
  topic: string
  instructions?: string
  target_duration_sec?: number
}

export const handoff: {
  editingVideo?: string
  publishingVideo?: string
  recordingPlan?: RecordingPlan
  workflowProjectId?: number
} = {}

// App.tsx がこのイベントを購読して view を切り替える
export function sendToEditing(path: string) {
  if (!path) return
  handoff.editingVideo = path
  window.dispatchEvent(new CustomEvent('aivc:navigate', { detail: 'editing' }))
}

export function sendToPublishing(path: string) {
  if (!path) return
  handoff.publishingVideo = path
  window.dispatchEvent(new CustomEvent('aivc:navigate', { detail: 'publishing' }))
}

// AI企画 → 録画支援（企画のテーマ・手順を録画画面へ引き継ぐ）
export function sendToRecording(plan: RecordingPlan) {
  handoff.recordingPlan = plan
  window.dispatchEvent(new CustomEvent('aivc:navigate', { detail: 'recording' }))
}

// プロジェクト作成後のガイド付きワークフロー（企画→録画→編集→投稿）を開始
export function startWorkflow(projectId?: number) {
  handoff.workflowProjectId = projectId
  window.dispatchEvent(
    new CustomEvent('aivc:workflow-start', { detail: projectId ?? null }),
  )
}
