<script setup>
import { computed, onMounted, ref } from 'vue'
import { getConfig, uploadVideo } from '../api/client'
import { formatBytes } from '../utils/format'

const emit = defineEmits(['uploaded'])

const config = ref(null)
const file = ref(null)
const provider = ref('')
const tencentEngine = ref('')
const speakerDiarization = ref(false)
const uploading = ref(false)
const uploadProgress = ref(0)
const error = ref('')
const dragOver = ref(false)
const inputRef = ref(null)

const VIDEO_EXTS = ['.mp4', '.mov', '.mkv', '.avi', '.webm', '.flv', '.wmv', '.m4v', '.ts', '.mpg', '.mpeg', '.3gp']

const providers = computed(() => config.value?.providers || [])
const currentProvider = computed(() => providers.value.find((p) => p.id === provider.value))
const hasConfigured = computed(() => providers.value.some((p) => p.configured))
const canSubmit = computed(() => !!(file.value && currentProvider.value?.configured && !uploading.value))

onMounted(async () => {
  try {
    config.value = await getConfig()
    const first = providers.value.find((p) => p.configured)
    if (first) {
      provider.value = first.id
      tencentEngine.value = first.default_engine || ''
    }
  } catch (e) {
    error.value = '无法连接后端服务，请确认 Flask 已启动（cd backend && python app.py）'
  }
})

function isVideo(name) {
  return name && VIDEO_EXTS.some((ext) => name.toLowerCase().endsWith(ext))
}

function setFile(f) {
  if (!f) return
  if (!isVideo(f.name)) {
    error.value = `不支持的视频格式，请上传 ${VIDEO_EXTS.join(' / ')} 文件`
    file.value = null
    return
  }
  file.value = f
  error.value = ''
}

function onFileInput(e) {
  setFile(e.target.files?.[0] || null)
  e.target.value = ''
}

function onDrop(e) {
  dragOver.value = false
  setFile(e.dataTransfer?.files?.[0] || null)
}

function pickFile() {
  inputRef.value?.click()
}

async function submit() {
  if (!canSubmit.value) return
  uploading.value = true
  uploadProgress.value = 0
  error.value = ''
  try {
    const options = {}
    if (provider.value === 'tencent') {
      options.engine = tencentEngine.value
      options.speaker_diarization = speakerDiarization.value
    }
    const job = await uploadVideo(file.value, provider.value, options, (p) => {
      uploadProgress.value = p
    })
    emit('uploaded', job)
  } catch (e) {
    error.value = e?.response?.data?.error || e?.message || '上传失败，请重试'
  } finally {
    uploading.value = false
  }
}
</script>

<template>
  <v-card class="pa-5">
    <v-card-title class="text-subtitle-1 font-weight-bold px-0 pt-0">
      上传视频
      <span v-if="config" class="text-caption text-medium-emphasis font-weight-regular ml-2">
        最大 {{ config.max_upload_mb }}MB
      </span>
    </v-card-title>

    <v-alert
      v-if="!hasConfigured && !error"
      type="warning"
      variant="tonal"
      density="compact"
      class="mb-4"
    >
      尚未配置任何转写服务商密钥。请在 <code>backend/.env</code> 中配置讯飞或腾讯云密钥，
      或设置 <code>ENABLE_MOCK_PROVIDER=1</code> 使用模拟转写体验流程。
    </v-alert>

    <!-- 拖拽上传区 -->
    <div
      class="drop-zone pa-6 text-center"
      :class="{ 'drag-over': dragOver, 'has-file': !!file }"
      @click="pickFile"
      @dragover.prevent="dragOver = true"
      @dragleave.prevent="dragOver = false"
      @drop.prevent="onDrop"
    >
      <input ref="inputRef" type="file" accept="video/*" class="d-none" @change="onFileInput" />
      <template v-if="!file">
        <v-icon icon="mdi-cloud-upload-outline" size="44" color="primary" />
        <div class="text-body-1 mt-2">点击选择或拖拽视频到此处</div>
        <div class="text-caption text-medium-emphasis mt-1">
          支持 MP4 / MOV / MKV / AVI / WEBM 等格式
        </div>
      </template>
      <template v-else>
        <v-icon icon="mdi-video-outline" size="44" color="primary" />
        <div class="text-body-1 mt-2 text-truncate">{{ file.name }}</div>
        <div class="text-caption text-medium-emphasis mt-1">{{ formatBytes(file.size) }}</div>
        <v-btn size="small" variant="text" color="error" class="mt-1" @click.stop="file = null">
          移除
        </v-btn>
      </template>
    </div>

    <!-- 转写服务商 -->
    <v-select
      v-model="provider"
      :items="providers"
      item-title="label"
      item-value="id"
      label="转写服务商"
      class="mt-4"
      :item-props="(item) => ({ disabled: !item.configured })"
    >
      <template #item="{ item, props: itemProps }">
        <v-list-item v-bind="itemProps" :subtitle="item.raw.configured ? undefined : item.raw.hint">
          <template #append>
            <v-chip v-if="!item.raw.configured" size="x-small" color="grey">未配置</v-chip>
            <v-chip v-else size="x-small" color="success" variant="tonal">已就绪</v-chip>
          </template>
        </v-list-item>
      </template>
    </v-select>

    <template v-if="provider === 'tencent'">
      <v-select
        v-model="tencentEngine"
        :items="currentProvider?.engines || []"
        item-title="label"
        item-value="id"
        label="识别引擎"
        class="mt-1"
        hide-details
      />
      <v-switch
        v-model="speakerDiarization"
        color="primary"
        label="说话人分离（区分不同说话人）"
        density="compact"
        class="mt-3"
        hide-details
      />
    </template>

    <v-alert v-if="error" type="error" variant="tonal" density="compact" class="mt-3">
      {{ error }}
    </v-alert>

    <template v-if="uploading">
      <v-progress-linear
        :model-value="uploadProgress"
        color="primary"
        height="8"
        rounded
        class="mt-4"
      />
      <div class="text-caption text-medium-emphasis mt-2 text-center">
        正在上传… {{ uploadProgress }}%
      </div>
    </template>

    <v-btn
      block
      color="primary"
      size="large"
      prepend-icon="mdi-magic-stick"
      class="mt-4"
      :disabled="!canSubmit"
      :loading="uploading"
      @click="submit"
    >
      {{ uploading ? '上传中' : '开始转写' }}
    </v-btn>
  </v-card>
</template>

<style scoped>
.drop-zone {
  border: 2px dashed rgba(var(--v-theme-primary), 0.35);
  border-radius: 14px;
  cursor: pointer;
  transition: all 0.15s ease;
  background: rgba(var(--v-theme-primary), 0.03);
}
.drop-zone:hover,
.drop-zone.drag-over {
  border-color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.07);
}
.drop-zone.has-file {
  border-style: solid;
}
</style>
