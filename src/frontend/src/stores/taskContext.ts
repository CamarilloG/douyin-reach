/**
 * 全局任务上下文 store
 * 进程监控 / 采集明细 / 私信发送 / 历史记录 共享"当前选中任务"，
 * 避免每个 view 各自维护一份 task 列表与选中态。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { bridge } from '@/api/bridge'

export interface TaskBrief {
  id: number
  name: string
  status: string
  keywords?: string[]
  [k: string]: unknown
}

export const useTaskContext = defineStore('taskContext', () => {
  const currentTaskId = ref<number | null>(null)
  const tasks = ref<TaskBrief[]>([])
  const loading = ref(false)

  async function refresh() {
    loading.value = true
    try {
      const list = (await bridge.get_tasks()) as TaskBrief[]
      tasks.value = Array.isArray(list) ? list : []
      // 默认选第一个；当前选中已不存在时回退到第一个
      if (tasks.value.length > 0) {
        if (currentTaskId.value == null || !tasks.value.find((t) => t.id === currentTaskId.value)) {
          currentTaskId.value = tasks.value[0].id
        }
      } else {
        currentTaskId.value = null
      }
    } finally {
      loading.value = false
    }
  }

  function selectTask(id: number | null) {
    currentTaskId.value = id
  }

  return { currentTaskId, tasks, loading, refresh, selectTask }
})
