import http from './http'

/* ---------- Health ---------- */
export const getHealth = (detail = true) =>
  http.get('/health', { params: { detail } })

/* ---------- Devices ---------- */
export const getDevices = (params?: Record<string, unknown>) =>
  http.get('/api/devices', { params })
export const createDevice = (data: Record<string, unknown>) =>
  http.post('/api/devices', data)
export const updateDevice = (id: string, data: Record<string, unknown>) =>
  http.put(`/api/devices/${id}`, data)
export const deleteDevice = (id: string) =>
  http.delete(`/api/devices/${id}`)

/* ---------- Rooms ---------- */
export const getRooms = () => http.get('/api/rooms')
export const getRoom = (id: string) => http.get(`/api/rooms/${id}`)
export const createRoom = (data: Record<string, unknown>) =>
  http.post('/api/rooms', data)
export const updateRoom = (id: string, data: Record<string, unknown>) =>
  http.put(`/api/rooms/${id}`, data)
export const deleteRoom = (id: string) =>
  http.delete(`/api/rooms/${id}`)

/* ---------- Employees ---------- */
export const getEmployees = (params?: Record<string, unknown>) =>
  http.get('/api/employees', { params })
export const getEmployee = (id: string) =>
  http.get(`/api/employees/${id}`)
export const createEmployee = (data: Record<string, unknown>) =>
  http.post('/api/employees', data)
export const updateEmployee = (id: string, data: Record<string, unknown>) =>
  http.put(`/api/employees/${id}`, data)
export const deleteEmployee = (id: string) =>
  http.delete(`/api/employees/${id}`)
export const uploadFace = (id: string, file: File) => {
  const fd = new FormData()
  fd.append('file', file)
  return http.post(`/api/employees/${id}/face`, fd)
}

/* ---------- Preferences ---------- */
export const getPreferences = (employeeId: string, params?: Record<string, unknown>) =>
  http.get(`/api/preferences/${employeeId}`, { params })
export const setPreference = (data: Record<string, unknown>) =>
  http.post('/api/preferences', data)
export const deletePreference = (id: number) =>
  http.delete(`/api/preferences/${id}`)

/* ---------- Agent Logs ---------- */
export const getAgentLogs = (params?: Record<string, unknown>) =>
  http.get('/api/agent-logs', { params })
export const getAgentLogStats = () =>
  http.get('/api/agent-logs/stats')
export const getAgentLog = (id: number) =>
  http.get(`/api/agent-logs/${id}`)

/* ---------- Toilet ---------- */
export const getToiletStatus = (params?: Record<string, unknown>) =>
  http.get('/api/toilet/status', { params })
export const getToiletSummary = () =>
  http.get('/api/toilet/summary')
export const createToiletStall = (data: Record<string, unknown>) =>
  http.post('/api/toilet/stalls', data)
export const updateToiletStatus = (stallId: string, data: Record<string, unknown>) =>
  http.put(`/api/toilet/status/${stallId}`, data)

/* ---------- Video ---------- */
export const getVideoCameras = () => http.get('/api/video/cameras')
export const getVideoStats = () => http.get('/api/video/stats')
export const videoStreamUrl = (cameraId: string) =>
  `${http.defaults.baseURL || ''}/api/video/stream/${cameraId}`
