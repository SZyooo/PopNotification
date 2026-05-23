import tkinter as tk
import re
import math
import os

from i18n import tr
from memory import update_memory

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

TYPE_COLORS = {
    "normal": "#2c3e50",
    "tip": "#27ae60",
    "warning": "#e74c3c",
}

TYPE_BG = {
    "normal": "#ecf0f1",
    "tip": "#e8f8f5",
    "warning": "#fdedec",
}

TYPE_ACCENT = {
    "normal": "#3498db",
    "tip": "#1abc9c",
    "warning": "#e67e22",
}

TYPE_TAG = {"normal": "popup.type_normal", "tip": "popup.type_tip", "warning": "popup.type_warning"}


class PopupWindow:
    def __init__(self, parent, item, on_review, on_close, on_link=None, on_edit=None, preview=False):
        self.item = item
        self.on_review = on_review
        self.on_close = on_close
        self.on_link = on_link
        self.on_edit = on_edit
        self.expanded = False
        self.closing = False
        self.preview = preview

        kw = item.get("keyword", "")
        knowledge = item.get("knowledge", "")
        ktype = item.get("type", "normal")
        subject = item.get("subject", "")
        chapter = item.get("chapter", "")
        self._subject = subject
        self._chapter = chapter
        related = item.get("related", [])

        self.width = 460
        self.height = 200
        self.expanded_h = 500
        self.knowledge = knowledge
        self.ktype = ktype

        screen_w = parent.winfo_screenwidth()
        screen_h = parent.winfo_screenheight()
        x = (screen_w - self.width) // 2
        y = -self.height

        self.top = tk.Toplevel(parent)
        self.top.title(f"{tr('popup.knowledge_card')} - {kw}")
        self.top.geometry(f"{self.width}x{self.height}+{x}+{y}")
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)

        accent = TYPE_ACCENT.get(ktype, TYPE_ACCENT["normal"])
        bg = TYPE_BG.get(ktype, TYPE_BG["normal"])

        self.top.configure(bg=accent)

        header_frame = tk.Frame(self.top, bg=accent, height=36)
        header_frame.pack(fill=tk.X)
        header_frame.pack_propagate(False)

        tk.Label(
            header_frame, text=f"[{subject}] {chapter}",
            bg=accent, fg="white",
            font=("Microsoft YaHei", 9), anchor=tk.W
        ).pack(side=tk.LEFT, padx=10, pady=4)

        type_tag = tr(TYPE_TAG.get(ktype, "popup.type_normal"))
        tk.Label(
            header_frame, text=type_tag,
            bg="white", fg=accent,
            font=("Microsoft YaHei", 8, "bold"), padx=6, pady=1
        ).pack(side=tk.RIGHT, padx=10)

        btn_bg = "#f0f0f0"
        btn_frame = tk.Frame(self.top, bg=accent, height=50)
        btn_frame.pack(fill=tk.X)
        btn_frame.pack_propagate(False)

        body_frame = tk.Frame(self.top, bg=bg)
        body_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=(0, 2))

        kw_label = tk.Label(
            body_frame, text=kw, bg=bg, fg=accent,
            font=("Microsoft YaHei", 13, "bold"), anchor=tk.W
        )
        kw_label.pack(fill=tk.X, padx=12, pady=(8, 2))

        self.text_frame = tk.Frame(body_frame, bg=bg)
        self.text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 4))

        self.text_hscroll = tk.Scrollbar(self.text_frame, orient=tk.HORIZONTAL)
        self.text_hscroll.pack(side=tk.BOTTOM, fill=tk.X)

        self.text_widget = tk.Text(
            self.text_frame, font=("Microsoft YaHei", 10),
            bg=bg, relief=tk.FLAT, bd=0,
            wrap=tk.NONE, padx=2, pady=2,
            xscrollcommand=self.text_hscroll.set,
            state=tk.DISABLED,
        )
        self.text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.text_hscroll.config(command=self.text_widget.xview)
        self._bind_drag()

        self.code_frames = []

        # Related topics section
        self.related_frame = tk.Frame(body_frame, bg=bg)
        if related:
            self.related_frame.pack(fill=tk.X, padx=10, pady=(0, 4))
            tk.Label(self.related_frame, text=tr("popup.related") + ":", font=("Microsoft YaHei", 9, "bold"),
                     fg=accent, bg=bg).pack(anchor=tk.W, pady=(0, 2))
            for rel in related:
                r_kw = rel.get("keyword", "")
                r_display = rel.get("display", r_kw)
                if r_kw:
                    row = tk.Frame(self.related_frame, bg=bg)
                    row.pack(anchor=tk.W)
                    link = tk.Label(row, text=f"🔗 {r_display}", font=("Microsoft YaHei", 9),
                                    fg="#2980b9", bg=bg, cursor="hand2")
                    link.pack(side=tk.LEFT)
                    tk.Label(row, text=f"  [{r_kw}]", font=("Microsoft YaHei", 7),
                             fg="#bbb", bg=bg).pack(side=tk.LEFT)
                    if self.on_link:
                        link.bind("<Button-1>", lambda e, k=r_kw: self.on_link(k))
                    link.bind("<Enter>", lambda e: self.text_widget.config(cursor="hand2"))
                    link.bind("<Leave>", lambda e: self.text_widget.config(cursor="hand2"))

        self.more_indicator = tk.Label(
            body_frame, text="…", bg=bg, fg="#999",
            font=("Microsoft YaHei", 10), anchor=tk.CENTER
        )

        self._populate_text(knowledge, ktype)
        # Schedule indicator check after slide-in animation completes (150ms)
        self.top.after(200, self._update_more_indicator)

        self.detail_btn = tk.Button(
            btn_frame, text=tr("popup.detail") + " ▼", font=("Microsoft YaHei", 9),
            bg=btn_bg, relief=tk.GROOVE, padx=10, cursor="hand2",
            command=self.toggle_expand
        )
        self.detail_btn.place(x=8, rely=0.5, anchor=tk.W, height=32)

        close_btn = tk.Button(
            btn_frame, text="×", font=("Arial", 14, "bold"),
            bg="#e74c3c", fg="white", relief=tk.FLAT, padx=6, cursor="hand2",
            command=lambda: self._close(suppress=True)
        )
        close_btn.place(relx=1.0, rely=0.5, anchor=tk.E, x=-8, height=28)

        edit_btn = tk.Button(
            btn_frame, text=tr("popup.edit"), font=("Microsoft YaHei", 9),
            bg=btn_bg, relief=tk.GROOVE, padx=8, cursor="hand2",
            command=self._edit
        )
        if not self.preview:
            edit_btn.place(relx=1.0, rely=0.5, anchor=tk.E, x=-55, height=28)

        if not self.preview:
            for i, (tr_key, action_key) in enumerate([("popup.strange", "strange"), ("popup.familiar", "familiar"), ("popup.master", "master")]):
                btn = tk.Button(
                    btn_frame, text=tr(tr_key), font=("Microsoft YaHei", 9),
                    bg=btn_bg, relief=tk.GROOVE, cursor="hand2",
                    command=lambda a=action_key: self._review(a)
                )
                btn.place(relx=0.3 + i * 0.15, rely=0.5, anchor=tk.CENTER, width=70, height=32)

        self._slide_in(self.width, self.height, screen_h)
        self.top.bind("<Escape>", lambda e: self._close())

    def _populate_text(self, text, ktype):
        accent = TYPE_ACCENT.get(ktype, TYPE_ACCENT["normal"])
        bg = TYPE_BG.get(ktype, TYPE_BG["normal"])
        default_fg = TYPE_COLORS.get(ktype, TYPE_COLORS["normal"])

        self.text_widget.config(state=tk.NORMAL)
        self.text_widget.delete("1.0", tk.END)

        self.text_widget.tag_config("normal", foreground=default_fg)
        self.text_widget.tag_config("highlight", foreground=accent, font=("Microsoft YaHei", 10, "bold"))
        self.text_widget.tag_config("tip", foreground="#27ae60", font=("Microsoft YaHei", 10))
        self.text_widget.tag_config("warning", foreground="#e74c3c", font=("Microsoft YaHei", 10, "bold"))
        self.text_widget.tag_config("bullet", foreground=default_fg, lmargin1=10, lmargin2=24)
        self.text_widget.tag_config("pin", foreground="#8e44ad", font=("Microsoft YaHei", 10, "bold"))
        self.text_widget.tag_config("code", foreground="#e67e22", font=("Consolas", 11, "bold"),
                                     background="#2d2d2d", relief=tk.GROOVE, borderwidth=1,
                                     overstrike=False, underline=False, spacing1=2, spacing3=2)
        for lvl, size in [(1, 16), (2, 14), (3, 12)]:
            self.text_widget.tag_config(f"h{lvl}",
                font=("Microsoft YaHei", size, "bold"), foreground="#2c3e50",
                spacing1=6, spacing3=2)
        self.text_widget.tag_config("italic", font=("Microsoft YaHei", 10, "italic"),
                                     foreground=default_fg)
        self.text_widget.tag_config("underline", font=("Microsoft YaHei", 10),
                                     foreground=default_fg, underline=1)
        self.text_widget.tag_config("underline_dashed", font=("Microsoft YaHei", 10, "italic"),
                                     foreground=default_fg, underline=1)
        self.text_widget.tag_config("strikethrough", font=("Microsoft YaHei", 10),
                                     foreground=default_fg, overstrike=1)

        self._insert_markup_text(text)

        self.text_widget.config(state=tk.DISABLED)

    def _bind_drag(self):
        self._space_held = False
        self._drag_active = False
        self._drag_start_x = 0
        self._drag_start_y = 0

        def on_space_press(event):
            self._space_held = True
            self.text_widget.config(cursor="hand2")

        def on_space_release(event):
            self._space_held = False
            self.text_widget.config(cursor="")

        def on_press(event):
            if self._space_held:
                self._drag_start_x = event.x_root
                self._drag_start_y = event.y_root
                self._drag_active = True
                self.text_widget.config(cursor="fleur")
                return "break"

        def on_drag(event):
            if self._space_held:
                if self._drag_active:
                    dx = self._drag_start_x - event.x_root
                    dy = self._drag_start_y - event.y_root
                    if abs(dx) > 3:
                        units = max(1, abs(dx) // 8)
                        self.text_widget.xview_scroll(units if dx > 0 else -units, "units")
                    if abs(dy) > 3:
                        units = max(1, abs(dy) // 8)
                        self.text_widget.yview_scroll(units if dy > 0 else -units, "units")
                    if abs(dx) > 3 or abs(dy) > 3:
                        self._drag_start_x = event.x_root
                        self._drag_start_y = event.y_root
                return "break"

        def on_release(event):
            if self._drag_active:
                self._drag_active = False
                self.text_widget.config(cursor="hand2" if self._space_held else "")
                return "break"

        self.text_widget.bind("<KeyPress-space>", on_space_press)
        self.text_widget.bind("<KeyRelease-space>", on_space_release)
        self.text_widget.bind("<Button-1>", on_press)
        self.text_widget.bind("<B1-Motion>", on_drag)
        self.text_widget.bind("<ButtonRelease-1>", on_release)
        self.text_widget.bind("<Button-2>", lambda e: "break")
        self.text_widget.bind("<B2-Motion>", lambda e: "break")

    def _insert_markup_text(self, text):
        from editor import expand_linkmap
        text = expand_linkmap(text)
        self._link_tag_counter = getattr(self, "_link_tag_counter", 0) + 1
        link_idx = 0
        lines = text.split("\n")
        i = 0
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
                self._insert_code_block(lang, code_lines)
                continue
            # Normal line processing
            bullet = False
            heading_tag = ""
            rest = line
            if rest.startswith("- ") or rest.startswith("* "):
                bullet = True
                rest = rest[2:]
                if rest.startswith("### "):
                    heading_tag = "h3"
                    rest = rest[4:]
                elif rest.startswith("## "):
                    heading_tag = "h2"
                    rest = rest[3:]
                elif rest.startswith("# "):
                    heading_tag = "h1"
                    rest = rest[2:]
                self.text_widget.insert(tk.END, "  • ", heading_tag or "bullet")
            else:
                if rest.startswith("### "):
                    heading_tag = "h3"
                    rest = rest[4:]
                elif rest.startswith("## "):
                    heading_tag = "h2"
                    rest = rest[3:]
                elif rest.startswith("# "):
                    heading_tag = "h1"
                    rest = rest[2:]
            pattern = r'(!\[.*?\]\([^)]+\)|\[\[.*?\]\]|\*\*.*?\*\*|!!.*?!!|\?\?.*?\?\?|~~.*?~~|__.*?__|~.*?~|//.*?//|`.*?`)'
            parts = re.split(pattern, rest)
            for part in parts:
                if part.startswith("![") and part.endswith(")"):
                    match = re.match(r'!\[(.*?)\]\((.+)\)', part)
                    if match:
                        alt_text = match.group(1)
                        img_path = match.group(2)
                        self._insert_image(img_path, alt_text)
                if part.startswith("[[") and part.endswith("]]"):
                    inner = part[2:-2]
                    if inner.startswith("pin:"):
                        pin_word = inner[4:]
                        pin_display = pin_word.split("|", 1)[0] if "|" in pin_word else pin_word
                        tags = ("bullet", "pin") if bullet else ("pin",)
                        self.text_widget.insert(tk.END, f"📌 {pin_display}", tags)
                    elif "|" in inner:
                        keyword, display = inner.split("|", 1)
                        if not keyword:
                            keyword = display or inner
                            display = keyword
                        if not display:
                            display = keyword or inner
                        link_idx += 1
                        tag = f"_link_{self._link_tag_counter}_{link_idx}"
                        if self.on_link:
                            self.text_widget.tag_config(tag, foreground="#2980b9", underline=1,
                                                        font=("Microsoft YaHei", 10))
                            bt = ("bullet", tag) if bullet else (tag,)
                            self.text_widget.insert(tk.END, display, bt)
                            self.text_widget.tag_bind(tag, "<Button-1>",
                                lambda e, k=keyword: self.on_link(k))
                            self.text_widget.tag_bind(tag, "<Enter>",
                                lambda e: self.text_widget.config(cursor="hand2"))
                            self.text_widget.tag_bind(tag, "<Leave>",
                                lambda e: self.text_widget.config(cursor="hand2"))
                        else:
                            tags = ("bullet",) if bullet else ()
                            self.text_widget.insert(tk.END, display, tags + ("normal",))
                    else:
                        keyword = inner
                        display = inner
                        link_idx += 1
                        tag = f"_link_{self._link_tag_counter}_{link_idx}"
                        if self.on_link:
                            self.text_widget.tag_config(tag, foreground="#2980b9", underline=1,
                                                        font=("Microsoft YaHei", 10))
                            bt = ("bullet", tag) if bullet else (tag,)
                            self.text_widget.insert(tk.END, display, bt)
                            self.text_widget.tag_bind(tag, "<Button-1>",
                                lambda e, k=keyword: self.on_link(k))
                            self.text_widget.tag_bind(tag, "<Enter>",
                                lambda e: self.text_widget.config(cursor="hand2"))
                            self.text_widget.tag_bind(tag, "<Leave>",
                                lambda e: self.text_widget.config(cursor="hand2"))
                        else:
                            tags = ("bullet",) if bullet else ()
                            self.text_widget.insert(tk.END, display, tags + ("normal",))
                elif part.startswith("**") and part.endswith("**"):
                    tags = ("bullet", "highlight") if bullet else ("highlight",)
                    self.text_widget.insert(tk.END, part[2:-2], tags)
                elif part.startswith("!!") and part.endswith("!!"):
                    tags = ("bullet", "warning") if bullet else ("warning",)
                    self.text_widget.insert(tk.END, part[2:-2], tags)
                elif part.startswith("??") and part.endswith("??"):
                    tags = ("bullet", "tip") if bullet else ("tip",)
                    self.text_widget.insert(tk.END, part[2:-2], tags)
                elif part.startswith("~~") and part.endswith("~~"):
                    tags = ("bullet", "strikethrough") if bullet else ("strikethrough",)
                    self.text_widget.insert(tk.END, part[2:-2], tags)
                elif part.startswith("__") and part.endswith("__"):
                    tags = ("bullet", "underline") if bullet else ("underline",)
                    self.text_widget.insert(tk.END, part[2:-2], tags)
                elif part.startswith("~") and part.endswith("~"):
                    tags = ("bullet", "underline_dashed") if bullet else ("underline_dashed",)
                    self.text_widget.insert(tk.END, part[1:-1], tags)
                elif part.startswith("//") and part.endswith("//"):
                    tags = ("bullet", "italic") if bullet else ("italic",)
                    self.text_widget.insert(tk.END, part[2:-2], tags)
                elif part.startswith("`") and part.endswith("`"):
                    tags = ("bullet", "code") if bullet else ("code",)
                    self.text_widget.insert(tk.END, part[1:-1].replace(" ", "\u00a0"), tags)
                elif part:
                    tag = heading_tag or ("bullet" if bullet else "normal")
                    self.text_widget.insert(tk.END, part, tag)
            self.text_widget.insert(tk.END, "\n")
            i += 1

    def _insert_image(self, img_path, alt_text=""):
        self.text_widget.insert(tk.END, "\n")
        
        if not HAS_PIL:
            self.text_widget.insert(tk.END, f"[图片: {alt_text or img_path}]", "normal")
            self.text_widget.insert(tk.END, "\n")
            return
        
        try:
            if not os.path.isabs(img_path):
                from config import load_config
                root_path = load_config().get("root_path", "")
                if root_path:
                    candidate = os.path.join(root_path, img_path)
                    if not os.path.exists(candidate) and "/" not in img_path and "\\" not in img_path:
                        candidate = os.path.join(root_path, getattr(self, '_subject', ''), getattr(self, '_chapter', ''), "_images", img_path)
                    img_path = candidate
            
            if not os.path.exists(img_path):
                self.text_widget.insert(tk.END, f"[图片不存在: {alt_text or img_path}]", "warning")
                self.text_widget.insert(tk.END, "\n")
                return
            
            max_width = self.width - 60
            max_height = 200
            
            img = Image.open(img_path)
            img_width, img_height = img.size
            
            if img_width > max_width or img_height > max_height:
                ratio = min(max_width / img_width, max_height / img_height)
                new_width = int(img_width * ratio)
                new_height = int(img_height * ratio)
                img = img.resize((new_width, new_height), Image.LANCZOS)
            
            photo = ImageTk.PhotoImage(img)
            
            self.text_widget.image_create(tk.END, image=photo)
            self.text_widget.insert(tk.END, "\n")
            
            if not hasattr(self, '_images'):
                self._images = []
            self._images.append(photo)
            
        except Exception as e:
            self.text_widget.insert(tk.END, f"[图片加载失败: {alt_text or img_path}]", "warning")
            self.text_widget.insert(tk.END, "\n")

    def _insert_code_block(self, lang, lines):
        self.text_widget.insert(tk.END, "\n")
        
        block_start = self.text_widget.index(tk.INSERT)
        
        self.text_widget.tag_config("cb_header", font=("Microsoft YaHei", 10, "bold"), 
                                     foreground="#858585")
        self.text_widget.tag_config("cb_header_lang", font=("Microsoft YaHei", 10, "bold"), 
                                     foreground="#c678dd")
        
        dots = "●●●"
        self.text_widget.insert(tk.END, dots, "cb_header")
        self.text_widget.insert(tk.END, " " * 8, "cb_header")
        self.text_widget.insert(tk.END, lang.upper(), "cb_header_lang")
        self.text_widget.insert(tk.END, "\n")

        self._highlight_code(lang, lines)
        
        self.text_widget.tag_config("cb_footer", font=("Microsoft YaHei", 8), 
                                     foreground="#666")
        self.text_widget.insert(tk.END, f" {len(lines)} lines", "cb_footer")
        self.text_widget.insert(tk.END, "\n")
        
        block_end = self.text_widget.index(tk.INSERT + " lineend")
        
        self.text_widget.tag_config("cb_block_bg", background="#1e1e1e")
        self.text_widget.tag_add("cb_block_bg", block_start, block_end)
        self.text_widget.tag_lower("cb_block_bg")
        
        self.text_widget.tag_config("cb_header_bg", background="#252526")
        self.text_widget.tag_add("cb_header_bg", block_start, block_start.split('.')[0] + ".0 lineend")
        
        self.text_widget.insert(tk.END, "\n")

    def _highlight_code(self, lang, lines):
        lang = lang.lower()
        kw_conf = self.__class__._LANG_KEYWORDS.get(lang, {})
        keywords = kw_conf.get("keywords", set())
        comment_markers = kw_conf.get("comment", [])
        string_chars = kw_conf.get("string", [])

        self.text_widget.tag_config("code_block", font=("Consolas", 11), background="#1e1e1e",
                                     foreground="#d4d4d4", lmargin1=50, lmargin2=10, 
                                     spacing1=2, spacing3=2)
        self.text_widget.tag_config("cb_line_num", font=("Consolas", 10), foreground="#858585", 
                                     background="#2d2d2d")
        self.text_widget.tag_config("cb_keyword", foreground="#569cd6", font=("Consolas", 11, "bold"))
        self.text_widget.tag_config("cb_string", foreground="#ce9178")
        self.text_widget.tag_config("cb_comment", foreground="#6a9955", font=("Consolas", 11, "italic"))
        self.text_widget.tag_config("cb_number", foreground="#b5cea8")
        self.text_widget.tag_config("cb_operator", foreground="#d4d4d4")
        self.text_widget.tag_config("cb_function", foreground="#dcdcaa")
        self.text_widget.tag_config("cb_class", foreground="#4ec9b0")

        operators = set("+-*/%=<>!&|^~?:")
        builtins = {"print", "len", "range", "type", "str", "int", "float", "bool", 
                    "list", "dict", "set", "tuple", "True", "False", "None",
                    "console", "log", "document", "window", "parseInt", "parseFloat",
                    "Math", "Array", "Object", "String", "Number", "Boolean"}

        bg_tag = "cb_bg_line"
        self.text_widget.tag_config(bg_tag, background="#1e1e1e")
        
        code_start = self.text_widget.index(tk.INSERT)
        
        for line_num, line in enumerate(lines, 1):
            self.text_widget.insert(tk.END, f"{line_num:3} ", "cb_line_num")
            
            self.text_widget.insert(tk.END, line, "code_block")
            self.text_widget.insert(tk.END, "\n")
        
        code_end = self.text_widget.index(tk.INSERT + " lineend")
        self.text_widget.tag_add(bg_tag, code_start, code_end)
        self.text_widget.tag_lower(bg_tag)
        
        for line_num, line in enumerate(lines, 1):
            line_start = f"{int(code_start.split('.')[0]) + line_num - 1}.0"
            self._highlight_line(line, line_start, keywords, comment_markers, string_chars, operators, builtins)

    def _highlight_line_in_widget(self, widget, line, keywords, comment_markers, string_chars, operators, builtins):
        i = 0
        line_start = widget.index(tk.INSERT)
        while i < len(line):
            ch = line[i]
            
            if ch.isspace():
                widget.insert(tk.END, ch)
                i += 1
                continue
            
            if ch in operators:
                widget.insert(tk.END, ch, "cb_operator")
                i += 1
                continue
            
            comment_hit = False
            for cm in comment_markers:
                if line[i:].startswith(cm):
                    widget.insert(tk.END, line[i:], "cb_comment")
                    return
            if comment_hit:
                continue
            
            string_hit = False
            for sc in sorted(string_chars, key=len, reverse=True):
                if line[i:].startswith(sc):
                    end = line.find(sc, i + len(sc))
                    if end == -1:
                        end = len(line)
                    else:
                        end += len(sc)
                    widget.insert(tk.END, line[i:end], "cb_string")
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
                widget.insert(tk.END, line[i:j], "cb_number")
                i = j
                continue
            
            if ch.isalpha() or ch == '_':
                j = i
                while j < len(line) and (line[j].isalnum() or line[j] == '_'):
                    j += 1
                word = line[i:j]
                word_upper = word.upper()
                
                if word in keywords or word_upper in keywords:
                    widget.insert(tk.END, word, "cb_keyword")
                elif word in builtins:
                    widget.insert(tk.END, word, "cb_function")
                elif word[0].isupper():
                    widget.insert(tk.END, word, "cb_class")
                else:
                    widget.insert(tk.END, word)
                i = j
                continue
            
            widget.insert(tk.END, ch)
            i += 1

    def _highlight_line(self, line, line_start, keywords, comment_markers, string_chars, operators, builtins):
        i = 0
        while i < len(line):
            ch = line[i]
            
            if ch.isspace():
                i += 1
                continue
            
            if ch in operators:
                pos = f"{line_start.split('.')[0]}.{int(line_start.split('.')[1]) + 4 + i}"
                end_pos = f"{line_start.split('.')[0]}.{int(line_start.split('.')[1]) + 4 + i + 1}"
                self.text_widget.tag_add("cb_operator", pos, end_pos)
                i += 1
                continue
            
            comment_hit = False
            for cm in comment_markers:
                if line[i:].startswith(cm):
                    pos = f"{line_start.split('.')[0]}.{int(line_start.split('.')[1]) + 4 + i}"
                    line_end = f"{line_start.split('.')[0]}.{int(line_start.split('.')[1]) + 4 + len(line)}"
                    self.text_widget.tag_add("cb_comment", pos, line_end)
                    return
            if comment_hit:
                continue
            
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
                    self.text_widget.tag_add("cb_string", start_pos, end_pos)
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
                self.text_widget.tag_add("cb_number", start_pos, end_pos)
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
                    self.text_widget.tag_add("cb_keyword", start_pos, end_pos)
                elif word in builtins:
                    self.text_widget.tag_add("cb_function", start_pos, end_pos)
                elif word[0].isupper():
                    self.text_widget.tag_add("cb_class", start_pos, end_pos)
                i = j
                continue
            
            i += 1


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

    def _update_more_indicator(self):
        content = self.text_widget.get("1.0", tk.END).rstrip("\n")
        total_lines = content.count("\n") + 1
        more = total_lines > 4
        if more:
            self.more_indicator.pack(fill=tk.X, padx=12, pady=(0, 2), side=tk.BOTTOM)
        else:
            self.more_indicator.pack_forget()

    def _insert_plain_text(self, text):
        self.text_widget.insert(tk.END, text, "normal")

    def _slide_in(self, width, height, screen_h):
        target_y = 40
        steps = 15
        delay = 10
        y_start = -height
        y_end = target_y

        def animate(step=0):
            if step > steps or self.closing:
                self.top.geometry(f"+{(self.top.winfo_screenwidth() - width)//2}+{y_end}")
                return
            ratio = 1 - math.cos((step / steps) * math.pi / 2)
            y = int(y_start + (y_end - y_start) * ratio)
            self.top.geometry(f"+{(self.top.winfo_screenwidth() - width)//2}+{y}")
            self.top.after(delay, lambda: animate(step + 1))

        animate()

    def toggle_expand(self):
        self.expanded = not self.expanded
        h = self.expanded_h if self.expanded else self.height
        if self.expanded:
            self.more_indicator.pack_forget()
            self.detail_btn.config(text=tr("popup.collapse") + " ▲")
        else:
            self.detail_btn.config(text=tr("popup.detail") + " ▼")
        self.text_widget.config(state=tk.NORMAL)
        self.text_widget.delete("1.0", tk.END)
        self._insert_markup_text(self.knowledge)
        self.text_widget.config(state=tk.DISABLED)
        if not self.expanded:
            self.top.after(50, self._update_more_indicator)
        self.top.geometry(f"{self.width}x{h}+{(self.top.winfo_screenwidth() - self.width)//2}+40")

    def _review(self, action):
        if self.closing:
            return
        mem = self.item.get("memory", {})
        new_mem = update_memory(mem, action)
        self.on_review(self.item, new_mem, action)
        self._close()

    def _edit(self):
        if self.closing:
            return
        if self.on_edit:
            self.on_edit(self.item)
        self._close(skip_next=True)

    def _close(self, skip_next=False, suppress=False):
        self.closing = True
        try:
            self.top.destroy()
        except tk.TclError:
            pass
        try:
            self.on_close(skip_next=skip_next, suppress=suppress)
        except TypeError:
            self.on_close()


def show_popup(parent, item, on_review, on_close, on_link=None, on_edit=None):
    return PopupWindow(parent, item, on_review, on_close, on_link, on_edit)
