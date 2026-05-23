from datetime import datetime, timedelta

LEVEL_INTERVALS = [
    (0, "strange", timedelta(minutes=10)),
    (1, "strange", timedelta(hours=1)),
    (2, "familiar", timedelta(hours=4)),
    (3, "familiar", timedelta(days=1)),
    (4, "master", timedelta(days=3)),
    (5, "master", timedelta(days=7)),
]

LEVEL_LABEL_KEYS = ["memory.level0", "memory.level1", "memory.level2",
                    "memory.level3", "memory.level4", "memory.level5"]

BUTTON_ACTIONS = {
    "strange": -1,
    "familiar": 1,
    "master": 2,
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


from i18n import tr

def get_level_label(level):
    level = max(0, min(5, level))
    return tr(LEVEL_LABEL_KEYS[level])

def get_interval_display(level):
    level = max(0, min(5, level))
    seconds = LEVEL_INTERVALS[level][2].total_seconds()
    if seconds < 3600:
        return f"{int(seconds // 60)}min"
    elif seconds < 86400:
        return f"{int(seconds // 3600)}h"
    else:
        return f"{int(seconds // 86400)}d"


def is_due(memory):
    next_review = memory.get("next_review")
    if next_review is None:
        return True
    try:
        dt = datetime.fromisoformat(next_review)
        return datetime.now() >= dt
    except (ValueError, TypeError):
        return True
