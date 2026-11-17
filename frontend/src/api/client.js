import axios from 'axios'

const api = axios.create({ baseURL: '/api', timeout: 0 })

export async function getConfig() {
  return (await api.get('/config')).data
}

export async function listJobs() {
  return (await api.get('/transcriptions')).data
}

export async function getJob(id) {
  return (await api.get(`/transcriptions/${id}`)).data
}

export async function deleteJob(id) {
  return (await api.delete(`/transcriptions/${id}`)).data
}

export async function getResult(id) {
  return (await api.get(`/transcriptions/${id}/result`)).data
}

export async function retryJob(id) {
  return (await api.post(`/transcriptions/${id}/retry`)).data
}

export function uploadVideo(file, provider, options, onProgress) {
  const form = new FormData()
  form.append('file', file)
  form.append('provider', provider)
  form.append('options', JSON.stringify(options))
  return api
    .post('/transcriptions', form, {
      onUploadProgress: (e) => {
        if (onProgress && e.total) onProgress(Math.round((e.loaded / e.total) * 100))
      },
    })
    .then((r) => r.data)
}

export const jobVideoUrl = (id) => `/api/transcriptions/${id}/video`
export const jobExportUrl = (id, format) => `/api/transcriptions/${id}/export?format=${format}`
