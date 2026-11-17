<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { deleteJob, listJobs } from '../api/client'
import JobList from '../components/JobList.vue'
import UploadPanel from '../components/UploadPanel.vue'

const router = useRouter()
const jobs = ref([])
const snackbar = ref(false)
const snackText = ref('')
let pollTimer = null

const hasActive = computed(() => jobs.value.some((j) => !['completed', 'failed'].includes(j.status)))

async function refresh() {
  try {
    jobs.value = await listJobs()
  } catch (e) {
    showSnack('刷新任务列表失败')
  }
}

function syncPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
  if (hasActive.value) {
    pollTimer = setInterval(refresh, 3000)
  }
}

function showSnack(text) {
  snackText.value = text
  snackbar.value = true
}

function onUploaded(job) {
  refresh()
  router.push({ name: 'job', params: { id: job.id } })
}

function openJob(job) {
  router.push({ name: 'job', params: { id: job.id } })
}

async function onDelete(job) {
  try {
    await deleteJob(job.id)
    showSnack('任务已删除')
    await refresh()
  } catch (e) {
    showSnack('删除失败：' + (e?.response?.data?.error || e.message))
  }
}

onMounted(refresh)
onMounted(() => {
  // 有进行中的任务时自动轮询
  pollTimer = setInterval(() => {
    if (hasActive.value) refresh()
    else syncPolling()
  }, 3000)
})
onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<template>
  <v-container class="py-8" style="max-width: 1120px">
    <div class="mb-6">
      <h1 class="text-h4 font-weight-bold">视频转文字</h1>
      <p class="text-body-1 text-medium-emphasis mt-1">
        上传视频，自动用 ffmpeg 分离音轨，调用讯飞 / 腾讯云语音识别，生成带时间轴的文字稿。
      </p>
    </div>

    <v-row>
      <v-col cols="12" md="5" lg="4">
        <UploadPanel @uploaded="onUploaded" />
      </v-col>
      <v-col cols="12" md="7" lg="8">
        <JobList :jobs="jobs" @open="openJob" @delete="onDelete" @refresh="refresh" />
      </v-col>
    </v-row>

    <v-snackbar v-model="snackbar" :timeout="3000" location="bottom">
      {{ snackText }}
    </v-snackbar>
  </v-container>
</template>
