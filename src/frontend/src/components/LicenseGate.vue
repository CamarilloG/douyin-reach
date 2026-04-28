<template>
  <div class="license-gate-mask">
    <n-card class="license-gate-card" :bordered="false">
      <template #header>
        <div style="display: flex; align-items: center; gap: 8px; font-size: 18px;">
          <span>🔐</span>
          <span>软件授权激活</span>
        </div>
      </template>

      <n-alert :type="alertType" :show-icon="true" style="margin-bottom: 16px;">
        <div style="white-space: pre-line; font-size: 13px;">{{ reasonMessage }}</div>
      </n-alert>

      <div style="margin-bottom: 16px;">
        <div style="font-size: 12px; color: #888; margin-bottom: 6px;">本机指纹（请发给软件提供方以签发激活码）</div>
        <div style="display: flex; gap: 8px;">
          <n-input
            :value="fingerprint"
            readonly
            size="small"
            style="font-family: monospace;"
          />
          <n-button size="small" @click="copyFingerprint">📋 复制</n-button>
        </div>
      </div>

      <n-tabs v-model:value="mode" type="line" animated>
        <n-tab-pane name="paste" tab="粘贴激活码">
          <n-input
            v-model:value="tokenInput"
            type="textarea"
            :autosize="{ minRows: 6, maxRows: 12 }"
            placeholder="将软件提供方给你的激活码粘贴到这里（一长串 base64 字符串，或完整 JSON 内容）"
            style="font-family: monospace; font-size: 12px;"
          />
        </n-tab-pane>
        <n-tab-pane name="file" tab="选择文件">
          <n-space vertical>
            <n-button block @click="onPickFile">📁 选择 license.key 文件</n-button>
            <div v-if="pickedPath" style="font-size: 12px; color: #888;">
              已加载：{{ pickedPath }}
            </div>
            <n-input
              v-if="tokenInput"
              :value="tokenInput"
              type="textarea"
              :autosize="{ minRows: 4, maxRows: 8 }"
              readonly
              style="font-family: monospace; font-size: 11px; opacity: 0.7;"
            />
          </n-space>
        </n-tab-pane>
      </n-tabs>

      <div style="display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px;">
        <n-button @click="onClear" :disabled="!tokenInput">清空</n-button>
        <n-button
          type="primary"
          :loading="activating"
          :disabled="!tokenInput.trim() || activating"
          @click="onActivate"
        >
          激活
        </n-button>
      </div>

      <div style="margin-top: 16px; padding-top: 12px; border-top: 1px solid #2a2a2a; font-size: 11px; color: #666; line-height: 1.7;">
        激活码每 7 天一期，到期后请重新联系软件提供方续期。<br />
        激活码绑定本机指纹，不可在其他机器使用。
      </div>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  NCard,
  NInput,
  NButton,
  NSpace,
  NTabs,
  NTabPane,
  NAlert,
  useMessage,
} from 'naive-ui'
import { bridge } from '@/api/bridge'

const props = defineProps<{
  reasonCode: string
  reasonMessage: string
  fingerprint: string
}>()

const emit = defineEmits<{
  (e: 'activated'): void
}>()

const message = useMessage()
const mode = ref<'paste' | 'file'>('paste')
const tokenInput = ref('')
const pickedPath = ref('')
const activating = ref(false)

const alertType = computed<'warning' | 'error' | 'info'>(() => {
  if (props.reasonCode === 'expired') return 'warning'
  if (props.reasonCode === 'missing') return 'info'
  return 'error'
})

async function copyFingerprint() {
  try {
    await navigator.clipboard.writeText(props.fingerprint)
    message.success('已复制本机指纹')
  } catch {
    message.error('复制失败，请手动选择文本复制')
  }
}

async function onPickFile() {
  const r = await bridge.pick_license_file()
  if (!r.ok) {
    if (r.error !== '已取消') message.error(r.error)
    return
  }
  tokenInput.value = r.content
  pickedPath.value = r.path
}

function onClear() {
  tokenInput.value = ''
  pickedPath.value = ''
}

async function onActivate() {
  const token = tokenInput.value.trim()
  if (!token) return
  activating.value = true
  try {
    const r = await bridge.activate_license(token)
    if (r.ok) {
      message.success('激活成功')
      emit('activated')
    } else {
      message.error(r.error_message || '激活失败')
    }
  } catch (e) {
    console.error(e)
    message.error('激活失败：' + String(e))
  } finally {
    activating.value = false
  }
}
</script>

<style scoped>
.license-gate-mask {
  position: fixed;
  inset: 0;
  background: rgba(16, 16, 20, 0.92);
  backdrop-filter: blur(4px);
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px;
}
.license-gate-card {
  width: 560px;
  max-width: 100%;
  background: #1f1f23;
  border: 1px solid #2a2a2a;
  border-radius: 8px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.6);
}
</style>
