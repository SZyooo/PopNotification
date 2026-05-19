import tkinter as tk
import os
import threading
import queue
import time

from db import KnowledgeBase
from config import load_config
from popup_window import show_popup


class Notifier:
    def __init__(self, root):
        self.root = root
        self.root.withdraw()
        self.root.title("PopNotification - 后台运行")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        cfg = load_config()
        self.db = KnowledgeBase(cfg.get("root_path", ""))
        self.check_interval_ms = max(60000, cfg.get("check_interval_minutes", 5) * 60000)
        self.max_per_check = cfg.get("max_items_per_check", 3)

        self.active_popups = []
        self.suppressed_items = set()
        self.running = True
        self._editor_window = None
        self._tray_icon = None
        self._cmd_queue = queue.Queue()
        self._next_check_at = time.time() + self.check_interval_ms / 1000

        self._setup_tray()
        self._schedule_check()
        self._poll_queue()
        self._update_tray_tooltip()

    def _setup_tray(self):
        try:
            from PIL import Image, ImageDraw, ImageFont
            import pystray

            img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.ellipse([2, 2, 62, 62], fill="#3498db", outline="#2980b9", width=2)
            font = None
            for name in ["segoeui.ttf", "arial.ttf", "msyh.ttc", "C:/Windows/Fonts/msyh.ttc"]:
                try:
                    font = ImageFont.truetype(name, 26)
                    break
                except Exception:
                    continue
            if font is None:
                font = ImageFont.load_default()
            draw.text((10, 16), "PN", fill="white", font=font)

            def on_open(icon, item):
                self._cmd_queue.put(self._open_editor)

            def on_check(icon, item):
                self._cmd_queue.put(self._check_now)

            def on_stats(icon, item):
                self._cmd_queue.put(self._show_stats)

            def on_quit(icon, item):
                self._cmd_queue.put(self._quit_app)
                icon.stop()

            menu = pystray.Menu(
                pystray.MenuItem("打开编辑器", on_open),
                pystray.MenuItem("立即检查", on_check),
                pystray.MenuItem("统计信息", on_stats),
                pystray.MenuItem("退出", on_quit),
            )

            self._tray_icon = pystray.Icon("PopNotification", img, "知识提醒", menu,
                                           on_double_click=lambda icon: self._cmd_queue.put(self._open_editor))
            t = threading.Thread(target=self._tray_icon.run, daemon=True)
            t.start()

        except Exception as e:
            import traceback
            traceback.print_exc()
            self._show_fallback()

    def _show_fallback(self):
        mini_frame = tk.Frame(self.root, bg="#f0f0f0")
        mini_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        tk.Label(mini_frame, text="PopNotification 正在后台运行",
                 font=("Microsoft YaHei", 12)).pack(pady=10)
        tk.Button(mini_frame, text="打开编辑器", font=("Microsoft YaHei", 10),
                  command=self._open_editor).pack(pady=4)
        tk.Button(mini_frame, text="立即检查", font=("Microsoft YaHei", 10),
                  command=self._check_now).pack(pady=4)
        tk.Button(mini_frame, text="退出", font=("Microsoft YaHei", 10),
                  command=self._quit_app).pack(pady=4)
        self.root.deiconify()

    def _schedule_check(self):
        if self.running:
            self._check_now(silent=True)
            self._next_check_at = time.time() + self.check_interval_ms / 1000
            self.root.after(self.check_interval_ms, self._schedule_check)

    def _poll_queue(self):
        if not self.running:
            return
        try:
            while True:
                cmd = self._cmd_queue.get_nowait()
                cmd()
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _update_tray_tooltip(self):
        if not self.running:
            return
        if self._tray_icon:
            remaining = self._next_check_at - time.time()
            if remaining > 0:
                mins = int(remaining // 60)
                secs = int(remaining % 60)
                text = f"下次弹出: {mins}分{secs}秒"
            else:
                text = "正在检查..."
            try:
                self._tray_icon.title = text
            except Exception:
                pass
        self.root.after(2000, self._update_tray_tooltip)

    def _check_now(self, silent=False):
        try:
            items = self.db.get_all_due_items()
            new_items = [it for it in items if it["keyword"] not in self.suppressed_items]
            if new_items:
                self._show_popups(new_items)
                if not silent:
                    self._show_balloon(f"弹出 {min(len(new_items), self.max_per_check)} 条知识卡片")
            elif not silent:
                if not items:
                    self._show_balloon("当前没有到期的知识卡片")
                else:
                    self._show_balloon(f"找到 {len(items)} 条，但已被临时忽略")
        except Exception:
            pass

    def _show_balloon(self, msg):
        if self._tray_icon:
            try:
                self._tray_icon.notify(msg, "知识提醒")
            except Exception:
                pass

    def _show_popups(self, items):
        count = min(len(items), self.max_per_check)
        for i in range(count):
            delay = i * 3000 if count > 1 else 0
            self.root.after(delay, lambda it=items[i]: self._create_popup(it))

    def _create_popup(self, item):
        popup = show_popup(self.root, item, self._on_review, self._on_popup_close)
        self.active_popups.append(popup)

    def _on_review(self, item_data, new_mem, action):
        try:
            self.db.update_memory(item_data["subject"], item_data["chapter"],
                                  item_data["keyword"], new_mem)
        except Exception:
            pass

    def _on_popup_close(self):
        self.active_popups = [p for p in self.active_popups if p is not None]

    def _open_editor(self):
        if self._editor_window is not None:
            try:
                self._editor_window.lift()
                self._editor_window.focus_force()
                return
            except tk.TclError:
                self._editor_window = None
        import editor
        top = tk.Toplevel(self.root)
        self._editor_window = top
        def on_close():
            self._editor_window = None
        editor.launch_editor(top, on_close=on_close)

    def _show_stats(self):
        try:
            stats = self.db.get_stats()
            labels = {0: "陌生", 1: "陌生", 2: "熟悉", 3: "熟悉", 4: "熟记", 5: "熟记"}
            parts = [f"{labels[lv]}({stats['by_level'].get(lv, 0)})" for lv in range(6) if stats['by_level'].get(lv, 0) > 0]
            msg = f"总知识卡片: {stats['total']}\n"
            msg += "掌握分布: " + ", ".join(parts) if parts else "暂无数据"
            from tkinter import messagebox
            messagebox.showinfo("知识统计", msg)
        except Exception:
            pass

    def _quit_app(self):
        self.running = False
        if self._tray_icon:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
            self._tray_icon = None
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass
        os._exit(0)

    def _on_close(self):
        self.root.withdraw()
