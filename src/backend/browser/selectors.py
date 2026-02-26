"""
抖音 PC 网页版元素选择器常量。
优先使用 aria-label、role、文案定位，便于页面改版后集中更新。
已采集策略见 docs/09-项目经验与关键信息.md。
"""
from __future__ import annotations

# ---------- 首页 / 通用 ----------
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
VIDEO_URL_TEMPLATE = "https://www.douyin.com/video/{aweme_id}"
USER_URL_TEMPLATE = "https://www.douyin.com/user/{sec_uid}"
# Session 校验接口（GET，需登录态）
USER_SETTINGS_API = "https://www.douyin.com/aweme/v1/web/get/user/settings"

# ---------- 搜索结果页 ----------
# 视频卡片：标题、作者 link（@昵称）、点赞等；无统一 list 容器，按标题+作者模式遍历
# 综合/视频 Tab 等
SEARCH_TAB_VIDEO = "视频"

# ---------- 视频详情页 / 评论区 ----------
# 评论区「点击加载更多」
COMMENT_LOAD_MORE_TEXT = "点击加载更多"
# 评论区标题/全部评论
COMMENT_SECTION_HEADING = "全部评论"
# 单条一级评论：用户 link（昵称）、评论正文、时间、点赞、回复
# 使用语义：评论区内 link（作者）+ 相邻评论内容

# ---------- 用户主页 ----------
# 私信按钮（用户主页）
USER_PAGE_DM_BUTTON = "私信"

# ---------- 风控 / 危险检测 ----------
# 页面出现以下文案视为危险，立即停止
DANGER_PAGE_TEXTS = ("账号异常", "验证码", "滑块", "安全验证")
# 登录浮层：页面出现以下文案视为未登录或登录浮层已弹出，终止流程并需用户先登录
LOGIN_OVERLAY_TEXTS = ("扫码登录", "验证码登录")

# ---------- 评论列表接口（www-hj 域名，用于可选接口拉取） ----------
COMMENT_LIST_API_TEMPLATE = "https://www-hj.douyin.com/aweme/v1/web/comment/list/"
