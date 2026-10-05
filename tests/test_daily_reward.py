import unittest
from datetime import datetime
from types import SimpleNamespace
import sqlite3
from unittest.mock import AsyncMock, Mock, patch
from zoneinfo import ZoneInfo

import discord

from bot.cogs.leveling_cog import LevelingCog
from bot.config import GENERAL_CHANNEL_ID
from bot.services.xp_service import XPService


class DailyRewardDateTests(unittest.TestCase):
    def test_reset_is_at_seven_in_warsaw_in_winter_and_summer(self):
        warsaw = ZoneInfo("Europe/Warsaw")

        self.assertEqual(
            XPService.daily_reward_date(datetime(2026, 1, 4, 6, 59, tzinfo=warsaw)),
            "2026-01-03",
        )
        self.assertEqual(
            XPService.daily_reward_date(datetime(2026, 1, 4, 7, 0, tzinfo=warsaw)),
            "2026-01-04",
        )
        self.assertEqual(
            XPService.daily_reward_date(datetime(2026, 7, 4, 6, 59, tzinfo=warsaw)),
            "2026-07-03",
        )
        self.assertEqual(
            XPService.daily_reward_date(datetime(2026, 7, 4, 7, 0, tzinfo=warsaw)),
            "2026-07-04",
        )

    def test_aware_non_warsaw_datetime_is_converted_before_reset_check(self):
        utc = ZoneInfo("UTC")

        self.assertEqual(
            XPService.daily_reward_date(datetime(2026, 7, 4, 4, 59, tzinfo=utc)),
            "2026-07-03",
        )
        self.assertEqual(
            XPService.daily_reward_date(datetime(2026, 7, 4, 5, 0, tzinfo=utc)),
            "2026-07-04",
        )


class DailyRewardListenerTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def new_profile():
        return {
            "text_xp": 0,
            "text_level": 0,
            "text_prestige": 0,
            "text_prestige_ready": False,
            "voice_xp": 0,
            "voice_level": 0,
            "voice_prestige": 0,
            "voice_prestige_ready": False,
            "bumps": 0,
        }

    @staticmethod
    def split_bonus(profile, amount):
        text_amount = amount // 2
        voice_amount = amount - text_amount
        profile["text_xp"] += text_amount
        profile["voice_xp"] += voice_amount
        return text_amount, voice_amount

    @staticmethod
    def make_message(
        *, channel_id=GENERAL_CHANNEL_ID, bot=False, webhook_id=None,
        message_type=discord.MessageType.default, content="hello",
    ):
        return SimpleNamespace(
            guild=object(),
            channel=SimpleNamespace(id=channel_id, category_id=None),
            author=SimpleNamespace(id=7, bot=bot, mention="<@7>"),
            webhook_id=webhook_id,
            type=message_type,
            content=content,
            id=101,
        )

    async def daily_call_count(self, message):
        cog = LevelingCog.__new__(LevelingCog)
        cog.przyznaj_daily_reward = AsyncMock(return_value=False)
        cog.cooldowns = {message.author.id: 100}

        with patch("bot.cogs.leveling_cog.time.time", return_value=100):
            await cog.on_message(message)

        return cog.przyznaj_daily_reward.await_count

    async def test_only_human_chat_messages_and_replies_are_daily_candidates(self):
        candidates = (
            self.make_message(),
            self.make_message(message_type=discord.MessageType.reply),
        )
        for message in candidates:
            with self.subTest(message_type=message.type):
                self.assertEqual(await self.daily_call_count(message), 1)

        rejected = (
            self.make_message(bot=True),
            self.make_message(webhook_id=123),
            self.make_message(message_type=discord.MessageType.new_member),
            self.make_message(content="$level"),
            self.make_message(channel_id=GENERAL_CHANNEL_ID + 1),
        )
        for message in rejected:
            with self.subTest(message=message):
                self.assertEqual(await self.daily_call_count(message), 0)

    async def test_database_error_retries_without_mutating_cache_before_commit(self):
        cog = LevelingCog.__new__(LevelingCog)
        cog.profile_locks = {}
        cog.dane_graczy = {}
        cog.get_profil = Mock(return_value=self.new_profile())
        cog.xp_service = Mock()
        cog.xp_service.split_bonus_xp.side_effect = self.split_bonus
        cog.player_repository = Mock()
        cog.player_repository.claim_daily_reward.side_effect = [
            sqlite3.OperationalError("database is locked"),
            True,
        ]
        cog.przelicz_poziom = Mock()
        message = self.make_message()
        message.channel.send = AsyncMock()

        with patch("bot.cogs.leveling_cog.asyncio.sleep", new_callable=AsyncMock) as sleep:
            self.assertTrue(await cog.przyznaj_daily_reward(message))

        self.assertEqual(cog.player_repository.claim_daily_reward.call_count, 2)
        self.assertEqual(cog.dane_graczy["7"]["text_xp"], 50)
        self.assertEqual(cog.dane_graczy["7"]["voice_xp"], 50)
        self.assertIn("Text +50, Voice +50", cog.player_repository.claim_daily_reward.call_args.kwargs["reason"])
        self.assertEqual(sleep.await_count, 1)
        message.channel.send.assert_awaited_once()

    async def test_announcement_failure_does_not_revoke_reward(self):
        cog = LevelingCog.__new__(LevelingCog)
        cog.profile_locks = {}
        cog.dane_graczy = {}
        cog.get_profil = Mock(return_value=self.new_profile())
        cog.xp_service = Mock()
        cog.xp_service.split_bonus_xp.side_effect = self.split_bonus
        cog.player_repository = Mock()
        cog.player_repository.claim_daily_reward.return_value = True
        cog.przelicz_poziom = Mock()
        message = self.make_message()
        response = Mock(status=403, reason="Forbidden")
        message.channel.send = AsyncMock(
            side_effect=discord.Forbidden(response, "Missing permission")
        )

        self.assertTrue(await cog.przyznaj_daily_reward(message))
        self.assertEqual(cog.dane_graczy["7"]["text_xp"], 50)
        self.assertEqual(cog.dane_graczy["7"]["voice_xp"], 50)


if __name__ == "__main__":
    unittest.main()