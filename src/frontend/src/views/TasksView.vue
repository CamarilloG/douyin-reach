<template>
  <div>
    <n-space vertical>
      <n-space justify="space-between">
        <n-h4 style="margin: 0">任务列表</n-h4>
        <n-button type="primary" @click="showModal = true">创建任务</n-button>
      </n-space>
      <n-data-table
        :columns="columns"
        :data="tasks"
        :loading="loading"
        :pagination="false"
        size="small"
      />
    </n-space>
    <n-modal v-model:show="showModal" preset="card" title="创建任务" style="width: 560px" @after-leave="loadTasks">
      <n-form ref="formRef" :model="form" label-placement="left" label-width="120">
        <n-form-item label="任务名称">
          <n-input v-model:value="form.name" placeholder="请输入任务名称" />
        </n-form-item>
        <n-form-item label="关键词">
          <n-dynamic-input v-model:value="form.keywords" :min="1" placeholder="关键词" />
        </n-form-item>
        <n-form-item label="每视频评论上限">
          <n-input-number v-model:value="form.max_comments_per_video" :min="1" :max="500" style="width: 100%" />
        </n-form-item>
        <n-form-item label="私信模板">
          <n-input v-model:value="form.template" type="textarea" placeholder="支持 {nickname} {video_title}" :rows="3" />
        </n-form-item>
        <n-form-item label="发送间隔(秒)">
          <n-input-number v-model:value="form.send_interval" :min="10" style="width: 100%" />
        </n-form-item>
        <n-form-item label="日上限">
          <n-input-number v-model:value="form.daily_limit" :min="1" style="width: 100%" />
        </n-form-item>
        <n-form-item label="任务上限">
          <n-input-number v-model:value="form.task_limit" :min="1" style="width: 100%" />
        </n-form-item>
        <n-form-item label="全自动发送">
          <n-switch v-model:value="form.auto_send" />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showModal = false">取消</n-button>
          <n-button type="primary" :loading="submitting" @click="onCreate">创建</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, h } from 'vue'
import { NButton, NSpace, NDataTable, NModal, NForm, NFormItem, NInput, NInputNumber, NSwitch, NH4 } from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import { bridge, isApiAvailable } from '@/api/bridge'

const loading = ref(false)
const tasks = ref<Record<string, unknown>[]>([])
const showModal = ref(false)
const submitting = ref(false)
const formRef = ref(null)
const form = ref({
  name: '',
  keywords: [''] as string[],
  max_comments_per_video: 50,
  template: '你好 {nickname}，看到你对「{video_title}」的评论～',
  send_interval: 30,
  daily_limit: 100,
  task_limit: 500,
  auto_send: false,
})

const statusMap: Record<string, string> = {
  pending: '待执行',
  collecting: '采集中',
  collected: '已采集',
  filtering: '筛选中',
  filtered: '已筛选',
  sending: '发送中',
  paused: '已暂停',
  completed: '已完成',
  error: '异常',
}

const columns: DataTableColumns<Record<string, unknown>> = [
  { title: 'ID', key: 'id', width: 60 },
  { title: '任务名', key: 'name', width: 140 },
  {
    title: '状态',
    key: 'status',
    width: 90,
    render: (row) => statusMap[(row.status as string) ?? ''] ?? row.status,
  },
  { title: '关键词', key: 'keywords', ellipsis: { tooltip: true }, render: (row) => (row.keywords as string[])?.join(', ') },
  { title: '创建时间', key: 'created_at', width: 160 },
  {
    title: '操作',
    key: 'actions',
    width: 200,
    render: (row) => {
      const id = row.id as number
      return h(NSpace, { size: 8 }, () => [
        h(NButton, { size: 'small', onClick: () => edit(id) }, '编辑'),
        h(NButton, { size: 'small', onClick: () => startCollect(id) }, '启动'),
        h(NButton, { size: 'small', type: 'error', onClick: () => del(id) }, '删除'),
      ])
    },
  },
]

async function loadTasks() {
  if (!bridge) return
  loading.value = true
  try {
    tasks.value = (await bridge.get_tasks()) as Record<string, unknown>[]
  } finally {
    loading.value = false
  }
}

async function onCreate() {
  if (!bridge) return
  submitting.value = true
  try {
    await bridge.create_task({
      name: form.value.name,
      keywords: form.value.keywords.filter(Boolean),
      max_comments_per_video: form.value.max_comments_per_video,
      template: form.value.template,
      send_interval: form.value.send_interval,
      daily_limit: form.value.daily_limit,
      task_limit: form.value.task_limit,
    })
    showModal.value = false
    form.value = { ...form.value, name: '', keywords: [''] }
  } finally {
    submitting.value = false
  }
}

function edit(_id: number) {
  // TODO: 编辑弹窗
}
function startCollect(id: number) {
  bridge?.start_collection(id)
  loadTasks()
}
function del(id: number) {
  bridge?.delete_task(id)
  loadTasks()
}

onMounted(() => {
  if (isApiAvailable()) loadTasks()
})
</script>
