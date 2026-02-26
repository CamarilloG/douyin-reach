<template>
  <n-space vertical>
    <n-h4 style="margin: 0">采集监控</n-h4>
    <n-card v-if="progress" title="当前进度" size="small">
      <n-descriptions :column="2" label-placement="left">
        <n-descriptions-item label="任务">#{{ progress.task_id }}</n-descriptions-item>
        <n-descriptions-item label="状态">{{ progress.status }}</n-descriptions-item>
        <n-descriptions-item label="当前关键词">{{ progress.current_keyword }}</n-descriptions-item>
        <n-descriptions-item label="关键词进度">{{ progress.current_keyword_index }} / {{ progress.total_keywords }}</n-descriptions-item>
        <n-descriptions-item label="已处理视频">{{ progress.processed_videos }} / {{ progress.total_videos }}</n-descriptions-item>
        <n-descriptions-item label="已采集评论">{{ progress.collected_comments }}</n-descriptions-item>
        <n-descriptions-item label="已采集用户">{{ progress.collected_users }}</n-descriptions-item>
      </n-descriptions>
      <template #footer>
        <n-space>
          <n-button type="primary" size="small" @click="start">启动</n-button>
          <n-button size="small" @click="pause">暂停</n-button>
          <n-button size="small" @click="stop">停止</n-button>
        </n-space>
      </template>
    </n-card>
    <n-card v-else title="当前进度" size="small">
      <p>请选择任务或暂无进行中的任务。可在任务管理页启动采集。</p>
    </n-card>
    <n-card title="日志" size="small">
      <div style="height: 240px; overflow: auto; font-family: monospace; font-size: 12px; white-space: pre-wrap; padding: 8px; background: #1a1a1a; border-radius: 4px;">
        <div v-for="(line, i) in logLines" :key="i">{{ line }}</div>
      </div>
    </n-card>
  </n-space>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { NCard, NSpace, NButton, NDescriptions, NDescriptionsItem, NH4 } from 'naive-ui'
import { bridge, isApiAvailable } from '@/api/bridge'

const taskId = ref(1)
const progress = ref<Record<string, unknown> | null>(null)
const logLines = ref<string[]>([])

async function refreshProgress() {
  if (!bridge) return
  const p = await bridge.get_collection_progress(taskId.value)
  progress.value = p as Record<string, unknown> | null
}

async function refreshLogs() {
  if (!bridge) return
  const logs = await bridge.get_logs(taskId.value, 50)
  logLines.value = (logs as { time?: string; level?: string; message?: string }[]).map(
    (e) => `[${e.time}] ${e.level}: ${e.message}`
  )
}

function start() {
  bridge?.start_collection(taskId.value)
  refreshProgress()
}
function pause() {
  bridge?.pause_collection(taskId.value)
  refreshProgress()
}
function stop() {
  bridge?.stop_collection(taskId.value)
  refreshProgress()
}

onMounted(() => {
  if (isApiAvailable()) {
    refreshProgress()
    refreshLogs()
  }
})
</script>
