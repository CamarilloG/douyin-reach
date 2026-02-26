/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}

interface PyWebViewApi {
  get_tasks: () => Promise<unknown[]>
  get_task: (task_id: number) => Promise<unknown | null>
  create_task: (data: Record<string, unknown>) => Promise<unknown>
  update_task: (task_id: number, data: Record<string, unknown>) => Promise<unknown | null>
  delete_task: (task_id: number) => Promise<boolean>
  start_collection: (task_id: number) => Promise<boolean>
  pause_collection: (task_id: number) => Promise<boolean>
  stop_collection: (task_id: number) => Promise<boolean>
  get_collection_progress: (task_id: number) => Promise<unknown | null>
  get_logs: (task_id: number, limit?: number) => Promise<unknown[]>
  run_filter: (task_id: number) => Promise<boolean>
  get_target_users: (task_id: number, page?: number, page_size?: number) => Promise<{ items: unknown[]; total: number; page: number; page_size: number }>
  update_user_selection: (task_id: number, user_ids: number[], selected: boolean) => Promise<boolean>
  export_target_users: (task_id: number, file_path: string) => Promise<string>
  start_sending: (task_id: number) => Promise<boolean>
  pause_sending: (task_id: number) => Promise<boolean>
  stop_sending: (task_id: number) => Promise<boolean>
  get_send_progress: (task_id: number) => Promise<unknown | null>
  get_send_history: (task_id: number, page?: number, page_size?: number, status?: string | null) => Promise<{ items: unknown[]; total: number; page: number; page_size: number }>
  export_send_history: (task_id: number, file_path: string) => Promise<string>
  open_login_browser: () => Promise<boolean>
  check_login_status: () => Promise<{ logged_in: boolean; username?: string | null; expires_at?: string | null }>
  get_settings: () => Promise<Record<string, unknown>>
  update_settings: (data: Record<string, unknown>) => Promise<Record<string, unknown>>
}

declare global {
  interface Window {
    pywebview?: { api: PyWebViewApi }
  }
}

export {}
