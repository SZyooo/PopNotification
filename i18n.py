import json
import os

LANG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lang")

LANGUAGES = {
    "zh": "中文",
    "en": "English",
    "ja": "日本語",
    "ko": "한국어",
}

_current_lang = "zh"
_translations = {}


def load_language(lang):
    global _current_lang, _translations
    _current_lang = lang
    path = os.path.join(LANG_DIR, f"{lang}.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            _translations = json.load(f)
    else:
        _translations = {}


def get_language():
    return _current_lang


def tr(text):
    if text in _translations:
        return _translations[text]
    return text
