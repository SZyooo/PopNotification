import tkinter as tk
import re
import math

from memory import update_memory

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

TYPE_TAG = {"normal": "常规", "tip": "提示", "warning": "警告"}


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
        self.top.title(f"知识卡片 - {kw}")
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

        type_tag = TYPE_TAG.get(ktype, "常规")
        tk.Label(
            header_frame, text=type_tag,
            bg="white", fg=accent,
            font=("Microsoft YaHei", 8, "bold"), padx=6, pady=1
        ).pack(side=tk.RIGHT, padx=10)

        btn_bg = "#f0f0f0"
        btn_frame = tk.Frame(self.top, bg=accent, height=46)
        btn_frame.pack(fill=tk.X)
        btn_frame.pack_propagate(False)

        body_frame = tk.Frame(self.top, bg=bg)
        body_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=(0, 2))

        kw_label = tk.Label(
            body_frame, text=kw, bg=bg, fg=accent,
            font=("Microsoft YaHei", 13, "bold"), anchor=tk.W
        )
        kw_label.pack(fill=tk.X, padx=12, pady=(8, 2))

        self.text_widget = tk.Text(
            body_frame, font=("Microsoft YaHei", 10),
            bg=bg, relief=tk.FLAT, bd=0,
            wrap=tk.WORD, padx=2, pady=2,
            state=tk.DISABLED,
        )
        self.text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 4))

        self.more_indicator = tk.Label(
            body_frame, text="…", bg=bg, fg="#999",
            font=("Microsoft YaHei", 10), anchor=tk.CENTER
        )

        self._populate_text(knowledge, ktype)
        # Schedule indicator check after slide-in animation completes (150ms)
        self.top.after(200, self._update_more_indicator)

        detail_btn = tk.Button(
            btn_frame, text="详细 ▼", font=("Microsoft YaHei", 9),
            bg=btn_bg, relief=tk.GROOVE, padx=10, cursor="hand2",
            command=self.toggle_expand
        )
        detail_btn.place(x=8, rely=0.5, anchor=tk.W, height=28)

        close_btn = tk.Button(
            btn_frame, text="×", font=("Arial", 14, "bold"),
            bg="#e74c3c", fg="white", relief=tk.FLAT, padx=6, cursor="hand2",
            command=lambda: self._close(suppress=True)
        )
        close_btn.place(relx=1.0, rely=0.5, anchor=tk.E, x=-8, height=28)

        edit_btn = tk.Button(
            btn_frame, text="编辑", font=("Microsoft YaHei", 9),
            bg=btn_bg, relief=tk.GROOVE, padx=8, cursor="hand2",
            command=self._edit
        )
        if not self.preview:
            edit_btn.place(relx=1.0, rely=0.5, anchor=tk.E, x=-55, height=28)

        if not self.preview:
            for i, label in enumerate(("陌生", "熟悉", "熟记")):
                btn = tk.Button(
                    btn_frame, text=label, font=("Microsoft YaHei", 9),
                    bg=btn_bg, relief=tk.GROOVE, padx=8, cursor="hand2",
                    command=lambda a=label: self._review(a)
                )
                btn.place(relx=0.35 + i * 0.12, rely=0.5, anchor=tk.CENTER, width=60, height=28)

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
        self.text_widget.tag_config("code", foreground="#e67e22", font=("Consolas", 10),
                                     background="#f4f4f4")

        self._insert_markup_text(text)

        self.text_widget.config(state=tk.DISABLED)

    def _insert_markup_text(self, text):
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
            rest = line
            if line.startswith("- ") or line.startswith("* "):
                bullet = True
                rest = line[2:]
                self.text_widget.insert(tk.END, "  • ", "bullet")
            pattern = r'(\[\[.*?\]\]|\*\*.*?\*\*|!!.*?!!|\?\?.*?\?\?|`.*?`)'
            parts = re.split(pattern, rest)
            for part in parts:
                if part.startswith("[[") and part.endswith("]]"):
                    keyword = part[2:-2]
                    if keyword and self.on_link:
                        tag = f"_link_{id(part)}_{id(line)}"
                        self.text_widget.tag_config(tag, foreground="#2980b9", underline=1,
                                                    font=("Microsoft YaHei", 10))
                        bt = ("bullet", tag) if bullet else (tag,)
                        self.text_widget.insert(tk.END, keyword, bt)
                        self.text_widget.tag_bind(tag, "<Button-1>",
                            lambda e, kw=keyword: self.on_link(kw))
                        self.text_widget.tag_bind(tag, "<Enter>",
                            lambda e: self.text_widget.config(cursor="hand2"))
                        self.text_widget.tag_bind(tag, "<Leave>",
                            lambda e: self.text_widget.config(cursor=""))
                    elif keyword:
                        tags = ("bullet",) if bullet else ()
                        self.text_widget.insert(tk.END, keyword, tags + ("normal",))
                elif part.startswith("**") and part.endswith("**"):
                    tags = ("bullet", "highlight") if bullet else ("highlight",)
                    self.text_widget.insert(tk.END, part[2:-2], tags)
                elif part.startswith("!!") and part.endswith("!!"):
                    tags = ("bullet", "warning") if bullet else ("warning",)
                    self.text_widget.insert(tk.END, part[2:-2], tags)
                elif part.startswith("??") and part.endswith("??"):
                    tags = ("bullet", "tip") if bullet else ("tip",)
                    self.text_widget.insert(tk.END, part[2:-2], tags)
                elif part.startswith("`") and part.endswith("`"):
                    tags = ("bullet", "code") if bullet else ("code",)
                    self.text_widget.insert(tk.END, part[1:-1].replace(" ", "\u00a0"), tags)
                elif part:
                    tag = "bullet" if bullet else "normal"
                    self.text_widget.insert(tk.END, part, tag)
            self.text_widget.insert(tk.END, "\n")
            i += 1

    def _insert_code_block(self, lang, lines):
        code = "\n".join(lines)
        self._highlight_code(lang, code)
        self.text_widget.insert(tk.END, "\n")

    def _highlight_code(self, lang, code):
        lang = lang.lower()
        kw_conf = self.__class__._LANG_KEYWORDS.get(lang, {})
        keywords = kw_conf.get("keywords", set())
        comment_markers = kw_conf.get("comment", [])
        string_chars = kw_conf.get("string", [])

        self.text_widget.tag_config("code_block", font=("Consolas", 10), background="#1e1e1e",
                                     foreground="#d4d4d4", lmargin1=10, lmargin2=10)
        self.text_widget.tag_config("cb_keyword", foreground="#569cd6")
        self.text_widget.tag_config("cb_string", foreground="#ce9178")
        self.text_widget.tag_config("cb_comment", foreground="#6a9955")
        self.text_widget.tag_config("cb_number", foreground="#b5cea8")

        i = 0
        line_start = 0
        while i < len(code):
            ch = code[i]
            # Check for comment
            comment_hit = False
            for cm in comment_markers:
                if code[i:].startswith(cm):
                    rest = code[i:]
                    self.text_widget.insert(tk.END, code[line_start:i], "code_block")
                    self.text_widget.insert(tk.END, rest, ("code_block", "cb_comment"))
                    line_start = len(code)
                    i = len(code)
                    comment_hit = True
                    break
            if comment_hit:
                continue
            # Check for string (multi-char markers first)
            string_hit = False
            for sc in sorted(string_chars, key=len, reverse=True):
                if code[i:].startswith(sc):
                    end = code.find(sc, i + len(sc))
                    if end == -1:
                        end = len(code)
                    else:
                        end += len(sc)
                    s = code[i:end]
                    self.text_widget.insert(tk.END, code[line_start:i], "code_block")
                    # Escape non-breaking spaces inside strings
                    self.text_widget.insert(tk.END, s.replace(" ", "\u00a0"), ("code_block", "cb_string"))
                    i = end
                    line_start = i
                    string_hit = True
                    break
            if string_hit:
                continue
            # Check for number
            if ch.isdigit() or (ch == '-' and i + 1 < len(code) and code[i + 1].isdigit()):
                j = i
                if ch == '-':
                    j += 1
                while j < len(code) and (code[j].isdigit() or code[j] == '.'):
                    j += 1
                num = code[i:j]
                self.text_widget.insert(tk.END, code[line_start:i], "code_block")
                self.text_widget.insert(tk.END, num, ("code_block", "cb_number"))
                i = j
                line_start = i
                continue
            # Check for keyword (word boundary)
            if ch.isalpha() or ch == '_':
                j = i
                while j < len(code) and (code[j].isalnum() or code[j] == '_'):
                    j += 1
                word = code[i:j]
                if word in keywords or word.upper() in keywords:
                    self.text_widget.insert(tk.END, code[line_start:i], "code_block")
                    self.text_widget.insert(tk.END, word, ("code_block", "cb_keyword"))
                    i = j
                    line_start = i
                    continue
                # If not a keyword, fall through to default
                i += 1
                continue
            i += 1
        # Flush remaining text
        if line_start < len(code):
            self.text_widget.insert(tk.END, code[line_start:], "code_block")


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
        self.on_close(skip_next=skip_next, suppress=suppress)


def show_popup(parent, item, on_review, on_close, on_link=None, on_edit=None):
    return PopupWindow(parent, item, on_review, on_close, on_link, on_edit)
