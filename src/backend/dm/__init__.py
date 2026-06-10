# 私信发送模块（M5）
from .template import render_template
from .sender import DMSender, SendResult

__all__ = ["render_template", "DMSender", "SendResult"]
