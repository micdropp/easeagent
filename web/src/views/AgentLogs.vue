<template>
  <div>
    <el-row :gutter="16" style="margin-bottom:16px">
      <el-col :span="5">
        <el-input v-model="filter.room_id" placeholder="房间 ID" clearable @change="load" />
      </el-col>
      <el-col :span="5">
        <el-date-picker v-model="filter.date_from" type="date" placeholder="开始日期" value-format="YYYY-MM-DD" @change="load" style="width:100%" />
      </el-col>
      <el-col :span="5">
        <el-date-picker v-model="filter.date_to" type="date" placeholder="结束日期" value-format="YYYY-MM-DD" @change="load" style="width:100%" />
      </el-col>
      <el-col :span="4">
        <el-select v-model="filter.success" placeholder="状态" clearable @change="load" style="width:100%">
          <el-option label="成功" :value="true" />
          <el-option label="失败" :value="false" />
        </el-select>
      </el-col>
      <el-col :span="5" style="text-align:right">
        <el-tag type="info">共 {{ total }} 条</el-tag>
      </el-col>
    </el-row>

    <el-row :gutter="16" style="margin-bottom:16px">
      <el-col :span="6"><el-card shadow="hover"><el-statistic title="总决策" :value="stats.total_decisions ?? 0" /></el-card></el-col>
      <el-col :span="6"><el-card shadow="hover"><el-statistic title="成功" :value="stats.successful ?? 0" /></el-card></el-col>
      <el-col :span="6"><el-card shadow="hover"><el-statistic title="失败" :value="stats.failed ?? 0" /></el-card></el-col>
      <el-col :span="6"><el-card shadow="hover"><el-statistic title="平均延迟">
        <template #default><span>{{ stats.avg_latency_ms?.toFixed(0) ?? '-' }} ms</span></template>
      </el-statistic></el-card></el-col>
    </el-row>

    <el-table :data="logs" stripe v-loading="loading" @row-click="showDetail">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="created_at" label="时间" width="170" />
      <el-table-column prop="room_id" label="房间" width="120" />
      <el-table-column prop="trigger_event" label="触发事件" width="140" />
      <el-table-column prop="agent_reasoning" label="Agent 推理" show-overflow-tooltip />
      <el-table-column prop="latency_ms" label="延迟(ms)" width="90" />
      <el-table-column label="结果" width="80">
        <template #default="{ row }">
          <el-tag :type="row.success ? 'success' : 'danger'" size="small">
            {{ row.success ? '成功' : '失败' }}
          </el-tag>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-if="total > pageSize"
      layout="prev, pager, next"
      :total="total"
      :page-size="pageSize"
      :current-page="page"
      @current-change="(p: number) => { page = p; load() }"
      style="margin-top:16px; justify-content:center"
    />

    <el-dialog v-model="detailVisible" title="决策详情" width="700px">
      <el-descriptions :column="1" border size="small" v-if="detail">
        <el-descriptions-item label="ID">{{ detail.id }}</el-descriptions-item>
        <el-descriptions-item label="时间">{{ detail.created_at }}</el-descriptions-item>
        <el-descriptions-item label="房间">{{ detail.room_id }}</el-descriptions-item>
        <el-descriptions-item label="触发事件">{{ detail.trigger_event }}</el-descriptions-item>
        <el-descriptions-item label="检测人员">{{ detail.detected_people }}</el-descriptions-item>
        <el-descriptions-item label="传感器数据">{{ detail.sensor_data }}</el-descriptions-item>
        <el-descriptions-item label="Agent 推理">
          <div style="white-space:pre-wrap">{{ detail.agent_reasoning }}</div>
        </el-descriptions-item>
        <el-descriptions-item label="工具调用">
          <pre style="margin:0;font-size:12px">{{ formatJson(detail.tool_calls) }}</pre>
        </el-descriptions-item>
        <el-descriptions-item label="执行结果">
          <pre style="margin:0;font-size:12px">{{ formatJson(detail.execution_results) }}</pre>
        </el-descriptions-item>
        <el-descriptions-item label="延迟">{{ detail.latency_ms }} ms</el-descriptions-item>
      </el-descriptions>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getAgentLogs, getAgentLogStats, getAgentLog } from '../api'

const logs = ref<any[]>([])
const stats = ref<Record<string, any>>({})
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = 20
const filter = ref({ room_id: '', date_from: '', date_to: '', success: undefined as boolean | undefined })
const detailVisible = ref(false)
const detail = ref<any>(null)

const load = async () => {
  loading.value = true
  try {
    const params: Record<string, any> = { limit: pageSize, offset: (page.value - 1) * pageSize }
    if (filter.value.room_id) params.room_id = filter.value.room_id
    if (filter.value.date_from) params.date_from = filter.value.date_from
    if (filter.value.date_to) params.date_to = filter.value.date_to
    if (filter.value.success !== undefined) params.success = filter.value.success
    const res = (await getAgentLogs(params)).data
    logs.value = Array.isArray(res) ? res : res.value ?? res.items ?? []
    total.value = res.count ?? res.total ?? logs.value.length
  } finally { loading.value = false }
}

onMounted(async () => {
  await load()
  try { stats.value = (await getAgentLogStats()).data } catch { /* */ }
})

const showDetail = async (row: any) => {
  try { detail.value = (await getAgentLog(row.id)).data } catch { detail.value = row }
  detailVisible.value = true
}

const formatJson = (s: string | null) => {
  if (!s) return '-'
  try { return JSON.stringify(JSON.parse(s), null, 2) } catch { return s }
}
</script>
