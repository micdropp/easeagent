<template>
  <div>
    <el-row justify="space-between" align="middle" style="margin-bottom:16px">
      <el-col :span="12">
        <el-select v-model="filterRoom" placeholder="按房间筛选" clearable style="width:200px" @change="load">
          <el-option v-for="r in rooms" :key="r.id" :label="r.name" :value="r.id" />
        </el-select>
      </el-col>
      <el-col :span="12" style="text-align:right">
        <el-button type="primary" @click="showAdd = true">添加设备</el-button>
      </el-col>
    </el-row>

    <el-table :data="devices" stripe v-loading="loading">
      <el-table-column prop="id" label="设备 ID" width="180" />
      <el-table-column prop="device_type" label="类型" width="120" />
      <el-table-column prop="room_id" label="房间" width="140" />
      <el-table-column prop="name" label="名称" />
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.is_online ? 'success' : 'info'" size="small">
            {{ row.is_online ? '在线' : '离线' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150">
        <template #default="{ row }">
          <el-button size="small" @click="editItem(row)">编辑</el-button>
          <el-button size="small" type="danger" @click="remove(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="showAdd" :title="editMode ? '编辑设备' : '添加设备'" width="460px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="设备 ID"><el-input v-model="form.id" :disabled="editMode" /></el-form-item>
        <el-form-item label="类型">
          <el-select v-model="form.device_type" style="width:100%">
            <el-option v-for="t in ['light','ac','curtain','screen','fresh_air','sensor','toilet_sensor']" :key="t" :value="t" />
          </el-select>
        </el-form-item>
        <el-form-item label="房间 ID"><el-input v-model="form.room_id" /></el-form-item>
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAdd = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getDevices, createDevice, updateDevice, deleteDevice, getRooms } from '../api'
import { ElMessage, ElMessageBox } from 'element-plus'

const devices = ref<any[]>([])
const rooms = ref<any[]>([])
const loading = ref(false)
const filterRoom = ref('')
const showAdd = ref(false)
const editMode = ref(false)
const form = ref({ id: '', device_type: 'light', room_id: '', name: '' })

const load = async () => {
  loading.value = true
  try {
    const params: Record<string, string> = {}
    if (filterRoom.value) params.room_id = filterRoom.value
    devices.value = (await getDevices(params)).data
  } finally { loading.value = false }
}

onMounted(async () => {
  await load()
  try { rooms.value = (await getRooms()).data } catch { /* */ }
})

const editItem = (row: any) => {
  form.value = { ...row }
  editMode.value = true
  showAdd.value = true
}

const save = async () => {
  try {
    if (editMode.value) await updateDevice(form.value.id, form.value)
    else await createDevice(form.value)
    ElMessage.success('保存成功')
    showAdd.value = false
    editMode.value = false
    await load()
  } catch { ElMessage.error('保存失败') }
}

const remove = async (id: string) => {
  await ElMessageBox.confirm('确认删除?', '提示')
  try { await deleteDevice(id); await load(); ElMessage.success('已删除') }
  catch { ElMessage.error('删除失败') }
}
</script>
