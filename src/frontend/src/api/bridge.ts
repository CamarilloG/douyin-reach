/**
 * 前端调用后端 API 的封装。
 * 在 pywebview 环境中使用 window.pywebview.api，否则可降级为 mock 或报错。
 */
declare const window: Window & { pywebview?: { api: Record<string, (...args: unknown[]) => Promise<unknown>> } }

function getApi() {
  if (typeof window !== 'undefined' && window.pywebview?.api) {
    return window.pywebview.api
  }
  return null
}

const api = getApi()

export const bridge = api
  ? {
      get_tasks: () => api.get_tasks() as Promise<unknown[]>,
      get_task: (task_id: number) => api.get_task(task_id) as Promise<unknown | null>,
      create_task: (data: Record<string, unknown>) => api.create_task(data) as Promise<unknown>,
      update_task: (task_id: number, data: Record<string, unknown>) =>
        api.update_task(task_id, data) as Promise<unknown | null>,
      delete_task: (task_id: number) => api.delete_task(task_id) as Promise<boolean>,
      start_collection: (task_id: number) => api.start_collection(task_id) as Promise<boolean>,
      pause_collection: (task_id: number) => api.pause_collection(task_id) as Promise<boolean>,
      stop_collection: (task_id: number) => api.stop_collection(task_id) as Promise<boolean>,
      get_collection_progress: (task_id: number) =>
        api.get_collection_progress(task_id) as Promise<unknown | null>,
      get_logs: (task_id: number, limit?: number) =>
        api.get_logs(task_id, limit) as Promise<unknown[]>,
      run_filter: (task_id: number) => api.run_filter(task_id) as Promise<boolean>,
      get_target_users: (task_id: number, page?: number, page_size?: number) =>
        api.get_target_users(task_id, page, page_size) as Promise<{
          items: unknown[]
          total: number
          page: number
          page_size: number
        }>,
      update_user_selection: (task_id: number, user_ids: number[], selected: boolean) =>
        api.update_user_selection(task_id, user_ids, selected) as Promise<boolean>,
      export_target_users: (task_id: number, file_path: string) =>
        api.export_target_users(task_id, file_path) as Promise<string>,
      start_sending: (task_id: number) => api.start_sending(task_id) as Promise<boolean>,
      pause_sending: (task_id: number) => api.pause_sending(task_id) as Promise<boolean>,
      stop_sending: (task_id: number) => api.stop_sending(task_id) as Promise<boolean>,
      get_send_progress: (task_id: number) =>
        api.get_send_progress(task_id) as Promise<unknown | null>,
      get_send_history: (
        task_id: number,
        page?: number,
        page_size?: number,
        status?: string | null
      ) =>
        api.get_send_history(task_id, page, page_size, status) as Promise<{
          items: unknown[]
          total: number
          page: number
          page_size: number
        }>,
      export_send_history: (task_id: number, file_path: string) =>
        api.export_send_history(task_id, file_path) as Promise<string>,
      open_login_browser: () => api.open_login_browser() as Promise<boolean>,
      check_login_status: () =>
        api.check_login_status() as Promise<{
          logged_in: boolean
          username?: string | null
          expires_at?: string | null
        }>,
      get_settings: () => api.get_settings() as Promise<Record<string, unknown>>,
      update_settings: (data: Record<string, unknown>) =>
        api.update_settings(data) as Promise<Record<string, unknown>>,
    }
  : null

export function isApiAvailable(): boolean {
  return !!getApi()
}
