import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import threading
import subprocess

from db import KnowledgeBase
from config import load_config, save_config


TYPE_OPTIONS = [
    ("普通", "normal", "#3498db", "默认格式"),
    ("提示", "tip", "#1abc9c", "技巧·建议"),
    ("警告", "warning", "#e74c3c", "易错·重点"),
]


class EditorWindow:
    def __init__(self, root, on_close_callback=None):
        self.root = root
        self.on_close_callback = on_close_callback
        self.root.title("知识卡片编辑器")
        self.root.geometry("950x650")
        self.root.minsize(750, 480)

        cfg = load_config()
        self.db = KnowledgeBase(cfg.get("root_path", ""))

        self.current_subject = None
        self.current_chapter = None
        self.current_keyword = None
        self._dirty = False

        self._build_ui()
        self._refresh_tree()
        self._refresh_primary_subjects()

        self.root.bind("<Control-s>", lambda e: self._save_keyword())
        self.root.bind("<Control-S>", lambda e: self._save_keyword())
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        self.pw = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, sashrelief=tk.RAISED,
                                  sashwidth=4, bg="#d0d0d0")
        self.pw.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        left_frame = tk.Frame(self.pw, width=280)
        self.pw.add(left_frame, width=280, minsize=160)

        tk.Label(left_frame, text="知识结构", font=("Microsoft YaHei", 11, "bold"),
                 anchor=tk.W).pack(fill=tk.X, pady=(0, 4))

        tree_frame = tk.Frame(left_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        self.tree = ttk.Treeview(tree_frame, columns=("type",), show="tree")
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.tree_scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=self._on_tree_scroll)
        self.tree.column("#0", width=200)

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Button-3>", self._on_tree_right_click)

        btn_frame1 = tk.Frame(left_frame)
        btn_frame1.pack(fill=tk.X, pady=(4, 0))

        tk.Button(btn_frame1, text="+ 学科", font=("Microsoft YaHei", 9),
                  command=self._add_subject_dialog).pack(side=tk.LEFT, padx=1)
        tk.Button(btn_frame1, text="+ 章节", font=("Microsoft YaHei", 9),
                  command=self._add_chapter_dialog).pack(side=tk.LEFT, padx=1)
        tk.Button(btn_frame1, text="+ 关键词", font=("Microsoft YaHei", 9),
                  command=self._add_keyword_dialog).pack(side=tk.LEFT, padx=1)
        tk.Button(btn_frame1, text="重命名", font=("Microsoft YaHei", 9),
                  command=self._rename_selected).pack(side=tk.RIGHT, padx=1)
        tk.Button(btn_frame1, text="删除", font=("Microsoft YaHei", 9), fg="red",
                  command=self._delete_selected).pack(side=tk.RIGHT, padx=1)

        right_frame = tk.Frame(self.pw)
        self.pw.add(right_frame, width=600, minsize=300)

        self._build_form(right_frame)

        bottom_frame = tk.Frame(self.root)
        bottom_frame.pack(fill=tk.X, padx=6, pady=(0, 6))
        self._bottom_frame = bottom_frame
        tk.Button(bottom_frame, text="更改保存根路径...", font=("Microsoft YaHei", 9),
                  command=self._change_root_path).pack(side=tk.LEFT)
        self.path_label = tk.Label(bottom_frame, text="", font=("Microsoft YaHei", 8),
                                   fg="gray", anchor=tk.W)
        self.path_label.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)
        self._git_btn = None
        self._git_hint = None
        self._update_path_label()

    def _build_form(self, parent):
        scroll_area = tk.Frame(parent, bg="#fafafa")
        scroll_area.pack(fill=tk.BOTH, expand=True)

        self.form_canvas = tk.Canvas(scroll_area, bg="#fafafa", highlightthickness=0)
        self.form_scrollbar = ttk.Scrollbar(scroll_area, orient=tk.VERTICAL,
                                            command=self.form_canvas.yview)
        self.form_canvas.configure(yscrollcommand=self.form_scrollbar.set)

        self.form_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.form_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.form_container = tk.Frame(self.form_canvas, bg="#fafafa")
        self.form_canvas.create_window((0, 0), window=self.form_container, anchor="nw",
                                        tags="form_window")

        def _on_container_configure(event):
            self.form_canvas.configure(scrollregion=self.form_canvas.bbox("all"))
        self.form_container.bind("<Configure>", _on_container_configure)

        def _on_canvas_configure(event):
            self.form_canvas.itemconfig("form_window", width=event.width)
        self.form_canvas.bind("<Configure>", _on_canvas_configure)

        def _on_mousewheel(event):
            self.form_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        self.form_container.bind("<Enter>", lambda e: self.form_container.bind_all(
            "<MouseWheel>", _on_mousewheel))
        self.form_container.bind("<Leave>", lambda e: self.form_container.unbind_all(
            "<MouseWheel>"))

        self.empty_label = tk.Label(
            self.form_container, text="请在左侧选择一个关键词进行编辑",
            font=("Microsoft YaHei", 12), fg="gray", bg="#fafafa"
        )
        self.empty_label.pack(expand=True)

        self.form_frame = tk.Frame(self.form_container, bg="#fafafa")

        tk.Label(self.form_frame, text="主要复习科目", font=("Microsoft YaHei", 10, "bold"),
                 bg="#fafafa").pack(anchor=tk.W, pady=(4, 0))
        subject_frame = tk.Frame(self.form_frame, bg="#fafafa")
        subject_frame.pack(fill=tk.X, pady=(2, 6))
        self.primary_subject_var = tk.StringVar(value="")
        self.primary_subject_combo = ttk.Combobox(
            subject_frame, textvariable=self.primary_subject_var,
            font=("Microsoft YaHei", 10), state="readonly", width=30
        )
        self.primary_subject_combo.pack(side=tk.LEFT)
        self.primary_subject_combo.bind("<<ComboboxSelected>>", self._on_primary_subject_changed)
        tk.Button(subject_frame, text="刷新列表", font=("Microsoft YaHei", 8),
                  command=self._refresh_primary_subjects).pack(side=tk.LEFT, padx=(6, 0))

        tk.Label(self.form_frame, text="关键词", font=("Microsoft YaHei", 10, "bold"),
                 bg="#fafafa").pack(anchor=tk.W, pady=(4, 0))
        self.keyword_entry = tk.Entry(self.form_frame, font=("Microsoft YaHei", 11))
        self.keyword_entry.pack(fill=tk.X, pady=(2, 6), ipady=3)
        self.keyword_entry.bind("<KeyRelease>", lambda e: setattr(self, '_dirty', True))

        tk.Label(self.form_frame, text="知识内容", font=("Microsoft YaHei", 10, "bold"),
                 bg="#fafafa").pack(anchor=tk.W)
        text_frame = tk.Frame(self.form_frame)
        text_frame.pack(fill=tk.BOTH, expand=True, pady=(2, 4))

        self.knowledge_text = tk.Text(text_frame, font=("Microsoft YaHei", 10),
                                       wrap=tk.WORD, relief=tk.SUNKEN, borderwidth=1,
                                       undo=True)
        self.knowledge_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.knowledge_text.bind("<KeyRelease>", lambda e: setattr(self, '_dirty', True))

        self.text_scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL,
                                             command=self.knowledge_text.yview)
        self.knowledge_text.configure(yscrollcommand=self._on_text_scroll)

        bottom_bar = tk.Frame(parent, bg="#fafafa")
        bottom_bar.pack(fill=tk.X, side=tk.BOTTOM)

        legend_frame = tk.Frame(bottom_bar, bg="#fafafa")
        legend_frame.pack(fill=tk.X, pady=(4, 2))
        tk.Label(legend_frame, text="行内标记语法:", font=("Microsoft YaHei", 8, "bold"),
                 fg="#888", bg="#fafafa").pack(side=tk.LEFT)
        for tag, desc, fg in [
            ("**加粗**", "强调", "#3498db"),
            ("!!警告!!", "重要", "#e74c3c"),
            ("??提示??", "提示", "#27ae60"),
            ("[[链接]]", "跳转", "#2980b9"),
        ]:
            lbl = tk.Label(legend_frame, text=f"  {tag}={desc}",
                           font=("Microsoft YaHei", 8), fg=fg, bg="#fafafa")
            lbl.pack(side=tk.LEFT, padx=(0, 6))
        lbl2 = tk.Label(legend_frame, text="  -列表=列表",
                        font=("Microsoft YaHei", 8), fg="#8e44ad", bg="#fafafa")
        lbl2.pack(side=tk.LEFT, padx=(0, 6))

        type_line = tk.Frame(bottom_bar, bg="#fafafa")
        type_line.pack(fill=tk.X, pady=(2, 2))

        tk.Label(type_line, text="整卡格式:", font=("Microsoft YaHei", 10, "bold"),
                 bg="#fafafa", anchor=tk.W).pack(fill=tk.X, pady=(0, 4))
        self.type_var = tk.StringVar(value="normal")
        selector = self._build_type_selector(type_line, self.type_var)
        selector.pack(fill=tk.X)

        btn_frame = tk.Frame(bottom_bar, bg="#fafafa")
        btn_frame.pack(fill=tk.X, pady=(4, 6))

        self.btn_save = tk.Button(btn_frame, text="保存", font=("Microsoft YaHei", 11, "bold"),
                                  bg="#3498db", fg="white", relief=tk.FLAT,
                                  padx=30, pady=5, cursor="hand2",
                                  command=self._save_keyword)
        self.btn_save.pack(side=tk.RIGHT, padx=(0, 4))

    def _update_path_label(self):
        cfg = load_config()
        self.path_label.config(text=f"根路径: {cfg.get('root_path', '未设置')}")
        self._update_git_button()

    def _update_git_button(self):
        if self._git_btn is not None:
            self._git_btn.destroy()
            self._git_btn = None
        if self._git_hint is not None:
            self._git_hint.destroy()
            self._git_hint = None
        root_path = load_config().get("root_path", "")
        if root_path and os.path.isdir(os.path.join(root_path, ".git")):
            self._git_btn = tk.Button(
                self._bottom_frame, text="上传到 GitHub",
                font=("Microsoft YaHei", 9), fg="white", bg="#2c3e50",
                relief=tk.FLAT, padx=10, cursor="hand2",
                command=self._git_push
            )
            self._git_btn.pack(side=tk.RIGHT, padx=(4, 0))
        elif root_path:
            bg = self._bottom_frame.cget("bg")
            self._git_hint = tk.Label(
                self._bottom_frame,
                text="未检测到Git仓库，可执行 git init 启用自动上传",
                font=("Microsoft YaHei", 8), fg="#aaa", bg=bg,
            )
            self._git_hint.pack(side=tk.RIGHT, padx=(4, 0))

    def _git_push(self):
        root_path = load_config().get("root_path", "")
        if not root_path or not os.path.isdir(os.path.join(root_path, ".git")):
            return
        if self._git_btn is None:
            return
        self._git_btn.config(text="上传中...", state=tk.DISABLED)
        def worker():
            try:
                subprocess.run(["git", "add", "."], cwd=root_path, check=True,
                               capture_output=True, text=True)
                subprocess.run(["git", "commit", "-m", "auto update"], cwd=root_path,
                               capture_output=True, text=True)
                subprocess.run(["git", "push"], cwd=root_path, check=True,
                               capture_output=True, text=True)
                self.root.after(0, self._git_success)
            except subprocess.CalledProcessError as e:
                self.root.after(0, lambda err=e: self._git_fail(err))
            except Exception as e:
                self.root.after(0, lambda err=e: self._git_error(str(err)))
        threading.Thread(target=worker, daemon=True).start()

    def _git_success(self):
        if self._git_btn is not None:
            self._git_btn.config(text="上传到 GitHub", state=tk.NORMAL)
        messagebox.showinfo("GitHub 上传", "上传成功")

    def _git_fail(self, err):
        if self._git_btn is not None:
            self._git_btn.config(text="上传到 GitHub", state=tk.NORMAL)
        msg = err.stderr.strip() or err.stdout.strip() or str(err)
        if "nothing to commit" in msg:
            messagebox.showinfo("GitHub 上传", "没有需要上传的改动")
        elif "could not read" in msg.lower() or "failed to push" in msg.lower():
            messagebox.showerror("GitHub 上传失败", f"推送失败，请检查远程仓库配置:\n{msg}")
        else:
            messagebox.showerror("GitHub 上传失败", msg)

    def _git_error(self, msg):
        if self._git_btn is not None:
            self._git_btn.config(text="上传到 GitHub", state=tk.NORMAL)
        messagebox.showerror("GitHub 上传失败", msg)

    def _update_type_color(self):
        pass

    def _build_type_selector(self, parent, variable, btn_size=(130, 44)):
        frame = tk.Frame(parent, bg=parent.cget("bg") if parent.cget("bg") else "#fafafa")

        def _lighten(hex_color, factor):
            r = int(hex_color[1:3], 16)
            g = int(hex_color[3:5], 16)
            b = int(hex_color[5:7], 16)
            r = int(r + (255 - r) * factor)
            g = int(g + (255 - g) * factor)
            b = int(b + (255 - b) * factor)
            return f"#{r:02x}{g:02x}{b:02x}"

        def _darken(hex_color, factor):
            r = int(hex_color[1:3], 16)
            g = int(hex_color[3:5], 16)
            b = int(hex_color[5:7], 16)
            r = int(r * (1 - factor))
            g = int(g * (1 - factor))
            b = int(b * (1 - factor))
            return f"#{r:02x}{g:02x}{b:02x}"

        def _set_colors(bf, inner, bg, border, thickness):
            bf.configure(bg=bg, highlightbackground=border, highlightthickness=thickness)
            inner.configure(bg=bg)
            for ch in inner.winfo_children():
                ch.configure(bg=bg)

        def update_style(*_):
            for bf, inner, val, color in buttons:
                if variable.get() == val:
                    _set_colors(bf, inner, color, "#2c3e50", 2)
                else:
                    tint = _lighten(color, 0.7)
                    _set_colors(bf, inner, tint, "#d0d0d0", 1)

        buttons = []
        for label, val, color, desc in TYPE_OPTIONS:
            btn_frame = tk.Frame(frame, bg="#fafafa", cursor="hand2",
                                 highlightbackground="#c0c0c0", highlightthickness=1)
            inner = tk.Frame(btn_frame, bg=color)
            inner.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
            tk.Label(inner, text=label, font=("Microsoft YaHei", 12, "bold"),
                     fg="white", bg=color).pack(anchor=tk.W, padx=(10, 4), pady=(4, 0))
            tk.Label(inner, text=desc, font=("Microsoft YaHei", 8),
                     fg="#e8f0ff", bg=color).pack(anchor=tk.W, padx=(10, 4), pady=(0, 4))

            def make_handlers(v, c, bf, inner):
                def on_enter(e):
                    if variable.get() != v:
                        _set_colors(bf, inner, _darken(c, 0.1), "#b0b0b0", 1)
                def on_leave(e):
                    if variable.get() != v:
                        update_style()
                def on_press(e):
                    _set_colors(bf, inner, _darken(c, 0.25), "#1a252f", 2)
                def on_release(e):
                    variable.set(v)
                return on_enter, on_leave, on_press, on_release

            enter_h, leave_h, press_h, release_h = make_handlers(val, color, btn_frame, inner)
            for widget in [btn_frame, inner] + inner.winfo_children():
                widget.bind("<Enter>", enter_h)
                widget.bind("<Leave>", leave_h)
                widget.bind("<Button-1>", press_h)
                widget.bind("<ButtonRelease-1>", release_h)

            buttons.append((btn_frame, inner, val, color))
            btn_frame.pack(side=tk.LEFT, padx=5, pady=2)

        variable.trace_add("write", update_style)
        self.root.after(50, update_style)
        return frame

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        for subject in self.db.list_subjects():
            sid = self.tree.insert("", tk.END, text=f"📚 {subject}",
                                    values=("subject",), open=True)
            for chapter in self.db.list_chapters(subject):
                cid = self.tree.insert(sid, tk.END, text=f"📖 {chapter}",
                                       values=("chapter",), open=True)
                for kw in self.db.list_keywords(subject, chapter):
                    self.tree.insert(cid, tk.END, text=f"💡 {kw}",
                                     values=("keyword",))
        self._refresh_primary_subjects()

    def _on_tree_scroll(self, first, last):
        self.tree_scrollbar.set(first, last)
        try:
            if first == "0.0" and last == "1.0":
                self.tree_scrollbar.pack_forget()
            else:
                self.tree_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        except tk.TclError:
            pass

    def _on_text_scroll(self, first, last):
        self.text_scrollbar.set(first, last)
        try:
            if first == "0.0" and last == "1.0":
                self.text_scrollbar.pack_forget()
            else:
                self.text_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        except tk.TclError:
            pass

    def _on_tree_select(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        item = sel[0]
        vals = self.tree.item(item, "values")
        typ = vals[0] if vals else ""
        text = self._strip_emoji(self.tree.item(item, "text"))

        if typ == "subject":
            self.current_subject = text
            self.current_chapter = None
            self.current_keyword = None
            self._show_empty("请选择一个章节或关键词")
        elif typ == "chapter":
            self.current_chapter = text
            self.current_keyword = None
            self._show_empty("请选择一个关键词进行编辑")
        elif typ == "keyword":
            parent_id = self.tree.parent(item)
            grandparent_id = self.tree.parent(parent_id)
            if grandparent_id:
                self.current_subject = self._strip_emoji(
                    self.tree.item(grandparent_id, "text"))
            if parent_id:
                self.current_chapter = self._strip_emoji(
                    self.tree.item(parent_id, "text"))
            self.current_keyword = text
            self._load_keyword()

    @staticmethod
    def _strip_emoji(text):
        return text.split(" ", 1)[-1] if " " in text else text

    def _show_empty(self, msg=""):
        self.empty_label.pack(expand=True)
        self.form_frame.pack_forget()
        self.empty_label.config(text=msg if msg else "请选择一个关键词进行编辑")

    def _show_form(self):
        self.empty_label.pack_forget()
        self.form_frame.pack(fill=tk.BOTH, expand=True)

    def _load_keyword(self):
        if not self.current_subject or not self.current_chapter or not self.current_keyword:
            self._show_empty()
            return
        data = self.db.get_keyword_data(
            self.current_subject, self.current_chapter, self.current_keyword
        )
        if data is None:
            self._show_empty("未找到数据")
            return

        self._show_form()
        self.keyword_entry.delete(0, tk.END)
        self.keyword_entry.insert(0, data.get("keyword", ""))
        self.knowledge_text.config(state=tk.NORMAL)
        self.knowledge_text.delete("1.0", tk.END)
        self.knowledge_text.insert("1.0", data.get("knowledge", ""))
        kt = data.get("type", "normal")
        self.type_var.set(kt)
        self._dirty = False
        self.root.after(50, self.knowledge_text.focus_set)

    def _save_keyword(self):
        if not self.current_subject or not self.current_chapter or not self.current_keyword:
            messagebox.showwarning("提示", "请先选择一个关键词")
            return
        kw = self.keyword_entry.get().strip()
        knowledge = self.knowledge_text.get("1.0", tk.END).strip()
        kt = self.type_var.get()
        if not kw or not knowledge:
            messagebox.showwarning("提示", "关键词和内容不能为空")
            return

        renamed = kw != self.current_keyword
        if renamed:
            old_kw = self.current_keyword

        self.db.save_keyword(self.current_subject, self.current_chapter, kw, knowledge, kt)

        if renamed:
            old_path = self.db.get_keyword_path(
                self.current_subject, self.current_chapter, old_kw)
            if os.path.exists(old_path):
                os.remove(old_path)
            self.current_keyword = kw
            self._refresh_tree()
            self._select_keyword_in_tree(kw)
        else:
            self.current_keyword = kw
            data = self.db.get_keyword_data(
                self.current_subject, self.current_chapter, self.current_keyword)
            if data:
                self._show_form()
                self.type_var.set(data.get("type", "normal"))

        self._dirty = False
        messagebox.showinfo("成功", "保存成功")

    def _select_keyword_in_tree(self, keyword):
        for item in self.tree.get_children(""):
            for child in self.tree.get_children(item):
                for grand in self.tree.get_children(child):
                    if self._strip_emoji(self.tree.item(grand, "text")) == keyword:
                        self.tree.see(item)
                        self.tree.see(child)
                        self.tree.selection_set(grand)
                        self.tree.see(grand)
                        return

    def navigate_to_keyword(self, keyword):
        self._select_keyword_in_tree(keyword)

    def _refresh_primary_subjects(self):
        from config import load_config
        subjects = [""] + self.db.list_subjects()
        self.primary_subject_combo["values"] = subjects
        display = {"": "全部科目"}
        for s in subjects:
            display[s] = s if s else "全部科目"
        current = load_config().get("primary_subject", "")
        if current not in subjects and current != "":
            current = ""
        self.primary_subject_var.set(current)

    def _on_primary_subject_changed(self, event):
        from config import load_config, save_config
        cfg = load_config()
        cfg["primary_subject"] = self.primary_subject_var.get()
        save_config(cfg)

    def _add_subject_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("添加学科")
        dialog.geometry("350x120")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        tk.Label(dialog, text="学科名称:", font=("Microsoft YaHei", 10)).pack(pady=(12, 4))
        entry = tk.Entry(dialog, font=("Microsoft YaHei", 11))
        entry.pack(padx=20, fill=tk.X, ipady=2)
        entry.focus_set()

        def confirm():
            name = entry.get().strip()
            if name:
                self.db.add_subject(name)
                self._refresh_tree()
                dialog.destroy()
            else:
                messagebox.showwarning("提示", "名称不能为空")

        tk.Button(dialog, text="确定", font=("Microsoft YaHei", 10),
                  command=confirm).pack(pady=(8, 0))
        dialog.bind("<Return>", lambda e: confirm())

    def _add_chapter_dialog(self):
        if not self.current_subject:
            messagebox.showwarning("提示", "请先选择一个学科")
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("添加章节")
        dialog.geometry("350x120")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        tk.Label(dialog, text=f"学科: {self.current_subject}", font=("Microsoft YaHei", 9),
                 fg="gray").pack(pady=(8, 0))
        tk.Label(dialog, text="章节名称:", font=("Microsoft YaHei", 10)).pack(pady=(4, 0))
        entry = tk.Entry(dialog, font=("Microsoft YaHei", 11))
        entry.pack(padx=20, fill=tk.X, ipady=2)
        entry.focus_set()

        def confirm():
            name = entry.get().strip()
            if name:
                self.db.add_chapter(self.current_subject, name)
                self._refresh_tree()
                dialog.destroy()
            else:
                messagebox.showwarning("提示", "名称不能为空")

        tk.Button(dialog, text="确定", font=("Microsoft YaHei", 10),
                  command=confirm).pack(pady=(8, 0))
        dialog.bind("<Return>", lambda e: confirm())

    def _add_keyword_dialog(self):
        if not self.current_subject or not self.current_chapter:
            messagebox.showwarning("提示", "请先选择一个章节")
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("添加关键词")
        dialog.geometry("450x340")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        tk.Label(dialog, text=f"学科: {self.current_subject}  >  {self.current_chapter}",
                 font=("Microsoft YaHei", 9), fg="gray").pack(pady=(6, 0))

        tk.Label(dialog, text="关键词:", font=("Microsoft YaHei", 10)).pack(pady=(4, 0))
        kw_entry = tk.Entry(dialog, font=("Microsoft YaHei", 11))
        kw_entry.pack(padx=20, fill=tk.X, ipady=2)
        kw_entry.focus_set()

        tk.Label(dialog, text="知识内容:", font=("Microsoft YaHei", 10)).pack(pady=(4, 0))
        txt = tk.Text(dialog, font=("Microsoft YaHei", 10), height=3, wrap=tk.WORD)
        txt.pack(padx=20, fill=tk.X, pady=(2, 4))

        tk.Label(dialog, text="格式类型（影响弹出卡片的配色）:", font=("Microsoft YaHei", 9),
                 fg="#666").pack(pady=(4, 0))
        type_var = tk.StringVar(value="normal")
        selector = self._build_type_selector(dialog, type_var)
        selector.pack(pady=(2, 4))

        def confirm():
            kw = kw_entry.get().strip()
            knowledge = txt.get("1.0", tk.END).strip()
            if kw and knowledge:
                self.db.save_keyword(
                    self.current_subject, self.current_chapter,
                    kw, knowledge, type_var.get())
                self._refresh_tree()
                self._select_keyword_in_tree(kw)
                dialog.destroy()
            else:
                messagebox.showwarning("提示", "关键词和内容不能为空")

        tk.Button(dialog, text="确定", font=("Microsoft YaHei", 10), bg="#3498db",
                  fg="white", relief=tk.FLAT, padx=20, pady=4,
                  command=confirm).pack(pady=(6, 0))
        dialog.bind("<Return>", lambda e: confirm())

    def _delete_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        item = sel[0]
        vals = self.tree.item(item, "values")
        typ = vals[0] if vals else ""
        text = self._strip_emoji(self.tree.item(item, "text"))

        if typ == "subject":
            if messagebox.askyesno("确认", f"确定要删除学科「{text}」及其所有内容？"):
                self.db.delete_subject(text)
                self._refresh_tree()
                self._show_empty()
        elif typ == "chapter":
            if self.current_subject and messagebox.askyesno("确认", f"确定要删除章节「{text}」及其所有内容？"):
                self.db.delete_chapter(self.current_subject, text)
                self._refresh_tree()
                self.current_chapter = None
                self._show_empty()
        elif typ == "keyword":
            if self.current_subject and self.current_chapter:
                if messagebox.askyesno("确认", f"确定要删除关键词「{text}」？"):
                    self.db.delete_keyword(self.current_subject, self.current_chapter, text)
                    self._refresh_tree()
                    self.current_keyword = None
                    self._show_empty()

    def _on_tree_right_click(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            menu = tk.Menu(self.root, tearoff=0, font=("Microsoft YaHei", 9))
            menu.add_command(label="重命名", command=self._rename_selected)
            menu.add_command(label="删除", command=self._delete_selected)
            menu.post(event.x_root, event.y_root)

    def _rename_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        item = sel[0]
        vals = self.tree.item(item, "values")
        typ = vals[0] if vals else ""
        old_name = self._strip_emoji(self.tree.item(item, "text"))

        if typ == "subject":
            self._rename_subject(item, old_name)
        elif typ == "chapter":
            self._rename_chapter(item, old_name)
        elif typ == "keyword":
            self._rename_keyword(item, old_name)

    def _rename_subject(self, item, old_name):
        dialog = tk.Toplevel(self.root)
        dialog.title("重命名学科")
        dialog.geometry("350x120")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        tk.Label(dialog, text="学科名称:", font=("Microsoft YaHei", 10)).pack(pady=(12, 4))
        entry = tk.Entry(dialog, font=("Microsoft YaHei", 11))
        entry.insert(0, old_name)
        entry.pack(padx=20, fill=tk.X, ipady=2)
        entry.select_range(0, tk.END)
        entry.focus_set()

        def confirm():
            new_name = entry.get().strip()
            if not new_name:
                messagebox.showwarning("提示", "名称不能为空")
                return
            if new_name == old_name:
                dialog.destroy()
                return
            self.db.rename_subject(old_name, new_name)
            self._refresh_tree()
            self.current_subject = new_name
            self.current_chapter = None
            self.current_keyword = None
            self._show_empty()
            dialog.destroy()

        tk.Button(dialog, text="确定", font=("Microsoft YaHei", 10),
                  command=confirm).pack(pady=(8, 0))
        dialog.bind("<Return>", lambda e: confirm())

    def _rename_chapter(self, item, old_name):
        parent_id = self.tree.parent(item)
        if not parent_id:
            return
        subject = self._strip_emoji(self.tree.item(parent_id, "text"))

        dialog = tk.Toplevel(self.root)
        dialog.title("重命名章节")
        dialog.geometry("350x120")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        tk.Label(dialog, text=f"学科: {subject}", font=("Microsoft YaHei", 9),
                 fg="gray").pack(pady=(8, 0))
        tk.Label(dialog, text="章节名称:", font=("Microsoft YaHei", 10)).pack(pady=(4, 0))
        entry = tk.Entry(dialog, font=("Microsoft YaHei", 11))
        entry.insert(0, old_name)
        entry.pack(padx=20, fill=tk.X, ipady=2)
        entry.select_range(0, tk.END)
        entry.focus_set()

        def confirm():
            new_name = entry.get().strip()
            if not new_name:
                messagebox.showwarning("提示", "名称不能为空")
                return
            if new_name == old_name:
                dialog.destroy()
                return
            self.db.rename_chapter(subject, old_name, new_name)
            self._refresh_tree()
            self.current_chapter = new_name
            self.current_keyword = None
            self._show_empty()
            dialog.destroy()

        tk.Button(dialog, text="确定", font=("Microsoft YaHei", 10),
                  command=confirm).pack(pady=(8, 0))
        dialog.bind("<Return>", lambda e: confirm())

    def _rename_keyword(self, item, old_name):
        messagebox.showinfo("提示", "在右侧编辑区修改关键词名称后点击「保存」即可重命名")

    def _change_root_path(self):
        path = filedialog.askdirectory(title="选择知识数据库根路径")
        if path:
            cfg = load_config()
            cfg["root_path"] = path
            save_config(cfg)
            self.db = KnowledgeBase(path)
            self.current_subject = None
            self.current_chapter = None
            self.current_keyword = None
            self._refresh_tree()
            self._show_empty()
            self._update_path_label()

    def _on_close(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        if self.on_close_callback:
            self.on_close_callback()


def launch_editor(root=None, on_close=None):
    if root is None:
        root = tk.Tk()
        app = EditorWindow(root, on_close)
        root.mainloop()
    else:
        app = EditorWindow(root, on_close)
        return app
