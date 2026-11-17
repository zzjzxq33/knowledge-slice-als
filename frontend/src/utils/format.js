export function formatTime(seconds, withMs = false) {
  if (seconds == null || Number.isNaN(seconds)) return '--:--'
  const total = Math.max(0, Math.floor(seconds))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const core =
    h > 0
      ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
      : `${m}:${String(s).padStart(2, '0')}`
  if (!withMs) return core
  const ms = Math.floor((seconds - total) * 1000)
  return `${core}.${String(ms).padStart(3, '0')}`
}

export function formatBytes(bytes) {
  if (bytes == null) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
}

export function formatDate(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleString('zh-CN', { hour12: false })
}

export const STATUS_META = {
  pending: { label: '排队中', color: 'grey', icon: 'mdi-clock-outline' },
  extracting: { label: '提取音轨', color: 'info', icon: 'mdi-waveform' },
  transcribing: { label: '语音转写中', color: 'warning', icon: 'mdi-microphone-message-outline' },
  completed: { label: '已完成', color: 'success', icon: 'mdi-check-circle-outline' },
  failed: { label: '失败', color: 'error', icon: 'mdi-alert-circle-outline' },
}

export const PROVIDER_LABELS = {
  xfyun: '讯飞开放平台',
  tencent: '腾讯云',
  mock: '模拟转写',
}

export function statusMeta(status) {
  return STATUS_META[status] || STATUS_META.pending
}

export function escapeHtml(text) {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

export function highlightHtml(text, query) {
  const safe = escapeHtml(text)
  const q = escapeHtml((query || '').trim())
  if (!q) return safe
  const escaped = q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const parts = safe.split(new RegExp(`(${escaped})`, 'gi'))
  return parts
    .map((p) => (p.toLowerCase() === q.toLowerCase() ? `<mark>${p}</mark>` : p))
    .join('')
}
