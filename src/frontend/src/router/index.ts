import { createRouter, createWebHashHistory } from 'vue-router'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/tasks' },
    { path: '/tasks', name: 'Tasks', component: () => import('@/views/TasksView.vue'), meta: { title: '任务管理' } },
    { path: '/collect', name: 'Collect', component: () => import('@/views/CollectView.vue'), meta: { title: '采集监控' } },
    { path: '/audit', name: 'Audit', component: () => import('@/views/AuditView.vue'), meta: { title: '名单审核' } },
    { path: '/send', name: 'Send', component: () => import('@/views/SendView.vue'), meta: { title: '发送控制' } },
    { path: '/history', name: 'History', component: () => import('@/views/HistoryView.vue'), meta: { title: '历史记录' } },
    { path: '/settings', name: 'Settings', component: () => import('@/views/SettingsView.vue'), meta: { title: '系统设置' } },
  ],
})

export default router
