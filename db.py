import json
import os
import re
from datetime import datetime

from config import load_config
from memory import get_initial_memory, is_due


def sanitize_filename(name):
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip()


class KnowledgeBase:
    def __init__(self, root_path=None):
        if root_path is None:
            root_path = load_config().get("root_path")
        self.root_path = root_path

    # ---- Subject ----
    def list_subjects(self):
        if not os.path.isdir(self.root_path):
            return []
        return sorted(
            d
            for d in os.listdir(self.root_path)
            if os.path.isdir(os.path.join(self.root_path, d)) and not d.startswith(".")
        )

    def add_subject(self, name):
        path = os.path.join(self.root_path, sanitize_filename(name))
        os.makedirs(path, exist_ok=True)

    def rename_subject(self, old_name, new_name):
        old_path = os.path.join(self.root_path, sanitize_filename(old_name))
        new_path = os.path.join(self.root_path, sanitize_filename(new_name))
        if os.path.exists(old_path) and not os.path.exists(new_path):
            os.rename(old_path, new_path)

    def delete_subject(self, name):
        path = os.path.join(self.root_path, sanitize_filename(name))
        if os.path.isdir(path):
            import shutil
            shutil.rmtree(path)

    # ---- Chapter ----
    def list_chapters(self, subject):
        path = os.path.join(self.root_path, sanitize_filename(subject))
        if not os.path.isdir(path):
            return []
        return sorted(
            d
            for d in os.listdir(path)
            if os.path.isdir(os.path.join(path, d)) and not d.startswith(".")
        )

    def add_chapter(self, subject, chapter):
        path = os.path.join(self.root_path, sanitize_filename(subject), sanitize_filename(chapter))
        os.makedirs(path, exist_ok=True)

    def rename_chapter(self, subject, old_name, new_name):
        base = os.path.join(self.root_path, sanitize_filename(subject))
        old_path = os.path.join(base, sanitize_filename(old_name))
        new_path = os.path.join(base, sanitize_filename(new_name))
        if os.path.exists(old_path) and not os.path.exists(new_path):
            os.rename(old_path, new_path)

    def delete_chapter(self, subject, chapter):
        path = os.path.join(self.root_path, sanitize_filename(subject), sanitize_filename(chapter))
        if os.path.isdir(path):
            import shutil
            shutil.rmtree(path)

    # ---- Keyword ----
    def list_keywords(self, subject, chapter):
        path = os.path.join(self.root_path, sanitize_filename(subject), sanitize_filename(chapter))
        if not os.path.isdir(path):
            return []
        items = []
        for f in os.listdir(path):
            if f.endswith(".json") and os.path.isfile(os.path.join(path, f)):
                try:
                    with open(os.path.join(path, f), "r", encoding="utf-8") as fh:
                        data = json.load(fh)
                    kw = data.get("keyword", f[:-5])
                except Exception:
                    kw = f[:-5]
                items.append(kw)
        return sorted(items)

    def get_keyword_path(self, subject, chapter, keyword):
        return os.path.join(
            self.root_path,
            sanitize_filename(subject),
            sanitize_filename(chapter),
            sanitize_filename(keyword) + ".json",
        )

    def get_keyword_data(self, subject, chapter, keyword):
        filepath = self.get_keyword_path(subject, chapter, keyword)
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    def save_keyword(self, subject, chapter, keyword, knowledge, knowledge_type="normal", memory=None):
        filepath = self.get_keyword_path(subject, chapter, keyword)
        data = {
            "keyword": keyword,
            "knowledge": knowledge,
            "type": knowledge_type,
            "updated_at": datetime.now().isoformat(),
        }
        if memory:
            data["memory"] = memory
        else:
            existing = self.get_keyword_data(subject, chapter, keyword)
            if existing and "memory" in existing:
                data["memory"] = existing["memory"]
            else:
                data["memory"] = get_initial_memory()
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return data

    def delete_keyword(self, subject, chapter, keyword):
        filepath = self.get_keyword_path(subject, chapter, keyword)
        if os.path.exists(filepath):
            os.remove(filepath)

    def update_memory(self, subject, chapter, keyword, new_memory):
        data = self.get_keyword_data(subject, chapter, keyword)
        if data:
            data["memory"] = new_memory
            filepath = self.get_keyword_path(subject, chapter, keyword)
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

    # ---- Query due items ----
    def get_all_due_items(self):
        due = []
        for subject in self.list_subjects():
            for chapter in self.list_chapters(subject):
                for keyword in self.list_keywords(subject, chapter):
                    data = self.get_keyword_data(subject, chapter, keyword)
                    if data is None:
                        continue
                    mem = data.get("memory", {})
                    if is_due(mem):
                        due.append({
                            "subject": subject,
                            "chapter": chapter,
                            "keyword": keyword,
                            "knowledge": data.get("knowledge", ""),
                            "type": data.get("type", "normal"),
                            "memory": mem,
                        })
        return due

    def get_stats(self):
        total = 0
        by_level = {i: 0 for i in range(6)}
        for subject in self.list_subjects():
            for chapter in self.list_chapters(subject):
                for keyword in self.list_keywords(subject, chapter):
                    data = self.get_keyword_data(subject, chapter, keyword)
                    if data:
                        total += 1
                        level = data.get("memory", {}).get("level", 0)
                        by_level[level] = by_level.get(level, 0) + 1
        return {"total": total, "by_level": by_level}
