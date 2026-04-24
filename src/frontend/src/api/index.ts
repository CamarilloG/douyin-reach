/**
 * API 接口 — 统一通过 pywebview bridge 调用
 */
export { bridge, isApiAvailable } from './bridge'
export type { Settings } from './bridge'

// ==================== 类型定义 ====================

export interface Task {
  id: number
  name: string
  keywords: string[]
  rules: Record<string, any>
  message_template: string
  status: string
  created_at: string
  updated_at: string
}
