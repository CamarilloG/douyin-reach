<template>
  <div>
    <n-space vertical :size="16">
      <n-space justify="space-between" align="center">
        <n-h4 style="margin: 0">任务列表</n-h4>
        <n-space>
          <n-button @click="openLoadTemplate">从模板创建</n-button>
          <n-button type="primary" @click="openCreate">创建任务</n-button>
        </n-space>
      </n-space>
      <n-data-table
        :columns="columns"
        :data="tasks"
        :loading="loading"
        :pagination="false"
        size="small"
      />
    </n-space>

    <!-- 主表单弹窗 -->
    <n-modal
      v-model:show="showModal"
      preset="card"
      :title="editId ? '编辑任务' : '创建任务'"
      style="width: 760px; max-height: 90vh;"
      :bordered="false"
      @after-leave="onModalClose"
    >
      <n-scrollbar style="max-height: 70vh;">
        <n-form ref="formRef" :model="form" label-placement="left" label-width="140" style="padding-right: 12px;">
          <n-collapse :default-expanded-names="['basic', 'collect', 'video', 'filter', 'send']">
            <!-- 基本信息 -->
            <n-collapse-item title="基本信息" name="basic">
              <n-form-item label="任务名称">
                <n-input v-model:value="form.name" placeholder="请输入任务名称" />
              </n-form-item>
              <n-form-item label="关键词">
                <n-dynamic-input v-model:value="form.keywords" :min="1" placeholder="关键词" />
              </n-form-item>
            </n-collapse-item>

            <!-- 采集参数 -->
            <n-collapse-item title="采集参数" name="collect">
              <n-form-item label="每视频评论上限">
                <n-input-number v-model:value="form.max_comments_per_video" :min="1" :max="500" style="width: 100%" />
              </n-form-item>
              <n-form-item label="每关键词视频上限">
                <n-input-number v-model:value="form.max_videos_per_keyword" :min="1" :max="500" style="width: 100%" />
              </n-form-item>
              <n-form-item label="每关键词滚动次数">
                <n-input-number v-model:value="form.max_scrolls_per_keyword" :min="1" :max="200" style="width: 100%" />
              </n-form-item>
              <n-form-item label="单视频超时(秒)">
                <n-input-number v-model:value="form.video_timeout" :min="5" :max="300" style="width: 100%" />
              </n-form-item>
            </n-collapse-item>

            <!-- 视频筛选 -->
            <n-collapse-item title="视频筛选（注：当前抖音网页可能忽略 URL 筛选参数）" name="video">
              <n-form-item label="排序方式">
                <n-radio-group v-model:value="form.sort_mode">
                  <n-radio value="general">综合</n-radio>
                  <n-radio value="latest">最新</n-radio>
                  <n-radio value="most_like">最赞</n-radio>
                </n-radio-group>
              </n-form-item>
              <n-form-item label="发布时间">
                <n-radio-group v-model:value="form.publish_time">
                  <n-radio value="unlimited">不限</n-radio>
                  <n-radio value="day">一天内</n-radio>
                  <n-radio value="week">一周内</n-radio>
                  <n-radio value="half_year">半年内</n-radio>
                  <n-radio value="custom">自定义</n-radio>
                </n-radio-group>
              </n-form-item>
              <n-form-item v-if="form.publish_time === 'custom'" label="自定义时间">
                <n-space>
                  <n-input v-model:value="form.publish_time_start" placeholder="起 YYYY-MM-DD HH:MM" />
                  <n-input v-model:value="form.publish_time_end" placeholder="止 YYYY-MM-DD HH:MM" />
                </n-space>
              </n-form-item>
              <n-form-item label="视频时长">
                <n-radio-group v-model:value="form.video_duration">
                  <n-radio value="unlimited">不限</n-radio>
                  <n-radio value="lt1m">1分钟内</n-radio>
                  <n-radio value="1to5m">1-5分钟</n-radio>
                  <n-radio value="gt5m">5分钟以上</n-radio>
                </n-radio-group>
              </n-form-item>
              <n-form-item label="搜索范围">
                <n-radio-group v-model:value="form.search_scope">
                  <n-radio value="unlimited">不限</n-radio>
                  <n-radio value="following">关注</n-radio>
                  <n-radio value="viewed">看过</n-radio>
                  <n-radio value="not_viewed">未看过</n-radio>
                </n-radio-group>
              </n-form-item>
              <n-form-item label="内容形式">
                <n-radio-group v-model:value="form.content_form">
                  <n-radio value="unlimited">不限</n-radio>
                  <n-radio value="video">视频</n-radio>
                  <n-radio value="image_text">图文</n-radio>
                </n-radio-group>
              </n-form-item>
            </n-collapse-item>

            <!-- 评论自动筛选 -->
            <n-collapse-item title="评论自动筛选" name="filter">
              <n-form-item label="启用自动筛选">
                <n-switch v-model:value="form.filter_enabled" />
              </n-form-item>
              <n-form-item label="白名单(含任一词保留)">
                <n-dynamic-input v-model:value="form.rules.whitelist" :min="0" placeholder="词" />
              </n-form-item>
              <n-form-item label="黑名单(含任一词排除)">
                <n-dynamic-input v-model:value="form.rules.blacklist" :min="0" placeholder="词" />
              </n-form-item>
              <n-form-item label="正则包含">
                <n-dynamic-input v-model:value="form.rules.regex_include" :min="0" placeholder="正则" />
              </n-form-item>
              <n-form-item label="正则排除">
                <n-dynamic-input v-model:value="form.rules.regex_exclude" :min="0" placeholder="正则" />
              </n-form-item>
            </n-collapse-item>

            <!-- 私信配置 -->
            <n-collapse-item title="私信配置" name="send">
              <n-form-item label="全自动发送">
                <n-switch v-model:value="form.auto_send" />
              </n-form-item>
              <n-form-item label="发送间隔(秒)">
                <n-input-number v-model:value="form.send_interval" :min="1" style="width: 100%" />
              </n-form-item>
              <n-form-item label="日上限">
                <n-input-number v-model:value="form.daily_limit" :min="1" style="width: 100%" />
              </n-form-item>
              <n-form-item label="任务上限">
                <n-input-number v-model:value="form.task_limit" :min="1" style="width: 100%" />
              </n-form-item>
              <n-form-item label="失败重试次数">
                <n-input-number v-model:value="form.retry_limit" :min="0" :max="10" style="width: 100%" />
              </n-form-item>
              <n-form-item label="私信模板列表">
                <n-dynamic-input
                  v-model:value="form.template"
                  :min="1"
                  #="{ value, index }"
                >
                  <n-input
                    :value="value"
                    type="textarea"
                    :rows="2"
                    placeholder="支持 {nickname} {video_title} {comment_text} {keyword}"
                    @update:value="(v: string) => (form.template[index] = v)"
                  />
                </n-dynamic-input>
              </n-form-item>
            </n-collapse-item>
          </n-collapse>
        </n-form>
      </n-scrollbar>
      <template #footer>
        <n-space justify="space-between">
          <n-button @click="openSaveTemplate" :disabled="submitting">保存为模板</n-button>
          <n-space>
            <n-button @click="showModal = false">取消</n-button>
            <n-button type="primary" :loading="submitting" @click="onSubmit">保存</n-button>
          </n-space>
        </n-space>
      </template>
    </n-modal>

    <!-- 保存模板弹窗 -->
    <n-modal v-model:show="showSaveTplModal" preset="dialog" title="保存为模板" positive-text="保存" negative-text="取消" @positive-click="confirmSaveTemplate">
      <n-input v-model:value="saveTplName" placeholder="模板名称（重名将覆盖）" />
    </n-modal>

    <!-- 载入模板弹窗 -->
    <n-modal v-model:show="showLoadTplModal" preset="card" title="从模板创建" style="width: 480px;">
      <n-list bordered>
        <n-list-item v-for="t in templateList" :key="t.id">
          <n-space justify="space-between" style="width: 100%;">
            <span>{{ t.name }}</span>
            <n-space>
              <n-button size="small" type="primary" @click="confirmLoadTemplate(t.id)">使用</n-button>
              <n-button size="small" type="error" @click="removeTemplate(t.id)">删除</n-button>
            </n-space>
          </n-space>
        </n-list-item>
        <n-list-item v-if="templateList.length === 0">
          <n-text depth="3">暂无已保存模板</n-text>
        </n-list-item>
      </n-list>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, h } from 'vue'
import {
  NButton, NSpace, NDataTable, NModal, NForm, NFormItem, NInput, NInputNumber, NSwitch,
  NDynamicInput, NH4, NCollapse, NCollapseItem, NRadio, NRadioGroup, NScrollbar,
  NList, NListItem, NText, useMessage,
} from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import { bridge, isApiAvailable } from '@/api/bridge'
import { useTaskContext } from '@/stores/taskContext'

const message = useMessage()
const taskCtx = useTaskContext()

const loading = ref(false)
const tasks = ref<Record<string, any>[]>([])
const showModal = ref(false)
const editId = ref<number | null>(null)
const submitting = ref(false)
const formRef = ref(null)

const showSaveTplModal = ref(false)
const showLoadTplModal = ref(false)
const saveTplName = ref('')
const templateList = ref<Array<{ id: number; name: string; created_at: string }>>([])

const emptyForm = () => ({
  name: '',
  keywords: [''] as string[],
  max_comments_per_video: 50,
  max_videos_per_keyword: 50,
  max_scrolls_per_keyword: 20,
  video_timeout: 30,
  sort_mode: 'general',
  publish_time: 'unlimited',
  publish_time_start: '',
  publish_time_end: '',
  video_duration: 'unlimited',
  search_scope: 'unlimited',
  content_form: 'unlimited',
  filter_enabled: true,
  retry_limit: 2,
  rules: {
    whitelist: [] as string[],
    blacklist: [] as string[],
    regex_include: [] as string[],
    regex_exclude: [] as string[],
  },
  template: ['你好 {nickname}，看到你对「{video_title}」的评论～'] as string[],
  send_interval: 30,
  daily_limit: 100,
  task_limit: 500,
  auto_send: false,
})
const form = ref(emptyForm())

const statusMap: Record<string, string> = {
  pending: '待执行', collecting: '采集中', collected: '已采集',
  filtering: '筛选中', filtered: '已筛选', sending: '发送中',
  paused: '已暂停', completed: '已完成', error: '异常',
}

const columns: DataTableColumns<Record<string, any>> = [
  { title: 'ID', key: 'id', width: 60 },
  { title: '任务名', key: 'name', width: 160 },
  { title: '状态', key: 'status', width: 90, render: (row) => statusMap[(row.status as string) ?? ''] ?? row.status },
  { title: '关键词', key: 'keywords', ellipsis: { tooltip: true }, render: (row) => (row.keywords as string[])?.join(', ') },
  { title: '创建时间', key: 'created_at', width: 160 },
  {
    title: '操作', key: 'actions', width: 280,
    render: (row) => {
      const id = row.id as number
      return h(NSpace, { size: 6 }, () => [
        h(NButton, { size: 'small', onClick: () => edit(id) }, { default: () => '编辑' }),
        h(NButton, { size: 'small', onClick: () => duplicate(id) }, { default: () => '复制' }),
        h(NButton, { size: 'small', type: 'primary', onClick: () => startCollect(id) }, { default: () => '启动' }),
        h(NButton, { size: 'small', type: 'error', onClick: () => del(id) }, { default: () => '删除' }),
      ])
    },
  },
]

async function loadTasks() {
  loading.value = true
  try {
    await taskCtx.refresh()
    tasks.value = taskCtx.tasks as Record<string, any>[]
  } catch (e) {
    console.error(e)
    message.error('加载任务列表失败')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editId.value = null
  form.value = emptyForm()
  showModal.value = true
}

async function edit(id: number) {
  try {
    const t = (await bridge.get_task(id)) as Record<string, any> | null
    if (!t) { message.error('任务不存在'); return }
    editId.value = id
    const r = (t.rules || {}) as Record<string, string[]>
    const tplArr = Array.isArray(t.template) ? (t.template as string[]) : (t.template ? [String(t.template)] : [''])
    form.value = {
      name: String(t.name ?? ''),
      keywords: Array.isArray(t.keywords) && t.keywords.length ? (t.keywords as string[]) : [''],
      max_comments_per_video: Number(t.max_comments_per_video) || 50,
      max_videos_per_keyword: Number(t.max_videos_per_keyword) || 50,
      max_scrolls_per_keyword: Number(t.max_scrolls_per_keyword) || 20,
      video_timeout: Number(t.video_timeout) || 30,
      sort_mode: String(t.sort_mode || 'general'),
      publish_time: String(t.publish_time || 'unlimited'),
      publish_time_start: String(t.publish_time_start || ''),
      publish_time_end: String(t.publish_time_end || ''),
      video_duration: String(t.video_duration || 'unlimited'),
      search_scope: String(t.search_scope || 'unlimited'),
      content_form: String(t.content_form || 'unlimited'),
      filter_enabled: t.filter_enabled !== false,
      retry_limit: Number(t.retry_limit ?? 2),
      rules: {
        whitelist: r.whitelist || [],
        blacklist: r.blacklist || [],
        regex_include: r.regex_include || [],
        regex_exclude: r.regex_exclude || [],
      },
      template: tplArr.length ? tplArr : [''],
      send_interval: Number(t.send_interval) || 30,
      daily_limit: Number(t.daily_limit) || 100,
      task_limit: Number(t.task_limit) || 500,
      auto_send: Boolean(t.auto_send),
    }
    showModal.value = true
  } catch (e) {
    console.error(e)
    message.error('加载任务失败')
  }
}

function buildPayload() {
  const r = form.value.rules
  return {
    name: form.value.name,
    keywords: form.value.keywords.filter(Boolean),
    max_comments_per_video: form.value.max_comments_per_video,
    max_videos_per_keyword: form.value.max_videos_per_keyword,
    max_scrolls_per_keyword: form.value.max_scrolls_per_keyword,
    video_timeout: form.value.video_timeout,
    sort_mode: form.value.sort_mode,
    publish_time: form.value.publish_time,
    publish_time_start: form.value.publish_time_start || null,
    publish_time_end: form.value.publish_time_end || null,
    video_duration: form.value.video_duration,
    search_scope: form.value.search_scope,
    content_form: form.value.content_form,
    filter_enabled: form.value.filter_enabled,
    retry_limit: form.value.retry_limit,
    rules: {
      whitelist: (r.whitelist || []).filter(Boolean),
      blacklist: (r.blacklist || []).filter(Boolean),
      regex_include: (r.regex_include || []).filter(Boolean),
      regex_exclude: (r.regex_exclude || []).filter(Boolean),
    },
    template: form.value.template.filter((s) => s && s.trim()),
    send_interval: form.value.send_interval,
    daily_limit: form.value.daily_limit,
    task_limit: form.value.task_limit,
    auto_send: form.value.auto_send,
  }
}

function onModalClose() {
  void loadTasks()
}

async function onSubmit() {
  submitting.value = true
  try {
    const payload = buildPayload()
    if (editId.value) {
      await bridge.update_task(editId.value, payload)
      message.success('任务更新成功')
    } else {
      await bridge.create_task(payload)
      message.success('任务创建成功')
    }
    await new Promise((r) => setTimeout(r, 300))
    showModal.value = false
  } catch (e) {
    console.error(e)
    message.error('保存失败: ' + String(e))
  } finally {
    submitting.value = false
  }
}

async function startCollect(id: number) {
  try {
    await bridge.start_collection(id)
    message.success('采集已启动')
    await loadTasks()
  } catch (e) {
    console.error(e); message.error('启动采集失败')
  }
}

async function duplicate(id: number) {
  try {
    const newTask = await bridge.duplicate_task(id)
    if (newTask) {
      message.success('任务已复制')
      await loadTasks()
    } else {
      message.error('复制失败')
    }
  } catch (e) {
    console.error(e); message.error('复制失败')
  }
}

async function del(id: number) {
  try {
    await bridge.delete_task(id)
    message.success('任务已删除')
    await loadTasks()
  } catch (e) {
    console.error(e); message.error('删除任务失败')
  }
}

function openSaveTemplate() {
  saveTplName.value = form.value.name || ''
  showSaveTplModal.value = true
}

async function confirmSaveTemplate() {
  if (!saveTplName.value.trim()) {
    message.warning('请输入模板名称')
    return
  }
  try {
    await bridge.save_task_template(saveTplName.value.trim(), buildPayload())
    message.success('模板已保存')
  } catch (e) {
    console.error(e); message.error('保存模板失败')
  }
}

async function openLoadTemplate() {
  try {
    templateList.value = await bridge.list_task_templates()
    showLoadTplModal.value = true
  } catch (e) {
    console.error(e); message.error('加载模板列表失败')
  }
}

async function confirmLoadTemplate(id: number) {
  try {
    const tpl = await bridge.load_task_template(id)
    if (!tpl) { message.error('模板不存在'); return }
    const payload = (tpl.payload || {}) as Record<string, any>
    editId.value = null
    form.value = {
      ...emptyForm(),
      ...payload,
      keywords: Array.isArray(payload.keywords) && payload.keywords.length ? payload.keywords : [''],
      rules: {
        whitelist: payload.rules?.whitelist || [],
        blacklist: payload.rules?.blacklist || [],
        regex_include: payload.rules?.regex_include || [],
        regex_exclude: payload.rules?.regex_exclude || [],
      },
      template: Array.isArray(payload.template) && payload.template.length ? payload.template : [''],
    }
    showLoadTplModal.value = false
    showModal.value = true
  } catch (e) {
    console.error(e); message.error('载入模板失败')
  }
}

async function removeTemplate(id: number) {
  try {
    await bridge.delete_task_template(id)
    templateList.value = await bridge.list_task_templates()
    message.success('模板已删除')
  } catch (e) {
    console.error(e); message.error('删除模板失败')
  }
}

onMounted(async () => {
  const ok = await isApiAvailable()
  if (ok) {
    await loadTasks()
  } else {
    message.error('无法连接到后端服务器')
  }
})
</script>
