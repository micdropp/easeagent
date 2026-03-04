import axios from 'axios'

const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE ?? '',
  timeout: 10000,
})

http.interceptors.response.use(
  (r) => r,
  (err) => {
    console.error('[API]', err?.response?.status, err?.config?.url)
    return Promise.reject(err)
  },
)

export default http
