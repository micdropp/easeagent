<template>
  <div>
    <el-row justify="end" style="margin-bottom:16px">
      <el-button type="primary" @click="showAdd = true">添加房间</el-button>
    </el-row>

    <el-table :data="rooms" stripe v-loading="loading">
      <el-table-column prop="id" label="房间 ID" width="160" />
      <el-table-column prop="name" label="名称" />
      <el-table-column prop="floor" label="楼层" width="80" />
      <el-table-column label="操作" width="150">
        <template #default="{ row }">
          <el-button size="small" @click="editItem(row)">编辑</el-button>
          <el-button size="small" type="danger" @click="remove(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="showAdd" :title="editMode ? '编辑房间' : '添加房间'" width="460px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="房间 ID"><el-input v-model="form.id" :disabled="editMode" /></el-form-item>
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="楼层"><el-input v-model="form.floor" /></el-form-item>
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
import { getRooms, createRoom, updateRoom, deleteRoom } from '../api'
import { ElMessage, ElMessageBox } from 'element-plus'

const rooms = ref<any[]>([])
const loading = ref(false)
const showAdd = ref(false)
const editMode = ref(false)
const form = ref({ id: '', name: '', floor: '' })

const load = async () => {
  loading.value = true
  try { rooms.value = (await getRooms()).data } finally { loading.value = false }
}
onMounted(load)

const editItem = (row: any) => { form.value = { ...row }; editMode.value = true; showAdd.value = true }
const save = async () => {
  try {
    if (editMode.value) await updateRoom(form.value.id, form.value)
    else await createRoom(form.value)
    ElMessage.success('保存成功'); showAdd.value = false; editMode.value = false; await load()
  } catch { ElMessage.error('保存失败') }
}
const remove = async (id: string) => {
  await ElMessageBox.confirm('确认删除?', '提示')
  try { await deleteRoom(id); await load(); ElMessage.success('已删除') } catch { ElMessage.error('删除失败') }
}
</script>
