<template>
  <n-space vertical :size="16">
    <n-h4 style="margin: 0">系统设置</n-h4>

    <n-card title="关于" size="small">
      <p>{{ appInfo.name }} v{{ appInfo.version }}</p>
      <p>按关键词检索视频 → 提取评论与用户 → 规则筛选 → 私信触达。</p>
    </n-card>

    <n-card title="AI 模型配置" size="small">
      <n-form label-placement="left" label-width="100" style="max-width: 560px">
        <n-form-item label="接口规范">
          <n-select
            v-model:value="aiSettings.ai_provider_type"
            :options="providerOptions"
            style="max-width: 280px"
          />
        </n-form-item>
        <n-form-item label="API Base URL">
          <n-input
            v-model:value="aiSettings.ai_endpoint"
            :placeholder="endpointPlaceholder"
          />
        </n-form-item>
        <n-form-item label="API Key">
          <n-input
            v-model:value="aiSettings.ai_api_key"
            type="password"
            show-password-on="click"
            placeholder="sk-***"
          />
        </n-form-item>
        <n-form-item label="模型名称">
          <n-input
            v-model:value="aiSettings.ai_model"
            :placeholder="modelPlaceholder"
          />
        </n-form-item>
        <n-button type="primary" size="small" :loading="aiSaving" @click="saveAiSettings">
          保存
        </n-button>
        <p style="color: #888; font-size: 12px; margin-top: 12px; line-height: 1.6;">
          常见配置参考：<br />
          • <b>DeepSeek</b>：规范 = OpenAI 兼容，Base URL = <code>https://api.deepseek.com/v1</code>，模型 = <code>deepseek-chat</code> / <code>deepseek-reasoner</code><br />
          • <b>OpenRouter</b>：规范 = OpenAI 兼容，Base URL = <code>https://openrouter.ai/api/v1</code>，模型如 <code>anthropic/claude-sonnet-4</code> / <code>deepseek/deepseek-chat</code><br />
          • <b>Anthropic 原生</b>：规范 = Anthropic，Base URL = <code>https://api.anthropic.com</code>，模型 = <code>claude-opus-4-7</code> 等
        </p>
      </n-form>
    </n-card>

    <n-card title="软件授权" size="small">
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
import { ref, reactive, computed, onMounted } from 'vue'
import {
  NCard,
  NSpace,
  NButton,
  NTag,
  NH4,
  NForm,
  NFormItem,
  NInput,
  NSelect,
  NDescriptions,
  NDescriptionsItem,
  NPopconfirm,
  useMessage,
} from 'naive-ui'
import { bridge, isApiAvailable } from '@/api/bridge'

type ProviderType = 'openai' | 'anthropic'

const providerOptions = [
  { label: 'OpenAI 兼容（DeepSeek / OpenRouter / Ollama 等）', value: 'openai' },
  { label: 'Anthropic 原生（Claude）', value: 'anthropic' },
]

const PROVIDER_HINTS: Record<ProviderType, { endpoint: string; model: string }> = {
  openai: { endpoint: 'https://api.deepseek.com/v1', model: 'deepseek-chat' },
  anthropic: { endpoint: 'https://api.anthropic.com', model: 'claude-opus-4-7' },
}

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
const appInfo = ref<{ version: string; name: string }>({ version: '0.0.0', name: '抖音助手' })
const licenseInfo = ref<LicenseInfo | null>(null)
const deactivating = ref(false)

const aiSettings = reactive<{
  ai_provider_type: ProviderType
  ai_endpoint: string
  ai_api_key: string
  ai_model: string
}>({
  ai_provider_type: 'openai',
  ai_endpoint: '',
  ai_api_key: '',
  ai_model: '',
})
const aiSaving = ref(false)

const endpointPlaceholder = computed(
  () => PROVIDER_HINTS[aiSettings.ai_provider_type].endpoint,
)
const modelPlaceholder = computed(
  () => PROVIDER_HINTS[aiSettings.ai_provider_type].model,
)

async function loadAiSettings() {
  try {
    const s = await bridge.get_settings()
    const t = String(s.ai_provider_type ?? 'openai')
    aiSettings.ai_provider_type = (t === 'anthropic' ? 'anthropic' : 'openai')
    aiSettings.ai_endpoint = String(s.ai_endpoint ?? '')
    aiSettings.ai_api_key = String(s.ai_api_key ?? '')
    aiSettings.ai_model = String(s.ai_model ?? '')
  } catch (e) {
    console.error(e)
  }
}

async function saveAiSettings() {
  aiSaving.value = true
  try {
    await bridge.update_settings({
      ai_provider_type: aiSettings.ai_provider_type,
      ai_endpoint: aiSettings.ai_endpoint.trim(),
      ai_api_key: aiSettings.ai_api_key,
      ai_model: aiSettings.ai_model.trim(),
    })
    message.success('AI 配置已保存')
  } catch (e: any) {
    message.error('保存失败：' + (e?.message ?? e))
  } finally {
    aiSaving.value = false
  }
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleString('zh-CN', { hour12: false })
  } catch {
    return iso
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

onMounted(async () => {
  const ok = await isApiAvailable()
  if (ok) {
    await Promise.all([loadAppInfo(), loadLicenseInfo(), loadAiSettings()])
  } else {
    message.error('无法连接到后端服务器')
  }
})
</script>
