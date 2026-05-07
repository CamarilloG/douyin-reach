/**
 * 前端调用后端 API 的封装（pywebview bridge 模式）
 * 通过 window.pywebview.api.xxx() 直接调用 Python 后端方法
 */

/** 设置结构 */
export interface Settings {
  cdp_url?: string
  cdp_enabled?: boolean
  browser_path?: string
  send_interval: number
  daily_limit: number
  risk_warning_pause: number
  risk_danger_stop?: boolean
  linear_collection?: boolean
  ai_api_key: string
  ai_endpoint: string
  ai_model: string
}

const DEFAULT_SETTINGS: Settings = {
  cdp_url: '',
  cdp_enabled: false,
  browser_path: '',
  send_interval: 30,
  daily_limit: 100,
  risk_warning_pause: 600,
  ai_api_key: '',
  ai_endpoint: 'https://api.openai.com/v1',
  ai_model: 'gpt-4',
}

/**
 * 调用 pywebview bridge 方法，带错误处理
 */
async function call<T>(method: string, ...args: any[]): Promise<T> {
  if (!window.pywebview?.api) {
    throw new Error('pywebview API 未就绪，请确保在桌面应用中运行')
  }
  const api = window.pywebview.api as unknown as Record<string, (...args: any[]) => any>
  const fn = api[method]
  if (typeof fn !== 'function') {
    throw new Error(`后端未实现方法: ${method}`)
  }
  return await fn(...args)
}

/**
 * 安全调用：出错时返回 fallback 值而非抛异常
 */
async function callSafe<T>(method: string, fallback: T, ...args: any[]): Promise<T> {
  try {
    return await call<T>(method, ...args)
  } catch (e) {
    console.warn(`bridge.${method} 调用失败:`, e)
    return fallback
  }
}

async function waitForPywebviewApi(timeoutMs: number = 5000): Promise<boolean> {
  if (window.pywebview?.api) {
    return true
  }

  return await new Promise<boolean>((resolve) => {
    let settled = false

    const finish = (value: boolean) => {
      if (settled) return
      settled = true
      window.removeEventListener('pywebviewready', onReady)
      clearTimeout(timer)
      resolve(value)
    }

    const onReady = () => finish(!!window.pywebview?.api)
    const timer = window.setTimeout(() => finish(!!window.pywebview?.api), timeoutMs)

    window.addEventListener('pywebviewready', onReady, { once: true })
  })
}

export const bridge = {
  // ==================== 任务管理 ====================

  get_tasks: () => callSafe('get_tasks', [] as any[]),

  get_task: (task_id: number) => callSafe('get_task', null, task_id),

  create_task: async (data: Record<string, unknown>) => {
    const result = await call<Record<string, unknown>>('create_task', data)
    return result?.id ?? result
  },

  update_task: (task_id: number, data: Record<string, unknown>) =>
    callSafe('update_task', null, task_id, data),

  delete_task: (task_id: number) => callSafe('delete_task', false, task_id),

  // ==================== 采集控制 ====================

  start_collection: (task_id: number) =>
    callSafe('start_collection', false, task_id),

  pause_collection: (task_id: number) =>
    callSafe('pause_collection', false, task_id),

  stop_collection: (task_id: number) =>
    callSafe('stop_collection', false, task_id),

  get_collection_progress: (task_id: number) =>
    callSafe('get_collection_progress', null, task_id),

  get_logs: (task_id: number, limit: number = 100) =>
    callSafe('get_logs', [] as any[], task_id, limit),

  clear_logs: (task_id: number) =>
    callSafe('clear_logs', { ok: false, deleted: 0 }, task_id),

  // ==================== 筛选 ====================

  run_filter: (task_id: number) =>
    callSafe('run_filter', { ok: false, count: 0, error: '后端未响应' }, task_id),

  // ==================== 目标用户 ====================

  get_target_users: (
    task_id: number,
    page: number = 1,
    page_size: number = 20,
    send_status: string | null = null,
  ) =>
    callSafe(
      'get_target_users',
      { items: [], total: 0, page: 1, page_size: 20 },
      task_id,
      page,
      page_size,
      send_status,
    ),

  update_user_selection: (task_id: number, user_ids: number[], selected: boolean) =>
    callSafe('update_user_selection', false, task_id, user_ids, selected),

  export_target_users: (task_id: number, file_path: string) =>
    callSafe('export_target_users', '', task_id, file_path),

  // ==================== 私信发送 ====================

  start_sending: (task_id: number) =>
    callSafe<{ ok: boolean; error?: string }>(
      'start_sending',
      { ok: false, error: '后端未响应' },
      task_id,
    ),

  pause_sending: (task_id: number) =>
    callSafe('pause_sending', false, task_id),

  stop_sending: (task_id: number) =>
    callSafe('stop_sending', false, task_id),

  get_send_progress: (task_id: number) =>
    callSafe('get_send_progress', null, task_id),

  get_send_history: (
    task_id: number,
    page: number = 1,
    page_size: number = 20,
    status: string | null = null
  ) =>
    callSafe(
      'get_send_history',
      { items: [], total: 0, page: 1, page_size: 20 },
      task_id,
      page,
      page_size,
      status
    ),

  export_send_history: (task_id: number, file_path: string) =>
    callSafe('export_send_history', '', task_id, file_path),

  // ==================== 系统设置 ====================

  get_settings: async (): Promise<Settings> => {
    const settings = await callSafe('get_settings', DEFAULT_SETTINGS)
    return { ...DEFAULT_SETTINGS, ...settings }
  },

  update_settings: async (data: Record<string, unknown>): Promise<Settings> => {
    await callSafe('update_settings', DEFAULT_SETTINGS, data)
    return await bridge.get_settings()
  },

  // ==================== 任务执行历史 (M7) ====================

  get_task_executions: (
    task_id: number | null = null,
    page: number = 1,
    page_size: number = 20,
    start_date: string | null = null,
    end_date: string | null = null,
  ) =>
    callSafe(
      'get_task_executions',
      { items: [] as any[], total: 0, page: 1, page_size: 20 },
      task_id,
      page,
      page_size,
      start_date,
      end_date,
    ),

  delete_task_execution: (exec_id: number) =>
    callSafe('delete_task_execution', false, exec_id),

  // ==================== 任务复制 ====================

  duplicate_task: (task_id: number) =>
    callSafe('duplicate_task', null, task_id),

  // ==================== 任务表单模板 ====================

  save_task_template: (name: string, payload: Record<string, unknown>) =>
    callSafe('save_task_template', 0, name, payload),

  list_task_templates: () =>
    callSafe('list_task_templates', [] as Array<{ id: number; name: string; created_at: string }>),

  load_task_template: (template_id: number) =>
    callSafe(
      'load_task_template',
      null as null | { id: number; name: string; payload: Record<string, unknown> },
      template_id,
    ),

  delete_task_template: (template_id: number) =>
    callSafe('delete_task_template', false, template_id),

  // ==================== 应用版本 ====================

  get_app_version: () =>
    callSafe('get_app_version', { version: '0.0.0', name: '抖音助手' }),

  // ==================== 商业授权 ====================

  get_license_info: () =>
    callSafe('get_license_info', {
      valid: false,
      reason_code: 'unavailable',
      reason_message: '后端不可用',
      fingerprint: '',
    } as
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
        }),

  activate_license: (token: string) =>
    callSafe(
      'activate_license',
      { ok: false, error_code: 'unavailable', error_message: '后端不可用' } as
        | { ok: true; info: any }
        | { ok: false; error_code: string; error_message: string },
      token,
    ),

  pick_license_file: () =>
    callSafe(
      'pick_license_file',
      { ok: false, error: '后端不可用' } as
        | { ok: true; content: string; path: string }
        | { ok: false; error: string },
    ),

  deactivate_license: () =>
    callSafe(
      'deactivate_license',
      { ok: false, error: '后端不可用' } as
        | { ok: true }
        | { ok: false; error: string },
    ),
}

/**
 * 检查 pywebview API 是否可用
 */
export async function isApiAvailable(): Promise<boolean> {
  return await waitForPywebviewApi()
}
