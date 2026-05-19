import json
import os
import sys

DEFAULT_CONFIG = {
    "root_path": os.path.join(os.path.expanduser("~"), "PopKnowledge"),
    "check_interval_minutes": 2,
    "popup_duration_seconds": 30,
    "popup_width": 460,
    "popup_height": 200,
    "popup_expanded_height": 500,
    "max_items_per_check": 3,
    "primary_subject": "",
}


def get_config_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_config.json")


def load_config():
    path = get_config_path()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            merged = DEFAULT_CONFIG.copy()
            merged.update(cfg)
            return merged
    return dict(DEFAULT_CONFIG)


def save_config(cfg):
    path = get_config_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
