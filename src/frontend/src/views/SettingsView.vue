<template>
  <n-space vertical>
    <n-h4 style="margin: 0">系统设置</n-h4>
    <n-card title="账号" size="small">
      <n-space align="center">
        <n-tag :type="loginStatus?.logged_in ? 'success' : 'default'">
          {{ loginStatus?.logged_in ? '已登录' : '未登录' }}
        </n-tag>
        <span v-if="loginStatus?.username">{{ loginStatus.username }}</span>
        <n-button size="small" @click="openLogin">打开浏览器登录</n-button>
      </n-space>
    </n-card>
    <n-card title="全局默认" size="small">
      <n-form label-placement="left" label-width="120" style="max-width: 400px">
        <n-form-item label="发送间隔(秒)">
          <n-input-number v-model:value="settings.send_interval" :min="10" style="width: 100%" />
        </n-form-item>
        <n-form-item label="日上限">
          <n-input-number v-model:value="settings.daily_limit" :min="1" style="width: 100%" />
        </n-form-item>
        <n-form-item label="风控预警暂停(秒)">
          <n-input-number v-model:value="settings.risk_warning_pause" :min="60" style="width: 100%" />
        </n-form-item>
        <n-button type="primary" size="small" @click="saveSettings">保存</n-button>
      </n-form>
    </n-card>
    <n-card title="AI 配置（MVP 仅 UI）" size="small">
      <n-form label-placement="left" label-width="100" style="max-width: 480px">
        <n-form-item label="API Key">
          <n-input v-model:value="settings.ai_api_key" placeholder="sk-***" type="password" show-password-on="click" />
        </n-form-item>
        <n-form-item label="端点">
          <n-input v-model:value="settings.ai_endpoint" placeholder="https://api.openai.com/v1" />
        </n-form-item>
        <n-form-item label="模型">
          <n-input v-model:value="settings.ai_model" placeholder="gpt-4" />
        </n-form-item>
      </n-form>
    </n-card>
    <n-card title="关于" size="small">
      <p>抖音助手 Douyin Reach v0.1.0</p>
      <p>按关键词检索视频 → 提取评论与用户 → 规则筛选 → 私信触达。</p>
    </n-card>
  </n-space>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { NCard, NSpace, NButton, NTag, NForm, NFormItem, NInput, NInputNumber, NH4 } from 'naive-ui'
import { bridge, isApiAvailable } from '@/api/bridge'

const loginStatus = ref<{ logged_in: boolean; username?: string | null; expires_at?: string | null } | null>(null)
const settings = ref<{
  send_interval: number
  daily_limit: number
  risk_warning_pause: number
  ai_api_key: string
  ai_endpoint: string
  ai_model: string
}>({
  send_interval: 30,
  daily_limit: 100,
  risk_warning_pause: 600,
  ai_api_key: '',
  ai_endpoint: 'https://api.openai.com/v1',
  ai_model: 'gpt-4',
})

async function loadLogin() {
  if (!bridge) return
  loginStatus.value = await bridge.check_login_status()
}

async function loadSettings() {
  if (!bridge) return
  const raw = await bridge.get_settings()
  settings.value = {
    send_interval: Number(raw.send_interval) || 30,
    daily_limit: Number(raw.daily_limit) || 100,
    risk_warning_pause: Number(raw.risk_warning_pause) || 600,
    ai_api_key: String(raw.ai_api_key ?? ''),
    ai_endpoint: String(raw.ai_endpoint ?? ''),
    ai_model: String(raw.ai_model ?? ''),
  }
}

function openLogin() {
  bridge?.open_login_browser()
}

async function saveSettings() {
  if (!bridge) return
  await bridge.update_settings({
    send_interval: settings.value.send_interval,
    daily_limit: settings.value.daily_limit,
    risk_warning_pause: settings.value.risk_warning_pause,
    ai_api_key: settings.value.ai_api_key,
    ai_endpoint: settings.value.ai_endpoint,
    ai_model: settings.value.ai_model,
  })
}

onMounted(() => {
  if (isApiAvailable()) {
    loadLogin()
    loadSettings()
  }
})
</script>
