<template>
  <n-space vertical :size="16">
    <n-h4 style="margin: 0">历史记录（任务执行）</n-h4>
    <n-space align="center">
      <n-select
        v-model:value="filterTaskId"
        :options="taskOptionsAll"
        placeholder="筛选任务"
        style="width: 220px"
        clearable
        @update:value="onFilterChange"
      />
      <n-input v-model:value="startDate" placeholder="开始时间 YYYY-MM-DD" style="width: 180px" />
      <n-input v-model:value="endDate" placeholder="结束时间 YYYY-MM-DD" style="width: 180px" />
      <n-button @click="load">刷新</n-button>
    </n-space>
    <n-data-table
      :columns="columns"
      :data="items"
      :loading="loading"
      :pagination="pagination"
      remote
    />
  </n-space>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, h } from 'vue'
import { useRouter } from 'vue-router'
import { NSpace, NDataTable, NSelect, NButton, NTag, NH4, NInput, useMessage } from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import { bridge, isApiAvailable } from '@/api/bridge'

const message = useMessage()
const router = useRouter()
const filterTaskId = ref<number | null>(null)
const taskOptionsAll = ref<{ label: string; value: number }[]>([])
const items = ref<Record<string, any>[]>([])
const loading = ref(false)
const startDate = ref<string>('')
const endDate = ref<string>('')

const pagination = reactive({
  page: 1,
  pageSize: 20,
  itemCount: 0,
  showSizePicker: true,
  pageSizes: [10, 20, 50],
  prefix: (info: { itemCount?: number }) => `共 ${info.itemCount ?? 0} 条`,
  onChange: (p: number) => { pagination.page = p; void load() },
  onUpdatePageSize: (s: number) => { pagination.pageSize = s; pagination.page = 1; void load() },
})

const STATUS_META: Record<string, { label: string; type: 'success' | 'info' | 'warning' | 'error' | 'default' }> = {
  running: { label: '运行中', type: 'info' },
  completed: { label: '已完成', type: 'success' },
  failed: { label: '失败', type: 'error' },
  stopped: { label: '已停止', type: 'warning' },
}

const columns: DataTableColumns<Record<string, any>> = [
  { title: '任务', key: 'task_name', width: 160, render: (row) => row.task_name || `#${row.task_id}` },
  { title: '开始时间', key: 'started_at', width: 160 },
  { title: '结束时间', key: 'ended_at', width: 160, render: (row) => row.ended_at || '—' },
  {
    title: '状态', key: 'status', width: 90,
    render: (row) => {
      const meta = STATUS_META[String(row.status)] ?? { label: String(row.status), type: 'default' as const }
      return h(NTag, { size: 'small', type: meta.type, bordered: false }, { default: () => meta.label })
    },
  },
  { title: '视频', key: 'videos_collected', width: 70 },
  { title: '评论', key: 'comments_collected', width: 70 },
  { title: '命中', key: 'users_matched', width: 70 },
  { title: '私信成功', key: 'sent_success', width: 90 },
  { title: '私信失败', key: 'sent_failed', width: 90 },
  {
    title: '操作', key: 'actions', width: 160,
    render: (row) => {
      const tid = row.task_id as number
      const eid = row.id as number
      return h(NSpace, { size: 4 }, () => [
        h(NButton, { size: 'small', onClick: () => viewDetail(tid) }, { default: () => '详情' }),
        h(NButton, { size: 'small', type: 'error', onClick: () => del(eid) }, { default: () => '删除' }),
      ])
    },
  },
]

async function loadTasks() {
  const list = (await bridge.get_tasks()) as { id: number; name: string }[]
  taskOptionsAll.value = list.map((t) => ({ label: t.name, value: t.id }))
}

async function load() {
  loading.value = true
  try {
    const res = await bridge.get_task_executions(
      filterTaskId.value,
      pagination.page,
      pagination.pageSize,
      startDate.value || null,
      endDate.value || null,
    )
    items.value = (res.items || []) as Record<string, any>[]
    pagination.itemCount = res.total ?? 0
  } catch (e) {
    console.error(e)
    message.error('加载执行历史失败')
  } finally {
    loading.value = false
  }
}

function onFilterChange() {
  pagination.page = 1
  void load()
}

function viewDetail(taskId: number) {
  router.push({ path: '/audit', query: { task_id: String(taskId) } })
}

async function del(execId: number) {
  try {
    await bridge.delete_task_execution(execId)
    message.success('已删除')
    await load()
  } catch (e) {
    console.error(e); message.error('删除失败')
  }
}

onMounted(async () => {
  if (await isApiAvailable()) {
    await loadTasks()
    await load()
  }
})
</script>
