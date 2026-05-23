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

    def list_all_keywords(self):
        """Return all keywords as list of (subject, chapter, keyword) tuples."""
        result = []
        for subject in self.list_subjects():
            for chapter in self.list_chapters(subject):
                for kw in self.list_keywords(subject, chapter):
                    result.append((subject, chapter, kw))
        return result

    def save_keyword(self, subject, chapter, keyword, knowledge, knowledge_type="normal", memory=None, related=None):
        filepath = self.get_keyword_path(subject, chapter, keyword)
        data = {
            "keyword": keyword,
            "knowledge": knowledge,
            "type": knowledge_type,
            "updated_at": datetime.now().isoformat(),
        }
        if related is not None:
            data["related"] = related
        if memory:
            data["memory"] = memory
        else:
            existing = self.get_keyword_data(subject, chapter, keyword)
            if existing and "memory" in existing:
                data["memory"] = existing["memory"]
            else:
                data["memory"] = get_initial_memory()
            if existing and related is None and "related" in existing:
                data["related"] = existing["related"]
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return data

    def delete_keyword(self, subject, chapter, keyword):
        filepath = self.get_keyword_path(subject, chapter, keyword)
        if os.path.exists(filepath):
            os.remove(filepath)

    def move_keyword(self, subject, chapter, keyword, to_subject, to_chapter):
        source_path = self.get_keyword_path(subject, chapter, keyword)
        if not os.path.exists(source_path):
            return False
        target_dir = os.path.join(self.root_path, sanitize_filename(to_subject), sanitize_filename(to_chapter))
        os.makedirs(target_dir, exist_ok=True)
        target_path = os.path.join(target_dir, sanitize_filename(keyword) + ".json")
        if os.path.exists(target_path):
            return False
        import shutil
        shutil.move(source_path, target_path)
        return True

    # ---- Subject/Chapter Description ----
    def get_subject_description(self, subject):
        path = os.path.join(self.root_path, sanitize_filename(subject), ".description.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f).get("description", "")
        return ""

    def save_subject_description(self, subject, description):
        path = os.path.join(self.root_path, sanitize_filename(subject), ".description.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"description": description}, f, ensure_ascii=False, indent=2)

    def get_chapter_description(self, subject, chapter):
        path = os.path.join(self.root_path, sanitize_filename(subject),
                            sanitize_filename(chapter), ".description.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f).get("description", "")
        return ""

    def save_chapter_description(self, subject, chapter, description):
        path = os.path.join(self.root_path, sanitize_filename(subject),
                            sanitize_filename(chapter), ".description.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"description": description}, f, ensure_ascii=False, indent=2)

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
                            "related": data.get("related", []),
                        })
        return due

    def cleanup_orphan_images(self, subject, chapter):
        import re
        chapter_path = os.path.join(self.root_path, sanitize_filename(subject), sanitize_filename(chapter))
        images_dir = os.path.join(chapter_path, "_images")
        if not os.path.isdir(images_dir):
            return 0
        referenced = set()
        for kw in self.list_keywords(subject, chapter):
            data = self.get_keyword_data(subject, chapter, kw)
            if data:
                for m in re.finditer(r'!\[.*?\]\(([^)]+)\)', data.get("knowledge", "")):
                    referenced.add(m.group(1))
        count = 0
        for f in os.listdir(images_dir):
            filepath = os.path.join(images_dir, f)
            if os.path.isfile(filepath) and f not in referenced:
                os.remove(filepath)
                count += 1
        return count

    def cleanup_all_orphan_images(self):
        total = 0
        for subject in self.list_subjects():
            for chapter in self.list_chapters(subject):
                total += self.cleanup_orphan_images(subject, chapter)
        return total

    def collect_pins(self, subject, chapter=None):
        """Collect all [[pin:word]] references from knowledge content.
        Returns dict: pin_word -> [(chapter, keyword), ...]"""
        import re
        pins = {}
        chapters = [chapter] if chapter else self.list_chapters(subject)
        for ch in chapters:
            for kw in self.list_keywords(subject, ch):
                data = self.get_keyword_data(subject, ch, kw)
                if data and data.get("knowledge"):
                    for m in re.finditer(r'\[\[pin:([^\]]+?)(?:\|[^\]]*)?\]\]', data["knowledge"]):
                        word = m.group(1).strip()
                        if word not in pins:
                            pins[word] = []
                        pins[word].append((ch, kw))
        return pins

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
