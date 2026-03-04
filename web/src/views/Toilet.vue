<template>
  <div>
    <el-row :gutter="16" style="margin-bottom:16px">
      <el-col :span="8" v-for="group in summaryList" :key="group.key">
        <el-card shadow="hover">
          <template #header>{{ group.label }}</template>
          <div class="stall-grid">
            <div
              v-for="stall in group.stalls"
              :key="stall.id"
              class="stall-box"
              :class="{ occupied: stall.is_occupied }"
            >
              <el-icon :size="28">
                <component :is="stall.is_occupied ? 'Lock' : 'Unlock'" />
              </el-icon>
              <span class="stall-label">{{ stall.id }}</span>
            </div>
          </div>
          <div class="stall-summary">
            空闲 {{ group.stalls.filter((s: any) => !s.is_occupied).length }}
            / {{ group.stalls.length }}
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card header="全部厕位详情">
      <el-table :data="stalls" stripe size="small">
        <el-table-column prop="id" label="厕位 ID" width="140" />
        <el-table-column prop="floor" label="楼层" width="80" />
        <el-table-column prop="gender" label="性别" width="80">
          <template #default="{ row }">{{ row.gender === 'M' ? '男' : '女' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_occupied ? 'danger' : 'success'" size="small">
              {{ row.is_occupied ? '占用' : '空闲' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="last_status_change" label="更新时间" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { getToiletStatus, getToiletSummary } from '../api'
import { useWebSocket } from '../composables/useWebSocket'
import { Lock, Unlock } from '@element-plus/icons-vue'

const stalls = ref<any[]>([])
const summary = ref<any>({})
const { lastMessage } = useWebSocket(['toilet_status'])

const load = async () => {
  try { stalls.value = (await getToiletStatus()).data } catch { /* */ }
  try { summary.value = (await getToiletSummary()).data } catch { /* */ }
}
onMounted(load)

watch(lastMessage, (msg) => {
  if (msg?.channel === 'toilet_status') load()
})

const summaryList = computed(() => {
  const groups: Record<string, any> = {}
  for (const s of stalls.value) {
    const key = `${s.floor ?? '?'}F_${s.gender ?? '?'}`
    if (!groups[key]) groups[key] = { key, label: `${s.floor ?? '?'}楼 ${s.gender === 'M' ? '男' : '女'}卫`, stalls: [] }
    groups[key].stalls.push(s)
  }
  return Object.values(groups)
})
</script>

<style scoped>
.stall-grid { display: flex; gap: 12px; flex-wrap: wrap; }
.stall-box {
  width: 72px; height: 72px; border-radius: 8px;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  background: #f0f9eb; color: #67c23a; border: 2px solid #e1f3d8; cursor: default;
}
.stall-box.occupied { background: #fef0f0; color: #f56c6c; border-color: #fde2e2; }
.stall-label { font-size: 11px; margin-top: 4px; }
.stall-summary { margin-top: 12px; font-size: 13px; color: #999; }
</style>
