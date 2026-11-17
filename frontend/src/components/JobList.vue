<script setup>
import { ref } from 'vue'
import { PROVIDER_LABELS, formatDate, formatTime, statusMeta } from '../utils/format'

defineProps({ jobs: { type: Array, default: () => [] } })
const emit = defineEmits(['open', 'delete', 'refresh'])

const confirmTarget = ref(null)

function askDelete(job) {
  confirmTarget.value = job
}

function confirmDelete() {
  if (confirmTarget.value) emit('delete', confirmTarget.value)
  confirmTarget.value = null
}
</script>

<template>
  <v-card>
    <v-card-title class="d-flex align-center py-3">
      <span class="text-subtitle-1 font-weight-bold">转写任务</span>
      <v-spacer />
      <v-btn v-if="jobs.length" variant="text" size="small" prepend-icon="mdi-refresh" @click="emit('refresh')">
        刷新
      </v-btn>
    </v-card-title>
    <v-divider />

    <div v-if="!jobs.length" class="text-center py-12 px-4 text-medium-emphasis">
      <v-icon icon="mdi-inbox-outline" size="44" class="mb-2" />
      <div class="text-body-1">还没有转写任务</div>
      <div class="text-caption mt-1">上传一个视频，自动分离音轨并生成带时间轴的文字稿</div>
    </div>

    <v-list v-else bg-color="transparent" lines="two">
      <v-list-item
        v-for="job in jobs"
        :key="job.id"
        class="mb-1"
        @click="emit('open', job)"
      >
        <template #prepend>
          <v-avatar :color="statusMeta(job.status).color" size="44" variant="tonal">
            <v-icon :icon="statusMeta(job.status).icon" />
          </v-avatar>
        </template>
        <v-list-item-title class="font-weight-medium text-truncate pr-2">
          {{ job.original_name }}
        </v-list-item-title>
        <v-list-item-subtitle>
          {{ PROVIDER_LABELS[job.provider] || job.provider }}
          <template v-if="job.duration"> · 时长 {{ formatTime(job.duration) }}</template>
          · {{ formatDate(job.created_at) }}
        </v-list-item-subtitle>
        <template #append>
          <div class="d-flex align-center ga-2">
            <v-chip size="small" :color="statusMeta(job.status).color" variant="tonal">
              {{ statusMeta(job.status).label }}
              <template v-if="!['completed', 'failed'].includes(job.status)">
                {{ Math.round(job.progress) }}%
              </template>
            </v-chip>
            <v-icon
              icon="mdi-delete-outline"
              size="20"
              color="grey"
              title="删除任务"
              @click.stop="askDelete(job)"
            />
          </div>
        </template>
      </v-list-item>
    </v-list>

    <v-dialog :model-value="!!confirmTarget" @update:model-value="confirmTarget = null" max-width="420">
      <v-card class="pa-4">
        <v-card-title class="text-h6">删除任务？</v-card-title>
        <v-card-text>
          <template v-if="confirmTarget">
            将删除「{{ confirmTarget.original_name }}」的视频与转写结果，此操作不可恢复。
          </template>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="confirmTarget = null">取消</v-btn>
          <v-btn color="error" variant="tonal" @click="confirmDelete">删除</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-card>
</template>
