"""授权码生成器 GUI（仅签发方使用）。

输入被授权方 / 机器指纹 / 有效天数 → 一键生成 base64 激活码 + 可导出 license.key 文件。
私钥默认从 ~/.douyin_reach_keys/license_signing_ed25519.pem 读取。

启动：
    python tools/license_studio.py
"""
from __future__ import annotations

import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

# 允许直接运行（tools/ 与本仓库根的 import 都需要）
_THIS = os.path.dirname(os.path.abspath(__file__))
if _THIS not in sys.path:
    sys.path.insert(0, _THIS)

from _issuer_core import (  # noqa: E402
    DEFAULT_KEY_PATH,
    IssuedLicense,
    IssuerError,
    issue,
    load_private_key,
)


APP_TITLE = "抖音助手 · 授权码生成器"


class StudioApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("780x640")
        self.root.minsize(680, 560)

        self._issued: IssuedLicense | None = None

        self._build_ui()

    # -------------------- UI --------------------

    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 6}

        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill="both", expand=True)

        # ---------- 输入表单 ----------
        form = ttk.LabelFrame(outer, text="签发参数", padding=10)
        form.pack(fill="x")

        # 被授权方
        ttk.Label(form, text="被授权方：").grid(row=0, column=0, sticky="w", **pad)
        self.var_licensee = tk.StringVar()
        ttk.Entry(form, textvariable=self.var_licensee, width=50).grid(
            row=0, column=1, columnspan=2, sticky="we", **pad
        )

        # 机器指纹
        ttk.Label(form, text="机器指纹：").grid(row=1, column=0, sticky="w", **pad)
        self.var_fingerprint = tk.StringVar()
        ttk.Entry(form, textvariable=self.var_fingerprint, width=50).grid(
            row=1, column=1, sticky="we", **pad
        )
        ttk.Label(form, text="（32 位十六进制）", foreground="#888").grid(
            row=1, column=2, sticky="w", **pad
        )

        # 有效天数
        ttk.Label(form, text="有效天数：").grid(row=2, column=0, sticky="w", **pad)
        self.var_days = tk.IntVar(value=7)
        ttk.Spinbox(form, from_=1, to=365, textvariable=self.var_days, width=8).grid(
            row=2, column=1, sticky="w", **pad
        )

        # 私钥路径
        ttk.Label(form, text="私钥路径：").grid(row=3, column=0, sticky="w", **pad)
        self.var_key_path = tk.StringVar(value=str(DEFAULT_KEY_PATH))
        ttk.Entry(form, textvariable=self.var_key_path).grid(
            row=3, column=1, sticky="we", **pad
        )
        ttk.Button(form, text="浏览…", command=self._on_pick_key).grid(
            row=3, column=2, sticky="w", **pad
        )

        form.columnconfigure(1, weight=1)

        # 生成按钮
        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=(8, 0))
        self.btn_generate = ttk.Button(actions, text="生成激活码", command=self._on_generate)
        self.btn_generate.pack(side="left")
        ttk.Label(
            actions,
            text="提示：客户运行 tools/get_fingerprint.py 或软件首次启动时可拿到机器指纹。",
            foreground="#888",
        ).pack(side="left", padx=12)

        # ---------- 结果输出 ----------
        result = ttk.LabelFrame(outer, text="激活码（base64，整行复制给客户）", padding=10)
        result.pack(fill="both", expand=True, pady=(12, 0))

        self.text_token = tk.Text(
            result,
            height=8,
            wrap="char",
            font=("Consolas", 10),
            bg="#f7f7f7",
        )
        self.text_token.pack(fill="both", expand=True)
        self.text_token.config(state="disabled")

        out_actions = ttk.Frame(outer)
        out_actions.pack(fill="x", pady=(8, 0))
        self.btn_copy = ttk.Button(
            out_actions, text="📋 复制激活码", command=self._on_copy, state="disabled"
        )
        self.btn_copy.pack(side="left")
        self.btn_export = ttk.Button(
            out_actions, text="💾 导出 license.key 文件", command=self._on_export, state="disabled"
        )
        self.btn_export.pack(side="left", padx=8)
        self.lbl_status = ttk.Label(out_actions, text="", foreground="#2c8a4d")
        self.lbl_status.pack(side="left", padx=12)

        # ---------- 摘要 ----------
        summary = ttk.LabelFrame(outer, text="签发摘要", padding=10)
        summary.pack(fill="x", pady=(12, 0))
        self.text_summary = tk.Text(
            summary,
            height=7,
            wrap="word",
            font=("Consolas", 10),
            bg="#f7f7f7",
        )
        self.text_summary.pack(fill="x")
        self.text_summary.config(state="disabled")

        # 底部说明
        ttk.Label(
            outer,
            text="安全提示：私钥永远不要离开本机；本工具仅用于签发方本地使用，请勿打包进客户交付物。",
            foreground="#a04040",
        ).pack(side="bottom", anchor="w", pady=(8, 0))

    # -------------------- Handlers --------------------

    def _on_pick_key(self) -> None:
        path = filedialog.askopenfilename(
            title="选择 Ed25519 私钥（PEM）",
            filetypes=[("PEM 文件", "*.pem"), ("所有文件", "*.*")],
            initialdir=str(Path(self.var_key_path.get()).parent),
        )
        if path:
            self.var_key_path.set(path)

    def _on_generate(self) -> None:
        try:
            priv = load_private_key(self.var_key_path.get())
            result = issue(
                licensee=self.var_licensee.get(),
                fingerprint=self.var_fingerprint.get(),
                days=int(self.var_days.get()),
                private_key=priv,
            )
        except IssuerError as e:
            messagebox.showerror("签发失败", str(e))
            return
        except Exception as e:
            messagebox.showerror("意外错误", f"{type(e).__name__}: {e}")
            return

        self._issued = result
        self._show_token(result.token_b64)
        self._show_summary(result.summary)
        self.btn_copy.config(state="normal")
        self.btn_export.config(state="normal")
        self.lbl_status.config(text="✅ 已生成", foreground="#2c8a4d")

    def _on_copy(self) -> None:
        if not self._issued:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self._issued.token_b64)
        self.root.update()  # 持久化到剪贴板（避免某些 WM 上立刻失效）
        self.lbl_status.config(text="✅ 已复制到剪贴板", foreground="#2c8a4d")

    def _on_export(self) -> None:
        if not self._issued:
            return
        s = self._issued.summary
        # 默认文件名带被授权方与签发日期，避免覆盖
        suggested = f"license_{_safe_filename(s['licensee'])}_{s['issued_at'][:10]}.key"
        path = filedialog.asksaveasfilename(
            title="导出 license.key",
            defaultextension=".key",
            initialfile=suggested,
            filetypes=[("License 文件", "*.key"), ("所有文件", "*.*")],
        )
        if not path:
            return
        try:
            Path(path).write_text(self._issued.file_text, encoding="utf-8")
        except OSError as e:
            messagebox.showerror("写入失败", str(e))
            return
        self.lbl_status.config(text=f"✅ 已导出：{path}", foreground="#2c8a4d")

    # -------------------- Helpers --------------------

    def _show_token(self, token: str) -> None:
        self.text_token.config(state="normal")
        self.text_token.delete("1.0", "end")
        self.text_token.insert("1.0", token)
        self.text_token.config(state="disabled")

    def _show_summary(self, s: dict) -> None:
        lines = [
            f"被授权方  : {s['licensee']}",
            f"机器指纹  : {s['fingerprint']}",
            f"签发时间  : {s['issued_at']}",
            f"过期时间  : {s['expires_at']}（{s['days']} 天后）",
            f"License ID: {s['license_id']}",
        ]
        self.text_summary.config(state="normal")
        self.text_summary.delete("1.0", "end")
        self.text_summary.insert("1.0", "\n".join(lines))
        self.text_summary.config(state="disabled")


def _safe_filename(s: str) -> str:
    """文件名安全：去掉 Windows / *nix 都不喜欢的字符，长度截到 32。"""
    out = []
    for ch in s:
        if ch.isalnum() or ch in "-_":
            out.append(ch)
        else:
            out.append("_")
    return ("".join(out) or "license")[:32]


def main() -> None:
    root = tk.Tk()
    # Windows 上 tk 默认字体偏小，统一用 9pt UI 字体
    style = ttk.Style()
    if "vista" in style.theme_names():
        style.theme_use("vista")
    StudioApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
