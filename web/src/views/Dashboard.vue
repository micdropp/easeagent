<template>
  <div class="dashboard">
    <el-row :gutter="16" class="stat-row">
      <el-col :span="6">
        <el-card shadow="hover">
          <div class="stat-cell">
            <div class="stat-label">系统状态</div>
            <el-tag :type="health.healthy ? 'success' : 'danger'" size="large">
              {{ health.healthy ? '正常' : '异常' }}
            </el-tag>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <div class="stat-cell">
            <div class="stat-label">在线设备</div>
            <div class="stat-value">{{ health.devices?.online ?? 0 }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <div class="stat-cell">
            <div class="stat-label">决策总数</div>
            <div class="stat-value">{{ agentStats.total_decisions ?? 0 }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <div class="stat-cell">
            <div class="stat-label">成功率</div>
            <div class="stat-pct">{{ successRate }}%</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" style="margin-top:16px">
      <el-col :span="12">
        <el-card header="服务状态">
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="MQTT">
              <el-tag :type="health.mqtt?.status === 'ok' ? 'success' : 'danger'" size="small">
                {{ health.mqtt?.status ?? 'N/A' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="Redis">
              <el-tag :type="health.redis?.status === 'ok' ? 'success' : 'danger'" size="small">
                {{ health.redis?.status ?? 'N/A' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="Database">
              <el-tag :type="health.database?.status === 'ok' ? 'success' : 'danger'" size="small">
                {{ health.database?.status ?? 'N/A' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="EventBus">
              <el-tag :type="health.event_bus?.status === 'ok' ? 'success' : 'danger'" size="small">
                {{ health.event_bus?.status ?? 'N/A' }}
              </el-tag>
            </el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card header="Agent 决策统计">
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="总决策">{{ agentStats.total_decisions ?? 0 }}</el-descriptions-item>
            <el-descriptions-item label="成功">{{ agentStats.successful ?? 0 }}</el-descriptions-item>
            <el-descriptions-item label="失败">{{ agentStats.failed ?? 0 }}</el-descriptions-item>
            <el-descriptions-item label="平均延迟">{{ agentStats.avg_latency_ms?.toFixed(0) ?? '-' }} ms</el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" style="margin-top:16px">
      <el-col :span="24">
        <el-card header="最近决策">
          <el-table :data="recentLogs" size="small" stripe max-height="320">
            <el-table-column prop="created_at" label="时间" width="170" />
            <el-table-column prop="room_id" label="房间" width="100" />
            <el-table-column prop="trigger_event" label="触发事件" width="120" />
            <el-table-column label="执行动作" width="220" show-overflow-tooltip>
              <template #default="{ row }">
                <span class="action-summary">{{ parseActions(row.tool_calls) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="agent_reasoning" label="Agent 推理" show-overflow-tooltip />
            <el-table-column prop="latency_ms" label="延迟(ms)" width="80" />
            <el-table-column label="结果" width="70">
              <template #default="{ row }">
                <el-tag :type="row.success ? 'success' : 'danger'" size="small">
                  {{ row.success ? '成功' : '失败' }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { getHealth, getAgentLogStats, getAgentLogs } from '../api'

const health = ref<Record<string, any>>({})
const agentStats = ref<Record<string, any>>({})
const recentLogs = ref<any[]>([])

const successRate = computed(() => {
  const t = agentStats.value.total_decisions || 0
  const s = agentStats.value.successful || 0
  return t > 0 ? ((s / t) * 100).toFixed(1) : '0.0'
})

const TOOL_LABELS: Record<string, string> = {
  control_light: '调灯光',
  control_curtain: '调窗帘',
  control_ac: '调空调',
  control_screen: '设屏幕',
  control_fresh_air: '调新风',
  get_employee_preference: '查偏好',
  notify_feishu: '飞书通知',
  update_preference_memory: '记偏好',
}

function parseActions(raw: string | any[] | null): string {
  if (!raw) return '-'
  let arr: any[]
  if (typeof raw === 'string') {
    try { arr = JSON.parse(raw) } catch { return raw }
  } else {
    arr = raw
  }
  if (!Array.isArray(arr) || arr.length === 0) return '-'
  return arr.map((tc: any) => {
    const label = TOOL_LABELS[tc.name] || tc.name || '?'
    const args = tc.arguments || {}
    const key = args.employee_id || args.room_id || args.screen_id || args.level || ''
    return key ? `${label}(${key})` : label
  }).join(' → ')
}

onMounted(async () => {
  try { health.value = (await getHealth()).data } catch { /* */ }
  try { agentStats.value = (await getAgentLogStats()).data } catch { /* */ }
  try { recentLogs.value = (await getAgentLogs({ limit: 10 })).data } catch { /* */ }
})
</script>

<style scoped>
.stat-row .el-card { text-align: center; }
.stat-cell { padding: 8px 0; }
.stat-label { font-size: 13px; color: #909399; margin-bottom: 8px; }
.stat-value { font-size: 28px; font-weight: 700; color: #303133; }
.stat-pct { font-size: 28px; font-weight: 700; color: #67c23a; }
.action-summary { color: #409eff; font-size: 12px; }
</style>
