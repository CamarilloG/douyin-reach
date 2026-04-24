<template>
  <n-config-provider :theme="darkTheme" :locale="zhCN" :date-locale="dateZhCN">
    <n-message-provider>
      <n-layout style="height: 100vh">
        <n-layout-header bordered style="padding: 8px 20px;">
          <div style="display: flex; align-items: center; justify-content: space-between;">
            <div style="display: flex; align-items: center; gap: 12px;">
              <img src="/app-icon.ico" alt="" style="width: 24px; height: 24px;" />
              <span style="font-size: 18px; font-weight: 600;">{{ appInfo.name }}</span>
              <span style="font-size: 11px; color: #888; padding: 1px 6px; border: 1px solid #444; border-radius: 3px;">
                v{{ appInfo.version }}
              </span>
              <n-tabs
                type="line"
                size="medium"
                :value="route.path"
                @update:value="onTabChange"
                style="margin-bottom: -8px;"
              >
                <n-tab-pane name="/tasks" tab="任务管理" />
                <n-tab-pane name="/collect" tab="进程监控" />
                <n-tab-pane name="/audit" tab="采集明细" />
                <n-tab-pane name="/send" tab="私信发送" />
                <n-tab-pane name="/history" tab="历史记录" />
                <n-tab-pane name="/settings" tab="系统设置" />
              </n-tabs>
            </div>
            <div style="display: flex; align-items: center; gap: 12px; font-size: 12px; color: #888;">
              <span v-if="currentTaskName">当前任务：{{ currentTaskName }}</span>
            </div>
          </div>
        </n-layout-header>
        <n-layout-content content-style="padding: 20px;" :native-scrollbar="false">
          <router-view v-slot="{ Component }">
            <component :is="Component" />
          </router-view>
        </n-layout-content>
      </n-layout>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import {
  NConfigProvider,
  NLayout,
  NLayoutHeader,
  NLayoutContent,
  NTabs,
  NTabPane,
  NMessageProvider,
  darkTheme,
} from 'naive-ui'
import { zhCN, dateZhCN } from 'naive-ui'
import { useTaskContext } from '@/stores/taskContext'
import { bridge, isApiAvailable } from '@/api/bridge'

const router = useRouter()
const route = useRoute()
const taskCtx = useTaskContext()
const appInfo = ref<{ version: string; name: string }>({ version: '', name: '抖音助手' })

const currentTaskName = computed(() => {
  const t = taskCtx.tasks.find((x) => x.id === taskCtx.currentTaskId)
  return t?.name || ''
})

function onTabChange(key: string) {
  router.push(key)
}

onMounted(async () => {
  taskCtx.refresh()
  if (await isApiAvailable()) {
    try {
      appInfo.value = await bridge.get_app_version()
    } catch (e) {
      console.warn('获取版本失败', e)
    }
  }
})
</script>
