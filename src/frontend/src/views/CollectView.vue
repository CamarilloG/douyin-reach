<template>
  <n-space vertical>
    <n-space justify="space-between" align="center">
      <n-h4 style="margin: 0">采集监控</n-h4>
      <n-space>
        <n-tag v-if="isCollecting" type="success" :bordered="false">
          <template #icon>
            <n-icon><div style="width: 8px; height: 8px; border-radius: 50%; background: #18a058; animation: pulse 1.5s infinite;"></div></n-icon>
          </template>
          采集中
        </n-tag>
        <n-text depth="3" style="font-size: 12px">最后更新: {{ lastUpdateTime }}</n-text>
      </n-space>
    </n-space>

    <n-space>
      <n-select
        v-model:value="taskId"
        :options="taskOptions"
        placeholder="选择任务"
        style="width: 300px"
        @update:value="onTaskChange"
      />
      <n-button v-if="taskId" type="primary" size="small" @click="start" :disabled="isCollecting">启动采集</n-button>
      <n-button v-if="taskId" size="small" @click="pause" :disabled="!isCollecting">暂停</n-button>
      <n-button v-if="taskId" size="small" @click="stop" :disabled="!isCollecting">停止</n-button>
      <n-button size="small" @click="refresh" :loading="refreshing">
        <template #icon>
          <n-icon><svg viewBox="0 0 24 24"><path fill="currentColor" d="M17.65 6.35A7.958 7.958 0 0 0 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08A5.99 5.99 0 0 1 12 18c-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg></n-icon>
        </template>
        刷新
      </n-button>
    </n-space>

    <!-- 状态卡片 -->
    <n-card v-if="progress" size="small">
      <template #header>
        <n-space align="center">
          <span>采集进度</span>
          <n-tag :type="getStatusType(progress.status as string)" size="small" :bordered="false">
            {{ getStatusText(progress.status as string) }}
          </n-tag>
        </n-space>
      </template>

      <n-space vertical>
        <!-- 关键词进度 -->
        <div>
          <n-space justify="space-between" style="margin-bottom: 8px">
            <n-text>关键词进度</n-text>
            <n-text depth="3">{{ progress.current_keyword_index || 0 }} / {{ progress.total_keywords || 0 }}</n-text>
          </n-space>
          <n-progress
            type="line"
            :percentage="getKeywordProgress()"
            :show-indicator="false"
            :color="getStatusType(progress.status as string) === 'error' ? '#d03050' : '#18a058'"
          />
          <n-text v-if="progress.current_keyword" depth="3" style="font-size: 12px; margin-top: 4px; display: block">
            当前: {{ progress.current_keyword }}
          </n-text>
        </div>

        <!-- 视频进度 -->
        <div>
          <n-space justify="space-between" style="margin-bottom: 8px">
            <n-text>视频处理进度</n-text>
            <n-text depth="3">{{ progress.processed_videos || 0 }} / {{ progress.total_videos || 0 }}</n-text>
          </n-space>
          <n-progress
            type="line"
            :percentage="getVideoProgress()"
            :show-indicator="false"
            status="info"
          />
        </div>

        <!-- 统计信息（数字卡片） -->
        <n-grid :cols="6" :x-gap="12">
          <n-gi>
            <n-statistic label="视频" :value="Number(progress.processed_videos || 0)">
              <template #suffix>
                <n-text depth="3" style="font-size: 12px;">/ {{ Number(progress.total_videos || 0) }}</n-text>
              </template>
            </n-statistic>
          </n-gi>
          <n-gi>
            <n-statistic label="评论" :value="Number(progress.collected_comments || 0)" />
          </n-gi>
          <n-gi>
            <n-statistic label="命中" :value="Number(progress.users_matched || progress.collected_users || 0)" />
          </n-gi>
          <n-gi>
            <n-statistic label="已发" :value="Number(progress.sent_success || 0)" />
          </n-gi>
          <n-gi>
            <n-statistic label="待发" :value="Number(progress.sent_pending || 0)" />
          </n-gi>
          <n-gi>
            <n-statistic label="失败" :value="Number(progress.sent_failed || 0)" />
          </n-gi>
          <n-gi>
            <n-statistic label="跳过" :value="Number(progress.sent_skipped || 0)" />
          </n-gi>
        </n-grid>

        <!-- 错误信息 -->
        <n-alert v-if="progress.last_error" type="error" title="错误信息" closable>
          {{ progress.last_error }}
        </n-alert>
      </n-space>
    </n-card>

    <n-card v-else title="当前进度" size="small">
      <n-empty description="请选择任务或暂无进行中的任务">
        <template #extra>
          <n-button size="small" @click="$router.push('/tasks')">前往任务管理</n-button>
        </template>
      </n-empty>
    </n-card>

    <!-- 日志卡片 -->
    <n-card size="small">
      <template #header>
        <n-space justify="space-between" align="center">
          <span>实时日志</span>
          <n-space>
            <n-select
              v-model:value="logLevel"
              :options="logLevelOptions"
              size="small"
              style="width: 100px"
              @update:value="refreshLogs"
            />
            <n-button size="tiny" @click="copyLogs">复制</n-button>
            <n-button size="tiny" @click="clearLogs">清空</n-button>
            <n-button size="tiny" @click="scrollToBottom">滚动到底部</n-button>
          </n-space>
        </n-space>
      </template>

      <div
        ref="logContainer"
        style="height: 320px; overflow: auto; font-family: 'Consolas', 'Monaco', monospace; font-size: 12px; line-height: 1.6; padding: 12px; background: #1a1a1a; border-radius: 4px; user-select: text; -webkit-user-select: text; white-space: pre-wrap;"
      >
        <div v-if="logLines.length === 0" style="color: #666; text-align: center; padding: 20px;">
          暂无日志信息
        </div>
        <div
          v-for="(line, i) in logLines"
          :key="i"
          :style="getLogLineStyle(line)"
          style="margin-bottom: 2px; padding: 2px 4px; border-radius: 2px;"
        >
          {{ line }}
        </div>
      </div>
    </n-card>
  </n-space>
</template>

<style scoped>
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
</style>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, nextTick } from 'vue'
import {
  NCard,
  NSpace,
  NButton,
  NSelect,
  NH4,
  NTag,
  NText,
  NProgress,
  NGrid,
  NGi,
  NStatistic,
  NIcon,
  NAlert,
  NEmpty,
  useMessage
} from 'naive-ui'
import { bridge, isApiAvailable } from '@/api/bridge'
import { useTaskContext } from '@/stores/taskContext'
import { storeToRefs } from 'pinia'

const message = useMessage()
const taskCtx = useTaskContext()
const { currentTaskId: taskId } = storeToRefs(taskCtx)
const taskOptions = ref<{ label: string; value: number }[]>([])
const progress = ref<Record<string, unknown> | null>(null)
const logLines = ref<string[]>([])
const logContainer = ref<HTMLDivElement | null>(null)
const lastUpdateTime = ref<string>('--:--:--')
const refreshing = ref(false)
const logLevel = ref<string>('all')
const logLevelOptions = [
  { label: '全部', value: 'all' },
  { label: '信息', value: 'info' },
  { label: '警告', value: 'warning' },
  { label: '错误', value: 'error' }
]

let pollTimer: ReturnType<typeof setInterval> | null = null
let logPollTimer: ReturnType<typeof setInterval> | null = null

const isCollecting = computed(() => {
  return progress.value?.status === 'collecting'
})

function getStatusType(status: string): 'success' | 'info' | 'warning' | 'error' | 'default' {
  const map: Record<string, 'success' | 'info' | 'warning' | 'error' | 'default'> = {
    collecting: 'info',
    collected: 'success',
    paused: 'warning',
    error: 'error',
    stopped: 'default'
  }
  return map[status] || 'default'
}

function getStatusText(status: string): string {
  const map: Record<string, string> = {
    pending: '待启动',
    collecting: '采集中',
    collected: '已完成',
    paused: '已暂停',
    error: '出错',
    stopped: '已停止',
    filtering: '筛选中',
    filtered: '已筛选',
    sending: '发送中',
    sent: '已发送'
  }
  return map[status] || status
}

function getKeywordProgress(): number {
  if (!progress.value) return 0
  const current = Number(progress.value.current_keyword_index) || 0
  const total = Number(progress.value.total_keywords) || 1
  return Math.round((current / total) * 100)
}

function getVideoProgress(): number {
  if (!progress.value) return 0
  const processed = Number(progress.value.processed_videos) || 0
  const total = Number(progress.value.total_videos) || 1
  return Math.round((processed / total) * 100)
}

function getLogLineStyle(line: string): Record<string, string> {
  if (line.includes('ERROR') || line.includes('error')) {
    return { color: '#ff6b6b', background: 'rgba(255, 107, 107, 0.1)' }
  }
  if (line.includes('WARNING') || line.includes('warning')) {
    return { color: '#ffd93d', background: 'rgba(255, 217, 61, 0.1)' }
  }
  if (line.includes('INFO') || line.includes('info')) {
    return { color: '#6bcf7f' }
  }
  return { color: '#c9d1d9' }
}

async function loadTasks() {
  await taskCtx.refresh()
  const list = taskCtx.tasks as { id: number; name: string; status: string }[]
  taskOptions.value = list.map((t) => ({ label: `${t.name} (#${t.id}) - ${getStatusText(t.status)}`, value: t.id }))
  if (list.length && taskId.value == null) {
    const collectingTask = list.find((t) => t.status === 'collecting')
    taskCtx.selectTask(collectingTask ? collectingTask.id : list[0].id)
  }
}

// 任务进入这些状态后,后台没有活跃工作,前端应停止高频轮询
const TERMINAL_STATUSES = new Set([
  'pending', 'collected', 'completed', 'error', 'filtered'
])

async function refreshProgress() {
  if (taskId.value == null) return
  try {
    const p = await bridge.get_collection_progress(taskId.value)
    progress.value = p as Record<string, unknown> | null
    updateLastUpdateTime()
    // 终态自动停止进度轮询(用户切任务或重新启动会重新触发 startPolling)
    const status = (p as unknown as { status?: string } | null)?.status
    if (status && TERMINAL_STATUSES.has(status)) {
      stopPolling()
    }
  } catch (error) {
    console.error('Failed to refresh progress:', error)
  }
}

async function refreshLogs() {
  if (taskId.value == null) return
  try {
    const logs = await bridge.get_logs(taskId.value, 100)
    const allLogs = (logs as { id?: number; time?: string; level?: string; module?: string; message?: string }[])

    // 后端按 id DESC 返回（最新在前），反转为升序以便在底部显示最新
    const ordered = [...allLogs].reverse()

    // 根据日志级别过滤
    const filteredLogs = logLevel.value === 'all'
      ? ordered
      : ordered.filter(e => e.level?.toLowerCase() === logLevel.value)

    logLines.value = filteredLogs.map((e) => {
      const time = e.time || '--:--:--'
      const level = (e.level || 'INFO').toUpperCase().padEnd(7)
      const source = e.module ? `[${e.module}]` : ''
      const message = e.message || ''
      return `[${time}] ${level} ${source} ${message}`
    })

    // 新日志在底部，自动滚动到底部跟随最新
    if (logLines.value.length > 0) {
      await nextTick()
      scrollToBottom()
    }
  } catch (error) {
    console.error('Failed to refresh logs:', error)
  }
}

function updateLastUpdateTime() {
  const now = new Date()
  lastUpdateTime.value = now.toLocaleTimeString('zh-CN', { hour12: false })
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(() => {
    void refreshProgress()
  }, 3000) // 3 秒刷新一次进度(原 2s,降低 DB/桥接压力)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

// 轮询日志（替代 WebSocket 推送）
function startLogPolling() {
  stopLogPolling()
  logPollTimer = setInterval(() => {
    void refreshLogs()
  }, 5000) // 5 秒刷新一次日志(原 3s)
}

function stopLogPolling() {
  if (logPollTimer) {
    clearInterval(logPollTimer)
    logPollTimer = null
  }
}

async function onTaskChange() {
  await refresh()
  if (taskId.value == null) {
    stopPolling()
    return
  }
  const status = (progress.value as unknown as { status?: string } | null)?.status
  if (status && !TERMINAL_STATUSES.has(status)) {
    startPolling()
  } else {
    stopPolling()
  }
}

async function refresh() {
  refreshing.value = true
  try {
    await Promise.all([refreshProgress(), refreshLogs()])
  } finally {
    refreshing.value = false
  }
}

async function start() {
  if (!taskId.value) return
  try {
    await bridge.start_collection(taskId.value)
    await refresh()
    startPolling()
  } catch (error) {
    console.error('Failed to start collection:', error)
  }
}

async function pause() {
  if (!taskId.value) return
  try {
    await bridge.pause_collection(taskId.value)
    await refreshProgress()
  } catch (error) {
    console.error('Failed to pause collection:', error)
  }
}

async function stop() {
  if (!taskId.value) return
  try {
    await bridge.stop_collection(taskId.value)
    message.info('已请求停止,后台正在收尾(关闭浏览器/落库),请稍候再启动新任务')
    await refreshProgress()
    stopPolling()
  } catch (error) {
    console.error('Failed to stop collection:', error)
  }
}

async function clearLogs() {
  if (taskId.value == null) {
    logLines.value = []
    return
  }
  try {
    const res = await bridge.clear_logs(taskId.value) as { ok?: boolean; deleted?: number }
    if (res?.ok) {
      message.success(`已清空日志(${res.deleted ?? 0} 条)`)
    } else {
      message.warning('日志清空请求失败')
    }
  } catch (error) {
    console.error('Failed to clear logs:', error)
    message.error('日志清空异常')
  }
  logLines.value = []
  await refreshLogs()
}

async function copyLogs() {
  const text = logLines.value.join('\n')
  if (!text) {
    message.warning('当前没有可复制的日志')
    return
  }
  try {
    await navigator.clipboard.writeText(text)
    message.success('日志已复制到剪贴板')
  } catch (error) {
    console.error('Failed to copy logs:', error)
    message.error('复制失败，请手动框选日志')
  }
}

function scrollToBottom() {
  if (logContainer.value) {
    logContainer.value.scrollTop = logContainer.value.scrollHeight
  }
}

onMounted(async () => {
  const apiAvailable = await isApiAvailable()
  if (apiAvailable) {
    await loadTasks()
    if (taskId.value != null) {
      await refresh()
      // 仅当任务处于活跃态时才启动进度轮询;终态由 refreshProgress 自动停
      const status = (progress.value as unknown as { status?: string } | null)?.status
      if (status && !TERMINAL_STATUSES.has(status)) {
        startPolling()
      }
    }
    // 启动日志轮询(日志可能在任务停止后还有收尾日志,保留)
    startLogPolling()
  }
})

onUnmounted(() => {
  stopPolling()
  stopLogPolling()
})
</script>
