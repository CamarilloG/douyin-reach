<template>
  <n-space vertical :size="16">
    <n-h4 style="margin: 0">私信发送</n-h4>

    <n-space align="center">
      <n-select
        v-model:value="taskId"
        :options="taskOptions"
        placeholder="选择任务"
        style="width: 240px"
        @update:value="onTaskChange"
      />
      <n-button v-if="taskId" type="primary" size="small" @click="start">启动发送</n-button>
      <n-button v-if="taskId" size="small" @click="pause">暂停</n-button>
      <n-button v-if="taskId" size="small" @click="stop">停止</n-button>
    </n-space>

    <n-card title="发送进度" size="small">
      <n-grid :cols="5" :x-gap="16">
        <n-gi><n-statistic label="待发" :value="progress?.pending ?? 0" /></n-gi>
        <n-gi><n-statistic label="发送中" :value="progress?.sending ?? 0" /></n-gi>
        <n-gi><n-statistic label="成功" :value="progress?.success ?? 0" /></n-gi>
        <n-gi><n-statistic label="失败" :value="progress?.failed ?? 0" /></n-gi>
        <n-gi><n-statistic label="跳过" :value="progress?.skipped ?? 0" /></n-gi>
      </n-grid>
    </n-card>

    <n-card title="发送参数" size="small" v-if="taskId">
      <n-form :model="params" label-placement="left" label-width="100" size="small">
        <n-grid :cols="3" :x-gap="12">
          <n-gi>
            <n-form-item label="发送间隔(秒)">
              <n-input-number v-model:value="params.send_interval" :min="1" style="width: 100%" />
            </n-form-item>
          </n-gi>
          <n-gi>
            <n-form-item label="日上限">
              <n-input-number v-model:value="params.daily_limit" :min="1" style="width: 100%" />
            </n-form-item>
          </n-gi>
          <n-gi>
            <n-form-item label="失败重试">
              <n-input-number v-model:value="params.retry_limit" :min="0" :max="10" style="width: 100%" />
            </n-form-item>
          </n-gi>
        </n-grid>
      </n-form>
    </n-card>

    <n-card title="私信模板（多条轮询）" size="small" v-if="taskId">
      <template #header-extra>
        <n-button size="small" type="primary" :loading="saving" @click="() => saveTemplate(false)">保存模板</n-button>
      </template>
      <n-dynamic-input
        v-model:value="templates"
        :min="1"
        #="{ value, index }"
      >
        <n-input
          :value="value"
          type="textarea"
          :rows="3"
          placeholder="一条消息原文,多条则按用户顺序轮询发送"
          @update:value="(v: string) => (templates[index] = v)"
        />
      </n-dynamic-input>
      <n-text depth="3" style="font-size: 12px; display: block; margin-top: 8px;">
        模板原文即最终发送内容,不再支持占位符;如需多种话术,直接添加多条,系统会按用户顺序轮询发送。
      </n-text>
    </n-card>
  </n-space>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, reactive, watch } from 'vue'
import {
  NCard, NSpace, NButton, NStatistic, NGrid, NGi, NSelect, NH4,
  NDynamicInput, NInput, NInputNumber, NForm, NFormItem, NText,
  useMessage,
} from 'naive-ui'
import { bridge, isApiAvailable } from '@/api/bridge'
import { useTaskContext } from '@/stores/taskContext'
import { storeToRefs } from 'pinia'

const message = useMessage()
const taskCtx = useTaskContext()
const { currentTaskId: taskId } = storeToRefs(taskCtx)
const taskOptions = ref<{ label: string; value: number }[]>([])
const progress = ref<{ pending?: number; sending?: number; success?: number; failed?: number; skipped?: number } | null>(null)
const templates = ref<string[]>([''])
const saving = ref(false)
const params = reactive({
  send_interval: 30,
  daily_limit: 100,
  retry_limit: 2,
})
let pollTimer: ReturnType<typeof setInterval> | null = null

async function loadTasks() {
  await taskCtx.refresh()
  const list = taskCtx.tasks as { id: number; name: string }[]
  taskOptions.value = list.map((t) => ({ label: `${t.name} (#${t.id})`, value: t.id }))
  if (list.length && taskId.value == null) taskCtx.selectTask(list[0].id)
}

async function loadTaskDetail() {
  if (taskId.value == null) return
  try {
    const t = (await bridge.get_task(taskId.value)) as Record<string, any> | null
    if (!t) return
    templates.value = Array.isArray(t.template) && t.template.length ? (t.template as string[]) : ['']
    params.send_interval = Number(t.send_interval) || 30
    params.daily_limit = Number(t.daily_limit) || 100
    params.retry_limit = Number(t.retry_limit ?? 2)
  } catch (e) {
    console.error(e)
  }
}

async function refresh() {
  if (taskId.value == null) return
  try {
    const p = await bridge.get_send_progress(taskId.value)
    progress.value = p as any
  } catch (e) {
    console.error(e)
  }
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(refresh, 2000)
}
function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

async function onTaskChange() {
  await Promise.all([refresh(), loadTaskDetail()])
  const s = progress.value?.sending
  if (s && s > 0) startPolling(); else stopPolling()
}

async function start() {
  if (taskId.value == null) return
  // 启动前先把模板与参数同步保存
  await saveTemplate(true)
  const res = await bridge.start_sending(taskId.value)
  if (!res?.ok) {
    message.error(res?.error || '启动发送失败')
    return
  }
  message.success('已启动发送')
  await refresh()
  startPolling()
}

async function pause() {
  if (taskId.value == null) return
  await bridge.pause_sending(taskId.value)
  await refresh()
}

async function stop() {
  if (taskId.value == null) return
  await bridge.stop_sending(taskId.value)
  await refresh()
  stopPolling()
}

async function saveTemplate(silent: boolean = false) {
  if (taskId.value == null) return
  saving.value = true
  try {
    await bridge.update_task(taskId.value, {
      template: templates.value.filter((s) => s && s.trim()),
      send_interval: params.send_interval,
      daily_limit: params.daily_limit,
      retry_limit: params.retry_limit,
    })
    if (!silent) message.success('已保存')
  } catch (e) {
    console.error(e)
    if (!silent) message.error('保存失败')
  } finally {
    saving.value = false
  }
}

watch(taskId, () => {
  void loadTaskDetail()
})

onMounted(async () => {
  if (await isApiAvailable()) {
    await loadTasks()
    if (taskId.value) {
      await Promise.all([refresh(), loadTaskDetail()])
      const s = progress.value?.sending
      if (s && s > 0) startPolling()
    }
  }
})

onUnmounted(() => stopPolling())
</script>
