import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import threading
import subprocess

from db import KnowledgeBase
from config import load_config, save_config
from i18n import tr, load_language, get_language, LANGUAGES
from popup_window import PopupWindow


class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self._enter)
        widget.bind("<Leave>", self._leave)

    def _enter(self, event):
        x = self.widget.winfo_rootx() + self.widget.winfo_width()
        y = self.widget.winfo_rooty() - 4
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        lbl = tk.Label(self.tip, text=self.text, font=("Microsoft YaHei", 9),
                       bg="#ffffcc", fg="#333", relief=tk.SOLID, borderwidth=1,
                       padx=6, pady=2)
        lbl.pack()
        self.tip.update_idletasks()
        tw = lbl.winfo_reqwidth() + 12
        self.tip.wm_geometry(f"+{x - tw}+{y}")

    def _leave(self, event):
        if self.tip:
            self.tip.destroy()
            self.tip = None


TYPE_OPTIONS = [
    ("popup.type_normal", "normal", "#3498db", "popup.type_normal_desc"),
    ("popup.type_tip", "tip", "#1abc9c", "popup.type_tip_desc"),
    ("popup.type_warning", "warning", "#e74c3c", "popup.type_warning_desc"),
]


def expand_linkmap(text):
    """Parse [linkmap] blocks and replace source words with [[target|word]] links.

    [linkmap]
    source -> target
    源词 → 目标关键词|显示文字
    [/linkmap]
    """
    import re
    mapping = {}
    def _replace(m):
        block = m.group(1)
        for line in block.split('\n'):
            line = line.strip()
            if not line:
                continue
            sep = '->' if '->' in line else ('→' if '→' in line else None)
            if sep is None:
                continue
            parts = line.split(sep, 1)
            if len(parts) != 2:
                continue
            src = parts[0].strip()
            rest = parts[1].strip()
            if '|' in rest:
                target, display = rest.split('|', 1)
                mapping[src] = (target.strip(), display.strip())
            else:
                mapping[src] = (rest, None)
        return ''
    cleaned = re.sub(r'\[linkmap\](.*?)\[/linkmap\]', _replace, text, flags=re.DOTALL)
    if not mapping:
        return cleaned

    result = []
    lines = cleaned.split('\n')
    keys = sorted(mapping.keys(), key=len, reverse=True)
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith('```'):
            result.append(line)
            i += 1
            while i < len(lines):
                result.append(lines[i])
                if lines[i].strip() == '```':
                    i += 1
                    break
                i += 1
            continue
        parts = re.split('(' + '|'.join(re.escape(k) for k in keys) + ')', line)
        new_parts = []
        for part in parts:
            if part in mapping:
                target, display = mapping[part]
                new_parts.append(f'[[{target}|{display or part}]]')
            else:
                new_parts.append(part)
        result.append(''.join(new_parts))
        i += 1
    return '\n'.join(result)


def parse_link(link_text):
    """Parse [[subject::chapter::keyword|display]] or [[keyword|display]] or [[pin:word]]

    Returns dict with keys: keyword/subject/chapter/display, or pin for pins, or None.
    """
    import re
    m = re.match(r'^\[\[([^:\]|]+)::([^:\]|]+)::([^\]|]+)(?:\|([^\]]+))?\]\]$', link_text)
    if m:
        kw = m.group(3)
        return {"keyword": kw, "subject": m.group(1), "chapter": m.group(2), "display": m.group(4) or kw}
    m = re.match(r'^\[\[pin:([^\]]+?)(?:\|[^\]]*)?\]\]$', link_text)
    if m:
        return {"pin": m.group(1)}
    m = re.match(r'^\[\[([^\]|]+)(?:\|([^\]]+))?\]\]$', link_text)
    if m:
        kw = m.group(1)
        return {"keyword": kw, "display": m.group(2) or kw}
    return None


class EditorWindow:
    def __init__(self, root, on_close_callback=None):
        self.root = root
        self.on_close_callback = on_close_callback
        self.root.title(tr("app.name") + " — " + tr("main.editor_title"))
        self.root.geometry("950x650")
        self.root.minsize(750, 480)

        cfg = load_config()
        self.db = KnowledgeBase(cfg.get("root_path", ""))

        self.current_subject = None
        self.current_chapter = None
        self.current_keyword = None
        self._dirty = False
        self._editing_type = None
        self._read_mode = False
        self._nav_stack = []
        self._nav_ignore = False
        self._related_topics = []
        self._related_matches = []
        self._selected_result_idx = -1
        self._preview_popup = None
        self._search_after_id = None
        self._related_sync_after_id = None
        self.search_var = tk.StringVar(value="")
        self._build_ui()
        self._refresh_tree()
        self._refresh_primary_subjects()
        self.root.after(1000, self._cleanup_orphan_images)

        self.root.bind("<Control-s>", lambda e: self._save_keyword())
        self.root.bind("<Control-S>", lambda e: self._save_keyword())
        self.root.bind("<Alt-Left>", lambda e: self._nav_back())
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        self.pw = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, sashrelief=tk.RAISED,
                                  sashwidth=4, bg="#d0d0d0")
        self.pw.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        left_frame = tk.Frame(self.pw, width=280)
        self.pw.add(left_frame, width=280, minsize=160)

        tk.Label(left_frame, text=tr("editor.primary_subject"), font=("Microsoft YaHei", 9, "bold"),
                 anchor=tk.W).pack(fill=tk.X, pady=(6, 0), padx=2)
        subject_frame = tk.Frame(left_frame)
        subject_frame.pack(fill=tk.X, pady=(2, 4))
        self.primary_subject_var = tk.StringVar(value="")
        self.primary_subject_combo = ttk.Combobox(
            subject_frame, textvariable=self.primary_subject_var,
            font=("Microsoft YaHei", 10), state="readonly", width=24
        )
        self.primary_subject_combo.pack(side=tk.LEFT, padx=(2, 0))
        self.primary_subject_combo.bind("<<ComboboxSelected>>", self._on_primary_subject_changed)
        tk.Button(subject_frame, text=tr("editor.refresh"), font=("Microsoft YaHei", 8),
                  command=self._refresh_primary_subjects).pack(side=tk.LEFT, padx=(4, 0))

        tk.Label(left_frame, text=tr("editor.knowledge_structure"), font=("Microsoft YaHei", 11, "bold"),
                 anchor=tk.W).pack(fill=tk.X, pady=(4, 2))

        search_frame = tk.Frame(left_frame)
        search_frame.pack(fill=tk.X, pady=(0, 2), padx=2)
        tk.Label(search_frame, text="🔍", font=("Microsoft YaHei", 9),
                 fg="#999").pack(side=tk.LEFT, padx=(0, 2))
        self.search_entry = tk.Entry(
            search_frame, textvariable=self.search_var,
            font=("Microsoft YaHei", 9), relief=tk.SUNKEN, bd=1
        )
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.search_entry.bind("<KeyRelease>", self._on_search_changed)
        search_clear = tk.Label(search_frame, text="✕",
                                font=("Microsoft YaHei", 9), fg="#999", cursor="hand2")
        search_clear.pack(side=tk.RIGHT, padx=(2, 0))
        search_clear.bind("<Button-1>", self._clear_search)

        tree_frame = tk.Frame(left_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        self.tree = ttk.Treeview(tree_frame, show="tree", selectmode="extended")
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.tree_scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=self._on_tree_scroll)
        self.tree.column("#0", width=200)

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Button-3>", self._on_tree_right_click)

        # Drag-and-drop state
        self._drag_data = {"item": None, "start_y": 0, "dragging": False, "target_item": None}
        self.tree.tag_configure("drag_target", background="#a8e6a8")
        self.tree.bind("<Button-1>", self._on_tree_press, True)
        self.tree.bind("<B1-Motion>", self._on_tree_drag)
        self.tree.bind("<ButtonRelease-1>", self._on_tree_release)

        self._add_btn_frame = tk.Frame(left_frame)
        self._add_btn_frame.pack(fill=tk.X, pady=(4, 0))

        def _make_icon_btn(parent, icon, tooltip, cmd):
            btn = tk.Button(parent, text=icon, font=("Microsoft YaHei", 12),
                            command=cmd, width=3, relief=tk.RAISED, bd=1,
                            cursor="hand2", bg="#f0f0f0", activebackground="#d4e6f1")
            def on_enter(e):
                btn.config(bg="#d4e6f1", relief=tk.RIDGE)
            def on_leave(e):
                btn.config(bg="#f0f0f0", relief=tk.RAISED)
            btn.bind("<Enter>", on_enter)
            btn.bind("<Leave>", on_leave)
            ToolTip(btn, tooltip)
            return btn
        self.btn_add_subject = _make_icon_btn(self._add_btn_frame, "📚", tr("editor.add_subject"), self._add_subject_dialog)
        self.btn_add_chapter = _make_icon_btn(self._add_btn_frame, "📖", tr("editor.add_chapter"), self._add_chapter_dialog)
        self.btn_add_keyword = _make_icon_btn(self._add_btn_frame, "💡", tr("editor.add_keyword"), self._add_keyword_dialog)
        ToolTip(self.btn_add_subject, tr("editor.add_subject"))
        ToolTip(self.btn_add_chapter, tr("editor.add_chapter"))
        ToolTip(self.btn_add_keyword, tr("editor.add_keyword"))

        tk.Button(self._add_btn_frame, text=tr("editor.rename_btn"), font=("Microsoft YaHei", 9),
                  command=self._rename_selected).pack(side=tk.RIGHT, padx=1)
        tk.Button(self._add_btn_frame, text=tr("editor.delete_btn"), font=("Microsoft YaHei", 9), fg="red",
                  command=self._delete_selected).pack(side=tk.RIGHT, padx=1)

        right_frame = tk.Frame(self.pw)
        self.pw.add(right_frame, width=600, minsize=300)

        self._build_form(right_frame)

        bottom_frame = tk.Frame(self.root)
        bottom_frame.pack(fill=tk.X, padx=6, pady=(0, 6))
        self._bottom_frame = bottom_frame
        tk.Button(bottom_frame, text=tr("editor.kb_path"), font=("Microsoft YaHei", 9),
                  command=self._change_root_path).pack(side=tk.LEFT)
        self.path_label = tk.Label(bottom_frame, text="", font=("Microsoft YaHei", 8),
                                   fg="gray", anchor=tk.W)
        self.path_label.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True)

        # Language selector
        lang_frame = tk.Frame(bottom_frame)
        lang_frame.pack(side=tk.RIGHT, padx=(4, 0))
        tk.Label(lang_frame, text=tr("editor.language") + ":", font=("Microsoft YaHei", 8),
                 fg="#888").pack(side=tk.LEFT)
        self._lang_code_to_display = dict(LANGUAGES)
        self._lang_display_to_code = {v: k for k, v in LANGUAGES.items()}
        current_code = get_language()
        current_display = LANGUAGES.get(current_code, "中文")
        self.lang_var = tk.StringVar(value=current_display)
        lang_combo = ttk.Combobox(lang_frame, textvariable=self.lang_var,
                                   values=list(LANGUAGES.values()), state="readonly", width=10)
        lang_combo.pack(side=tk.LEFT, padx=(2, 0))
        lang_combo.bind("<<ComboboxSelected>>", self._on_language_change)

        self._git_btn = None
        self._git_hint = None
        self._git_url_label = None
        self._update_path_label()

    def _build_form(self, parent):
        # Main content area (fills all space above the fixed bottom frame)
        self.form_container = tk.Frame(parent, bg="#fafafa")
        self.form_container.grid(row=0, column=0, sticky="nsew")

        self.empty_label = tk.Label(
            self.form_container, text=tr("editor.empty_select"),
            font=("Microsoft YaHei", 12), fg="gray", bg="#fafafa"
        )
        self.empty_label.pack(expand=True)

        # Keyword editing form
        self.form_frame = tk.Frame(self.form_container, bg="#fafafa")

        tk.Label(self.form_frame, text=tr("editor.keyword_label"), font=("Microsoft YaHei", 10, "bold"),
                 bg="#fafafa").pack(anchor=tk.W, pady=(4, 0))
        self.keyword_entry = tk.Entry(self.form_frame, font=("Microsoft YaHei", 11))
        self.keyword_entry.pack(fill=tk.X, pady=(2, 6), ipady=3)
        self.keyword_entry.bind("<KeyRelease>", lambda e: setattr(self, '_dirty', True))

        tk.Label(self.form_frame, text=tr("editor.knowledge_label"), font=("Microsoft YaHei", 10, "bold"),
                 bg="#fafafa").pack(anchor=tk.W)
        
        text_toolbar = tk.Frame(self.form_frame, bg="#fafafa")
        text_toolbar.pack(fill=tk.X, pady=(0, 2))

        self.nav_back_btn = tk.Button(text_toolbar, text="◀", font=("Microsoft YaHei", 9),
                                      bg="#eee", fg="#555", relief=tk.FLAT, padx=6, cursor="hand2",
                                      state=tk.DISABLED, command=self._nav_back)
        self.nav_back_btn.pack(side=tk.LEFT, padx=(0, 6))

        tk.Button(text_toolbar, text=tr("editor.insert_image"), font=("Microsoft YaHei", 9),
                  bg="#3498db", fg="white", relief=tk.FLAT, padx=8, cursor="hand2",
                  command=self._insert_image_dialog).pack(side=tk.LEFT)
        self.image_status_label = tk.Label(text_toolbar, text="", font=("Microsoft YaHei", 9),
                                           fg="#27ae60", bg="#fafafa")
        self.image_status_label.pack(side=tk.LEFT, padx=(8, 0))
        
        text_frame = tk.Frame(self.form_frame)
        text_frame.pack(fill=tk.BOTH, expand=True, pady=(2, 4))

        self.knowledge_text = tk.Text(text_frame, font=("Microsoft YaHei", 10),
                                       wrap=tk.WORD, relief=tk.SUNKEN, borderwidth=1,
                                       undo=True)
        self.text_scrollbar_y = tk.Scrollbar(text_frame, orient=tk.VERTICAL, width=16,
                                               command=self.knowledge_text.yview)
        # Pack scrollbar first so it anchors to the right edge
        self.text_scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.knowledge_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.knowledge_text.configure(yscrollcommand=self._on_text_scroll_y)
        self.knowledge_text.bind("<KeyRelease>", self._on_knowledge_change)
        self.knowledge_text.bind("<Return>", self._on_enter_in_knowledge)

        # Bottom frame (always visible, contains related topics + bottom bar)
        self.bottom_frame = tk.Frame(parent, bg="#e8f4f8")
        self.bottom_frame.grid(row=1, column=0, sticky="ew")

        # Configure parent grid so form row stretches, bottom row stays at natural height
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        # Related Topics Drawer container (fixed position, not scrollable)
        self.related_outer = tk.Frame(self.bottom_frame, bg="#e8f4f8")
        self._related_drawer_open = False

        # Drawer content panel (above the toggle bar, hidden by default)
        self.related_drawer = tk.Frame(self.related_outer, bg="#e8f4f8")
        # Do not pack here; pack dynamically in _toggle_related_drawer
        self._related_drawer_open = False

        # Separator line at top of drawer
        tk.Frame(self.related_drawer, height=1, bg="#ddd").pack(fill=tk.X)

        # Topics list (top of drawer)
        self.related_canvas = tk.Canvas(self.related_drawer, bg="#e8f4f8", highlightthickness=0,
                                          height=50)
        self.related_scrollbar = ttk.Scrollbar(self.related_drawer, orient=tk.VERTICAL,
                                                command=self.related_canvas.yview)
        self.related_list_inner = tk.Frame(self.related_canvas, bg="#e8f4f8")
        self.related_canvas.configure(yscrollcommand=self.related_scrollbar.set)
        self.related_canvas.create_window((0, 0), window=self.related_list_inner, anchor="nw",
                                           tags="related_window")

        def _on_related_inner_configure(event):
            self.related_canvas.configure(scrollregion=self.related_canvas.bbox("all"))
        self.related_list_inner.bind("<Configure>", _on_related_inner_configure)

        def _on_related_canvas_configure(event):
            self.related_canvas.itemconfig("related_window", width=event.width)
        self.related_canvas.bind("<Configure>", _on_related_canvas_configure)

        self.related_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.related_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Results panel
        self.related_results_outer = tk.Frame(self.related_drawer, bg="#e8f4f8")
        self.related_results_outer.pack(fill=tk.X, pady=(0, 2))
        self.related_results_outer.pack_forget()

        self.related_results_canvas = tk.Canvas(self.related_results_outer, bg="#e8f4f8",
                                                  highlightthickness=0)
        self.related_results_inner = tk.Frame(self.related_results_canvas, bg="#e8f4f8")
        self.related_results_canvas.create_window((0, 0), window=self.related_results_inner,
                                                   anchor="nw", tags="results_window")
        self.related_results_canvas.configure(yscrollcommand=self._on_results_scroll)
        self.related_results_scrollbar = ttk.Scrollbar(self.related_results_outer,
                                                        orient=tk.VERTICAL,
                                                        command=self.related_results_canvas.yview)
        self.related_results_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.related_results_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.related_results_scrollbar.pack_forget()

        def _on_results_inner_configure(event):
            self.related_results_canvas.configure(scrollregion=self.related_results_canvas.bbox("all"))
        self.related_results_inner.bind("<Configure>", _on_results_inner_configure)

        def _on_results_canvas_configure(event):
            self.related_results_canvas.itemconfig("results_window", width=event.width)
        self.related_results_canvas.bind("<Configure>", _on_results_canvas_configure)

        self.related_results_canvas.bind("<Enter>", lambda e: self.related_results_canvas.bind_all(
            "<MouseWheel>", self._on_results_mousewheel))
        self.related_results_canvas.bind("<Leave>", lambda e: self.related_results_canvas.unbind_all(
            "<MouseWheel>"))

        # Toggle bar (always visible at bottom) — contains label + search + add
        self.related_toggle_bar = tk.Frame(self.related_outer, bg="#e8f4f8", height=30)
        self.related_toggle_bar.pack(fill=tk.X, side=tk.BOTTOM)
        self.related_toggle_bar.pack_propagate(False)

        self.related_toggle_btn = tk.Button(self.related_toggle_bar, text="▴ " + tr("editor.related_topics"),
                                            font=("Microsoft YaHei", 9, "bold"), fg="#555",
                                            bg="#e8f4f8", relief=tk.FLAT, cursor="hand2",
                                            command=self._toggle_related_drawer)
        self.related_toggle_btn.pack(side=tk.LEFT, padx=4)
        self.related_count_lbl = tk.Label(self.related_toggle_bar, text="(0)", font=("Microsoft YaHei", 8),
                                          fg="#aaa", bg="#e8f4f8")
        self.related_count_lbl.pack(side=tk.LEFT, padx=(0, 8))

        self.related_search_var = tk.StringVar()
        self.related_search_entry = tk.Entry(self.related_toggle_bar, font=("Microsoft YaHei", 9),
                                              textvariable=self.related_search_var, width=30,
                                              relief=tk.FLAT, bd=0, bg="#fff",
                                              highlightthickness=1, highlightbackground="#ddd")
        self.related_search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3)
        self.related_search_entry.config(highlightthickness=1, highlightbackground="#ddd")
        self.related_search_entry.bind("<KeyRelease>", self._on_related_search)
        self.related_search_entry.bind("<Return>", lambda e: self._on_related_add())
        self.related_search_entry.bind("<Down>", lambda e: self._focus_next_result())
        self.related_search_entry.bind("<Up>", lambda e: self._focus_prev_result())

        self.related_add_btn = tk.Button(self.related_toggle_bar, text=tr("editor.related_add"), font=("Microsoft YaHei", 9),
                  bg="#3498db", fg="white", relief=tk.FLAT, padx=10, pady=3,
                  cursor="hand2", command=self._on_related_add)
        self.related_add_btn.pack(side=tk.LEFT, padx=(6, 4))
        self.related_hint_lbl = tk.Label(self.related_toggle_bar, text="", font=("Microsoft YaHei", 8),
                                          fg="#e74c3c", bg="#e8f4f8")
        self.related_hint_lbl.pack(side=tk.LEFT)

        # Subject/Chapter description form
        self.desc_frame = tk.Frame(self.form_container, bg="#fafafa")
        self.desc_title = tk.Label(self.desc_frame, font=("Microsoft YaHei", 10, "bold"),
                                   bg="#fafafa", anchor=tk.W)
        self.desc_title.pack(fill=tk.X, pady=(8, 4))
        self.desc_text = tk.Text(self.desc_frame, font=("Microsoft YaHei", 10),
                                 wrap=tk.WORD, relief=tk.SUNKEN, borderwidth=1,
                                 height=8, undo=True)
        self.desc_text.pack(fill=tk.X, pady=(2, 4))
        self.desc_text.bind("<KeyRelease>", lambda e: setattr(self, '_dirty', True))

        # Directory listing frame (used for chapter/subject pages)
        self.dir_frame = tk.Frame(self.form_container, bg="#fafafa")
        self.dir_inner = tk.Frame(self.dir_frame, bg="#fafafa")
        self.dir_inner.pack(fill=tk.BOTH, expand=True)

        # Bottom bar container with fixed height
        self.bottom_bar_container = tk.Frame(self.bottom_frame, bg="#fff8e1", height=32)
        self.bottom_bar_container.pack(fill=tk.X, side=tk.BOTTOM)
        self.bottom_bar_container.pack_propagate(False)

        # Bottom bar (always visible)
        bottom_bar = tk.Frame(self.bottom_bar_container, bg="#fff8e1")
        bottom_bar.pack(fill=tk.BOTH, expand=True)

        # Top separator line
        tk.Frame(bottom_bar, height=1, bg="#e0d8c8").pack(fill=tk.X)

        # Keyword-only UI elements
        self.kw_legend_frame = tk.Frame(bottom_bar, bg="#fff8e1")
        self.kw_type_line = tk.Frame(bottom_bar, bg="#fff8e1")
        self.kw_type_line.pack(fill=tk.X, pady=(2, 2))

        tk.Label(self.kw_type_line, text=tr("editor.card_type"),
                 font=("Microsoft YaHei", 9, "bold"),
                 bg="#fff8e1").pack(anchor=tk.W, pady=(0, 2))
        self.type_var = tk.StringVar(value="normal")
        selector = self._build_type_selector(self.kw_type_line, self.type_var, compact=True)
        selector.pack(fill=tk.X)

        self.btn_frame = tk.Frame(bottom_bar, bg="#fff8e1")
        self.btn_frame.pack(fill=tk.X, pady=(2, 3))

        self.btn_save = tk.Button(self.btn_frame, text=tr("editor.save_btn") + "  Ctrl+S", font=("Microsoft YaHei", 11, "bold"),
                                  bg="#3498db", fg="white", relief=tk.FLAT,
                                  padx=24, pady=4, cursor="hand2",
                                  command=self._save_keyword)
        self.btn_save.pack(side=tk.RIGHT, padx=(0, 4))
        self.btn_preview = tk.Button(self.btn_frame, text=tr("editor.preview_btn"), font=("Microsoft YaHei", 10),
                                     bg="#95a5a6", fg="white", relief=tk.FLAT,
                                     padx=12, pady=4, cursor="hand2",
                                     command=self._preview_card)
        tk.Button(self.btn_frame, text=tr("editor.markup_help"), font=("Microsoft YaHei", 10),
                  bg="#f0f0f0", fg="#555", relief=tk.FLAT, padx=10, pady=4, cursor="hand2",
                  command=self._show_markup_help).pack(side=tk.LEFT, padx=(4, 0))

        # Initially hide keyword-only UI (shown when keyword is selected)
        self.kw_legend_frame.pack_forget()
        self.kw_type_line.pack_forget()
        self.btn_preview.pack_forget()

    def _update_path_label(self):
        cfg = load_config()
        root_path = cfg.get('root_path', '')
        self.path_label.config(text=f"KB: {root_path}" if root_path else tr("editor.kb_path"))
        self._update_git_button()

    def _on_language_change(self, event=None):
        display = self.lang_var.get()
        lang = self._lang_display_to_code.get(display, "zh")
        if lang == get_language():
            return
        load_language(lang)
        from config import save_config
        cfg = load_config()
        cfg["language"] = lang
        save_config(cfg)
        messagebox.showinfo(tr("app.info"), tr("editor.lang_restart"))

    def _update_git_button(self):
        if self._git_btn is not None:
            self._git_btn.destroy()
            self._git_btn = None
        if self._git_hint is not None:
            self._git_hint.destroy()
            self._git_hint = None
        if self._git_url_label is not None:
            self._git_url_label.destroy()
            self._git_url_label = None
        root_path = load_config().get("root_path", "")
        if root_path and os.path.isdir(os.path.join(root_path, ".git")):
            bg = self._bottom_frame.cget("bg")
            self._git_btn = tk.Button(
                self._bottom_frame, text=tr("editor.git_upload"),
                font=("Microsoft YaHei", 9), fg="white", bg="#2c3e50",
                relief=tk.FLAT, padx=10, cursor="hand2",
                command=self._git_push
            )
            self._git_btn.pack(side=tk.RIGHT, padx=(4, 0))
            def fetch_url():
                url = ""
                try:
                    r = subprocess.run(["git", "remote", "get-url", "origin"],
                                       cwd=root_path, capture_output=True, text=True)
                    if r.returncode == 0:
                        url = r.stdout.strip()
                except Exception:
                    pass
                self.root.after(0, lambda u=url: self._show_git_url(u))
            threading.Thread(target=fetch_url, daemon=True).start()
        elif root_path:
            bg = self._bottom_frame.cget("bg")
            self._git_hint = tk.Label(
                self._bottom_frame,
                text=tr("editor.git_no_repo"),
                font=("Microsoft YaHei", 8), fg="#aaa", bg=bg,
            )
            self._git_hint.pack(side=tk.RIGHT, padx=(4, 0))

    def _show_git_url(self, url):
        if not url or self._git_btn is None:
            return
        bg = self._bottom_frame.cget("bg")
        self._git_url_label = tk.Label(
            self._bottom_frame, text=tr("editor.git_remote_url").format(url=url),
            font=("Microsoft YaHei", 8), fg="#555", bg=bg,
        )
        self._git_url_label.pack(side=tk.RIGHT, padx=(4, 0))

    def _git_push(self):
        root_path = load_config().get("root_path", "")
        if not root_path or not os.path.isdir(os.path.join(root_path, ".git")):
            return
        if self._git_btn is None:
            return
        self._git_btn.config(text=tr("editor.git_pushing"), state=tk.DISABLED)
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
            self._git_btn.config(text=tr("editor.git_upload"), state=tk.NORMAL)
        messagebox.showinfo(tr("app.success"), tr("editor.upload_success"))

    def _git_fail(self, err):
        if self._git_btn is not None:
            self._git_btn.config(text=tr("editor.git_upload"), state=tk.NORMAL)
        msg = err.stderr.strip() or err.stdout.strip() or str(err)
        if "nothing to commit" in msg:
            messagebox.showinfo(tr("app.info"), tr("editor.no_changes"))
        elif "could not read" in msg.lower() or "failed to push" in msg.lower():
            messagebox.showerror(tr("editor.git_fail_title"), tr("editor.git_fail_msg").format(msg=msg))
        else:
            messagebox.showerror("GitHub 上传失败", msg)

    def _git_error(self, msg):
        if self._git_btn is not None:
            self._git_btn.config(text=tr("editor.git_upload"), state=tk.NORMAL)
        messagebox.showerror("GitHub 上传失败", msg)

    def _update_type_color(self):
        pass

    def _build_type_selector(self, parent, variable, btn_size=(130, 44), compact=False):
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
        btn_font = ("Microsoft YaHei", 12, "bold")
        desc_font = ("Microsoft YaHei", 8)
        label_pady = (6, 0)
        desc_pady = (0, 6)
        inpady = 4
        btn_width = 120
        btn_height = 52
        for label, val, color, desc in TYPE_OPTIONS:
            btn_frame = tk.Frame(frame, bg="#fafafa", cursor="hand2",
                                 highlightbackground="#c0c0c0", highlightthickness=1,
                                 width=btn_width, height=btn_height)
            btn_frame.pack_propagate(False)
            inner = tk.Frame(btn_frame, bg=color)
            inner.pack(fill=tk.BOTH, expand=True, padx=2, pady=inpady)
            tk.Label(inner, text=tr(label), font=btn_font,
                     fg="white", bg=color).pack(anchor=tk.W, padx=(10, 4), pady=label_pady)
            tk.Label(inner, text=tr(desc), font=desc_font,
                     fg="#e8f0ff", bg=color).pack(anchor=tk.W, padx=(10, 4), pady=desc_pady)

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
        # Save expanded state and selection before rebuild
        expanded = set()
        sel_key = None
        sel = self.tree.selection()
        if sel:
            item = sel[0]
            parent_id = self.tree.parent(item)
            grandparent_id = self.tree.parent(parent_id) if parent_id else ""
            name = self._strip_emoji(self.tree.item(item, "text"))
            if not parent_id:
                sel_key = ("subject", name)
            elif not grandparent_id:
                sel_key = ("chapter", name)
            else:
                sel_key = ("keyword", name)
        for item in self.tree.get_children(""):
            if self.tree.item(item, "open"):
                expanded.add(("subject", self._strip_emoji(self.tree.item(item, "text"))))
            for child in self.tree.get_children(item):
                if self.tree.item(child, "open"):
                    expanded.add(("chapter", self._strip_emoji(self.tree.item(child, "text"))))

        self.tree.delete(*self.tree.get_children())
        for subject in self.db.list_subjects():
            opened = ("subject", subject) in expanded
            sid = self.tree.insert("", tk.END, text=f"📚 {subject}", open=opened)
            for chapter in self.db.list_chapters(subject):
                opened = ("chapter", chapter) in expanded
                cid = self.tree.insert(sid, tk.END, text=f"📖 {chapter}", open=opened)
                for kw in self.db.list_keywords(subject, chapter):
                    self.tree.insert(cid, tk.END, text=f"💡 {kw}")
        self._refresh_primary_subjects()
        self._apply_tree_filter()
        # Restore selection
        if sel_key:
            self._select_tree_item(sel_key)

    def _apply_tree_filter(self):
        query = self.search_var.get().strip().lower() if hasattr(self, 'search_var') else ""
        if not query:
            return
        for subject_item in self.tree.get_children(""):
            subject_name = self._strip_emoji(self.tree.item(subject_item, "text")).lower()
            subject_match = query in subject_name
            any_visible = subject_match
            for chapter_item in self.tree.get_children(subject_item):
                chapter_name = self._strip_emoji(self.tree.item(chapter_item, "text")).lower()
                chapter_match = query in chapter_name
                kw_visible = chapter_match
                for kw_item in self.tree.get_children(chapter_item):
                    kw_name = self._strip_emoji(self.tree.item(kw_item, "text")).lower()
                    if query in kw_name:
                        kw_visible = True
                    else:
                        self.tree.detach(kw_item)
                if kw_visible:
                    any_visible = True
                else:
                    self.tree.detach(chapter_item)
            if not any_visible:
                self.tree.detach(subject_item)

    def _on_search_changed(self, event=None):
        if self._search_after_id is not None:
            self.root.after_cancel(self._search_after_id)
        self._search_after_id = self.root.after(200, self._do_filter_tree)

    def _do_filter_tree(self):
        self._search_after_id = None
        self._refresh_tree()

    def _select_tree_item(self, key):
        typ, name = key
        for item in self.tree.get_children(""):
            if typ == "subject" and self._strip_emoji(self.tree.item(item, "text")) == name:
                self.tree.selection_set(item)
                self.tree.see(item)
                self.tree.item(item, open=True)
                return
            for child in self.tree.get_children(item):
                if typ == "chapter" and self._strip_emoji(self.tree.item(child, "text")) == name:
                    self.tree.selection_set(child)
                    self.tree.item(item, open=True)
                    self.tree.see(child)
                    self.tree.item(child, open=True)
                    return
                for grand in self.tree.get_children(child):
                    if typ == "keyword" and self._strip_emoji(self.tree.item(grand, "text")) == name:
                        self.tree.selection_set(grand)
                        self.tree.item(item, open=True)
                        self.tree.item(child, open=True)
                        self.tree.see(grand)
                        return

    def _clear_search(self, event=None):
        self.search_var.set("")
        self._do_filter_tree()

    def _on_tree_scroll(self, first, last):
        self.tree_scrollbar.set(first, last)
        try:
            if first == "0.0" and last == "1.0":
                self.tree_scrollbar.pack_forget()
            else:
                self.tree_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        except tk.TclError:
            pass

    def _on_text_scroll_y(self, first, last):
        self.text_scrollbar_y.set(first, last)

    def _on_results_scroll(self, first, last):
        pass

    def _on_results_mousewheel(self, event):
        self.related_results_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # ---- Drag-and-drop (reorder + link insertion) ----
    def _on_tree_press(self, event):
        item = self.tree.identify_row(event.y)
        if not item:
            return
        parent_id = self.tree.parent(item)
        grandparent_id = self.tree.parent(parent_id) if parent_id else ""
        if not parent_id or not grandparent_id:
            return
        self._drag_data = {"item": item, "start_y": event.y, "start_x": event.x_root, "start_y_root": event.y_root,
                           "dragging": False, "target_item": None}
        return "break"

    def _on_tree_drag(self, event):
        data = self._drag_data
        if not data["item"]:
            return
        if not data["dragging"] and abs(event.y - data["start_y"]) > 5:
            data["dragging"] = True
        if not data["dragging"]:
            return
        tx = self.knowledge_text.winfo_rootx()
        ty = self.knowledge_text.winfo_rooty()
        tw = self.knowledge_text.winfo_width()
        th = self.knowledge_text.winfo_height()
        if tx <= event.x_root <= tx + tw and ty <= event.y_root <= ty + th:
            self.tree.config(cursor="plus")
            self._clear_drag_highlight()
            return
        self.tree.config(cursor="")
        target = self.tree.identify_row(event.y)
        if target and target != data["item"]:
            t_parent = self.tree.parent(target)
            t_grandparent = self.tree.parent(t_parent) if t_parent else ""
            if not t_parent:
                new_target = None
            elif not t_grandparent:
                new_target = target
            else:
                new_target = t_parent
        else:
            new_target = None
        if new_target and new_target != data.get("target_item"):
            self._clear_drag_highlight()
            self.tree.item(new_target, tags=("drag_target",))
            data["target_item"] = new_target
        elif not new_target:
            self._clear_drag_highlight()
            data["target_item"] = None

    def _on_tree_release(self, event):
        data = self._drag_data
        item = data["item"]
        self.tree.config(cursor="")
        if data["dragging"]:
            tx = self.knowledge_text.winfo_rootx()
            ty = self.knowledge_text.winfo_rooty()
            tw = self.knowledge_text.winfo_width()
            th = self.knowledge_text.winfo_height()
            if tx <= event.x_root <= tx + tw and ty <= event.y_root <= ty + th:
                self._insert_link_from_tree(item)
            elif data["target_item"]:
                self._clear_drag_highlight()
                self._move_keyword_by_drag(item, data["target_item"])
        elif item and not data["dragging"]:
            self.tree.selection_set(item)
        self._clear_drag_highlight()
        self._drag_data = {"item": None, "start_y": 0, "dragging": False, "target_item": None}

    def _insert_link_from_tree(self, item):
        kw = self._strip_emoji(self.tree.item(item, "text"))
        parent_id = self.tree.parent(item)
        grandparent_id = self.tree.parent(parent_id) if parent_id else ""
        ch = self._strip_emoji(self.tree.item(parent_id, "text"))
        subj = self._strip_emoji(self.tree.item(grandparent_id, "text"))
        link = f"[[{subj}::{ch}::{kw}|{kw}]]"
        self.knowledge_text.insert(tk.INSERT, link)
        self._dirty = True

    def _move_keyword_by_drag(self, item, target_item):
        parent_id = self.tree.parent(item)
        grandparent_id = self.tree.parent(parent_id) if parent_id else ""
        keyword_name = self._strip_emoji(self.tree.item(item, "text"))
        source_chapter = self._strip_emoji(self.tree.item(parent_id, "text"))
        source_subject = self._strip_emoji(self.tree.item(grandparent_id, "text"))
        t_parent = self.tree.parent(target_item)
        target_chapter = self._strip_emoji(self.tree.item(target_item, "text"))
        target_subject = self._strip_emoji(self.tree.item(t_parent, "text"))
        if source_subject == target_subject and source_chapter == target_chapter:
            return
        success = self.db.move_keyword(source_subject, source_chapter, keyword_name, target_subject, target_chapter)
        if success:
            self._refresh_tree()
            self._select_keyword_in_tree(keyword_name)
        else:
            messagebox.showerror(tr("app.error"), tr("editor.move_failed").format(kw=keyword_name))

    def _clear_drag_highlight(self):
        ti = self._drag_data.get("target_item")
        if ti:
            try:
                self.tree.item(ti, tags=())
            except tk.TclError:
                pass

    def _on_tree_select(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        item = sel[0]
        parent_id = self.tree.parent(item)
        grandparent_id = self.tree.parent(parent_id) if parent_id else ""
        text = self._strip_emoji(self.tree.item(item, "text"))

        if not parent_id:
            self.current_subject = text
            self.current_chapter = None
            self.current_keyword = None
            self._load_subject_desc(text)
        elif not grandparent_id:
            self.current_subject = self._strip_emoji(
                self.tree.item(parent_id, "text"))
            self.current_chapter = text
            self.current_keyword = None
            self._load_chapter_desc(text)
        else:
            nav_programmatic = self._nav_ignore
            self._nav_ignore = False
            if not nav_programmatic:
                self._nav_visit()
            self.current_subject = self._strip_emoji(
                self.tree.item(grandparent_id, "text"))
            self.current_chapter = self._strip_emoji(
                self.tree.item(parent_id, "text"))
            self.current_keyword = text
            self._load_keyword()
        self._update_add_buttons()

    def _update_add_buttons(self):
        self.btn_add_chapter.pack_forget()
        self.btn_add_keyword.pack_forget()
        self.btn_add_subject.pack(side=tk.LEFT, padx=1)
        if self.current_subject:
            self.btn_add_chapter.pack(side=tk.LEFT, padx=1)
        if self.current_subject and self.current_chapter:
            self.btn_add_keyword.pack(side=tk.LEFT, padx=1)

    @staticmethod
    def _strip_emoji(text):
        return text.split(" ", 1)[-1] if " " in text else text

    def _show_empty(self, msg=""):
        self.empty_label.pack(expand=True)
        self.form_frame.pack_forget()
        self.desc_frame.pack_forget()
        self.dir_frame.pack_forget()
        self.kw_legend_frame.pack_forget()
        self.kw_type_line.pack_forget()
        self.btn_preview.pack_forget()
        self.btn_frame.pack_forget()
        self.related_outer.pack_forget()
        self._related_topics = []
        self._related_drawer_open = False
        self.empty_label.config(text=msg if msg else tr("editor.empty_select"))
        self._editing_type = None
        self.bottom_bar_container.config(height=32)

    def _show_form(self):
        self.empty_label.pack_forget()
        self.desc_frame.pack_forget()
        self.dir_frame.pack_forget()
        self.form_frame.pack(fill=tk.BOTH, expand=True)
        self.kw_legend_frame.pack(fill=tk.X, pady=(4, 2))
        self.kw_type_line.pack(fill=tk.X, pady=(2, 2))
        self.btn_frame.pack(fill=tk.X, pady=(2, 4))
        self.btn_preview.pack(side=tk.RIGHT, padx=(0, 6))
        self.related_outer.pack(fill=tk.X, side=tk.BOTTOM, pady=(8, 0))
        self._editing_type = "keyword"
        self._read_mode = False
        self.btn_save.config(text="保存", bg="#3498db", command=self._save_keyword)
        self.knowledge_text.config(state=tk.NORMAL)
        self.bottom_bar_container.config(height=140)

    def _show_desc_form(self):
        self.empty_label.pack_forget()
        self.form_frame.pack_forget()
        self.dir_frame.pack_forget()
        self.kw_legend_frame.pack_forget()
        self.kw_type_line.pack_forget()
        self.btn_preview.pack_forget()
        self.btn_frame.pack_forget()
        self.desc_frame.pack(fill=tk.BOTH, expand=True)
        self.bottom_bar_container.config(height=32)

    def _show_dir_page(self):
        self.empty_label.pack_forget()
        self.form_frame.pack_forget()
        self.kw_legend_frame.pack_forget()
        self.kw_type_line.pack_forget()
        self.related_outer.pack_forget()
        self.desc_frame.pack(fill=tk.X, pady=(0, 2))
        self.dir_frame.pack(fill=tk.BOTH, expand=True, pady=(2, 4))
        # Show save button in bottom bar (no preview, no keyword UI)
        self.btn_preview.pack_forget()
        self.btn_frame.pack(fill=tk.X, pady=(2, 3))
        self.btn_save.config(text=tr("editor.save_desc"), bg="#3498db", command=self._save_keyword)
        self.bottom_bar_container.config(height=50)

    def _load_keyword(self):
        if not self.current_subject or not self.current_chapter or not self.current_keyword:
            self._show_empty()
            return
        data = self.db.get_keyword_data(
            self.current_subject, self.current_chapter, self.current_keyword
        )
        if data is None:
            self._show_empty(tr("editor.empty_no_data"))
            return

        self._show_form()
        self.keyword_entry.config(state="normal")
        kw_display = self.current_keyword
        self.keyword_entry.delete(0, tk.END)
        self.keyword_entry.insert(0, kw_display)
        kt = data.get("type", "normal")
        self.type_var.set(kt)
        self.knowledge_text.config(state=tk.NORMAL)
        self.knowledge_text.delete("1.0", tk.END)
        self.knowledge_text.insert("1.0", data.get("knowledge", ""))
        knowledge_text = data.get("knowledge", "")
        self._related_topics = data.get("related", [])
        self._sync_related_from_content(knowledge_text)
        self._refresh_related_search()
        self._render_related_topics()
        self._update_related_count()
        self._dirty = False
        self.root.after(50, self.knowledge_text.focus_set)
        self._switch_to_read_mode()

    def _load_subject_desc(self, subject):
        self._show_dir_page()
        self.desc_title.config(text="📁 " + tr("editor.subject") + f": {subject}")
        self.desc_text.config(state=tk.NORMAL)
        self.desc_text.delete("1.0", tk.END)
        desc = self.db.get_subject_description(subject)
        self.desc_text.insert("1.0", desc)
        self._editing_type = "subject"

        # Clear and populate directory
        for w in self.dir_inner.winfo_children():
            w.destroy()

        chapters = self.db.list_chapters(subject)
        if not chapters:
            tk.Label(self.dir_inner, text=tr("editor.no_chapters"), font=("Microsoft YaHei", 9),
                     fg="#999", bg="#fafafa").pack(anchor=tk.W, pady=(4, 0))
        else:
            tk.Label(self.dir_inner, text="📖 " + tr("editor.subject_dir") + f" ({len(chapters)} " + tr("chapters") + ")",
                     font=("Microsoft YaHei", 10, "bold"), bg="#fafafa",
                     anchor=tk.W).pack(fill=tk.X, pady=(4, 2))
            for ch in chapters:
                kws = self.db.list_keywords(subject, ch)
                ch_frame = tk.Frame(self.dir_inner, bg="#f5f5f5", relief=tk.GROOVE, bd=1)
                ch_frame.pack(fill=tk.X, pady=(2, 0), padx=4)
                header = tk.Label(ch_frame, text="  📖 " + ch + f"  ({len(kws)} " + tr("keywords") + ")",
                                  font=("Microsoft YaHei", 9, "bold"), bg="#f5f5f5",
                                  anchor=tk.W, cursor="hand2", fg="#2c3e50")
                header.pack(fill=tk.X, padx=4, pady=2)
                header.bind("<Button-1>", lambda e, s=subject, c=ch:
                    self._select_tree_item(("chapter", c)) if hasattr(self, '_select_tree_item') else None)
                if kws:
                    for kw in kws:
                        lbl = tk.Label(ch_frame, text=f"    💡 {kw}",
                                       font=("Microsoft YaHei", 9), fg="#2980b9",
                                       bg="#f5f5f5", cursor="hand2", anchor=tk.W)
                        lbl.pack(fill=tk.X, padx=(24, 4), pady=1)
                        lbl.bind("<Button-1>", lambda e, k=kw:
                            self.navigate_to_keyword(k))
                else:
                    tk.Label(ch_frame, text="    " + tr("editor.empty_chapter"), font=("Microsoft YaHei", 8),
                             fg="#aaa", bg="#f5f5f5", anchor=tk.W).pack(fill=tk.X, padx=(24, 4))

        # Pins section
        pins = self.db.collect_pins(subject)
        if pins:
            tk.Label(self.dir_inner, text="\n📍 " + tr("editor.pin_section") + f" ({sum(len(v) for v in pins.values())} " + tr("pin.count") + ")",
                     font=("Microsoft YaHei", 10, "bold"), bg="#fafafa",
                     anchor=tk.W).pack(fill=tk.X, pady=(8, 2))
            pin_line = tk.Frame(self.dir_inner, bg="#fafafa")
            pin_line.pack(fill=tk.X, padx=4)
            for pin_word in sorted(pins.keys()):
                chapters_kws = ", ".join(f"{ch}/{kw}" for ch, kw in pins[pin_word])
                lbl = tk.Label(pin_line, text=f"📌 {pin_word}",
                               font=("Microsoft YaHei", 9), fg="#8e44ad",
                               bg="#fafafa", cursor="hand2")
                lbl.pack(side=tk.LEFT, padx=(0, 12))
                def _pin_click(pin_word, targets):
                    first = targets[0] if targets else None
                    if first:
                        self.navigate_to_keyword(first[1])
                lbl.bind("<Button-1>", lambda e, w=pin_word, p=pins:
                    _pin_click(w, p[w]))

    def _load_chapter_desc(self, chapter):
        self._show_dir_page()
        self.desc_title.config(text=f"📂 {self.current_subject} → {chapter}")
        self.desc_text.config(state=tk.NORMAL)
        self.desc_text.delete("1.0", tk.END)
        desc = self.db.get_chapter_description(self.current_subject, chapter)
        self.desc_text.insert("1.0", desc)
        self._editing_type = "chapter"

        # Clear and populate directory
        for w in self.dir_inner.winfo_children():
            w.destroy()

        kws = self.db.list_keywords(self.current_subject, chapter)
        tk.Label(self.dir_inner, text="📋 " + tr("editor.chapter_dir") + f" ({len(kws)} " + tr("keywords") + ")",
                 font=("Microsoft YaHei", 10, "bold"), bg="#fafafa",
                 anchor=tk.W).pack(fill=tk.X, pady=(4, 2))

        if not kws:
            tk.Label(self.dir_inner, text=tr("editor.no_keywords"), font=("Microsoft YaHei", 9),
                     fg="#999", bg="#fafafa").pack(anchor=tk.W, padx=4)
        else:
            for kw in kws:
                lbl = tk.Label(self.dir_inner, text=f"  💡 {kw}",
                               font=("Microsoft YaHei", 9), fg="#2980b9",
                               bg="#fafafa", cursor="hand2", anchor=tk.W)
                lbl.pack(fill=tk.X, padx=(8, 4), pady=1)
                lbl.bind("<Button-1>", lambda e, k=kw:
                    self.navigate_to_keyword(k))

        # Pins section
        pins = self.db.collect_pins(self.current_subject, chapter)
        if pins:
            tk.Label(self.dir_inner, text="\n📍 " + tr("editor.pin_section") + f" ({sum(len(v) for v in pins.values())} " + tr("pin.count") + ")",
                     font=("Microsoft YaHei", 10, "bold"), bg="#fafafa",
                     anchor=tk.W).pack(fill=tk.X, pady=(8, 2))
            pin_line = tk.Frame(self.dir_inner, bg="#fafafa")
            pin_line.pack(fill=tk.X, padx=4)
            for pin_word in sorted(pins.keys()):
                lbl = tk.Label(pin_line, text=f"📌 {pin_word}",
                               font=("Microsoft YaHei", 9), fg="#8e44ad",
                               bg="#fafafa", cursor="hand2")
                lbl.pack(side=tk.LEFT, padx=(0, 12))
                lbl.bind("<Button-1>", lambda e, w=pin_word:
                    self.navigate_to_keyword(pins[w][0][1]) if pins[w] else None)

    def _refresh_related_search(self):
        all_kw = self.db.list_all_keywords()
        current = (self.current_subject, self.current_chapter, self.current_keyword)
        related_kw_set = {(r.get("subject"), r.get("chapter"), r.get("keyword")) for r in self._related_topics}
        self._all_related_items = []
        for subj, ch, kw in all_kw:
            if (subj, ch, kw) == current:
                continue
            if (subj, ch, kw) in related_kw_set:
                continue
            self._all_related_items.append((subj, ch, kw))
        self.related_search_var.set("")
        self._related_matches = []
        self._selected_result_idx = -1
        self._update_add_button(False)
        self._filter_related_list()

    def _score_match(self, query, subj, ch, kw):
        ql = query.lower()
        kl = kw.lower()
        sl = subj.lower()
        cl = ch.lower()
        if kl == ql:
            return 100
        if kl.startswith(ql):
            return 80
        if ql in kl:
            return 60
        if ql in sl or ql in cl:
            return 30
        return 10

    def _filter_related_list(self):
        query = self.related_search_var.get().strip()
        for w in self.related_results_inner.winfo_children():
            w.destroy()
        if not self._all_related_items:
            self.related_results_outer.pack_forget()
            self._update_add_button(False, tr("editor.related_no_more"))
            return
        if not query:
            self.related_results_outer.pack_forget()
            self._update_add_button(False, tr("editor.related_search_hint"))
            return
        ql = query.lower()
        scored = []
        for subj, ch, kw in self._all_related_items:
            s = self._score_match(query, subj, ch, kw)
            if s >= 10:
                scored.append((s, subj, ch, kw))
        scored.sort(key=lambda x: (-x[0], x[3]))
        matches = [(s, c, k) for _, s, c, k in scored]
        if not matches:
            self.related_results_outer.pack_forget()
            self._update_add_button(False, tr("editor.related_not_found"))
            return
        self.related_results_outer.pack(fill=tk.X, pady=(0, 4))
        self._related_matches = matches
        self._selected_result_idx = 0
        max_show = min(len(matches), 5)
        for i, (subj, ch, kw) in enumerate(matches[:max_show]):
            row = tk.Frame(self.related_results_inner, bg="#fff")
            row.pack(fill=tk.X)
            if i > 0:
                tk.Frame(row, height=1, bg="#f0f0f0").pack(fill=tk.X, padx=8)
            content = tk.Frame(row, bg="#fff")
            content.pack(fill=tk.X, padx=8, pady=4)
            kw_lbl = tk.Label(content, text=kw, font=("Microsoft YaHei", 9, "bold"),
                              fg="#2c3e50", bg="#fff", anchor=tk.W)
            kw_lbl.pack(fill=tk.X)
            path_lbl = tk.Label(content, text=f"{subj} > {ch}", font=("Microsoft YaHei", 8),
                                fg="#aaa", bg="#fff", anchor=tk.W)
            path_lbl.pack(fill=tk.X)
            for w in [row, content, kw_lbl, path_lbl]:
                w.bind("<Button-1>", lambda e, idx=i: self._select_result_row(idx))
                w.config(cursor="hand2")
            if i == 0:
                self._highlight_result_row(row, content, kw_lbl, path_lbl)
            row._content = content
            row._kw_lbl = kw_lbl
            row._path_lbl = path_lbl
        if len(matches) > max_show:
            more = tk.Label(self.related_results_inner, text=f"... 还有 {len(matches) - max_show} 个结果",
                            font=("Microsoft YaHei", 8), fg="#aaa", bg="#fff")
            more.pack(pady=(0, 4))
        self.related_results_canvas.configure(scrollregion=self.related_results_canvas.bbox("all"))
        h = self.related_results_inner.winfo_reqheight()
        max_h = 160
        self.related_results_canvas.configure(height=min(h, max_h))
        if h > max_h:
            self.related_results_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        else:
            self.related_results_scrollbar.pack_forget()
        self._update_add_button(True)

    def _update_add_button(self, enabled, hint=""):
        if enabled:
            self.related_add_btn.config(state="normal", bg="#3498db", cursor="hand2")
            self.related_hint_lbl.config(text="")
        else:
            self.related_add_btn.config(state="disabled", bg="#bdc3c7", cursor="")
            self.related_hint_lbl.config(text=hint)

    def _highlight_result_row(self, row, content, kw_lbl, path_lbl):
        bg = "#e8f4fd"
        row.configure(bg=bg)
        content.configure(bg=bg)
        kw_lbl.configure(bg=bg)
        path_lbl.configure(bg=bg)

    def _unhighlight_result_row(self, row, content, kw_lbl, path_lbl):
        bg = "#fff"
        row.configure(bg=bg)
        content.configure(bg=bg)
        kw_lbl.configure(bg=bg)
        path_lbl.configure(bg=bg)

    def _select_result_row(self, idx):
        if idx < 0 or idx >= len(self._related_matches):
            return
        self._selected_result_idx = idx
        for w in self.related_results_inner.winfo_children():
            if hasattr(w, '_content'):
                self._unhighlight_result_row(w, w._content, w._kw_lbl, w._path_lbl)
        children = self.related_results_inner.winfo_children()
        row_idx = 0
        for child in children:
            if hasattr(child, '_content'):
                if row_idx == idx:
                    self._highlight_result_row(child, child._content, child._kw_lbl, child._path_lbl)
                row_idx += 1

    def _focus_next_result(self):
        if not self._related_matches:
            return
        self._selected_result_idx = (self._selected_result_idx + 1) % len(self._related_matches)
        self._select_result_row(self._selected_result_idx)

    def _focus_prev_result(self):
        if not self._related_matches:
            return
        self._selected_result_idx = (self._selected_result_idx - 1) % len(self._related_matches)
        self._select_result_row(self._selected_result_idx)

    def _on_related_search(self, event=None):
        self._filter_related_list()

    def _on_related_add(self, event=None):
        if not self._related_matches:
            return
        idx = self._selected_result_idx
        if idx < 0 or idx >= len(self._related_matches):
            idx = 0
        subj, ch, kw = self._related_matches[idx]
        display = self.related_search_var.get().strip()
        if not display:
            display = kw
        self._related_topics.append({
            "subject": subj, "chapter": ch, "keyword": kw, "display": display
        })
        if not self._related_drawer_open:
            self._related_drawer_open = True
            self.related_drawer.pack(fill=tk.X, side=tk.BOTTOM)
        self._render_related_topics()
        self._refresh_related_search()
        self._update_related_count()
        self._save_related_now()

    def _on_related_remove(self, idx):
        if 0 <= idx < len(self._related_topics):
            rel = self._related_topics[idx]
            kw = rel.get("keyword", "")
            display = rel.get("display", kw)
            self._related_topics.pop(idx)
            self._remove_link_from_knowledge(kw, display)
            self._render_related_topics()
            self._refresh_related_search()
            self._update_related_count()
            self._save_related_now()

    def _remove_link_from_knowledge(self, keyword, display):
        import re
        kw_escaped = re.escape(keyword)
        display_escaped = re.escape(display)
        pattern = rf'\[\[(?:[^:|]+::[^:|]+::)?{kw_escaped}(\|{display_escaped})?\]\]'
        text = self.knowledge_text.get("1.0", tk.END).strip()
        new_text = re.sub(pattern, '', text, count=1).strip()
        if new_text == text:
            return
        was_read = self._read_mode
        if was_read:
            self.knowledge_text.config(state=tk.NORMAL)
        self.knowledge_text.delete("1.0", tk.END)
        self.knowledge_text.insert("1.0", new_text)
        self._dirty = True
        if was_read:
            self._raw_knowledge = new_text
            self._switch_to_read_mode()

    def _save_related_now(self):
        if not self.current_subject or not self.current_chapter or not self.current_keyword:
            return
        self.db.save_keyword(
            self.current_subject, self.current_chapter,
            self.current_keyword,
            self.knowledge_text.get("1.0", tk.END).strip(),
            self.type_var.get(),
            related=self._related_topics
        )

    def _render_related_topics(self):
        self.related_outer.update_idletasks()
        cw = self.related_canvas.winfo_width()
        if cw > 1:
            self.related_canvas.itemconfig("related_window", width=cw)
        for w in self.related_list_inner.winfo_children():
            w.destroy()
        toggle_h = 30
        if not self._related_topics:
            tk.Label(self.related_list_inner, text=tr("editor.related_none"), font=("Microsoft YaHei", 9),
                     fg="#bbb", bg="#e8f4f8").pack(anchor=tk.W, padx=6, pady=6)
            self.related_canvas.configure(height=28)
            self.related_scrollbar.pack_forget()
            self.related_outer.config(height=toggle_h + (0 if not self._related_drawer_open else 28))
            return
        for i, rel in enumerate(self._related_topics):
            card = tk.Frame(self.related_list_inner, bg="#fff", relief=tk.FLAT, bd=0)
            card.pack(fill=tk.X, pady=2, padx=2)
            inner = tk.Frame(card, bg="#fff")
            inner.pack(fill=tk.X, padx=6, pady=4)
            subj = rel.get("subject", "")
            ch = rel.get("chapter", "")
            kw = rel.get("keyword", "")
            display = rel.get("display", kw)
            link_lbl = tk.Label(inner, text=f"🔗 {display}", font=("Microsoft YaHei", 9, "bold"),
                                fg="#2980b9", bg="#fff", cursor="hand2", anchor=tk.W)
            link_lbl.pack(fill=tk.X)
            path_lbl = tk.Label(inner, text=f"[{kw}]  {subj} > {ch}", font=("Microsoft YaHei", 8),
                                fg="#bbb", bg="#fff", anchor=tk.W)
            path_lbl.pack(fill=tk.X)
            link_lbl.bind("<Button-1>", lambda e, k=kw: self.navigate_to_keyword(k))
            remove_btn = tk.Button(card, text="✕", font=("Microsoft YaHei", 8), fg="#e74c3c",
                                   bg="#fff", relief=tk.FLAT, padx=4, pady=2, cursor="hand2",
                                   command=lambda idx=i: self._on_related_remove(idx))
            remove_btn.place(relx=1.0, rely=0.5, anchor=tk.E, x=-3)
            for w in [card, inner]:
                w.bind("<Enter>", lambda e, c=card: c.configure(bg="#f0f7ff"))
                w.bind("<Leave>", lambda e, c=card: c.configure(bg="#fff"))
        self.related_list_inner.update_idletasks()
        content_h = self.related_list_inner.winfo_reqheight()
        max_h = 200
        actual_h = min(content_h, max_h)
        self.related_canvas.configure(height=actual_h)
        if content_h > max_h:
            self.related_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        else:
            self.related_scrollbar.pack_forget()
        drawer_h = actual_h if self._related_drawer_open else 0
        self.related_outer.config(height=toggle_h + drawer_h)

    def _toggle_related_drawer(self):
        self._related_drawer_open = not self._related_drawer_open
        if self._related_drawer_open:
            self.related_drawer.pack(fill=tk.X, side=tk.BOTTOM)
            self.related_toggle_btn.config(text="▾ " + tr("editor.related_topics"))
        else:
            self.related_drawer.pack_forget()
            self.related_toggle_btn.config(text="▴ " + tr("editor.related_topics"))
        self._update_related_count()
        self._render_related_topics()

    def _update_related_count(self):
        n = len(self._related_topics)
        self.related_count_lbl.config(text=f"({n})")

    def _sync_related_from_content(self, knowledge_text):
        import re
        knowledge_text = expand_linkmap(knowledge_text)
        all_items = self.db.list_all_keywords()
        kw_map = {}
        for subj, ch, kw in all_items:
            if kw not in kw_map:
                kw_map[kw] = (subj, ch)
            elif kw_map[kw] != (self.current_subject, self.current_chapter):
                if subj == self.current_subject and ch == self.current_chapter:
                    kw_map[kw] = (subj, ch)
                elif kw_map[kw][0] != self.current_subject and subj == self.current_subject:
                    kw_map[kw] = (subj, ch)
        auto_kws = set()
        for m in re.finditer(r'\[\[(?:[^:\]|]+::[^:\]|]+::)?([^\]|]+)(?:\|([^\]]+))?\]\]', knowledge_text):
            target_kw = m.group(1)
            if target_kw in kw_map:
                auto_kws.add(target_kw)
        self._related_topics = [
            r for r in self._related_topics
            if not (r.get("_auto") and r["keyword"] not in auto_kws)
        ]
        existing = {r["keyword"] for r in self._related_topics}
        for target_kw in auto_kws:
            if target_kw not in existing:
                subj, ch = kw_map[target_kw]
                self._related_topics.append({
                    "subject": subj, "chapter": ch,
                    "keyword": target_kw, "display": target_kw,
                    "_auto": True,
                })

    def _on_knowledge_change(self, event):
        self._dirty = True
        self._schedule_related_sync()

    def _schedule_related_sync(self):
        if self._related_sync_after_id is not None:
            self.root.after_cancel(self._related_sync_after_id)
        self._related_sync_after_id = self.root.after(600, self._do_sync_related)

    def _do_sync_related(self):
        self._related_sync_after_id = None
        text = self._raw_knowledge if self._read_mode else self.knowledge_text.get("1.0", tk.END).strip()
        self._sync_related_from_content(text)
        self._render_related_topics()
        self._update_related_count()

    def _render_knowledge(self, text, ktype):
        text = expand_linkmap(text)
        import re as _re
        self.knowledge_text.delete("1.0", tk.END)
        default_fg = "#2c3e50"
        accent = "#3498db"
        self.knowledge_text.tag_config("r_normal", foreground=default_fg)
        self.knowledge_text.tag_config("r_highlight", foreground=accent, font=("Microsoft YaHei", 10, "bold"))
        self.knowledge_text.tag_config("r_tip", foreground="#27ae60", font=("Microsoft YaHei", 10))
        self.knowledge_text.tag_config("r_warning", foreground="#e74c3c", font=("Microsoft YaHei", 10, "bold"))
        self.knowledge_text.tag_config("r_link", foreground="#2980b9", underline=1, font=("Microsoft YaHei", 10))
        self.knowledge_text.tag_config("r_pin", foreground="#8e44ad", font=("Microsoft YaHei", 10, "bold"))
        self.knowledge_text.tag_config("r_bullet", foreground=default_fg, lmargin1=10, lmargin2=24)
        self.knowledge_text.tag_config("r_code", foreground="#e67e22", font=("Consolas", 11, "bold"),
                                        background="#2d2d2d", relief=tk.GROOVE, borderwidth=1,
                                        overstrike=False, underline=False, spacing1=2, spacing3=2)
        for lvl, size in [(1, 16), (2, 14), (3, 12)]:
            self.knowledge_text.tag_config(f"r_h{lvl}",
                font=("Microsoft YaHei", size, "bold"), foreground="#2c3e50",
                spacing1=6, spacing3=2)
        self.knowledge_text.tag_config("r_italic", font=("Microsoft YaHei", 10, "italic"),
                                        foreground=default_fg)
        self.knowledge_text.tag_config("r_underline", font=("Microsoft YaHei", 10),
                                        foreground=default_fg, underline=1)
        self.knowledge_text.tag_config("r_underline_dashed", font=("Microsoft YaHei", 10, "italic"),
                                        foreground=default_fg, underline=1)
        self.knowledge_text.tag_config("r_strikethrough", font=("Microsoft YaHei", 10),
                                        foreground=default_fg, overstrike=1)
        self.knowledge_text.tag_config("r_link_gap", foreground=default_fg)
        self._link_tag_counter = getattr(self, "_link_tag_counter", 0) + 1
        link_base = self._link_tag_counter
        pattern = r'(!\[.*?\]\([^)]+\)|\[\[.*?\]\]|\*\*.*?\*\*|!!.*?!!|\?\?.*?\?\?|~~.*?~~|__.*?__|~.*?~|//.*?//|`.*?`)'
        link_idx = 0
        lines = text.split("\n")
        i = 0
        prev_was_link = False
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            if stripped.startswith("```"):
                lang = stripped[3:].strip()
                code_lines = []
                i += 1
                while i < len(lines):
                    if lines[i].strip() == "```":
                        i += 1
                        break
                    code_lines.append(lines[i])
                    i += 1
                self._insert_code_block_editor(lang, code_lines)
                continue
            # Normal line processing
            bullet = False
            heading_tag = ""
            rest = line
            if rest.startswith("- ") or rest.startswith("* "):
                bullet = True
                rest = rest[2:]
                if rest.startswith("### "):
                    heading_tag = "r_h3"
                    rest = rest[4:]
                elif rest.startswith("## "):
                    heading_tag = "r_h2"
                    rest = rest[3:]
                elif rest.startswith("# "):
                    heading_tag = "r_h1"
                    rest = rest[2:]
                self.knowledge_text.insert(tk.END, "  • ", "r_bullet" if not heading_tag else heading_tag)
            else:
                if rest.startswith("### "):
                    heading_tag = "r_h3"
                    rest = rest[4:]
                elif rest.startswith("## "):
                    heading_tag = "r_h2"
                    rest = rest[3:]
                elif rest.startswith("# "):
                    heading_tag = "r_h1"
                    rest = rest[2:]
            parts = _re.split(pattern, rest)
            prev_was_link = False
            for part in parts:
                if part.startswith("![") and part.endswith(")"):
                    match = _re.match(r'!\[(.*?)\]\((.+)\)', part)
                    if match:
                        alt_text = match.group(1)
                        img_name = match.group(2)
                        self._render_image(img_name, alt_text)
                elif part.startswith("[[") and part.endswith("]]"):
                    inner = part[2:-2]
                    if inner.startswith("pin:"):
                        pin_word = inner[4:]
                        pin_display = pin_word.split("|", 1)[0] if "|" in pin_word else pin_word
                        tags = ("r_bullet", "r_pin") if bullet else ("r_pin",)
                        self.knowledge_text.insert(tk.END, f"📌 {pin_display}", tags)
                    else:
                        display = inner.split("|", 1)[1] if "|" in inner else inner
                        if prev_was_link:
                            self.knowledge_text.insert(tk.END, "\u2009", "r_link_gap")
                        prev_was_link = True
                        link_idx += 1
                        tag = f"_r_link_{link_base}_{link_idx}"
                        self.knowledge_text.tag_config(tag, foreground="#2980b9", underline=1, font=("Microsoft YaHei", 10))
                        self.knowledge_text.tag_bind(tag, "<Button-1>", lambda e, t=tag, p=part: self._on_link_click(p, t))
                        self.knowledge_text.tag_bind(tag, "<Enter>", lambda e: self.knowledge_text.config(cursor="hand2"))
                        self.knowledge_text.tag_bind(tag, "<Leave>", lambda e: self.knowledge_text.config(cursor=""))
                        tags = ("r_bullet", tag) if bullet else (tag,)
                        self.knowledge_text.insert(tk.END, display, tags)
                elif part.startswith("**") and part.endswith("**"):
                    tags = ("r_bullet", "r_highlight") if bullet else ("r_highlight",)
                    self.knowledge_text.insert(tk.END, part[2:-2], tags)
                elif part.startswith("!!") and part.endswith("!!"):
                    tags = ("r_bullet", "r_warning") if bullet else ("r_warning",)
                    self.knowledge_text.insert(tk.END, part[2:-2], tags)
                elif part.startswith("??") and part.endswith("??"):
                    tags = ("r_bullet", "r_tip") if bullet else ("r_tip",)
                    self.knowledge_text.insert(tk.END, part[2:-2], tags)
                elif part.startswith("~~") and part.endswith("~~"):
                    tags = ("r_bullet", "r_strikethrough") if bullet else ("r_strikethrough",)
                    self.knowledge_text.insert(tk.END, part[2:-2], tags)
                elif part.startswith("__") and part.endswith("__"):
                    tags = ("r_bullet", "r_underline") if bullet else ("r_underline",)
                    self.knowledge_text.insert(tk.END, part[2:-2], tags)
                elif part.startswith("~") and part.endswith("~"):
                    tags = ("r_bullet", "r_underline_dashed") if bullet else ("r_underline_dashed",)
                    self.knowledge_text.insert(tk.END, part[1:-1], tags)
                elif part.startswith("//") and part.endswith("//"):
                    tags = ("r_bullet", "r_italic") if bullet else ("r_italic",)
                    self.knowledge_text.insert(tk.END, part[2:-2], tags)
                elif part.startswith("`") and part.endswith("`"):
                    tags = ("r_bullet", "r_code") if bullet else ("r_code",)
                    self.knowledge_text.insert(tk.END, part[1:-1].replace(" ", "\u00a0"), tags)
                elif part:
                    prev_was_link = False
                    tag = heading_tag or ("r_bullet" if bullet else "r_normal")
                    self.knowledge_text.insert(tk.END, part, tag)
            self.knowledge_text.insert(tk.END, "\n")
            i += 1

    def _render_image(self, img_name, alt_text=""):
        try:
            from PIL import Image, ImageTk
        except ImportError:
            self.knowledge_text.insert(tk.END, f"[图片: {alt_text or img_name}]", "r_normal")
            return
        try:
            from config import load_config
            root_path = load_config().get("root_path", "")
            if not root_path or not self.current_subject or not self.current_chapter:
                self.knowledge_text.insert(tk.END, f"[图片: {alt_text or img_name}]", "r_normal")
                return
            img_path = os.path.join(root_path, self.current_subject, self.current_chapter, "_images", img_name)
            if not os.path.exists(img_path):
                self.knowledge_text.insert(tk.END, f"[图片不存在: {alt_text or img_name}]", "r_warning")
                return
            img = Image.open(img_path)
            max_width = 380
            max_height = 200
            w, h = img.size
            if w > max_width or h > max_height:
                ratio = min(max_width / w, max_height / h)
                img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self.knowledge_text.image_create(tk.END, image=photo)
            self.knowledge_text.insert(tk.END, "\n")
            if not hasattr(self, '_rendered_images'):
                self._rendered_images = []
            self._rendered_images.append(photo)
        except Exception:
            self.knowledge_text.insert(tk.END, f"[图片加载失败: {alt_text or img_name}]", "r_warning")

    def _insert_code_block_editor(self, lang, lines):
        self.knowledge_text.insert(tk.END, "\n")
        
        block_start = self.knowledge_text.index(tk.INSERT)
        
        self.knowledge_text.tag_config("r_cb_header", font=("Microsoft YaHei", 10, "bold"), 
                                       foreground="#858585")
        self.knowledge_text.tag_config("r_cb_header_lang", font=("Microsoft YaHei", 10, "bold"), 
                                       foreground="#c678dd")
        
        dots = "●●●"
        self.knowledge_text.insert(tk.END, dots, "r_cb_header")
        self.knowledge_text.insert(tk.END, " " * 8, "r_cb_header")
        self.knowledge_text.insert(tk.END, lang.upper(), "r_cb_header_lang")
        self.knowledge_text.insert(tk.END, "\n")

        self._highlight_code_editor(lang, lines)
        
        self.knowledge_text.tag_config("r_cb_footer", font=("Microsoft YaHei", 8), 
                                       foreground="#666")
        self.knowledge_text.insert(tk.END, f" {len(lines)} lines", "r_cb_footer")
        self.knowledge_text.insert(tk.END, "\n")
        
        block_end = self.knowledge_text.index(tk.INSERT + " lineend")
        
        self.knowledge_text.tag_config("r_cb_block_bg", background="#1e1e1e")
        self.knowledge_text.tag_add("r_cb_block_bg", block_start, block_end)
        self.knowledge_text.tag_lower("r_cb_block_bg")
        
        self.knowledge_text.tag_config("r_cb_header_bg", background="#252526")
        self.knowledge_text.tag_add("r_cb_header_bg", block_start, block_start.split('.')[0] + ".0 lineend")
        
        self.knowledge_text.insert(tk.END, "\n")

    def _highlight_code_editor(self, lang, lines):
        lang = lang.lower()
        kw_conf = _LANG_KEYWORDS.get(lang, {})
        keywords = kw_conf.get("keywords", set())
        comment_markers = kw_conf.get("comment", [])
        string_chars = kw_conf.get("string", [])

        self.knowledge_text.tag_config("r_code_block", font=("Consolas", 11), background="#1e1e1e",
                                        foreground="#d4d4d4", lmargin1=50, lmargin2=10, 
                                        spacing1=2, spacing3=2, borderwidth=1, relief=tk.SUNKEN)
        self.knowledge_text.tag_config("r_cb_line_num", font=("Consolas", 10), foreground="#858585", 
                                       background="#2d2d2d", borderwidth=0)
        self.knowledge_text.tag_config("r_cb_keyword", foreground="#569cd6", font=("Consolas", 11, "bold"))
        self.knowledge_text.tag_config("r_cb_string", foreground="#ce9178")
        self.knowledge_text.tag_config("r_cb_comment", foreground="#6a9955", font=("Consolas", 11, "italic"))
        self.knowledge_text.tag_config("r_cb_number", foreground="#b5cea8")
        self.knowledge_text.tag_config("r_cb_operator", foreground="#d4d4d4")
        self.knowledge_text.tag_config("r_cb_function", foreground="#dcdcaa")
        self.knowledge_text.tag_config("r_cb_class", foreground="#4ec9b0")

        operators = set("+-*/%=<>!&|^~?:")
        builtins = {"print", "len", "range", "type", "str", "int", "float", "bool", 
                    "list", "dict", "set", "tuple", "True", "False", "None",
                    "console", "log", "document", "window", "parseInt", "parseFloat",
                    "Math", "Array", "Object", "String", "Number", "Boolean"}

        bg_tag = "r_cb_bg_line"
        self.knowledge_text.tag_config(bg_tag, background="#1e1e1e")
        
        self.knowledge_text.tag_config("r_code_block", font=("Consolas", 11), foreground="#d4d4d4",
                                        lmargin1=50, lmargin2=10, spacing1=2, spacing3=2)
        self.knowledge_text.tag_config("r_cb_line_num", font=("Consolas", 10), foreground="#858585")
        self.knowledge_text.tag_config("r_cb_keyword", foreground="#569cd6", font=("Consolas", 11, "bold"))
        self.knowledge_text.tag_config("r_cb_string", foreground="#ce9178")
        self.knowledge_text.tag_config("r_cb_comment", foreground="#6a9955", font=("Consolas", 11, "italic"))
        self.knowledge_text.tag_config("r_cb_number", foreground="#b5cea8")
        self.knowledge_text.tag_config("r_cb_operator", foreground="#d4d4d4")
        self.knowledge_text.tag_config("r_cb_function", foreground="#dcdcaa")
        self.knowledge_text.tag_config("r_cb_class", foreground="#4ec9b0")
        
        code_start = self.knowledge_text.index(tk.INSERT)
        
        for line_num, line in enumerate(lines, 1):
            self.knowledge_text.insert(tk.END, f"{line_num:3} ", "r_cb_line_num")
            self.knowledge_text.insert(tk.END, line, "r_code_block")
            self.knowledge_text.insert(tk.END, "\n")
        
        code_end = self.knowledge_text.index(tk.INSERT + " lineend")
        self.knowledge_text.tag_add(bg_tag, code_start, code_end)
        self.knowledge_text.tag_lower(bg_tag)
        
        for line_num, line in enumerate(lines, 1):
            line_start = f"{int(code_start.split('.')[0]) + line_num - 1}.0"
            self._highlight_line_editor(line, line_start, keywords, comment_markers, string_chars, operators, builtins)

    def _highlight_line_editor(self, line, line_start, keywords, comment_markers, string_chars, operators, builtins):
        i = 0
        while i < len(line):
            ch = line[i]
            
            if ch.isspace():
                i += 1
                continue
            
            if ch in operators:
                pos = f"{line_start.split('.')[0]}.{int(line_start.split('.')[1]) + 4 + i}"
                end_pos = f"{line_start.split('.')[0]}.{int(line_start.split('.')[1]) + 4 + i + 1}"
                self.knowledge_text.tag_add("r_cb_operator", pos, end_pos)
                i += 1
                continue
            
            for cm in comment_markers:
                if line[i:].startswith(cm):
                    pos = f"{line_start.split('.')[0]}.{int(line_start.split('.')[1]) + 4 + i}"
                    line_end = f"{line_start.split('.')[0]}.{int(line_start.split('.')[1]) + 4 + len(line)}"
                    self.knowledge_text.tag_add("r_cb_comment", pos, line_end)
                    return
            
            string_hit = False
            for sc in sorted(string_chars, key=len, reverse=True):
                if line[i:].startswith(sc):
                    end = line.find(sc, i + len(sc))
                    if end == -1:
                        end = len(line)
                    else:
                        end += len(sc)
                    start_pos = f"{line_start.split('.')[0]}.{int(line_start.split('.')[1]) + 4 + i}"
                    end_pos = f"{line_start.split('.')[0]}.{int(line_start.split('.')[1]) + 4 + end}"
                    self.knowledge_text.tag_add("r_cb_string", start_pos, end_pos)
                    i = end
                    string_hit = True
                    break
            if string_hit:
                continue
            
            if ch.isdigit() or (ch == '-' and i + 1 < len(line) and line[i + 1].isdigit()):
                j = i
                if ch == '-':
                    j += 1
                while j < len(line) and (line[j].isdigit() or line[j] == '.'):
                    j += 1
                start_pos = f"{line_start.split('.')[0]}.{int(line_start.split('.')[1]) + 4 + i}"
                end_pos = f"{line_start.split('.')[0]}.{int(line_start.split('.')[1]) + 4 + j}"
                self.knowledge_text.tag_add("r_cb_number", start_pos, end_pos)
                i = j
                continue
            
            if ch.isalpha() or ch == '_':
                j = i
                while j < len(line) and (line[j].isalnum() or line[j] == '_'):
                    j += 1
                word = line[i:j]
                word_upper = word.upper()
                start_pos = f"{line_start.split('.')[0]}.{int(line_start.split('.')[1]) + 4 + i}"
                end_pos = f"{line_start.split('.')[0]}.{int(line_start.split('.')[1]) + 4 + j}"
                
                if word in keywords or word_upper in keywords:
                    self.knowledge_text.tag_add("r_cb_keyword", start_pos, end_pos)
                elif word in builtins:
                    self.knowledge_text.tag_add("r_cb_function", start_pos, end_pos)
                elif word[0].isupper():
                    self.knowledge_text.tag_add("r_cb_class", start_pos, end_pos)
                i = j
                continue
            
            i += 1

    def _on_enter_in_knowledge(self, event):
        if self._read_mode and self._editing_type == "keyword":
            self._switch_to_edit_mode()
            return "break"

    def _switch_to_read_mode(self):
        self._read_mode = True
        self._raw_knowledge = self.knowledge_text.get("1.0", tk.END).strip()
        self._render_knowledge(self._raw_knowledge, self.type_var.get())
        self.knowledge_text.config(state=tk.DISABLED)
        self.keyword_entry.config(state="readonly")
        self.kw_legend_frame.pack_forget()
        self.kw_type_line.pack_forget()
        self.btn_save.config(text=tr("editor.edit_btn") + "  ↵", bg="#2ecc71", command=self._switch_to_edit_mode)
        self.btn_preview.pack_forget()
        self.bottom_bar_container.config(height=32)

    def _switch_to_edit_mode(self):
        if self._search_after_id is not None:
            self.root.after_cancel(self._search_after_id)
            self._search_after_id = None
        self._read_mode = False
        self.knowledge_text.config(state=tk.NORMAL)
        self.knowledge_text.delete("1.0", tk.END)
        self.knowledge_text.insert("1.0", self._raw_knowledge)
        self.keyword_entry.config(state="normal")
        self.kw_legend_frame.pack(fill=tk.X, pady=(4, 2))
        self.kw_type_line.pack(fill=tk.X, pady=(2, 2))
        self.btn_save.config(text=tr("editor.save_btn") + "  Ctrl+S", bg="#3498db", command=self._save_keyword)
        self.btn_preview.pack(side=tk.RIGHT, padx=(0, 6))
        self.bottom_bar_container.config(height=140)

    def _save_keyword(self):
        if self._search_after_id is not None:
            self.root.after_cancel(self._search_after_id)
            self._search_after_id = None
        if self._related_sync_after_id is not None:
            self.root.after_cancel(self._related_sync_after_id)
            self._related_sync_after_id = None
        if self._editing_type == "subject":
            desc = self.desc_text.get("1.0", tk.END).strip()
            self.db.save_subject_description(self.current_subject, desc)
            self._dirty = False
            messagebox.showinfo(tr("app.success"), tr("editor.saved_subject"))
            return
        if self._editing_type == "chapter":
            desc = self.desc_text.get("1.0", tk.END).strip()
            self.db.save_chapter_description(self.current_subject, self.current_chapter, desc)
            self._dirty = False
            messagebox.showinfo(tr("app.success"), tr("editor.saved_chapter"))
            return
        if not self.current_subject or not self.current_chapter or not self.current_keyword:
            messagebox.showwarning(tr("app.warning"), tr("editor.warn_select"))
            return
        kw = self.keyword_entry.get().strip()
        knowledge = self.knowledge_text.get("1.0", tk.END).strip()
        kt = self.type_var.get()
        if not kw or not knowledge:
            messagebox.showwarning(tr("app.warning"), tr("editor.warn_input"))
            return

        self._sync_related_from_content(knowledge)

        renamed = kw != self.current_keyword
        old_kw = self.current_keyword if renamed else None
        self.db.save_keyword(self.current_subject, self.current_chapter, kw, knowledge, kt, related=self._related_topics)
        self.current_keyword = kw
        if renamed:
            if old_kw:
                old_path = self.db.get_keyword_path(
                    self.current_subject, self.current_chapter, old_kw)
                if os.path.exists(old_path):
                    os.remove(old_path)
        if renamed:
            self._refresh_tree()
            self._select_keyword_in_tree(kw)
        data = self.db.get_keyword_data(
            self.current_subject, self.current_chapter, self.current_keyword)
        if data:
            self.type_var.set(data.get("type", "normal"))
        self._dirty = False
        if self._editing_type == "keyword":
            self._switch_to_read_mode()

    def _preview_card(self):
        if self._editing_type != "keyword":
            return
        try:
            kw = self.keyword_entry.get().strip()
            knowledge = self.knowledge_text.get("1.0", tk.END).strip()
            if not kw or not knowledge:
                messagebox.showwarning("提示", "关键词和内容不能为空")
                return
            if self._preview_popup is not None:
                try:
                    self._preview_popup.top.destroy()
                except tk.TclError:
                    pass
                self._preview_popup = None
            item = {
                "keyword": kw,
                "knowledge": knowledge,
                "type": self.type_var.get(),
                "subject": self.current_subject or "",
                "chapter": self.current_chapter or "",
                "related": self._related_topics,
            }
            self._preview_popup = PopupWindow(
                self.root, item, on_review=lambda *a: None,
                on_close=self._clear_preview, on_link=self.navigate_to_keyword, preview=True
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            messagebox.showerror("预览失败", str(e))

    def _clear_preview(self):
        self._preview_popup = None

    def _show_markup_help(self):
        dialog = tk.Toplevel(self.root)
        dialog.title(tr("markup.help_title"))
        dialog.geometry("500x420")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - 500) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - 420) // 2
        dialog.geometry(f"+{x}+{y}")

        header = tk.Frame(dialog, bg="#3498db", height=40)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text="📖 " + tr("markup.help_title"), font=("Microsoft YaHei", 12, "bold"),
                 fg="white", bg="#3498db").pack(expand=True)

        text = tk.Text(dialog, font=("Microsoft YaHei", 10), wrap=tk.WORD,
                       bg="white", relief=tk.SUNKEN, borderwidth=1, padx=12, pady=8)
        scrollbar = tk.Scrollbar(dialog, orient=tk.VERTICAL, command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8, pady=8)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=8)

        text.tag_config("h", font=("Microsoft YaHei", 11, "bold"), foreground="#2c3e50",
                        spacing1=6, spacing3=2)
        text.tag_config("red", foreground="#e74c3c", font=("Microsoft YaHei", 9, "bold"))
        text.tag_config("blue", foreground="#3498db", font=("Microsoft YaHei", 9, "bold"))
        text.tag_config("orange", foreground="#e67e22", font=("Microsoft YaHei", 9, "bold"))
        text.tag_config("code", font=("Consolas", 9), foreground="#555", background="#f9f9f9",
                        spacing1=1, spacing3=1)

        text.insert(tk.END, "📐 " + tr("markup.heading") + "\n", "h")
        text.insert(tk.END, "# H1\n## H2\n### H3\n\n", "code")
        text.insert(tk.END, "🖍 " + tr("markup.bold") + "\n", "h")
        text.insert(tk.END, "**" + tr("markup.bold") + "**\n\n", "code")
        text.insert(tk.END, "⚠️ " + tr("markup.warning") + "\n", "h")
        text.insert(tk.END, "!!" + tr("markup.warning") + "!!\n\n", "code")
        text.insert(tk.END, "💡 " + tr("markup.tip") + "\n", "h")
        text.insert(tk.END, "??" + tr("markup.tip") + "??\n\n", "code")
        text.insert(tk.END, "🔗 " + tr("markup.link") + "\n", "h")
        text.insert(tk.END, "[[" + tr("markup.link") + "]]\n[[target|display]]\n\n", "code")
        text.insert(tk.END, "📍 " + tr("markup.pin") + "\n", "h")
        text.insert(tk.END, "[[pin:word]]\n\n", "code")
        text.insert(tk.END, "🖼 " + tr("markup.image") + "\n", "h")
        text.insert(tk.END, "![alt](file.png)\n\n", "code")
        text.insert(tk.END, "💻 " + tr("markup.code_block") + "\n", "h")
        text.insert(tk.END, "```python\nprint(\"hello\")\n```\n\n", "code")
        text.insert(tk.END, "📄 " + tr("markup.inline_code") + "\n", "h")
        text.insert(tk.END, "`" + tr("markup.code") + "`\n\n", "code")
        text.insert(tk.END, "📋 " + tr("markup.list") + "\n", "h")
        text.insert(tk.END, "- " + tr("markup.item") + "\n* " + tr("markup.item") + "\n\n", "code")
        text.insert(tk.END, "🔁 " + tr("markup.linkmap") + "\n", "h")
        text.insert(tk.END, "[linkmap]\n" + tr("markup.linkmap_src") + " -> " + tr("markup.linkmap_target") + "\n[/linkmap]", "code")
        text.insert(tk.END, "\n\n🎴 " + tr("markup.italic") + "\n", "h")
        text.insert(tk.END, "//" + tr("markup.italic") + "//\n\n", "code")
        text.insert(tk.END, "📝 " + tr("markup.underline") + "\n", "h")
        text.insert(tk.END, "__" + tr("markup.underline") + "__\n\n", "code")
        text.insert(tk.END, "┅ " + tr("markup.underline_dashed") + "\n", "h")
        text.insert(tk.END, "~" + tr("markup.underline_dashed") + "~\n\n", "code")
        text.insert(tk.END, "⨁ " + tr("markup.strikethrough") + "\n", "h")
        text.insert(tk.END, "~~" + tr("markup.strikethrough") + "~~\n\n", "code")

        text.config(state=tk.DISABLED)

    def _cleanup_orphan_images(self):
        try:
            count = self.db.cleanup_all_orphan_images()
            if count > 0:
                self.image_status_label.config(text=f"✓ 已清理 {count} 张未引用图片", fg="#e67e22")
                self.root.after(4000, lambda: self.image_status_label.config(text=""))
        except Exception:
            pass

    def _insert_image_dialog(self):
        if self._editing_type != "keyword":
            messagebox.showinfo(tr("app.warning"), tr("editor.warn_select"))
            return
        
        self.image_status_label.config(text="📷 正在选择图片...", fg="#3498db")
        self.root.update_idletasks()
        
        file_path = filedialog.askopenfilename(
            title="选择图片",
            filetypes=[
                ("图片文件", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
                ("所有文件", "*.*")
            ]
        )
        if not file_path:
            self.image_status_label.config(text="", fg="#27ae60")
            return
        
        cfg = load_config()
        root_path = cfg.get("root_path", "")
        if not root_path:
            self.image_status_label.config(text="")
            messagebox.showerror("错误", "请先设置知识库路径")
            return
        
        if not self.current_subject or not self.current_chapter:
            self.image_status_label.config(text="")
            messagebox.showerror("错误", "请先选择一个关键词进行编辑")
            return
        
        images_dir = os.path.join(root_path, self.current_subject, self.current_chapter, "_images")
        if not os.path.exists(images_dir):
            os.makedirs(images_dir)
        
        filename = os.path.basename(file_path)
        dest_path = os.path.join(images_dir, filename)
        
        if os.path.exists(dest_path):
            result = messagebox.askyesno("确认覆盖", f"图片 \"{filename}\" 已存在，是否覆盖？")
            if not result:
                self.image_status_label.config(text="")
                return
        
        self.image_status_label.config(text="📷 正在添加图片...", fg="#27ae60")
        self.root.update_idletasks()
        
        import shutil
        shutil.copy2(file_path, dest_path)
        
        alt_text = os.path.splitext(filename)[0]
        
        image_markup = f"![{alt_text}]({filename})"
        
        was_read_mode = getattr(self, '_read_mode', False)
        if was_read_mode:
            self._switch_to_edit_mode()
        
        self.knowledge_text.insert(tk.INSERT, image_markup)
        self._dirty = True
        
        self.image_status_label.config(text=f"✓ 图片 \"{filename}\" 已添加")
        self.root.after(3000, lambda: self.image_status_label.config(text=""))

    def _select_keyword_in_tree(self, keyword, subject=None, chapter=None):
        subject = subject or self.current_subject
        chapter = chapter or self.current_chapter
        for item in self.tree.get_children(""):
            if subject and self._strip_emoji(self.tree.item(item, "text")) != subject:
                continue
            for child in self.tree.get_children(item):
                if chapter and self._strip_emoji(self.tree.item(child, "text")) != chapter:
                    continue
                for grand in self.tree.get_children(child):
                    if self._strip_emoji(self.tree.item(grand, "text")) == keyword:
                        self.tree.item(item, open=True)
                        self.tree.item(child, open=True)
                        self.tree.selection_set(grand)
                        self.tree.see(grand)
                        return


    def _nav_visit(self):
        if self.current_subject and self.current_chapter and self.current_keyword:
            entry = (self.current_subject, self.current_chapter, self.current_keyword)
            if not self._nav_stack or self._nav_stack[-1] != entry:
                self._nav_stack.append(entry)
        self._update_nav_buttons()

    def _nav_back(self):
        if self._nav_stack:
            entry = self._nav_stack.pop()
            self._nav_ignore = True
            self._select_keyword_in_tree(entry[2])
        self._update_nav_buttons()

    def _update_nav_buttons(self):
        try:
            self.nav_back_btn.config(state=tk.NORMAL if self._nav_stack else tk.DISABLED)
        except Exception:
            pass

    def navigate_to_keyword(self, keyword):
        if "::" in keyword:
            parts = keyword.split("::", 2)
            if len(parts) == 3:
                self._nav_visit()
                self._nav_ignore = True
                self._select_keyword_in_tree(parts[2], parts[0], parts[1])
                return
        best = None
        for item in self.tree.get_children(""):
            for child in self.tree.get_children(item):
                for grand in self.tree.get_children(child):
                    if self._strip_emoji(self.tree.item(grand, "text")) == keyword:
                        subj = self._strip_emoji(self.tree.item(item, "text"))
                        ch = self._strip_emoji(self.tree.item(child, "text"))
                        candidate = (item, child, grand, subj, ch)
                        if best is None:
                            best = candidate
                        s = candidate[3], candidate[4]
                        bs = best[3], best[4]
                        if (s[0] == self.current_subject and s[1] == self.current_chapter):
                            best = candidate
                            break
                        elif bs[0] != self.current_subject or bs[1] != self.current_chapter:
                            if s[0] == self.current_subject:
                                best = candidate
        if best:
            self._nav_visit()
            self._nav_ignore = True
            item, child, grand = best[:3]
            self.tree.item(item, open=True)
            self.tree.item(child, open=True)
            self.tree.selection_set(grand)
            self.tree.see(grand)

    def _on_link_click(self, link_text, tag):
        parsed = parse_link(link_text)
        if not parsed or "keyword" not in parsed:
            return
        keyword = parsed["keyword"]
        subject = parsed.get("subject")
        chapter = parsed.get("chapter")
        if subject and chapter:
            self._nav_visit()
            self._nav_ignore = True
            self._select_keyword_in_tree(keyword, subject, chapter)
            return
        candidates = []
        for item in self.tree.get_children(""):
            for child in self.tree.get_children(item):
                for grand in self.tree.get_children(child):
                    if self._strip_emoji(self.tree.item(grand, "text")) == keyword:
                        subj = self._strip_emoji(self.tree.item(item, "text"))
                        ch = self._strip_emoji(self.tree.item(child, "text"))
                        candidates.append((subj, ch, keyword))
        if len(candidates) == 1:
            self._nav_visit()
            self._nav_ignore = True
            self._select_keyword_in_tree(keyword, candidates[0][0], candidates[0][1])
        elif len(candidates) > 1:
            self._show_link_disambiguation(link_text, tag, keyword, candidates)

    def _show_link_disambiguation(self, link_text, tag, keyword, candidates):
        dialog = tk.Toplevel(self.root)
        dialog.title(tr("editor.link_ambiguous"))
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        tk.Label(dialog, text=tr("editor.link_ambiguous_desc").format(kw=keyword),
                 font=("Microsoft YaHei", 10)).pack(pady=(10, 4))
        lb = tk.Listbox(dialog, font=("Microsoft YaHei", 10), width=50, height=min(len(candidates), 8))
        lb.pack(padx=16, fill=tk.BOTH, expand=True)
        for subj, ch, _ in candidates:
            lb.insert(tk.END, f"{subj} › {ch} › {keyword}")
        def confirm():
            sel = lb.curselection()
            if not sel:
                return
            subj, ch, _ = candidates[sel[0]]
            dialog.destroy()
            self._finish_rewrite(link_text, tag, subj, ch, keyword)
        tk.Button(dialog, text=tr("app.confirm"), font=("Microsoft YaHei", 10),
                  command=confirm).pack(pady=(8, 10))
        dialog.bind("<Return>", lambda e: confirm())
        lb.bind("<Double-Button-1>", lambda e: confirm())
        lb.select_set(0)
        dialog.focus_set()
        self._center_dialog(dialog, 420, 280)

    def _finish_rewrite(self, link_text, tag, subject, chapter, keyword):
        import re
        try:
            full = self._raw_knowledge if self._read_mode else self.knowledge_text.get("1.0", tk.END)
            m = re.match(r'\[\[(?:[^:\]|]+::[^:\]|]+::)?([^\]|]+)(?:\|([^\]]+))?\]\]', link_text)
            display = m.group(2) or m.group(1) if m else keyword
            new_link = f"[[{subject}::{chapter}::{keyword}|{display}]]"
            updated = full.replace(link_text, new_link, 1)
            if updated != full:
                if self._read_mode:
                    self._raw_knowledge = updated.strip()
                    was_disabled = self.knowledge_text.cget("state") == tk.DISABLED
                    if was_disabled:
                        self.knowledge_text.config(state=tk.NORMAL)
                    self.knowledge_text.delete("1.0", tk.END)
                    self.knowledge_text.insert("1.0", updated.strip())
                    if was_disabled:
                        self.knowledge_text.config(state=tk.DISABLED)
                else:
                    self.knowledge_text.delete("1.0", tk.END)
                    self.knowledge_text.insert("1.0", updated.strip())
                    self._dirty = True
                if self.current_subject and self.current_chapter and self.current_keyword:
                    data = self.db.get_keyword_data(
                        self.current_subject, self.current_chapter, self.current_keyword)
                    ktype = data.get("type", "normal") if data else "normal"
                    self.db.save_keyword(
                        self.current_subject, self.current_chapter, self.current_keyword,
                        updated.strip(), ktype
                    )
            self._nav_visit()
            self._nav_ignore = True
            self._select_keyword_in_tree(keyword, subject, chapter)
        except Exception as e:
            import traceback
            traceback.print_exc()
            try:
                messagebox.showerror(tr("app.error"), str(e))
            except Exception:
                pass

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

    def _center_dialog(self, dialog, width=350, height=120):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - width) // 2
        y = (sh - height) // 2
        dialog.geometry(f"{width}x{height}+{x}+{y}")

    def _add_subject_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title(tr("editor.dialog_add_subject"))
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        self._center_dialog(dialog)

        tk.Label(dialog, text=tr("editor.dialog_subject_name"), font=("Microsoft YaHei", 10)).pack(pady=(12, 4))
        entry = tk.Entry(dialog, font=("Microsoft YaHei", 11))
        entry.pack(padx=20, fill=tk.X, ipady=2)
        entry.focus_set()

        def confirm():
            name = entry.get().strip()
            if name:
                self.db.add_subject(name)
                self.search_var.set("")
                self._refresh_tree()
                self._select_tree_item(("subject", name))
                dialog.destroy()
            else:
                messagebox.showwarning(tr("app.warning"), tr("editor.dialog_name_required"))

        tk.Button(dialog, text=tr("app.confirm"), font=("Microsoft YaHei", 10),
                  command=confirm).pack(pady=(8, 0))
        dialog.bind("<Return>", lambda e: confirm())

    def _add_chapter_dialog(self):
        if not self.current_subject:
            messagebox.showwarning(tr("app.warning"), tr("editor.dialog_select_subject"))
            return
        dialog = tk.Toplevel(self.root)
        dialog.title(tr("editor.dialog_add_chapter"))
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        self._center_dialog(dialog)

        tk.Label(dialog, text=tr("editor.subject") + f": {self.current_subject}", font=("Microsoft YaHei", 9),
                 fg="gray").pack(pady=(8, 0))
        tk.Label(dialog, text=tr("editor.dialog_chapter_name"), font=("Microsoft YaHei", 10)).pack(pady=(4, 0))
        entry = tk.Entry(dialog, font=("Microsoft YaHei", 11))
        entry.pack(padx=20, fill=tk.X, ipady=2)
        entry.focus_set()

        def confirm():
            name = entry.get().strip()
            if name:
                self.db.add_chapter(self.current_subject, name)
                self.search_var.set("")
                self._refresh_tree()
                self._select_tree_item(("chapter", name))
                dialog.destroy()
            else:
                messagebox.showwarning(tr("app.warning"), tr("editor.dialog_name_required"))

        tk.Button(dialog, text=tr("app.confirm"), font=("Microsoft YaHei", 10),
                  command=confirm).pack(pady=(8, 0))
        dialog.bind("<Return>", lambda e: confirm())

    def _add_keyword_dialog(self):
        if not self.current_subject or not self.current_chapter:
            messagebox.showwarning(tr("app.warning"), tr("editor.dialog_select_chapter"))
            return
        dialog = tk.Toplevel(self.root)
        dialog.title(tr("editor.dialog_add_keyword"))
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        self._center_dialog(dialog, 450, 340)

        tk.Label(dialog, text=tr("editor.subject") + f": {self.current_subject}  >  {self.current_chapter}",
                 font=("Microsoft YaHei", 9), fg="gray").pack(pady=(6, 0))

        tk.Label(dialog, text=tr("editor.keyword_label") + ":", font=("Microsoft YaHei", 10)).pack(pady=(4, 0))
        kw_entry = tk.Entry(dialog, font=("Microsoft YaHei", 11))
        kw_entry.pack(padx=20, fill=tk.X, ipady=2)
        kw_entry.focus_set()

        tk.Label(dialog, text=tr("editor.knowledge_label") + ":", font=("Microsoft YaHei", 10)).pack(pady=(4, 0))
        txt = tk.Text(dialog, font=("Microsoft YaHei", 10), height=3, wrap=tk.WORD)
        txt.pack(padx=20, fill=tk.X, pady=(2, 4))

        tk.Label(dialog, text=tr("editor.dialog_type_hint"), font=("Microsoft YaHei", 9),
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
                self.search_var.set("")
                self._refresh_tree()
                self.current_keyword = kw
                self._select_keyword_in_tree(kw)
                self._load_keyword()
                dialog.destroy()
            else:
                messagebox.showwarning(tr("app.warning"), tr("editor.warn_input"))

        tk.Button(dialog, text=tr("app.confirm"), font=("Microsoft YaHei", 10), bg="#3498db",
                  fg="white", relief=tk.FLAT, padx=20, pady=4,
                  command=confirm).pack(pady=(6, 0))
        dialog.bind("<Return>", lambda e: confirm())

    def _delete_selected(self):
        sel = self.tree.selection()
        if not sel:
            return

        items_to_delete = []
        for item in sel:
            parent_id = self.tree.parent(item)
            grandparent_id = self.tree.parent(parent_id) if parent_id else ""
            text = self._strip_emoji(self.tree.item(item, "text"))
            if not parent_id:
                items_to_delete.append(("subject", text))
            elif not grandparent_id:
                subj = self._strip_emoji(self.tree.item(parent_id, "text"))
                items_to_delete.append(("chapter", subj, text))
            else:
                subj = self._strip_emoji(self.tree.item(grandparent_id, "text"))
                ch = self._strip_emoji(self.tree.item(parent_id, "text"))
                items_to_delete.append(("keyword", subj, ch, text))

        if not items_to_delete:
            return

        lines = []
        for entry in items_to_delete:
            if entry[0] == "subject":
                lines.append("  " + tr("editor.subject") + f": {entry[1]}")
            elif entry[0] == "chapter":
                lines.append("  " + tr("editor.chapter") + f": {entry[1]} → {entry[2]}")
            else:
                lines.append("  " + tr("editor.keyword_label") + f": {entry[1]} → {entry[2]} → {entry[3]}")
        msg = f"确定要删除以下 {len(items_to_delete)} 个项目？\n\n" + "\n".join(lines)
        if not messagebox.askyesno("确认", msg):
            return

        for entry in items_to_delete:
            if entry[0] == "subject":
                self.db.delete_subject(entry[1])
            elif entry[0] == "chapter":
                self.db.delete_chapter(entry[1], entry[2])
            else:
                self.db.delete_keyword(entry[1], entry[2], entry[3])

        self._refresh_tree()
        self.current_keyword = None
        self.current_chapter = None
        self._show_empty()

    def _on_tree_right_click(self, event):
        item = self.tree.identify_row(event.y)
        if not item:
            return
        sel = self.tree.selection()
        if item not in sel:
            self.tree.selection_set(item)
        menu = tk.Menu(self.root, tearoff=0, font=("Microsoft YaHei", 9))
        if len(self.tree.selection()) == 1:
            menu.add_command(label=tr("editor.rename_btn"), command=self._rename_selected)
        menu.add_command(label=tr("editor.delete_btn"), command=self._delete_selected)
        menu.post(event.x_root, event.y_root)

    def _rename_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        item = sel[0]
        parent_id = self.tree.parent(item)
        grandparent_id = self.tree.parent(parent_id) if parent_id else ""
        old_name = self._strip_emoji(self.tree.item(item, "text"))

        if not parent_id:
            self._rename_subject(item, old_name)
        elif not grandparent_id:
            self._rename_chapter(item, old_name)
        else:
            self._rename_keyword(item, old_name)

    def _rename_subject(self, item, old_name):
        dialog = tk.Toplevel(self.root)
        dialog.title("重命名学科")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        self._center_dialog(dialog)

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
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        self._center_dialog(dialog)

        tk.Label(dialog, text=tr("editor.subject") + f": {subject}", font=("Microsoft YaHei", 9),
                 fg="gray").pack(pady=(8, 0))
        tk.Label(dialog, text=tr("editor.chapter") + ":", font=("Microsoft YaHei", 10)).pack(pady=(4, 0))
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
        messagebox.showinfo(tr("app.info"), tr("editor.rename_hint"))

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


_LANG_KEYWORDS = {
    "python": {
        "keywords": {
            "def", "class", "if", "else", "elif", "for", "while", "import", "from",
            "return", "try", "except", "finally", "with", "as", "in", "not", "and",
            "or", "True", "False", "None", "pass", "break", "continue", "lambda",
            "yield", "raise", "is", "del", "global", "nonlocal", "assert", "async",
            "await",
        },
        "comment": ["#"],
        "string": ["\"", "'", "\"\"\"", "'''"],
    },
    "javascript": {
        "keywords": {
            "function", "const", "let", "var", "if", "else", "for", "while", "do",
            "switch", "case", "break", "continue", "return", "import", "export",
            "from", "class", "extends", "new", "this", "super", "try", "catch",
            "finally", "throw", "async", "await", "yield", "typeof", "instanceof",
            "of", "in", "true", "false", "null", "undefined", "NaN", "delete",
            "void", "with", "debugger",
        },
        "comment": ["//", "/*"],
        "string": ["\"", "'", "`"],
    },
    "typescript": {
        "keywords": {
            "function", "const", "let", "var", "if", "else", "for", "while", "do",
            "switch", "case", "break", "continue", "return", "import", "export",
            "from", "class", "extends", "implements", "interface", "type", "enum",
            "new", "this", "super", "try", "catch", "finally", "throw", "async",
            "await", "yield", "typeof", "instanceof", "of", "in", "true", "false",
            "null", "undefined", "as", "is", "keyof", "readonly", "public",
            "private", "protected", "static", "abstract", "declare",
        },
        "comment": ["//", "/*"],
        "string": ["\"", "'", "`"],
    },
    "java": {
        "keywords": {
            "public", "private", "protected", "static", "class", "interface",
            "extends", "implements", "abstract", "final", "void", "return",
            "if", "else", "for", "while", "do", "switch", "case", "break",
            "continue", "new", "this", "super", "try", "catch", "finally",
            "throw", "throws", "import", "package", "boolean", "int", "long",
            "float", "double", "char", "byte", "short", "String", "true",
            "false", "null", "synchronized", "volatile", "transient",
            "instanceof", "enum", "var",
        },
        "comment": ["//", "/*"],
        "string": ["\""],
    },
    "cpp": {
        "keywords": {
            "int", "long", "float", "double", "char", "bool", "void", "auto",
            "const", "static", "class", "struct", "enum", "union", "typedef",
            "template", "typename", "namespace", "using", "virtual", "override",
            "public", "private", "protected", "if", "else", "for", "while", "do",
            "switch", "case", "break", "continue", "return", "new", "delete",
            "this", "try", "catch", "throw", "true", "false", "nullptr",
            "include", "define", "pragma", "sizeof", "typedef", "constexpr",
            "inline", "extern", "friend", "operator",
        },
        "comment": ["//", "/*"],
        "string": ["\"", "'"],
    },
    "c": {
        "keywords": {
            "int", "long", "float", "double", "char", "void", "short", "unsigned",
            "signed", "const", "static", "struct", "union", "enum", "typedef",
            "if", "else", "for", "while", "do", "switch", "case", "break",
            "continue", "return", "sizeof", "include", "define", "pragma",
            "extern", "volatile", "register", "goto",
        },
        "comment": ["//", "/*"],
        "string": ["\"", "'"],
    },
    "html": {
        "keywords": set(),
        "comment": ["<!--"],
        "string": ["\"", "'"],
    },
    "css": {
        "keywords": set(),
        "comment": ["/*"],
        "string": ["\"", "'"],
    },
    "bash": {
        "keywords": {
            "if", "then", "else", "elif", "fi", "for", "while", "do", "done",
            "case", "esac", "function", "return", "exit", "echo", "export",
            "local", "source", "cd", "ls", "rm", "mv", "cp", "mkdir",
        },
        "comment": ["#"],
        "string": ["\"", "'"],
    },
    "sql": {
        "keywords": {
            "SELECT", "FROM", "WHERE", "INSERT", "INTO", "VALUES", "UPDATE",
            "SET", "DELETE", "CREATE", "TABLE", "DROP", "ALTER", "INDEX",
            "JOIN", "LEFT", "RIGHT", "INNER", "OUTER", "ON", "AND", "OR",
            "NOT", "IN", "LIKE", "BETWEEN", "ORDER", "BY", "GROUP", "HAVING",
            "LIMIT", "OFFSET", "AS", "DISTINCT", "COUNT", "SUM", "AVG", "MIN",
            "MAX", "NULL", "IS", "TRUE", "FALSE", "PRIMARY", "KEY", "FOREIGN",
            "REFERENCES", "UNION", "ALL", "CASE", "WHEN", "THEN", "ELSE", "END",
            "EXISTS", "UNIQUE", "DEFAULT", "CHECK", "VIEW", "INDEX",
        },
        "comment": ["--", "/*"],
        "string": ["\"", "'"],
    },
}
