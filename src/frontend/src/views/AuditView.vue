<template>
  <n-space vertical>
    <n-space justify="space-between" align="center">
      <div>
        <n-h4 style="margin: 0">待触达名单（筛选后）</n-h4>
        <n-text depth="3" style="font-size: 12px">
          本页展示的是「执行筛选」按钮跑出来的 target_list,不是实时评论流。原始评论需要先点「执行筛选」才会进入此名单。
        </n-text>
      </div>
      <n-text depth="3" style="font-size: 13px">共 {{ total }} 人</n-text>
    </n-space>

    <!-- 实时采集状态(只读,反映 collectors 线程的累计写入) -->
    <n-card size="small" v-if="taskId">
      <n-space :size="32" align="center">
        <n-statistic label="已采集评论" :value="liveStats.comments">
          <template #suffix>
            <n-text depth="3" style="font-size: 12px">条</n-text>
          </template>
        </n-statistic>
        <n-statistic label="已采集用户" :value="liveStats.users">
          <template #suffix>
            <n-text depth="3" style="font-size: 12px">人</n-text>
          </template>
        </n-statistic>
        <n-statistic label="待筛选 → 待触达" :value="total">
          <template #suffix>
            <n-text depth="3" style="font-size: 12px">人</n-text>
          </template>
        </n-statistic>
        <n-text depth="3" style="font-size: 12px">
          采集状态: {{ liveStats.phase || '—' }}
        </n-text>
      </n-space>
    </n-card>

    <!-- 当前任务规则展示 -->
    <n-card size="small" v-if="taskId">
      <template #header>
        <n-space justify="space-between" align="center">
          <span>当前任务规则</span>
          <n-button size="tiny" @click="goEditRules">编辑规则（去任务管理）</n-button>
        </n-space>
      </template>
      <n-descriptions :column="2" size="small" bordered>
        <n-descriptions-item label="白名单">{{ (rules.whitelist || []).join('、') || '—' }}</n-descriptions-item>
        <n-descriptions-item label="黑名单">{{ (rules.blacklist || []).join('、') || '—' }}</n-descriptions-item>
        <n-descriptions-item label="正则包含">{{ (rules.regex_include || []).join('、') || '—' }}</n-descriptions-item>
        <n-descriptions-item label="正则排除">{{ (rules.regex_exclude || []).join('、') || '—' }}</n-descriptions-item>
      </n-descriptions>
    </n-card>

    <n-space>
      <n-select
        v-model:value="taskId"
        :options="taskOptions"
        placeholder="选择任务"
        style="width: 220px"
        @update:value="onTaskChange"
      />
      <n-select
        v-model:value="filterStatus"
        :options="statusOptions"
        style="width: 140px"
        @update:value="onFilterStatusChange"
      />
      <n-button type="primary" @click="runFilter">执行筛选</n-button>
      <n-button @click="load">刷新</n-button>
      <n-button @click="toggleSelect(true)">全选</n-button>
      <n-button @click="toggleSelect(false)">反选</n-button>
      <n-button type="primary" ghost @click="importToSend">导入私信流程</n-button>
      <n-button @click="exportCsv">导出 CSV</n-button>
    </n-space>
    <n-data-table
      :columns="columns"
      :data="items"
      :loading="loading"
      :row-key="(row: Record<string, unknown>) => String(row.user_id ?? row.id)"
      :checked-row-keys="checkedRowKeys"
      :max-height="560"
      virtual-scroll
      @update:checked-row-keys="onChecked"
    />
  </n-space>
</template>

<script setup lang="ts">
import { ref, h, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NSpace, NDataTable, NSelect, NH4, NText, NTag, NCard, NStatistic, NDescriptions, NDescriptionsItem, useMessage } from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import { bridge, isApiAvailable } from '@/api/bridge'
import { useTaskContext } from '@/stores/taskContext'
import { storeToRefs } from 'pinia'

const message = useMessage()
const router = useRouter()
const taskCtx = useTaskContext()
const { currentTaskId: taskId } = storeToRefs(taskCtx)
const taskOptions = ref<{ label: string; value: number }[]>([])
const rules = ref<{ whitelist?: string[]; blacklist?: string[]; regex_include?: string[]; regex_exclude?: string[] }>({})
const filterStatus = ref<string>('all')
const statusOptions = [
  { label: '全部', value: 'all' },
  { label: '未发', value: 'unsent' },
  { label: '已发', value: 'sent' },
  { label: '失败', value: 'failed' },
]
const items = ref<Record<string, unknown>[]>([])
const loading = ref(false)
const total = ref(0)
const checkedRowKeys = ref<(string | number)[]>([])
// 实时采集统计(从 progress_snapshot 读取,不是 target_list)
const liveStats = ref<{ comments: number; users: number; phase: string }>({
  comments: 0,
  users: 0,
  phase: '',
})
let liveStatsTimer: ReturnType<typeof setInterval> | null = null

const SEND_STATUS_META: Record<string, { label: string; type: 'default' | 'info' | 'success' | 'warning' | 'error' }> = {
  unsent: { label: '待发送', type: 'default' },
  pending: { label: '待发送', type: 'default' },
  sending: { label: '发送中', type: 'info' },
  sent: { label: '已发送', type: 'success' },
  success: { label: '已发送', type: 'success' },
  failed: { label: '失败', type: 'error' },
  failure: { label: '失败', type: 'error' },
  skipped: { label: '已跳过', type: 'warning' },
}

const columns: DataTableColumns<Record<string, unknown>> = [
  { type: 'selection' },
  {
    title: '昵称',
    key: 'nickname',
    width: 120,
    render: (row) => (row.nickname as string) || '—',
  },
  { title: '评论内容', key: 'comment_text', ellipsis: { tooltip: true } },
  {
    title: '来源视频',
    key: 'source_video_title',
    width: 160,
    ellipsis: { tooltip: true },
    render: (row) => (row.source_video_title as string) || '—',
  },
  {
    title: '命中规则',
    key: 'matched_rule',
    width: 120,
    render: (row) => {
      const v = (row.matched_rule as string) || ''
      return v || '—'
    },
  },
  {
    title: '粉丝数',
    key: 'fans_count',
    width: 90,
    render: (row) => {
      const v = row.fans_count
      if (v === null || v === undefined || v === '' || v === 0) return '—'
      return String(v)
    },
  },
  {
    title: '发送状态',
    key: 'send_status',
    width: 100,
    render: (row) => {
      const raw = String(row.send_status ?? 'unsent').toLowerCase()
      const meta = SEND_STATUS_META[raw] ?? { label: raw || '待发送', type: 'default' as const }
      return h(NTag, { size: 'small', type: meta.type, bordered: false }, { default: () => meta.label })
    },
  },
]

async function loadTasks() {
  if (!bridge) return
  await taskCtx.refresh()
  const list = taskCtx.tasks as { id: number; name: string }[]
  taskOptions.value = list.map((t) => ({ label: t.name, value: t.id }))
  if (list.length && taskId.value == null) taskCtx.selectTask(list[0].id)
}

async function loadRules() {
  if (taskId.value == null) { rules.value = {}; return }
  try {
    const t = (await bridge.get_task(taskId.value)) as Record<string, any> | null
    rules.value = (t?.rules || {}) as any
  } catch (e) {
    console.error(e); rules.value = {}
  }
}

const COLLECTING_STATUSES = new Set(['collecting', 'filtering'])

async function loadLiveStats() {
  if (taskId.value == null) {
    liveStats.value = { comments: 0, users: 0, phase: '' }
    return
  }
  try {
    const p = await bridge.get_collection_progress(taskId.value) as Record<string, any> | null
    if (!p) return
    liveStats.value = {
      comments: Number(p.collected_comments ?? 0),
      users: Number(p.collected_users ?? 0),
      phase: String(p.status ?? ''),
    }
    // 采集进行中时启动轮询,终态时停止
    if (COLLECTING_STATUSES.has(liveStats.value.phase)) {
      ensureLiveStatsPolling()
    } else {
      stopLiveStatsPolling()
    }
  } catch (e) {
    console.error('Failed to load live stats:', e)
  }
}

function ensureLiveStatsPolling() {
  if (liveStatsTimer) return
  liveStatsTimer = setInterval(() => { void loadLiveStats() }, 3000)
}

function stopLiveStatsPolling() {
  if (liveStatsTimer) {
    clearInterval(liveStatsTimer)
    liveStatsTimer = null
  }
}

async function load() {
  if (!bridge || taskId.value == null) return
  loading.value = true
  try {
    const status = filterStatus.value === 'all' ? null : filterStatus.value
    // 限制单次拉取量,避免 bridge 序列化和前端内存压力;total 用服务端真实计数
    const res = await bridge.get_target_users(taskId.value, 1, 5000, status)
    items.value = res.items as Record<string, unknown>[]
    total.value = res.total
    checkedRowKeys.value = items.value
      .filter((r) => r.selected)
      .map((r) => String(r.user_id ?? r.id))
  } finally {
    loading.value = false
  }
}

function onTaskChange() {
  void loadRules()
  void load()
  void loadLiveStats()
}

function onFilterStatusChange() {
  void load()
}

function goEditRules() {
  router.push('/tasks')
}

async function importToSend() {
  if (taskId.value == null) {
    message.warning('请先选择任务')
    return
  }
  // items 已是当前筛选条件下的全量(取消分页),全部置 selected=true
  const ids = items.value.map((r) => r.user_id as number).filter((v) => v != null)
  if (!ids.length) {
    message.warning('当前列表无待选用户')
    return
  }
  await bridge.update_user_selection(taskId.value, ids, true)
  checkedRowKeys.value = items.value.map((r) => String(r.user_id ?? r.id))
  message.success(`已选 ${ids.length} 人，请到「私信发送」标签启动发送`)
}

function onChecked(keys: (string | number)[]) {
  checkedRowKeys.value = keys
  if (bridge && taskId.value != null) {
    const keySet = new Set(keys.map(String))
    const selectedIds = items.value
      .filter((r) => keySet.has(String(r.user_id ?? r.id)))
      .map((r) => r.user_id as number)
    const unselected = items.value
      .filter((r) => !keySet.has(String(r.user_id ?? r.id)))
      .map((r) => r.user_id as number)
    if (selectedIds.length) bridge.update_user_selection(taskId.value, selectedIds, true)
    if (unselected.length) bridge.update_user_selection(taskId.value, unselected, false)
  }
}

function toggleSelect(selected: boolean) {
  if (!bridge || taskId.value == null) return
  const ids = items.value.map((r) => r.user_id as number)
  bridge.update_user_selection(taskId.value, ids, selected)
  checkedRowKeys.value = selected ? items.value.map((r) => String(r.user_id ?? r.id)) : []
}

async function runFilter() {
  if (!bridge || taskId.value == null) {
    message.warning('请先选择任务')
    return
  }
  try {
    const res = await bridge.run_filter(taskId.value) as { ok?: boolean; count?: number; error?: string }
    if (res?.ok) {
      message.success(`筛选完成，待触达 ${res.count ?? 0} 人`)
    } else {
      message.error(`筛选失败: ${res?.error || '未知原因'}`)
    }
  } catch (e) {
    message.error('筛选请求异常: ' + String(e))
  }
  await load()
}

async function exportCsv() {
  if (!bridge || taskId.value == null) return
  await bridge.export_target_users(taskId.value, '')
}

watch(taskId, () => {
  void loadRules()
  void loadLiveStats()
})

import { onUnmounted } from 'vue'

onMounted(async () => {
  if (await isApiAvailable()) {
    await loadTasks()
    await loadRules()
    await load()
    await loadLiveStats()
  }
})

onUnmounted(() => {
  stopLiveStatsPolling()
})
</script>
