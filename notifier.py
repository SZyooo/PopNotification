import tkinter as tk
import os
import threading
import queue
import time
from datetime import datetime

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
        self._primary_subject = cfg.get("primary_subject", "")

        self.active_popups = []
        self.suppressed_items = set()
        self._active_item_keys = set()
        self._today_date = datetime.now().date()
        self._today_popup_counts = {}
        self.running = True
        self._editor_window = None
        self._tray_icon = None
        self._cmd_queue = queue.Queue()
        self._next_check_at = time.time() + self.check_interval_ms / 1000
        self._tray_status = ""

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

            def set_subject(subj):
                def action(icon, item):
                    self._cmd_queue.put(lambda: self._set_primary_subject(subj))
                return action

            def build_subject_items():
                items = [pystray.MenuItem(
                    "全部科目", set_subject(""),
                    checked=lambda item: self._primary_subject == ""
                )]
                for s in self.db.list_subjects():
                    items.append(pystray.MenuItem(
                        s, set_subject(s),
                        checked=lambda item, sub=s: self._primary_subject == sub
                    ))
                return items

            menu = pystray.Menu(
                pystray.MenuItem("打开编辑器", on_open, default=True),
                pystray.MenuItem("立即检查", on_check),
                pystray.MenuItem("复习科目", pystray.Menu(build_subject_items)),
                pystray.MenuItem("统计信息", on_stats),
                pystray.MenuItem("退出", on_quit),
            )

            self._tray_icon = pystray.Icon("PopNotification", img, "知识提醒", menu)
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
            self._check_now(silent=False)
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
            if self._tray_status:
                text = self._tray_status
            else:
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

    def _set_primary_subject(self, subject):
        self._primary_subject = subject
        from config import save_config
        cfg = load_config()
        cfg["primary_subject"] = subject
        save_config(cfg)

    def _check_now(self, silent=False):
        try:
            self._ensure_date_reset()
            items = self.db.get_all_due_items()
            if self._primary_subject:
                items = [it for it in items if it["subject"] == self._primary_subject]
            candidates = [
                it for it in items
                if (it["subject"], it["chapter"], it["keyword"]) not in self.suppressed_items
                and (it["subject"], it["chapter"], it["keyword"]) not in self._active_item_keys
            ]
            best = self._pick_best(candidates)
            if best:
                if self.active_popups:
                    self._tray_status = f"队列待复习: {len(candidates)} 张卡片"
                    self.root.after(10000, self._clear_tray_status)
                    return
                key = (best["subject"], best["chapter"], best["keyword"])
                self._today_popup_counts[key] = self._today_popup_counts.get(key, 0) + 1
                self.root.after(0, lambda it=best: self._create_popup(it))
                cnt = self._today_popup_counts[key]
                self._tray_status = f"正在弹出: {best['keyword']}" + (f" (今日第{cnt}次)" if cnt > 1 else "")
                self.root.after(8000, self._clear_tray_status)
                if not silent:
                    self._show_balloon(self._tray_status)
            else:
                self._tray_status = "暂无到期卡片" if not items else f"找到 {len(items)} 条待复习"
                self.root.after(10000, self._clear_tray_status)
        except Exception:
            import traceback
            traceback.print_exc()

    def _clear_tray_status(self):
        self._tray_status = ""

    def _ensure_date_reset(self):
        today = datetime.now().date()
        if today != self._today_date:
            self._today_date = today
            self._today_popup_counts.clear()

    def _pick_best(self, items):
        if not items:
            return None

        def score(item):
            level = item.get("memory", {}).get("level", 0)
            key = (item["subject"], item["chapter"], item["keyword"])

            # 记忆等级越低越优先 (0=最优先, 5=最不优先)
            level_score = 5 - level

            # 距上次复习时间加分
            last = item.get("memory", {}).get("last_review")
            time_bonus = 0.0
            if last:
                try:
                    hrs = (datetime.now() - datetime.fromisoformat(last)).total_seconds() / 3600
                    time_bonus = min(hrs / 24, 3.0)
                except Exception:
                    pass

            # 今日已弹次数扣分
            pop_penalty = self._today_popup_counts.get(key, 0) * 3

            return level_score + time_bonus - pop_penalty

        return max(items, key=score)

    def _show_balloon(self, msg):
        if self._tray_icon:
            try:
                self._tray_icon.notify(msg, "知识提醒")
            except Exception:
                pass

    def _create_popup(self, item):
        item_key = (item["subject"], item["chapter"], item["keyword"])
        self._active_item_keys.add(item_key)
        def on_close(skip_next=False, suppress=False):
            self._on_popup_close(item_key, popup, skip_next, suppress)
        def on_edit(item_data):
            self._open_link(item_data["keyword"])
        popup = show_popup(self.root, item, self._on_review, on_close,
                           on_link=self._open_link, on_edit=on_edit)
        self.active_popups.append(popup)

    def _on_review(self, item_data, new_mem, action):
        try:
            self.db.update_memory(item_data["subject"], item_data["chapter"],
                                  item_data["keyword"], new_mem)
        except Exception:
            pass

    def _on_popup_close(self, item_key, popup, skip_next=False, suppress=False):
        self._active_item_keys.discard(item_key)
        if popup in self.active_popups:
            self.active_popups.remove(popup)
        if suppress:
            self.suppressed_items.add(item_key)
        if not skip_next:
            self.root.after(100, self._check_now)

    def _open_editor(self):
        if self._editor_window is not None:
            try:
                self._editor_window.lift()
                self._editor_window.focus_force()
                return
            except tk.TclError:
                self._editor_window = None
                self._editor_app = None
        import editor
        top = tk.Toplevel(self.root)
        self._editor_window = top
        def on_close():
            self._editor_window = None
            self._editor_app = None
        self._editor_app = editor.launch_editor(top, on_close=on_close)

    def _open_link(self, keyword):
        self._open_editor()
        if self._editor_app:
            self._editor_app.navigate_to_keyword(keyword)

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
