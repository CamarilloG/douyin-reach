<template>
  <n-config-provider :theme="darkTheme" :locale="zhCN" :date-locale="dateZhCN">
    <n-message-provider>
      <n-layout has-sider style="height: 100vh">
        <n-layout-sider
          bordered
          collapse-mode="width"
          :collapsed-width="64"
          :width="200"
          show-trigger
          content-style="padding: 16px;"
        >
          <n-menu
            :options="menuOptions"
            :value="currentRoute"
            @update:value="onMenuSelect"
          />
        </n-layout-sider>
        <n-layout>
          <n-layout-header bordered style="padding: 12px 20px; font-size: 18px;">
            抖音助手
          </n-layout-header>
          <n-layout-content content-style="padding: 20px;" :native-scrollbar="false">
            <router-view v-slot="{ Component }">
              <component :is="Component" />
            </router-view>
          </n-layout-content>
        </n-layout>
      </n-layout>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { h, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import {
  NConfigProvider,
  NLayout,
  NLayoutSider,
  NLayoutHeader,
  NLayoutContent,
  NMenu,
  NMessageProvider,
  darkTheme,
  type MenuOption,
} from 'naive-ui'
import { zhCN, dateZhCN } from 'naive-ui'

const router = useRouter()
const route = useRoute()

const menuOptions: MenuOption[] = [
  { label: '任务管理', key: '/tasks', icon: () => h('span', '📋') },
  { label: '采集监控', key: '/collect', icon: () => h('span', '📥') },
  { label: '名单审核', key: '/audit', icon: () => h('span', '📝') },
  { label: '发送控制', key: '/send', icon: () => h('span', '✉️') },
  { label: '历史记录', key: '/history', icon: () => h('span', '📜') },
  { label: '系统设置', key: '/settings', icon: () => h('span', '⚙️') },
]

const currentRoute = computed(() => route.path)

function onMenuSelect(key: string) {
  router.push(key)
}
</script>
