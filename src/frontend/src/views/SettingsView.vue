<template>
  <n-space vertical :size="16">
    <n-h4 style="margin: 0">系统设置</n-h4>

    <n-card title="浏览器配置" size="small">
      <n-form label-placement="left" label-width="120" style="max-width: 640px">
        <n-form-item label="浏览器路径">
          <n-input v-model:value="settings.browser_path" placeholder="留空使用 Playwright 内置浏览器；或填 chrome.exe 完整路径" />
        </n-form-item>
        <n-form-item label="CDP URL">
          <n-input v-model:value="settings.cdp_url" placeholder="如 http://127.0.0.1:9222（接管已开启的 Chrome）" />
        </n-form-item>
        <n-form-item label="启用 CDP 接管">
          <n-switch v-model:value="settings.cdp_enabled" />
        </n-form-item>
        <n-button type="primary" size="small" @click="saveSettings">保存</n-button>
      </n-form>
    </n-card>

    <n-card title="登录状态" size="small">
      <n-space align="center">
        <n-tag :type="loginStatus?.logged_in ? 'success' : 'default'">
          {{ loginStatus?.logged_in ? '已登录' : '未登录' }}
        </n-tag>
        <span v-if="loginStatus?.username">{{ loginStatus.username }}</span>
        <span v-if="loginStatus?.expires_at" style="color: #888; font-size: 12px;">
          过期：{{ loginStatus.expires_at }}
        </span>
        <n-button size="small" @click="openLogin">打开浏览器登录</n-button>
        <n-button size="small" @click="loadLogin">刷新状态</n-button>
      </n-space>
    </n-card>

    <n-card title="任务默认参数" size="small">
      <n-form label-placement="left" label-width="140" style="max-width: 480px">
        <n-form-item label="发送间隔(秒)">
          <n-input-number v-model:value="settings.send_interval" :min="1" style="width: 100%" />
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
      <p>{{ appInfo.name }} v{{ appInfo.version }}</p>
      <p>按关键词检索视频 → 提取评论与用户 → 规则筛选 → 私信触达。</p>
      <p style="color: #888; font-size: 12px;">
        项目仓库：<a href="https://github.com/CamarilloG/douyin_ass" target="_blank" style="color: #63e2b7;">CamarilloG/douyin_ass</a>
      </p>
    </n-card>

    <n-card title="商业授权" size="small">
      <div v-if="licenseInfo && licenseInfo.valid">
        <n-descriptions :column="1" size="small" label-placement="left" bordered>
          <n-descriptions-item label="被授权方">
            {{ licenseInfo.licensee }}
          </n-descriptions-item>
          <n-descriptions-item label="状态">
            <n-tag
              :type="licenseInfo.expired ? 'error' : licenseInfo.days_left <= 2 ? 'warning' : 'success'"
              size="small"
            >
              {{ licenseInfo.expired
                  ? '已过期'
                  : licenseInfo.days_left <= 2
                    ? `即将过期（剩余 ${licenseInfo.days_left} 天）`
                    : `有效（剩余 ${licenseInfo.days_left} 天）` }}
            </n-tag>
          </n-descriptions-item>
          <n-descriptions-item label="签发时间">
            {{ formatDate(licenseInfo.issued_at) }}
          </n-descriptions-item>
          <n-descriptions-item label="过期时间">
            {{ formatDate(licenseInfo.expires_at) }}
          </n-descriptions-item>
          <n-descriptions-item label="License ID">
            <code style="font-size: 11px; color: #888;">{{ licenseInfo.license_id }}</code>
          </n-descriptions-item>
          <n-descriptions-item label="本机指纹">
            <code style="font-size: 11px; color: #888;">{{ licenseInfo.fingerprint }}</code>
          </n-descriptions-item>
        </n-descriptions>
        <p style="color: #888; font-size: 12px; margin-top: 12px;">
          续期：联系软件提供方，提供上方"本机指纹"，签发方会发回新的激活码或 license.key 文件；点下方「退出当前授权」后即可在激活蒙版中粘贴新激活码。
        </p>
        <div style="margin-top: 12px;">
          <n-popconfirm
            :positive-button-props="{ type: 'error' }"
            positive-text="确认退出"
            negative-text="取消"
            @positive-click="onDeactivate"
          >
            <template #trigger>
              <n-button size="small" type="error" ghost :loading="deactivating">
                🚪 退出当前授权
              </n-button>
            </template>
            <div style="max-width: 320px;">
              确认要退出当前授权吗？<br />
              退出后软件主要功能将不可用，需要重新激活。<br />
              <span style="color: #888; font-size: 11px;">（适用于：续期 / 换激活码 / 切换被授权方）</span>
            </div>
          </n-popconfirm>
        </div>
      </div>
      <div v-else-if="licenseInfo">
        <n-tag type="error" size="small">未激活</n-tag>
        <p style="color: #888; font-size: 12px; margin-top: 8px;">{{ licenseInfo.reason_message }}</p>
        <p style="color: #888; font-size: 12px;">本机指纹：<code>{{ licenseInfo.fingerprint }}</code></p>
      </div>
      <p v-else style="color: #888; font-size: 12px;">
        授权信息加载中...
      </p>
    </n-card>
  </n-space>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import {
  NCard,
  NSpace,
  NButton,
  NTag,
  NForm,
  NFormItem,
  NInput,
  NInputNumber,
  NSwitch,
  NH4,
  NDescriptions,
  NDescriptionsItem,
  NPopconfirm,
  useMessage,
} from 'naive-ui'
import { bridge, isApiAvailable } from '@/api/bridge'

type LicenseInfo =
  | {
      valid: true
      licensee: string
      license_id: string
      fingerprint: string
      issued_at: string
      expires_at: string
      days_left: number
      expired: boolean
    }
  | {
      valid: false
      reason_code: string
      reason_message: string
      fingerprint: string
    }

const message = useMessage()
const loginStatus = ref<{ logged_in: boolean; username?: string | null; expires_at?: string | null } | null>(null)
const appInfo = ref<{ version: string; name: string }>({ version: '0.0.0', name: '抖音助手' })
const licenseInfo = ref<LicenseInfo | null>(null)
const deactivating = ref(false)

function formatDate(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleString('zh-CN', { hour12: false })
  } catch {
    return iso
  }
}
const settings = reactive({
  browser_path: '',
  cdp_url: '',
  cdp_enabled: false,
  send_interval: 30,
  daily_limit: 100,
  risk_warning_pause: 600,
  ai_api_key: '',
  ai_endpoint: 'https://api.openai.com/v1',
  ai_model: 'gpt-4',
})

async function loadLogin() {
  try {
    loginStatus.value = await bridge.check_login_status()
  } catch (e) {
    console.error(e)
  }
}

async function loadSettings() {
  try {
    const raw = await bridge.get_settings()
    settings.browser_path = String(raw.browser_path ?? '')
    settings.cdp_url = String(raw.cdp_url ?? '')
    settings.cdp_enabled = Boolean(raw.cdp_enabled)
    settings.send_interval = Number(raw.send_interval) || 30
    settings.daily_limit = Number(raw.daily_limit) || 100
    settings.risk_warning_pause = Number(raw.risk_warning_pause) || 600
    settings.ai_api_key = String(raw.ai_api_key ?? '')
    settings.ai_endpoint = String(raw.ai_endpoint ?? '')
    settings.ai_model = String(raw.ai_model ?? '')
  } catch (e) {
    console.error(e); message.error('加载设置失败')
  }
}

async function loadAppInfo() {
  try {
    appInfo.value = await bridge.get_app_version()
  } catch (e) {
    console.error(e)
  }
}

async function loadLicenseInfo() {
  try {
    licenseInfo.value = (await bridge.get_license_info()) as LicenseInfo
  } catch (e) {
    console.error(e)
  }
}

async function onDeactivate() {
  deactivating.value = true
  try {
    const r = await bridge.deactivate_license()
    if (!r.ok) {
      message.error(r.error || '退出授权失败')
      return
    }
    message.success('已退出授权，正在重新加载...')
    // 重载页面，App.vue 会重新拉取授权状态、自动弹出激活蒙版
    setTimeout(() => window.location.reload(), 600)
  } finally {
    deactivating.value = false
  }
}

async function openLogin() {
  try {
    await bridge.open_login_browser()
    message.success('浏览器已启动，请登录抖音')
  } catch (e) {
    console.error(e); message.error('启动浏览器失败')
  }
}

async function saveSettings() {
  try {
    await bridge.update_settings({ ...settings })
    message.success('设置已保存')
  } catch (e) {
    console.error(e); message.error('保存设置失败')
  }
}

onMounted(async () => {
  const ok = await isApiAvailable()
  if (ok) {
    await Promise.all([loadLogin(), loadSettings(), loadAppInfo(), loadLicenseInfo()])
  } else {
    message.error('无法连接到后端服务器')
  }
})
</script>
