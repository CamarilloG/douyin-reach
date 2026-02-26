<template>
  <n-space vertical>
    <n-h4 style="margin: 0">发送控制</n-h4>
    <n-card v-if="progress" title="发送进度" size="small">
      <n-grid :cols="4" :x-gap="16">
        <n-gi><n-statistic label="待发" :value="progress.pending ?? 0" /></n-gi>
        <n-gi><n-statistic label="发送中" :value="progress.sending ?? 0" /></n-gi>
        <n-gi><n-statistic label="已成功" :value="progress.success ?? 0" /></n-gi>
        <n-gi><n-statistic label="已失败" :value="progress.failed ?? 0" /></n-gi>
      </n-grid>
      <template #footer>
        <n-space>
          <n-button type="primary" size="small" @click="start">启动发送</n-button>
          <n-button size="small" @click="pause">暂停</n-button>
          <n-button size="small" @click="stop">停止</n-button>
        </n-space>
      </template>
    </n-card>
    <n-card v-else title="发送进度" size="small">
      <p>请先选择任务并在名单审核页确认待发用户。</p>
    </n-card>
  </n-space>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { NCard, NSpace, NButton, NStatistic, NGrid, NGi, NH4 } from 'naive-ui'
import { bridge, isApiAvailable } from '@/api/bridge'

const taskId = ref(1)
const progress = ref<{ pending?: number; sending?: number; success?: number; failed?: number } | null>(null)

async function refresh() {
  if (!bridge) return
  const p = await bridge.get_send_progress(taskId.value)
  progress.value = p as { pending?: number; sending?: number; success?: number; failed?: number } | null
}

function start() {
  bridge?.start_sending(taskId.value)
  refresh()
}
function pause() {
  bridge?.pause_sending(taskId.value)
  refresh()
}
function stop() {
  bridge?.stop_sending(taskId.value)
  refresh()
}

onMounted(() => {
  if (isApiAvailable()) refresh()
})
</script>
