import { ref, onUnmounted } from 'vue'

export interface WsMessage {
  channel: string
  data: Record<string, unknown>
}

export function useWebSocket(channels: string[] = ['device_status', 'toilet_status', 'agent_log', 'sensor_data']) {
  const connected = ref(false)
  const lastMessage = ref<WsMessage | null>(null)
  let ws: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null

  const connect = () => {
    const base = (import.meta.env.VITE_API_BASE || location.origin).replace(/^http/, 'ws')
    const url = `${base}/ws/realtime?channels=${channels.join(',')}`
    ws = new WebSocket(url)
    ws.onopen = () => { connected.value = true }
    ws.onclose = () => {
      connected.value = false
      if (reconnectTimer) clearTimeout(reconnectTimer)
      reconnectTimer = setTimeout(connect, 3000)
    }
    ws.onmessage = (e) => {
      try { lastMessage.value = JSON.parse(e.data) } catch { /* ignore */ }
    }
  }

  connect()

  onUnmounted(() => {
    if (reconnectTimer) clearTimeout(reconnectTimer)
    ws?.close()
  })

  return { connected, lastMessage }
}
