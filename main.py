import sys
import os
import tkinter as tk
from tkinter import filedialog, messagebox


def get_default_font():
    try:
        from tkinter import font
        families = [f.lower() for f in font.families()]
        for name in ["microsoft yahei", "microsoft jhenghei", "simsun", "tahoma", "arial"]:
            if name in families:
                return name
    except Exception:
        pass
    return "TkDefaultFont"


def ensure_root_path(parent):
    from config import load_config, save_config
    cfg = load_config()
    root_path = cfg.get("root_path", "")
    if root_path and os.path.isdir(root_path):
        return cfg
    messagebox.showinfo(
        "欢迎使用 PopNotification",
        "请选择知识数据库的根路径。\n所有学科和知识卡片将保存在此目录下。",
        parent=parent,
    )
    path = filedialog.askdirectory(title="选择知识数据库根路径", parent=parent)
    if path:
        cfg["root_path"] = path
    else:
        default = os.path.join(os.path.expanduser("~"), "PopKnowledge")
        cfg["root_path"] = default
        messagebox.showinfo("提示", f"已使用默认路径:\n{default}", parent=parent)
    save_config(cfg)
    return cfg


def start_notifier(parent):
    from notifier import Notifier
    app = Notifier(parent)
    parent.mainloop()


def start_editor(parent):
    from editor import EditorWindow
    app = EditorWindow(parent)
    parent.mainloop()


def main():
    try:
        import ctypes
        mutex_name = "PopNotification-Instance"
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW(None, False, mutex_name)
        if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            sys.exit(0)
    except Exception:
        pass

    root = tk.Tk()
    root.withdraw()

    icon_path = os.path.join(os.path.dirname(__file__), "ICON.png")
    if os.path.exists(icon_path):
        try:
            root.iconbitmap(default=icon_path)
        except Exception:
            pass

    default_font = get_default_font()
    root.option_add("*Font", (default_font, 10))

    ensure_root_path(root)

    if "--background" in sys.argv:
        start_notifier(root)
        return

    answer = messagebox.askyesno(
        "PopNotification",
        "是否启动后台提醒进程？\n\n"
        "选「是」= 启动后台提醒 + 系统托盘（最小化运行）\n"
        "选「否」= 仅打开编辑器",
        parent=root,
    )

    root.title("PopNotification")

    if answer:
        start_notifier(root)
    else:
        root.deiconify()
        root.geometry("950x650")
        from updater import check_for_update, show_changelog_if_needed
        check_for_update(root, silent=True)
        root.after(800, lambda: show_changelog_if_needed(root))
        start_editor(root)


if __name__ == "__main__":
    main()
