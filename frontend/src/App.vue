<script setup>
import { useTheme } from 'vuetify'

const theme = useTheme()

function toggleTheme() {
  theme.global.name.value = theme.global.current.value.dark ? 'light' : 'dark'
}
</script>

<template>
  <v-app>
    <v-app-bar flat density="comfortable" border="b">
      <v-app-bar-title class="cursor-pointer" style="cursor: pointer" @click="$router.push('/')">
        <v-icon icon="mdi-movie-open-cog-outline" color="primary" class="mr-2" />
        <span class="font-weight-bold">知识切片</span>
        <span class="text-medium-emphasis ml-1">· 视频转文字</span>
      </v-app-bar-title>
      <v-spacer />
      <v-btn
        :icon="theme.global.current.value.dark ? 'mdi-weather-sunny' : 'mdi-weather-night'"
        variant="text"
        :title="theme.global.current.value.dark ? '切换浅色模式' : '切换深色模式'"
        @click="toggleTheme"
      />
    </v-app-bar>

    <v-main>
      <router-view />
    </v-main>

    <v-footer border="t" class="justify-center text-caption text-medium-emphasis" height="40">
      ffmpeg 音轨分离 · 讯飞 / 腾讯云语音识别 · 带时间轴文字稿
    </v-footer>
  </v-app>
</template>
