<template>
  <div>
    <el-row justify="end" style="margin-bottom:16px">
      <el-button type="primary" @click="openAdd">添加员工</el-button>
    </el-row>

    <el-table :data="list" stripe v-loading="loading">
      <el-table-column prop="id" label="员工 ID" width="160" />
      <el-table-column prop="name" label="姓名" width="140" />
      <el-table-column prop="email" label="邮箱" width="200" />
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
            {{ row.is_active ? '在职' : '离职' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="人脸" width="80">
        <template #default="{ row }">
          <el-tag :type="row.face_registered ? 'success' : 'warning'" size="small">
            {{ row.face_registered ? '已注册' : '未注册' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="240">
        <template #default="{ row }">
          <el-button size="small" @click="editItem(row)">编辑</el-button>
          <el-upload
            :action="faceUploadUrl(row.id)"
            :show-file-list="false"
            accept="image/*"
            :on-success="() => { ElMessage.success('人脸注册成功'); load() }"
          >
            <el-button size="small" type="success">注册人脸</el-button>
          </el-upload>
          <el-button size="small" type="danger" @click="remove(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="showDialog" :title="editMode ? '编辑员工' : '添加员工'" width="500px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="员工 ID"><el-input v-model="form.id" :disabled="editMode" /></el-form-item>
        <el-form-item label="姓名"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="邮箱"><el-input v-model="form.email" /></el-form-item>
        <el-form-item label="在职">
          <el-switch v-model="form.is_active" />
        </el-form-item>
      </el-form>

      <template v-if="editMode">
        <el-divider>偏好设置</el-divider>
        <el-table :data="prefs" size="small" max-height="200">
          <el-table-column prop="category" label="类别" width="100" />
          <el-table-column prop="key" label="键" width="120" />
          <el-table-column prop="value" label="值" />
          <el-table-column prop="context" label="场景" width="100" />
          <el-table-column label="" width="60">
            <template #default="{ row }">
              <el-button size="small" type="danger" link @click="delPref(row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-row :gutter="8" style="margin-top:8px">
          <el-col :span="5"><el-input v-model="newPref.category" placeholder="类别" size="small" /></el-col>
          <el-col :span="5"><el-input v-model="newPref.key" placeholder="键" size="small" /></el-col>
          <el-col :span="5"><el-input v-model="newPref.value" placeholder="值" size="small" /></el-col>
          <el-col :span="5"><el-input v-model="newPref.context" placeholder="场景" size="small" /></el-col>
          <el-col :span="4"><el-button size="small" type="primary" @click="addPref">添加</el-button></el-col>
        </el-row>
      </template>

      <template #footer>
        <el-button @click="showDialog = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import http from '../api/http'
import {
  getEmployees, createEmployee, updateEmployee, deleteEmployee,
  getPreferences, setPreference, deletePreference,
} from '../api'
import { ElMessage, ElMessageBox } from 'element-plus'

const list = ref<any[]>([])
const loading = ref(false)
const showDialog = ref(false)
const editMode = ref(false)
const form = ref({ id: '', name: '', email: '', is_active: true })
const prefs = ref<any[]>([])
const newPref = ref({ category: '', key: '', value: '', context: '' })

const faceUploadUrl = (id: string) =>
  `${http.defaults.baseURL || ''}/api/employees/${id}/face`

const load = async () => {
  loading.value = true
  try { list.value = (await getEmployees()).data } finally { loading.value = false }
}
onMounted(load)

const openAdd = () => {
  form.value = { id: '', name: '', email: '', is_active: true }
  editMode.value = false; prefs.value = []; showDialog.value = true
}

const editItem = async (row: any) => {
  form.value = { ...row }; editMode.value = true; showDialog.value = true
  try { prefs.value = (await getPreferences(row.id)).data } catch { prefs.value = [] }
}

const save = async () => {
  try {
    if (editMode.value) await updateEmployee(form.value.id, form.value)
    else await createEmployee(form.value)
    ElMessage.success('保存成功'); showDialog.value = false; await load()
  } catch { ElMessage.error('保存失败') }
}

const remove = async (id: string) => {
  await ElMessageBox.confirm('确认删除?', '提示')
  try { await deleteEmployee(id); await load(); ElMessage.success('已删除') } catch { ElMessage.error('删除失败') }
}

const addPref = async () => {
  try {
    await setPreference({ ...newPref.value, employee_id: form.value.id })
    prefs.value = (await getPreferences(form.value.id)).data
    newPref.value = { category: '', key: '', value: '', context: '' }
    ElMessage.success('偏好已添加')
  } catch { ElMessage.error('添加失败') }
}

const delPref = async (id: number) => {
  try {
    await deletePreference(id)
    prefs.value = prefs.value.filter((p: any) => p.id !== id)
    ElMessage.success('已删除')
  } catch { ElMessage.error('删除失败') }
}
</script>
