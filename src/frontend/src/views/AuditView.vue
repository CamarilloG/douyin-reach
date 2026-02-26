<template>
  <n-space vertical>
    <n-h4 style="margin: 0">待触达名单</n-h4>
    <n-space>
      <n-select
        v-model:value="taskId"
        :options="taskOptions"
        placeholder="选择任务"
        style="width: 200px"
        @update:value="load"
      />
      <n-button @click="load">刷新</n-button>
      <n-button @click="toggleSelect(true)">全选</n-button>
      <n-button @click="toggleSelect(false)">反选</n-button>
      <n-button @click="exportCsv">导出 CSV</n-button>
    </n-space>
    <n-data-table
      :columns="columns"
      :data="items"
      :loading="loading"
      :row-key="(row: Record<string, unknown>) => String(row.id)"
      :checked-row-keys="checkedRowKeys"
      :pagination="pagination"
      @update:checked-row-keys="onChecked"
      @update:page="onPage"
    />
  </n-space>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { NButton, NSpace, NDataTable, NSelect, NH4 } from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import { bridge, isApiAvailable } from '@/api/bridge'

const taskId = ref<number | null>(null)
const taskOptions = ref<{ label: string; value: number }[]>([])
const items = ref<Record<string, unknown>[]>([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const checkedRowKeys = ref<(string | number)[]>([])

const pagination = ref({ page: 1, pageSize: 20, itemCount: 0, showSizePicker: true, pageSizes: [10, 20, 50] })

const columns: DataTableColumns<Record<string, unknown>> = [
  { type: 'selection' },
  { title: '昵称', key: 'nickname', width: 120 },
  { title: '评论内容', key: 'comment_text', ellipsis: { tooltip: true } },
  { title: '来源视频', key: 'source_video_title', width: 160, ellipsis: { tooltip: true } },
  { title: '命中规则', key: 'matched_rule', width: 120 },
  { title: '粉丝数', key: 'fans_count', width: 90 },
  { title: '发送状态', key: 'send_status', width: 90 },
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
    const res = await bridge.get_target_users(taskId.value, page.value, pageSize.value)
    items.value = res.items as Record<string, unknown>[]
    total.value = res.total
    pagination.value = { ...pagination.value, page: page.value, pageSize: pageSize.value, itemCount: res.total }
  } finally {
    loading.value = false
  }
}

function onPage(p: number) {
  page.value = p
  load()
}

function onChecked(keys: (string | number)[]) {
  checkedRowKeys.value = keys
  if (bridge && taskId.value != null) {
    const ids = keys.map((k) => (typeof k === 'number' ? k : Number(k)))
    bridge.update_user_selection(taskId.value, ids, true)
    const unselected = items.value
      .filter((r) => !keys.includes(r.id as string | number))
      .map((r) => r.id as number)
    if (unselected.length) bridge.update_user_selection(taskId.value, unselected, false)
  }
}

function toggleSelect(selected: boolean) {
  if (!bridge || taskId.value == null) return
  const ids = items.value.map((r) => r.id as number)
  bridge.update_user_selection(taskId.value, ids, selected)
  checkedRowKeys.value = selected ? items.value.map((r) => r.id as string | number) : []
}

function exportCsv() {
  if (!bridge || taskId.value == null) return
  bridge.export_target_users(taskId.value, '')
}

onMounted(() => {
  if (isApiAvailable()) {
    loadTasks().then(() => load())
  }
})
</script>
