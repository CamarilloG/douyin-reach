<template>
  <n-space vertical>
    <n-h4 style="margin: 0">发送历史</n-h4>
    <n-space>
      <n-select
        v-model:value="taskId"
        :options="taskOptions"
        placeholder="选择任务"
        style="width: 200px"
        @update:value="load"
      />
      <n-button @click="load">刷新</n-button>
      <n-button @click="exportCsv">导出 CSV</n-button>
    </n-space>
    <n-data-table
      :columns="columns"
      :data="items"
      :loading="loading"
      :pagination="pagination"
      @update:page="onPage"
    />
  </n-space>
</template>

<script setup lang="ts">
import { ref, onMounted, h } from 'vue'
import { NSpace, NDataTable, NSelect, NButton, NTag, NH4 } from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import { bridge, isApiAvailable } from '@/api/bridge'

const taskId = ref<number | null>(null)
const taskOptions = ref<{ label: string; value: number }[]>([])
const items = ref<Record<string, unknown>[]>([])
const loading = ref(false)
const page = ref(1)
const pageSize = ref(20)
const pagination = ref({ page: 1, pageSize: 20, itemCount: 0, showSizePicker: true, pageSizes: [10, 20, 50] })

const columns: DataTableColumns<Record<string, unknown>> = [
  { title: '时间', key: 'time', width: 160 },
  { title: '用户', key: 'nickname', width: 100 },
  { title: '任务', key: 'task_name', width: 120 },
  {
    title: '状态',
    key: 'status',
    width: 90,
    render: (row) =>
      row.status === 'success'
        ? h(NTag, { type: 'success', size: 'small' }, () => '成功')
        : h(NTag, { type: 'error', size: 'small' }, () => '失败'),
  },
  { title: '失败原因', key: 'reason', ellipsis: { tooltip: true } },
]

async function loadTasks() {
  if (!bridge) return
  const list = (await bridge.get_tasks()) as { id: number; name: string }[]
  taskOptions.value = list.map((t) => ({ label: t.name, value: t.id }))
  if (list.length && taskId.value == null) taskId.value = list[0].id
}

async function load() {
  if (!bridge || taskId.value == null) return
  loading.value = true
  try {
    const res = await bridge.get_send_history(taskId.value, page.value, pageSize.value)
    items.value = res.items as Record<string, unknown>[]
    pagination.value = {
      ...pagination.value,
      page: page.value,
      pageSize: pageSize.value,
      itemCount: res.total,
    }
  } finally {
    loading.value = false
  }
}

function onPage(p: number) {
  page.value = p
  load()
}

function exportCsv() {
  if (!bridge || taskId.value == null) return
  bridge.export_send_history(taskId.value, '')
}

onMounted(() => {
  if (isApiAvailable()) {
    loadTasks().then(() => load())
  }
})
</script>
