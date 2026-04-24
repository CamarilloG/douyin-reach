"""
抖音 PC 网页版元素选择器常量。
优先使用 aria-label、role、文案定位，便于页面改版后集中更新。
已采集策略见 docs/09-项目经验与关键信息.md。
"""
from __future__ import annotations

from typing import Any

# ---------- 首页 / 通用 ----------
# 新手引导：点击「我知道了」关闭引导浮层
NEWBIE_GUIDE_DISMISS_TEXT = "我知道了"
# 搜索框（placeholder 或可点击输入）
SEARCH_BOX_PLACEHOLDER = "搜索你感兴趣的内容"
# 搜索按钮
SEARCH_BUTTON_TEXT = "搜索"
# 登录入口文案
LOGIN_TEXT = "登录"
# 私信入口（顶栏）
DM_TEXT = "私信"

# ---------- URL 模板 ----------
BASE_URL = "https://www.douyin.com"
SEARCH_URL_TEMPLATE = "https://www.douyin.com/search/{keyword}?type=general"


def build_search_url(
    keyword: str,
    *,
    sort_mode: str = "general",
    publish_time: str = "unlimited",
    publish_time_start: str | None = None,
    publish_time_end: str | None = None,
    video_duration: str = "unlimited",
    search_scope: str = "unlimited",
    content_form: str = "unlimited",
    tab: str = "general",
) -> str:
    """根据筛选条件拼接搜索 URL。

    依据 2026-04 实地调研（更正版）：
    - 筛选操作本身不修改浏览器 URL，由前端 JS 通过 API 请求参数维护；
      但作为初次进入页面的提示参数仍可能影响首屏加载。
    - 综合 tab：用 `filter_selected` JSON 字段，仅 `sort_type` / `publish_time`。
    - 视频 tab：用独立 URL 参数（sort_type / publish_time / filter_duration），
      其中 filter_duration 取值是字符串区间："0-1" / "1-5" / "5-10000"。

    sort_type 取值（与抖音 API 一致）：
      综合排序=0  最多点赞=1  最新发布=2
    """
    from urllib.parse import quote, urlencode
    import json as _json

    base = f"https://www.douyin.com/search/{quote(keyword)}"
    params: dict[str, str] = {"type": "video" if tab == "video" else "general"}

    # sort_type: general=0 / most_like=1 / latest=2 （注意 1 / 2 的位置）
    sort_map = {"general": "0", "most_like": "1", "latest": "2"}
    sort_val = sort_map.get(sort_mode, "0")

    pub_map = {"unlimited": "0", "day": "1", "week": "7", "half_year": "180"}
    pub_val = pub_map.get(publish_time, "0")

    duration_map = {"unlimited": "0", "lt1m": "0-1", "1to5m": "1-5", "gt5m": "5-10000"}
    duration_val = duration_map.get(video_duration, "0")

    if tab == "video":
        # 视频 tab：独立参数
        if sort_val != "0":
            params["sort_type"] = sort_val
        if pub_val != "0":
            params["publish_time"] = pub_val
        if duration_val != "0":
            params["filter_duration"] = duration_val
        if sort_val != "0" or pub_val != "0" or duration_val != "0":
            params["is_filter_search"] = "1"
    else:
        # 综合 tab：仅 sort_type / publish_time 进 filter_selected JSON
        filter_selected: dict[str, Any] = {}
        if sort_val != "0":
            filter_selected["sort_type"] = sort_val
        if pub_val != "0":
            filter_selected["publish_time"] = pub_val
        if filter_selected:
            params["filter_selected"] = _json.dumps(filter_selected, ensure_ascii=False)
            params["is_filter_search"] = "1"

    # search_scope / content_form 参数名暂未确认，先不下发；
    # 调用方可后续在 panel 上点击补齐。
    _ = (search_scope, content_form, publish_time_start, publish_time_end)

    return f"{base}?{urlencode(params)}"
VIDEO_URL_TEMPLATE = "https://www.douyin.com/video/{aweme_id}"
USER_URL_TEMPLATE = "https://www.douyin.com/user/{sec_uid}"
# Session 校验接口（GET，需登录态）
USER_SETTINGS_API = "https://www.douyin.com/aweme/v1/web/get/user/settings"

# ---------- 搜索结果页 ----------
# Tab 切换：<span data-key="video">视频</span>，无 ARIA 属性
SEARCH_TAB_VIDEO = "视频"
SEARCH_TAB_VIDEO_DATA_KEY = "video"
# 视频卡片容器（语义化 class，比 hash class 稳定）
SEARCH_CARD_CLASS = "search-result-card"

# ---------- 视频详情页 / 评论区 ----------
# 评论区标题（语义化 class）
COMMENT_SECTION_HEADING = "全部评论"
COMMENT_TITLE_CLASS = "comment-title"
# 评论区容器（语义化 class，非虚拟滚动，DOM 直接追加）
COMMENT_MAIN_CONTENT_CLASS = "comment-mainContent"
# 单条评论评论正文所在容器 class（结构：div.C7LroK_h > span.WFJiGxr7）
# 注意：hash class 可能变化，优先用 a[href*="/user/"] 定位评论块再取兄弟节点
# 子回复展开按钮（语义化 class）
COMMENT_REPLY_EXPAND_BTN_CLASS = "comment-reply-expand-btn"

# ---------- 用户主页 ----------
# 私信按钮文案（用户主页）。
# ⚠️ 陷阱 1：页面有两个 textContent === "私信" 的 <button>（响应式布局副本），
# 只有一个可见，另一个 0×0。定位时必须加可见性过滤。
# ⚠️ 陷阱 2：页面顶部导航栏也有 "私信" 文字（`[data-e2e="im-entry"] p`），
# 但它是 <p> 不是 <button>，并且点击它进入的是全局消息中心不是浮窗。
# 因此按钮定位应限制为 <button> 且祖先在 [data-e2e="user-detail"] 容器内。
USER_PAGE_DM_BUTTON = "私信"
# 主页私信按钮 Playwright 选择器（:visible 伪类过滤隐藏副本）
USER_PAGE_DM_BUTTON_SELECTOR = 'button.semi-button:has-text("私信"):visible'
# 用户主页详情容器（data-e2e，稳定）
USER_DETAIL_CONTAINER = '[data-e2e="user-detail"]'

# ---------- 私信叠层（M5 DOM 发送）---------
# 真实 DOM 结构（已在登录态页面验证，2026-04）：
#   [data-e2e="im-entry"]
#     └─ .lGxh4PDP.popShadowAnimation        ← 浮窗根（hash class 不稳定）
#         ├─ [data-e2e="im-dialog"]          ← 左侧会话列表面板（不是聊天区！）
#         └─ [data-e2e="msg-input"]          ← 右侧聊天输入区容器（稳定锚点）
#             ├─ .im-richtext-container
#             │   └─ .DraftEditor-editorContainer
#             │       └─ div[role="textbox" contenteditable="true"].public-DraftEditor-content
#             └─ span.PygT7Ced.e2e-send-msg-btn  ← 发送按钮（<span>，无 disabled）
#
# 关键事实：
# - 全页面只有一个 role="textbox"，就是私信输入框（搜索框是 <input data-e2e="searchbar-input">）
# - 搜索框是原生 <input>，私信框是 DraftJS contenteditable，DOM 类型上天然互斥
# - 输入框本身没有 data-e2e / aria-label，但它的祖先 [data-e2e="msg-input"] 是稳定锚点

# ⚠️ im-entry 是顶部导航栏消息入口（点它进全局消息中心），**不是**主页私信浮窗。
# 之前把它当浮窗锚点是错的 — 浮窗打开后真正新增的是 [data-e2e="im-dialog"]。
DM_ENTRY_SELECTOR = '[data-e2e="im-entry"]'  # 保留供旧逻辑兼容，不建议做浮窗判据
# 私信浮窗根容器（推荐的浮窗已打开判据，data-e2e 稳定）
DM_DIALOG_SELECTOR = '[data-e2e="im-dialog"]'
# 右侧聊天输入区容器（稳定锚点，包含输入框 + 发送按钮）
DM_MSG_INPUT_CONTAINER = '[data-e2e="msg-input"]'
# 输入框（1 级选择器，100% 命中率）
DM_INPUT_SELECTOR = '[data-e2e="msg-input"] [contenteditable="true"]'
# 备用：DraftJS richtext 容器路径
DM_INPUT_SELECTOR_ALT = '.im-richtext-container [contenteditable="true"]'
# 发送按钮（1 级选择器，含容器限定）
DM_SEND_BTN_SELECTOR = '[data-e2e="msg-input"] .e2e-send-msg-btn'
# 发送按钮 class（备用，全局唯一）
DM_SEND_BTN_CLASS = "e2e-send-msg-btn"
# 输入框 placeholder 文案（仅作文案展示用途，DraftJS 不使用原生 placeholder）
DM_INPUT_DESC = "发送消息"
# 发送失败 / 业务限制文案（用于检测失败）
DM_FAIL_SEND = "发送失败"
DM_ONE_MSG_LIMIT = "只能发送一条"

# ---------- 风控 / 危险检测 ----------
# 页面出现以下文案视为危险，立即停止。
# ⚠️ 务必使用足够具体的短语 — 单字"验证码"/"滑块"/"拼图"会被评论区 UGC 内容误命中
# (例: 用户评论"我这种验证码都得看好几遍的来说太难了" 触发了 2026-04-10 的误报)。
DANGER_PAGE_TEXTS = (
    "账号存在异常",
    "请完成安全验证",
    "请输入验证码",
    "请完成验证",
    "拖动滑块完成拼图",
    "拖动下方滑块",
    "您的访问出现异常",
    "访问过于频繁",
)
# 验证码浮层 DOM：抖音滑块/拼图验证码（vc-captcha-verify-visibility 可见时）
CAPTCHA_DOM_SELECTORS = (
    ".vc-captcha-verify-visibility",  # 验证码浮层可见容器
    "#captcha_verify_image",          # 滑块验证码图片
    ".captcha_verify_bar",            # 验证码条（含「拖动滑块，完成拼图」）
)
# 登录浮层 DOM 选择器（id 前缀匹配，后缀为随机 12 位）
LOGIN_PANEL_SELECTOR = '[id^="login-full-panel"]'
# 面板本体（稳定 id）
LOGIN_PANEL_NEW_ID = "login-panel-new"
# 登录组件根（稳定 id）
LOGIN_COMPONENT_ID = "douyin-login-new-id"
# 登录浮层文案（检测到任一即视为未登录弹窗）
LOGIN_OVERLAY_TEXTS = ("扫码登录", "验证码登录", "密码登录", "登录后即可搜索")

# ---------- 评论列表接口（www-hj 域名，用于可选接口拉取） ----------
COMMENT_LIST_API_TEMPLATE = "https://www-hj.douyin.com/aweme/v1/web/comment/list/"

# ---------- 创作者中心私信（M7+ 通道切换） ----------
# 审核宽松，支持微信号/链接；走 DOM 自动化。实测要点见 docs/DOM调研.txt。
# hash 类名全部使用 [class*="..."] 前缀匹配，抗 Semi Design CSS-in-JS 发版漂移。
CREATOR_HOME_URL = "https://creator.douyin.com/creator-micro/home"
CREATOR_CHAT_URL = "https://creator.douyin.com/creator-micro/data/following/chat"

# 会话列表容器：ReactVirtualized 虚拟列表（!! 不在可视区的 <li> 可能未渲染到 DOM）
# 新会话通常置顶，所以大多数场景不需要滚动；如果需要往下找较老的会话，
# 要主动滚动这个容器触发懒加载。
CREATOR_VIRT_LIST = ".ReactVirtualized__Grid.ReactVirtualized__List"
# 会话列表单项（稳定语义类）
CREATOR_CONV_ITEM = "li.semi-list-item"
# 当前选中会话（点击后 li 会追加 hash 前缀 "active-xxxx"，用前缀匹配）
CREATOR_CONV_ACTIVE = 'li.semi-list-item[class*="active"]'
# 会话行内元素（hash 类名前缀匹配）
CREATOR_CONV_NAME = '[class*="item-header-name"]'
CREATOR_CONV_TIME = '[class*="item-header-time"]'
# 聊天输入框（contenteditable div，不是 textarea / DraftJS）
CREATOR_INPUT_SELECTOR = 'div[contenteditable="true"][class*="chat-input"]'
# 输入框父容器（备用锚点）
CREATOR_CHAT_EDITOR = '[class*="chat-editor"]'
# 发送按钮（类含 chat-btn，输入为空时 disabled=true）
CREATOR_SEND_BTN_SELECTOR = "button.chat-btn, button[class*=\"chat-btn\"]"
# 发送按钮父容器（备用锚点）
CREATOR_CHAT_FOOTER = '[class*="chat-footer"]'
# 消息气泡（用于发送后验证最新气泡文本 == 刚发文本）
# 注意：气泡外层类名此次调研未给出，首次实测时若此前缀不中需立即修正。
CREATOR_MSG_BUBBLE = '[class*="chat-bubble"]'
# 错误 toast（Semi Design 标准类）
CREATOR_ERROR_TOAST = ".semi-toast-error"
