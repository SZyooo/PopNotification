from datetime import datetime, timedelta

LEVEL_INTERVALS = [
    (0, "陌生", timedelta(minutes=10),  "10分钟"),
    (1, "陌生", timedelta(hours=1),     "1小时"),
    (2, "熟悉", timedelta(hours=4),     "4小时"),
    (3, "熟悉", timedelta(days=1),      "1天"),
    (4, "熟记", timedelta(days=3),      "3天"),
    (5, "熟记", timedelta(days=7),      "7天"),
]

INTERVAL_DISPLAY = {lv: desc for lv, _, _, desc in LEVEL_INTERVALS}

BUTTON_ACTIONS = {
    "陌生": -1,
    "熟悉": 1,
    "熟记": 2,
}


def get_initial_memory():
    return {
        "level": 0,
        "interval_seconds": 600,
        "last_review": None,
        "next_review": (datetime.now() + timedelta(minutes=5)).isoformat(),
    }


def update_memory(memory, action):
    now = datetime.now()
    level = memory.get("level", 0)
    delta = BUTTON_ACTIONS.get(action, 1)
    new_level = max(0, min(5, level + delta))

    delta_td = LEVEL_INTERVALS[new_level][2]
    next_review = (now + delta_td).isoformat()

    return {
        "level": new_level,
        "interval_seconds": int(delta_td.total_seconds()),
        "last_review": now.isoformat(),
        "next_review": next_review,
    }


def get_level_label(level):
    level = max(0, min(5, level))
    return LEVEL_INTERVALS[level][1]

def get_interval_display(level):
    level = max(0, min(5, level))
    return INTERVAL_DISPLAY.get(level, "")


def is_due(memory):
    next_review = memory.get("next_review")
    if next_review is None:
        return True
    try:
        dt = datetime.fromisoformat(next_review)
        return datetime.now() >= dt
    except (ValueError, TypeError):
        return True
