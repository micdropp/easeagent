<template>
  <div>
    <el-row :gutter="16" style="margin-bottom:16px">
      <el-col :span="6" v-for="cam in cameras" :key="cam.camera_id">
        <el-card shadow="hover" :body-style="{ padding: '0' }">
          <img
            :src="streamUrl(cam.camera_id)"
            :alt="cam.camera_id"
            style="width:100%; display:block; border-radius:4px 4px 0 0; background:#000; min-height:180px"
            @error="($event.target as HTMLImageElement).style.opacity = '0.3'"
          />
          <div style="padding:10px">
            <el-tag size="small" type="info">{{ cam.camera_id }}</el-tag>
            <span style="margin-left:8px; font-size:12px; color:#999">{{ cam.room_id }}</span>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card header="摄像头性能" v-if="videoStats.length">
      <el-table :data="videoStats" size="small" stripe>
        <el-table-column prop="camera_id" label="摄像头" width="160" />
        <el-table-column prop="stream_fps" label="推流 FPS" width="120">
          <template #default="{ row }">{{ row.stream_fps?.toFixed(1) }}</template>
        </el-table-column>
        <el-table-column prop="detect_fps" label="检测 FPS" width="120">
          <template #default="{ row }">{{ row.detect_fps?.toFixed(1) }}</template>
        </el-table-column>
        <el-table-column prop="inference_ms" label="推理延迟" width="120">
          <template #default="{ row }">{{ row.inference_ms?.toFixed(1) }} ms</template>
        </el-table-column>
        <el-table-column prop="person_count" label="检测人数" width="100" />
        <el-table-column prop="resolution" label="分辨率" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getVideoCameras, getVideoStats, videoStreamUrl } from '../api'

const cameras = ref<any[]>([])
const videoStats = ref<any[]>([])

const streamUrl = (id: string) => videoStreamUrl(id)

onMounted(async () => {
  try { cameras.value = (await getVideoCameras()).data.cameras ?? [] } catch { /* */ }
  try {
    const raw = (await getVideoStats()).data
    const statsObj = raw?.stats ?? {}
    videoStats.value = Object.entries(statsObj).map(([camId, s]: [string, any]) => ({
      camera_id: camId, ...s,
    }))
  } catch { /* */ }
})
</script>
