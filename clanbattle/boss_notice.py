from enum import IntEnum


class BossNoticeLevel(IntEnum):
    MANUAL = 0
    REMINDER = 1
    STAGE = 2
    D_LAP = 3
    D_KILL = 4
    LAP = 5
    KILL = 6


BOSS_NOTICE_NAMES = (
    "手动", "需要通知时", "阶段切换", "D面新周目", "D面首领击杀", "新周目", "首领击杀",
)


def parse_boss_notice_level(value):
    value = value.strip()
    if value in BOSS_NOTICE_NAMES:
        return BOSS_NOTICE_NAMES.index(value)
    value = value.removesuffix("级")
    if len(value) == 1 and value.isdecimal() and int(value) < len(BOSS_NOTICE_NAMES):
        return int(value)
    return None


def boss_notice_lines(level, previous_lap, previous_stage, lap, stage, kills, has_reminders):
    """Return headings for one state snapshot; kills are (lap, order, stage)."""
    lines = []
    announced_kills = [
        f"{kill_lap}周目{order}王"
        for kill_lap, order, kill_stage in kills
        if level >= BossNoticeLevel.KILL
        or (level >= BossNoticeLevel.D_KILL and kill_stage == "D")
        or (level >= BossNoticeLevel.REMINDER and has_reminders)
    ]
    if announced_kills:
        lines.append("首领击杀：" + "、".join(announced_kills))
    if previous_lap and lap > previous_lap:
        if level >= BossNoticeLevel.STAGE and previous_stage and stage != previous_stage:
            lines.append(f"阶段切换：{previous_stage}面 → {stage}面")
        if level >= BossNoticeLevel.LAP or (level >= BossNoticeLevel.D_LAP and stage == "D"):
            lines.append(f"进入新周目：{stage}面{lap}周目")
    return lines
