"""Task limits and protocol defaults; compatibility names retained."""

LIGHT_UP_DANMAKU_COUNT = 10
INTIMACY_DANMAKU_COUNT = 5
DANMAKU_DELAY = 0
DANMAKU_RECHECK_INTERVAL = 10 * 60
DANMAKU_WORK_BUDGET = 90
DANMAKU_ATTEMPTS_PER_CHECK = 16
# Task work must end this long before the next heartbeat is due; the beat loop
# only waits the unspent part of the interval, so overrunning it makes X late.
HEARTBEAT_TASK_MARGIN = 15
DANMAKU_SESSION_ATTEMPT_LIMIT = 35
WATCH_MINUTES = 25
HEARTBEAT_INTERVAL = 60
LIVE_LIKE_BATCH_SIZE = 30
LIVE_LIKE_BATCHES = 5
LIVE_LIKE_DELAY = 15
LIVE_LIKE_RECHECK_INTERVAL = 60
LIVE_LIKE_PROGRESS_DELAY = 3
LIVE_LIKE_PROGRESS_RETRY_DELAY = 5
_DANMAKU_MSGS = [
    "来了",
    "来啦",
    "晚上好",
    "好耶",
    "加油",
    "辛苦啦",
    "支持",
    "不错",
    "可以的",
    "稳",
    "好听",
    "好看",
    "厉害",
    "赞",
    "哈哈",
    "666",
    "冲",
    "打卡",
    "摸鱼",
    "慢慢来",
    "喝口水",
    "注意休息",
    "OK",
    "不赖",
    "好吧",
    "+3",
    "+6",
    "+9",
    "3",
    "？",
    "咋这样",
    "呃呃",
    "考",
    "dnys",
    "做人真的可以",
    "收到",
]
