<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { getJob, getResult, jobExportUrl, jobVideoUrl, retryJob } from '../api/client'
import { PROVIDER_LABELS, formatTime, highlightHtml, statusMeta } from '../utils/format'

const props = defineProps({ id: { type: String, required: true } })

const job = ref(null)
const result = ref(null)
const pageError = ref('')
const videoError = ref(false)
const search = ref('')
const autoScroll = ref(true)
const currentTime = ref(0)
const snackbar = ref(false)
const snackText = ref('')
const videoEl = ref(null)
const retrying = ref(false)
let pollTimer = null

const terminal = computed(() => job.value && ['completed', 'failed'].includes(job.value.status))
const meta = computed(() => statusMeta(job.value?.status))
const segments = computed(() => result.value?.segments || [])

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return segments.value
  return segments.value.filter((s) => s.text.toLowerCase().includes(q))
})

const activeIndex = computed(() => {
  const t = currentTime.value
  const list = filtered.value
  for (let i = 0; i < list.length; i++) {
    if (t >= list[i].start && t < list[i].end) return i
  }
  return -1
})

async function loadJob() {
  try {
    job.value = await getJob(props.id)
    pageError.value = ''
  } catch (e) {
    pageError.value = '加载失败：' + (e?.response?.data?.error || e.message)
  }
}

async function loadResult() {
  try {
    result.value = await getResult(props.id)
  } catch (e) {
    // 转写中 409 属正常，忽略
  }
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(async () => {
    if (!job.value || terminal.value) {
      stopPolling()
      return
    }
    await loadJob()
    if (terminal.value) await loadResult()
  }, 2000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function onTimeUpdate() {
  currentTime.value = videoEl.value?.currentTime ?? 0
}

function seekTo(seg) {
  const v = videoEl.value
  if (!v) return
  v.currentTime = seg.start
  v.play().catch(() => {})
}

function onVideoError() {
  videoError.value = true
}

function fullText() {
  return segments.value.map((s) => `[${formatTime(s.start)}] ${s.text}`).join('\n')
}

async function copyAll() {
  try {
    await navigator.clipboard.writeText(fullText())
    showSnack('已复制全部文字稿')
  } catch {
    showSnack('复制失败，请手动选择复制')
  }
}

function download(format) {
  window.location.href = jobExportUrl(props.id, format)
}

async function retry() {
  retrying.value = true
  try {
    job.value = await retryJob(props.id)
    result.value = null
    videoError.value = false
    startPolling()
    showSnack('已重新提交转写')
  } catch (e) {
    pageError.value = '重试失败：' + (e?.response?.data?.error || e.message)
  } finally {
    retrying.value = false
  }
}

function showSnack(text) {
  snackText.value = text
  snackbar.value = true
}

watch(activeIndex, (i) => {
  if (!autoScroll.value || i < 0) return
  document.getElementById(`seg-${i}`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
})

onMounted(async () => {
  await loadJob()
  if (terminal.value) await loadResult()
  if (!terminal.value) startPolling()
})
onUnmounted(stopPolling)
</script>

<template>
  <v-container class="py-6" style="max-width: 1400px">
    <v-btn prepend-icon="mdi-arrow-left" variant="text" class="mb-4" @click="$router.push('/')">
      返回列表
    </v-btn>

    <v-alert v-if="pageError" type="error" variant="tonal" class="mb-4">
      {{ pageError }}
    </v-alert>

    <template v-if="job">
      <!-- 头部信息 -->
      <div class="d-flex flex-wrap align-center ga-3 mb-4">
        <h1 class="text-h5 font-weight-bold">{{ job.original_name }}</h1>
        <v-chip size="small" :color="meta.color" variant="tonal">
          <v-icon start :icon="meta.icon" size="16" />
          {{ meta.label }}
        </v-chip>
        <v-chip size="small" variant="tonal" prepend-icon="mdi-server-outline">
          {{ PROVIDER_LABELS[job.provider] || job.provider }}
        </v-chip>
        <v-chip v-if="job.duration" size="small" variant="tonal" prepend-icon="mdi-clock-outline">
          时长 {{ formatTime(job.duration) }}
        </v-chip>
      </div>

      <v-alert v-if="job.status === 'failed'" type="error" variant="tonal" class="mb-4">
        <div class="d-flex align-center flex-wrap ga-3">
          <span class="flex-grow-1">转写失败：{{ job.error || '未知错误' }}</span>
          <v-btn
            color="error"
            variant="flat"
            size="small"
            prepend-icon="mdi-refresh"
            :loading="retrying"
            @click="retry"
          >
            重新转写
          </v-btn>
        </div>
      </v-alert>

      <v-row>
        <!-- 视频 + 进度 -->
        <v-col cols="12" lg="7">
          <v-card class="pa-4 video-card">
            <video
              ref="videoEl"
              controls
              preload="metadata"
              class="video-player"
              :src="jobVideoUrl(job.id)"
              @timeupdate="onTimeUpdate"
              @error="onVideoError"
            />
            <v-alert
              v-if="videoError"
              type="info"
              variant="tonal"
              density="compact"
              class="mt-3 mb-0"
            >
              当前浏览器无法播放该视频编码（如 MKV / HEVC）。时间轴与文字稿不受影响，
              可下载后本地播放对照。
            </v-alert>
            <div v-if="!terminal" class="mt-4">
              <div class="d-flex justify-space-between align-center mb-1">
                <span class="text-body-2 text-medium-emphasis">
                  <v-icon icon="mdi-cog-sync-outline" size="16" class="mr-1" />
                  {{ job.message || '处理中…' }}
                </span>
                <span class="text-body-2 font-weight-bold">{{ Math.round(job.progress || 0) }}%</span>
              </div>
              <v-progress-linear
                :model-value="job.progress || 0"
                color="primary"
                height="8"
                rounded
              />
              <p class="text-caption text-medium-emphasis mt-2 mb-0">
                音轨分离与语音识别在服务端进行，请保持页面打开，完成后自动加载文字稿。
              </p>
            </div>
          </v-card>
        </v-col>

        <!-- 文字稿 -->
        <v-col cols="12" lg="5">
          <v-card>
            <v-card-title class="d-flex align-center ga-1 flex-wrap py-3">
              <span class="text-subtitle-1 font-weight-bold">文字稿</span>
              <v-chip v-if="terminal" size="x-small" variant="tonal" color="primary">
                {{ segments.length }} 段
              </v-chip>
              <v-spacer />
              <v-btn
                icon="mdi-content-copy"
                size="small"
                variant="text"
                title="复制全部文字稿"
                :disabled="!segments.length"
                @click="copyAll"
              />
              <v-menu>
                <template #activator="{ props: menuProps }">
                  <v-btn
                    icon="mdi-download"
                    size="small"
                    variant="text"
                    title="下载字幕"
                    :disabled="!segments.length"
                    v-bind="menuProps"
                  />
                </template>
                <v-list density="compact">
                  <v-list-item prepend-icon="mdi-file-document-outline" title="SRT 字幕" @click="download('srt')" />
                  <v-list-item prepend-icon="mdi-file-document-outline" title="VTT 字幕" @click="download('vtt')" />
                  <v-list-item prepend-icon="mdi-file-document-outline" title="纯文本（带时间）" @click="download('txt')" />
                </v-list>
              </v-menu>
            </v-card-title>
            <v-divider />
            <v-card-text class="pb-0 pt-3">
              <v-text-field
                v-model="search"
                placeholder="搜索文字稿…"
                prepend-inner-icon="mdi-magnify"
                density="compact"
                clearable
                hide-details
              />
              <div class="d-flex align-center mt-2">
                <span v-if="search && terminal" class="text-caption text-medium-emphasis">
                  匹配 {{ filtered.length }} / {{ segments.length }} 段
                </span>
                <v-spacer />
                <v-switch
                  v-model="autoScroll"
                  color="primary"
                  label="自动跟随播放"
                  density="compact"
                  hide-details
                  class="flex-grow-0"
                />
              </div>
            </v-card-text>

            <div class="segments-container overflow-y-auto pa-2 mx-2 mb-2" style="max-height: 66vh">
              <div v-if="!terminal" class="text-center py-10 text-medium-emphasis">
                <v-icon icon="mdi-microphone-message-outline" size="36" class="mb-2" />
                <div>等待转写完成…</div>
              </div>
              <template v-else-if="segments.length">
                <div
                  v-for="(seg, i) in filtered"
                  :id="`seg-${i}`"
                  :key="i"
                  class="segment d-flex"
                  :class="{ active: i === activeIndex }"
                  @click="seekTo(seg)"
                >
                  <div class="segment-time">{{ formatTime(seg.start) }}</div>
                  <div class="segment-body flex-grow-1">
                    <span class="segment-text" v-html="highlightHtml(seg.text, search)" />
                    <v-chip
                      v-if="seg.speaker != null"
                      size="x-small"
                      variant="tonal"
                      color="secondary"
                      class="ml-2"
                    >
                      说话人 {{ seg.speaker }}
                    </v-chip>
                  </div>
                </div>
              </template>
              <div v-else class="text-center py-10 text-medium-emphasis">
                <v-icon icon="mdi-movie-off-outline" size="36" class="mb-2" />
                <div>未识别到语音内容</div>
              </div>
            </div>
          </v-card>
        </v-col>
      </v-row>
    </template>

    <v-snackbar v-model="snackbar" :timeout="3000" location="bottom">
      {{ snackText }}
    </v-snackbar>
  </v-container>
</template>

<style scoped>
.segment {
  gap: 12px;
  padding: 10px 12px;
  border-radius: 10px;
  cursor: pointer;
  transition: background-color 0.1s ease;
}
.segment:hover {
  background: rgba(var(--v-theme-primary), 0.06);
}
.segment.active {
  background: rgba(var(--v-theme-primary), 0.13);
}
.segment-time {
  font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
  font-size: 0.82rem;
  font-weight: 600;
  color: rgb(var(--v-theme-primary));
  min-width: 56px;
  padding-top: 1px;
  user-select: none;
}
.segment-text {
  font-size: 0.95rem;
  line-height: 1.6;
}

@media (min-width: 1280px) {
  .video-card {
    position: sticky;
    top: 16px;
  }
}
</style>
