import sys
import os
import tkinter as tk
from tkinter import filedialog, messagebox
from i18n import tr, load_language
from config import load_config


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
    from config import save_config
    cfg = load_config()
    root_path = cfg.get("root_path", "")
    if root_path and os.path.isdir(root_path):
        return cfg
    messagebox.showinfo(
        tr("app.name"),
        tr("main.select_root"),
        parent=parent,
    )
    path = filedialog.askdirectory(title=tr("main.select_root"), parent=parent)
    if path:
        cfg["root_path"] = path
    else:
        default = os.path.join(os.path.expanduser("~"), "PopKnowledge")
        cfg["root_path"] = default
        messagebox.showinfo(tr("app.info"), f"{default}", parent=parent)
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
        mutex_name = "BubbleMind-Instance"
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW(None, False, mutex_name)
        if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            sys.exit(0)
    except Exception:
        pass

    cfg = load_config()
    load_language(cfg.get("language", "zh"))

    root = tk.Tk()
    root.withdraw()

    icon_path_png = os.path.join(os.path.dirname(__file__), "ICON.png")
    icon_path_ico = os.path.join(os.path.dirname(__file__), "ICON.ico")
    root._icon_ref = None

    def _set_icon():
        try:
            if os.path.exists(icon_path_ico):
                root.iconbitmap(default=icon_path_ico)
            if os.path.exists(icon_path_png):
                from PIL import Image, ImageTk
                img = Image.open(icon_path_png)
                root._icon_ref = ImageTk.PhotoImage(img)
                root.iconphoto(True, root._icon_ref)
        except Exception:
            pass

    default_font = get_default_font()
    root.option_add("*Font", (default_font, 10))

    ensure_root_path(root)

    if "--background" in sys.argv:
        start_notifier(root)
        return

    answer = messagebox.askyesno(
        tr("app.name"),
        tr("main.prompt"),
        parent=root,
    )

    root.title(tr("app.name"))
    _set_icon()

    if answer:
        start_notifier(root)
    else:
        root.deiconify()
        _set_icon()
        root.geometry("950x650")
        from updater import check_for_update, show_changelog_if_needed
        check_for_update(root, silent=True)
        root.after(800, lambda: show_changelog_if_needed(root))
        start_editor(root)


if __name__ == "__main__":
    main()
