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
              <n-tooltip v-if="license" placement="bottom">
                <template #trigger>
                  <span
                    :style="licenseBadgeStyle"
                    style="font-size: 11px; padding: 1px 6px; border-radius: 3px; cursor: help;"
                  >
                    {{ badgeText }}
                  </span>
                </template>
                <div style="font-size: 12px; line-height: 1.7;">
                  <template v-if="license.valid">
                    <div>被授权方：{{ license.licensee }}</div>
                    <div>到期时间：{{ formatDate(license.expires_at) }}</div>
                    <div style="color: #888;">License ID：{{ license.license_id }}</div>
                    <div v-if="license.days_left <= 2" style="color: #ff7875; margin-top: 4px;">
                      ⚠ 即将到期，请联系软件提供方续期
                    </div>
                  </template>
                  <template v-else>
                    <div style="color: #ff7875;">软件未激活，主要功能不可用</div>
                  </template>
                </div>
              </n-tooltip>
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

      <LicenseGate
        v-if="license && !license.valid"
        :reason-code="license.reason_code"
        :reason-message="license.reason_message"
        :fingerprint="license.fingerprint"
        @activated="onActivated"
      />
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
  NTooltip,
  NMessageProvider,
  darkTheme,
} from 'naive-ui'
import { zhCN, dateZhCN } from 'naive-ui'
import { useTaskContext } from '@/stores/taskContext'
import { bridge, isApiAvailable } from '@/api/bridge'
import LicenseGate from '@/components/LicenseGate.vue'

type LicenseValid = {
  valid: true
  licensee: string
  license_id: string
  fingerprint: string
  issued_at: string
  expires_at: string
  days_left: number
  expired: boolean
}
type LicenseInvalid = {
  valid: false
  reason_code: string
  reason_message: string
  fingerprint: string
}
type LicenseState = LicenseValid | LicenseInvalid

const router = useRouter()
const route = useRoute()
const taskCtx = useTaskContext()
const appInfo = ref<{ version: string; name: string }>({ version: '', name: '抖音助手' })
const license = ref<LicenseState | null>(null)

const currentTaskName = computed(() => {
  const t = taskCtx.tasks.find((x) => x.id === taskCtx.currentTaskId)
  return t?.name || ''
})

const badgeText = computed(() => {
  const l = license.value
  if (!l) return ''
  if (l.valid) return `📜 授权剩余 ${l.days_left} 天`
  return '⚠ 未激活'
})

const licenseBadgeStyle = computed(() => {
  const l = license.value
  if (!l) return {}
  if (!l.valid) {
    return {
      color: '#ff7875',
      border: '1px solid #ff7875',
      fontWeight: 600,
    }
  }
  if (l.expired || l.days_left <= 2) {
    return {
      color: '#ff7875',
      border: '1px solid #ff7875',
      fontWeight: 600,
    }
  }
  return {
    color: '#63e2b7',
    border: '1px solid #2c5d4d',
  }
})

function formatDate(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleString('zh-CN', { hour12: false })
  } catch {
    return iso
  }
}

function onTabChange(key: string) {
  router.push(key)
}

async function refreshLicense() {
  try {
    license.value = (await bridge.get_license_info()) as LicenseState
  } catch (e) {
    console.warn('获取授权信息失败', e)
  }
}

async function onActivated() {
  await refreshLicense()
  // 激活成功后刷新任务上下文，让首屏数据可用
  taskCtx.refresh()
}

onMounted(async () => {
  taskCtx.refresh()
  if (await isApiAvailable()) {
    try {
      appInfo.value = await bridge.get_app_version()
    } catch (e) {
      console.warn('获取版本失败', e)
    }
    await refreshLicense()
  }
})
</script>
