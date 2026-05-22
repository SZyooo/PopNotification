import json
import os
import tkinter as tk
from tkinter import messagebox
import urllib.request
import urllib.error
import webbrowser
import threading
import ssl

GITHUB_REPO = "SZyooo/PopNotification"
API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASE_URL = f"https://github.com/{GITHUB_REPO}/releases/latest"


def get_local_version():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "version.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f).get("version", "0.0.0")
        except Exception:
            return "0.0.0"
    return "0.0.0"


def set_local_version(version):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "version.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"version": version}, f, ensure_ascii=False, indent=2)


def _parse_version(v):
    try:
        return tuple(int(x) for x in v.split("."))
    except Exception:
        return (0, 0, 0)


def _fetch_latest_release():
    ctx = ssl.create_default_context()
    req = urllib.request.Request(API_URL, headers={"User-Agent": "PopNotification-Updater/1.0"})
    with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check_for_update(parent, silent=False):
    def _do_check():
        try:
            data = _fetch_latest_release()
            remote_version = data.get("tag_name", "").lstrip("v")
            body = data.get("body", "暂无更新说明")
            local_ver = get_local_version()
            if _parse_version(remote_version) > _parse_version(local_ver):
                parent.after(0, lambda: _show_update_dialog(parent, local_ver, remote_version, body))
            elif not silent:
                parent.after(0, lambda: messagebox.showinfo("检查更新", f"当前已是最新版本 v{local_ver}", parent=parent))
        except Exception:
            if not silent:
                parent.after(0, lambda: messagebox.showwarning("检查更新", "无法连接到更新服务器，请检查网络后重试", parent=parent))

    t = threading.Thread(target=_do_check, daemon=True)
    t.start()


def _show_update_dialog(parent, local_ver, remote_ver, body):
    dialog = tk.Toplevel(parent)
    dialog.title("发现新版本")
    dialog.geometry("500x400")
    dialog.resizable(True, True)
    dialog.transient(parent)
    dialog.grab_set()
    x = parent.winfo_rootx() + (parent.winfo_width() - 500) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - 400) // 2
    dialog.geometry(f"+{x}+{y}")

    header = tk.Frame(dialog, bg="#3498db", height=60)
    header.pack(fill=tk.X)
    header.pack_propagate(False)
    tk.Label(header, text="发现新版本！", font=("Microsoft YaHei", 14, "bold"),
             fg="white", bg="#3498db").pack(expand=True)

    info_frame = tk.Frame(dialog, bg="#fafafa")
    info_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)

    tk.Label(info_frame, text=f"当前版本: v{local_ver}   最新版本: v{remote_ver}",
             font=("Microsoft YaHei", 10, "bold"), fg="#2c3e50", bg="#fafafa",
             anchor=tk.W).pack(fill=tk.X, pady=(0, 6))

    tk.Label(info_frame, text="更新内容:", font=("Microsoft YaHei", 10, "bold"),
             fg="#555", bg="#fafafa", anchor=tk.W).pack(fill=tk.X)

    text_frame = tk.Frame(info_frame, bg="white", relief=tk.SUNKEN, borderwidth=1)
    text_frame.pack(fill=tk.BOTH, expand=True)

    text_widget = tk.Text(text_frame, font=("Microsoft YaHei", 9), wrap=tk.WORD,
                          bg="white", relief=tk.FLAT, padx=6, pady=4)
    text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar = tk.Scrollbar(text_frame, command=text_widget.yview)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    text_widget.config(yscrollcommand=scrollbar.set)
    text_widget.insert(tk.END, body)
    text_widget.config(state=tk.DISABLED)

    btn_frame = tk.Frame(dialog, bg="#fafafa")
    btn_frame.pack(fill=tk.X, pady=(0, 8))

    def on_download():
        webbrowser.open(RELEASE_URL)
        dialog.destroy()

    def on_skip():
        dialog.destroy()

    tk.Button(btn_frame, text="下载更新", font=("Microsoft YaHei", 10, "bold"),
              bg="#3498db", fg="white", relief=tk.FLAT, padx=20, pady=4, cursor="hand2",
              command=on_download).pack(side=tk.RIGHT, padx=(4, 12))
    tk.Button(btn_frame, text="稍后提醒", font=("Microsoft YaHei", 10),
              bg="#95a5a6", fg="white", relief=tk.FLAT, padx=16, pady=4, cursor="hand2",
              command=on_skip).pack(side=tk.RIGHT, padx=4)


def show_changelog_if_needed(parent):
    local_ver = get_local_version()
    from config import load_config, save_config
    cfg = load_config()
    last_viewed = cfg.get("last_viewed_version", "")
    if last_viewed and last_viewed == local_ver:
        return
    try:
        data = _fetch_latest_release()
        remote_version = data.get("tag_name", "").lstrip("v")
        body = data.get("body", "暂无更新说明")
        if remote_version == local_ver:
            parent.after(0, lambda: _show_changelog(parent, local_ver, body))
    except Exception:
        pass
    cfg["last_viewed_version"] = local_ver
    save_config(cfg)


def _show_changelog(parent, version, body):
    dialog = tk.Toplevel(parent)
    dialog.title(f"更新说明 - v{version}")
    dialog.geometry("520x420")
    dialog.resizable(True, True)
    dialog.transient(parent)
    dialog.grab_set()
    x = parent.winfo_rootx() + (parent.winfo_width() - 520) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - 420) // 2
    dialog.geometry(f"+{x}+{y}")

    header = tk.Frame(dialog, bg="#27ae60", height=60)
    header.pack(fill=tk.X)
    header.pack_propagate(False)
    tk.Label(header, text=f"🎉 已更新至 v{version}", font=("Microsoft YaHei", 14, "bold"),
             fg="white", bg="#27ae60").pack(expand=True)

    text_frame = tk.Frame(dialog, bg="white", relief=tk.SUNKEN, borderwidth=1)
    text_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)

    text_widget = tk.Text(text_frame, font=("Microsoft YaHei", 9), wrap=tk.WORD,
                          bg="white", relief=tk.FLAT, padx=8, pady=6)
    text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar = tk.Scrollbar(text_frame, command=text_widget.yview)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    text_widget.config(yscrollcommand=scrollbar.set)
    text_widget.insert(tk.END, body)
    text_widget.config(state=tk.DISABLED)

    btn_frame = tk.Frame(dialog, bg="#fafafa")
    btn_frame.pack(fill=tk.X, pady=(0, 8))

    tk.Button(btn_frame, text="知道了", font=("Microsoft YaHei", 10, "bold"),
              bg="#27ae60", fg="white", relief=tk.FLAT, padx=24, pady=4, cursor="hand2",
              command=dialog.destroy).pack(pady=4)
