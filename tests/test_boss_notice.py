import ast
import asyncio
import time
import unittest
from contextlib import asynccontextmanager
from enum import IntEnum
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock


ROOT = Path(__file__).resolve().parents[1]
SPEC = spec_from_file_location("boss_notice", ROOT / "clanbattle" / "boss_notice.py")
BOSS_NOTICE = module_from_spec(SPEC)
SPEC.loader.exec_module(BOSS_NOTICE)


class BossNoticePolicyTest(unittest.TestCase):
    def test_numeric_levels_and_named_levels(self):
        for level, name in enumerate(BOSS_NOTICE.BOSS_NOTICE_NAMES):
            for text in (str(level), f" {level}级 ", name):
                self.assertEqual(BOSS_NOTICE.parse_boss_notice_level(text), level)
        for value in ("", "7", "-1", "1.5", "未知"):
            self.assertIsNone(BOSS_NOTICE.parse_boss_notice_level(value))

    def test_each_level_includes_lower_conditions(self):
        scenarios = (
            (1, 10, "C", 10, "C", [(10, 1, "C")], True),
            (2, 9, "B", 10, "C", [], False),
            (3, 30, "D", 31, "D", [], False),
            (4, 30, "D", 30, "D", [(30, 2, "D")], False),
            (5, 10, "C", 11, "C", [], False),
            (6, 10, "C", 10, "C", [(10, 1, "C")], False),
        )
        for minimum, *args in scenarios:
            for level in range(7):
                with self.subTest(minimum=minimum, level=level):
                    self.assertEqual(bool(BOSS_NOTICE.boss_notice_lines(level, *args)), level >= minimum)

    def test_classifies_kill_by_its_own_lap_and_combines_headings(self):
        lines = BOSS_NOTICE.boss_notice_lines(
            4, 30, "C", 31, "D", [(30, 5, "C"), (31, 2, "D")], False
        )
        self.assertEqual(lines, [
            "首领击杀：31周目2王",
            "阶段切换：C面 → D面",
            "进入新周目：D面31周目",
        ])

    def test_does_not_announce_initial_progress_or_reservation_without_a_kill(self):
        self.assertEqual(BOSS_NOTICE.boss_notice_lines(6, 0, "", 30, "D", [], True), [])
        self.assertEqual(BOSS_NOTICE.boss_notice_lines(6, 30, "D", 30, "D", [], True), [])


class BossNoticePollTest(unittest.IsolatedAsyncioTestCase):
    async def test_sends_attacks_then_state_then_reminders(self):
        # Exercise the poll and its real notification code without booting Hoshino.
        model = ast.parse((ROOT / "clanbattle" / "model.py").read_text(encoding="utf-8"))
        methods = {"do_single", "send_notice", "send_boss_notice"}
        bodies = [node for cls in model.body if isinstance(cls, ast.ClassDef)
                  for node in cls.body if isinstance(node, ast.AsyncFunctionDef) and node.name in methods]
        messages = []

        async def send(message, *_):
            if message:
                messages.append(message)

        @asynccontextmanager
        async def monitor_context(*_):
            yield

        class NoticeType(IntEnum):
            subscribe, tree, dao, fighter = range(4)

        settings = AsyncMock(return_value=6)
        scope = dict(asyncio=asyncio, time=time, List=list, DamageHistory=object,
                     ClanbattleItem=lambda clan, loop: SimpleNamespace(clan_info=clan, loop_num=loop),
                     ClanbattleHandle=monitor_context,
                     PrioritizedQueryItem=SimpleNamespace, NoticeType=NoticeType,
                     anywhere_send=send, boss_notice_lines=BOSS_NOTICE.boss_notice_lines,
                     clan_boss_info=SimpleNamespace(lap2stage=lambda lap: "C" if lap < 31 else "D"),
                     pcr_sqla=SimpleNamespace(get_boss_notice_level=settings))
        exec(compile(ast.Module(body=bodies, type_ignores=[]), "monitor_poll", "exec"), scope)

        class ClanStub:
            send_notice = scope["send_notice"]
            send_boss_notice = scope["send_boss_notice"]

        clan = ClanStub()
        clan.loop_num, clan.lap_num, clan.period, clan.group_id, clan.bot_id = 1, 30, "C", 123, 456
        clan.get_clanbattle_top = AsyncMock(return_value=SimpleNamespace(lap_num=31, period_rank=10))
        clan.refresh_boss = AsyncMock()
        clan.record_change = AsyncMock(return_value=[SimpleNamespace(lap_num=30, order_num=5)])
        clan.reconcile_damage = AsyncMock()
        clan.general_boss = lambda: "当前首领状态"
        clan.notice_dao, clan.notice_subscribe, clan.notice_tree, clan.notice_fighter = ["出刀"], ["预约"], ["下树"], []
        pool = SimpleNamespace(add_task=AsyncMock())

        item = SimpleNamespace(data=SimpleNamespace(clan_info=clan, loop_num=1))
        await scope["do_single"](pool, item)
        await asyncio.sleep(0)

        self.assertEqual(messages, [
            "出刀",
            "首领击杀：30周目5王\n阶段切换：C面 → D面\n进入新周目：D面31周目\n当前首领状态",
            "预约", "下树",
        ])
        settings.assert_awaited_once_with(123)
        clan.reconcile_damage.assert_awaited_once()


class BossNoticeCommandTest(unittest.IsolatedAsyncioTestCase):
    async def test_anyone_can_query_but_only_foreman_or_qq_admin_can_set(self):
        commands = ast.parse((ROOT / "clanbattle" / "__init__.py").read_text(encoding="utf-8"))
        handler = next(node for node in commands.body
                       if isinstance(node, ast.AsyncFunctionDef) and node.name == "boss_notice_setting")
        handler.decorator_list = []
        db = SimpleNamespace(get_boss_notice_level=AsyncMock(return_value=0),
                             get_clan_member=AsyncMock(return_value=None),
                             set_boss_notice_level=AsyncMock())
        priv = SimpleNamespace(ADMIN=21, NORMAL=1, get_user_priv=lambda ev: ev.priority)
        scope = dict(HoshinoBot=object, CQEvent=object, priv=priv, pcr_sqla=db,
                     BOSS_NOTICE_NAMES=BOSS_NOTICE.BOSS_NOTICE_NAMES,
                     parse_boss_notice_level=BOSS_NOTICE.parse_boss_notice_level)
        exec(compile(ast.Module(body=[handler], type_ignores=[]), "boss_notice_command", "exec"), scope)

        class Event(dict):
            group_id, user_id = 123, 456

        bot = SimpleNamespace(send=AsyncMock())

        async def command(text, priority=1):
            ev = Event(message_type="group")
            ev.priority = priority
            ev.message = SimpleNamespace(extract_plain_text=lambda: text)
            await scope["boss_notice_setting"](bot, ev)

        await command("")
        db.get_boss_notice_level.assert_awaited_once_with(123)
        await command("6")
        db.set_boss_notice_level.assert_not_awaited()

        db.get_clan_member.return_value = SimpleNamespace(priority=21)
        await command("D面首领击杀")
        db.set_boss_notice_level.assert_awaited_once_with(123, 4)

        db.set_boss_notice_level.reset_mock()
        await command("7", priority=21)
        db.set_boss_notice_level.assert_not_awaited()
        await command("0", priority=21)
        db.set_boss_notice_level.assert_awaited_once_with(123, 0)
