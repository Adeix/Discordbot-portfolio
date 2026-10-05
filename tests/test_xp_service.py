import asyncio
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from bot.cogs.leveling_cog import LevelingCog
from bot.config import BUMP_BASE_XP, BUMP_NEW_MEMBER_MULTIPLIER
from bot.services.xp_service import PROFILE_DEFAULTS, XPService


class XPServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory(dir=Path.cwd())
        root = Path(self.temporary_directory.name)
        self.service = XPService(root / "players.sqlite3", Path.cwd() / "poziomy.json")

    def tearDown(self):
        self.service.close()
        self.temporary_directory.cleanup()

    def level_for_xp(self, amount: int, prestige: int, source: str) -> int:
        level = 0
        while level < 130 and amount >= self.service.required_xp(
            level + 1, prestige, source
        ):
            level += 1
        return level

    def test_bonus_split_values_and_profile_shape(self):
        expected = ((100, 50, 50), (15, 7, 8), (1, 0, 1), (101, 50, 51))
        for total, expected_text, expected_voice in expected:
            with self.subTest(total=total):
                profile = PROFILE_DEFAULTS.copy()
                self.assertEqual(
                    self.service.split_bonus_xp(profile, total),
                    (expected_text, expected_voice),
                )
                self.assertEqual(profile["text_xp"], expected_text)
                self.assertEqual(profile["voice_xp"], expected_voice)
                self.assertEqual(
                    set(profile),
                    {
                        "text_xp", "text_level", "text_prestige",
                        "text_prestige_ready", "voice_xp", "voice_level",
                        "voice_prestige", "voice_prestige_ready", "bumps",
                    },
                )

    def test_recalculation_uses_only_selected_path_and_its_prestige(self):
        profile = PROFILE_DEFAULTS.copy()
        profile.update(
            text_xp=self.service.required_xp(18, 4, "text"),
            text_prestige=4,
            text_level=0,
            voice_xp=self.service.required_xp(40, 1, "voice"),
            voice_prestige=1,
            voice_level=7,
        )

        self.service.recalculate_levels(profile, "text")
        self.assertEqual(profile["text_level"], 18)
        self.assertEqual(profile["voice_level"], 7)
        self.assertEqual(profile["voice_prestige"], 1)

        self.service.recalculate_levels(profile, "voice")
        self.assertEqual(profile["voice_level"], 40)
        self.assertEqual(profile["text_level"], 18)

    def test_prestige_ready_is_set_at_cap_without_additional_xp(self):
        profile = PROFILE_DEFAULTS.copy()
        profile["text_xp"] = self.service.required_xp(50, 0, "text")

        self.service.recalculate_levels(profile, "text")

        self.assertEqual(profile["text_level"], 50)
        self.assertTrue(profile["text_prestige_ready"])
        self.assertFalse(profile["voice_prestige_ready"])

    async def test_bonus_is_one_event_and_updates_both_paths(self):
        cog = LevelingCog.__new__(LevelingCog)
        cog.profile_locks = self.service.profile_locks
        cog.xp_service = self.service
        cog.player_repository = self.service.repository
        cog.dane_graczy = self.service.profiles
        cog.bot = Mock()
        cog.wymaga_zapisu = False
        cog.get_profil = self.service.get_profile
        cog.przelicz_poziom = self.service.recalculate_levels

        await cog.dodaj_xp(7, 15, source="bonus", reason="test bonus")

        profile = self.service.get_profile(7)
        event = self.service.repository.connection.execute(
            "SELECT source, amount, reason FROM xp_events WHERE user_id = '7'"
        ).fetchone()
        self.assertEqual((profile["text_xp"], profile["voice_xp"]), (7, 8))
        self.assertEqual(tuple(event[:2]), ("bonus", 15))
        self.assertIn("Text +7, Voice +8", event["reason"])
        self.assertEqual(
            self.service.repository.connection.execute(
                "SELECT COUNT(*) FROM xp_events WHERE user_id = '7'"
            ).fetchone()[0],
            1,
        )

    async def test_normal_text_and_voice_xp_do_not_cross_paths(self):
        cog = LevelingCog.__new__(LevelingCog)
        cog.profile_locks = self.service.profile_locks
        cog.xp_service = self.service
        cog.player_repository = self.service.repository
        cog.dane_graczy = self.service.profiles
        cog.bot = Mock()
        cog.wymaga_zapisu = False
        cog.get_profil = self.service.get_profile
        cog.przelicz_poziom = self.service.recalculate_levels

        await cog.dodaj_xp(7, 50, source="text")
        profile = self.service.get_profile(7)
        self.assertEqual((profile["text_xp"], profile["voice_xp"]), (50, 0))

        await cog.dodaj_xp(7, 60, source="voice")
        self.assertEqual((profile["text_xp"], profile["voice_xp"]), (50, 60))

    async def test_prestige_retains_excess_and_does_not_change_other_path(self):
        text_cap_xp = self.service.required_xp(50, 0, "text")
        profile = PROFILE_DEFAULTS.copy()
        profile.update(
            text_xp=text_cap_xp + 800,
            voice_xp=2345,
            voice_level=4,
            voice_prestige=2,
        )
        self.service.recalculate_levels(profile)
        self.assertTrue(profile["text_prestige_ready"])
        self.service.profiles["7"] = profile
        self.service.repository.save_profiles(self.service.profiles)
        voice_before = {
            key: profile[key]
            for key in (
                "voice_xp", "voice_level", "voice_prestige",
                "voice_prestige_ready",
            )
        }

        updated = await self.service.perform_prestige(7, "text")

        self.assertIsNotNone(updated)
        self.assertEqual(updated["text_prestige"], 1)
        self.assertEqual(updated["text_xp"], 800)
        self.assertEqual(
            updated["text_level"], self.level_for_xp(800, 1, "text")
        )
        self.assertFalse(updated["text_prestige_ready"])
        self.assertEqual(
            {key: updated[key] for key in voice_before}, voice_before
        )

    async def test_simultaneous_prestige_claims_only_increment_once(self):
        profile = PROFILE_DEFAULTS.copy()
        profile["text_xp"] = self.service.required_xp(50, 0, "text")
        self.service.recalculate_levels(profile)
        self.service.profiles["7"] = profile
        self.service.repository.save_profiles(self.service.profiles)

        results = await asyncio.gather(
            self.service.perform_prestige(7, "text"),
            self.service.perform_prestige(7, "text"),
        )

        self.assertEqual(sum(result is not None for result in results), 1)
        persisted = self.service.repository.load_profiles()["7"]
        self.assertEqual(persisted["text_prestige"], 1)

    def test_bump_low_level_multiplier_checks_either_path(self):
        member = SimpleNamespace(
            id=7,
            joined_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
            roles=[],
        )
        profile = self.service.get_profile(7)
        profile.update(text_level=16, voice_level=3)
        self.assertEqual(
            self.service.bump_reward(member),
            min(BUMP_BASE_XP * BUMP_NEW_MEMBER_MULTIPLIER, 1000),
        )

        profile.update(text_level=16, voice_level=16)
        self.assertEqual(self.service.bump_reward(member), BUMP_BASE_XP)

    def test_sqlite_migration_recalculates_levels_from_only_retained_xp(self):
        self.service.close()
        database_path = Path(self.temporary_directory.name) / "legacy.sqlite3"
        connection = sqlite3.connect(database_path)
        connection.execute(
            """CREATE TABLE player_profiles (
                user_id TEXT PRIMARY KEY, text_xp INTEGER, voice_xp INTEGER,
                bonus_xp INTEGER, total_xp INTEGER, text_level INTEGER,
                voice_level INTEGER, total_level INTEGER, prestige INTEGER,
                bumps INTEGER, prestige_ready INTEGER, extra_json TEXT,
                created_at TEXT, updated_at TEXT
            )"""
        )
        connection.execute(
            """INSERT INTO player_profiles VALUES
                ('7', 1000, 2000, 1000000, 2000000, 99, 88, 77, 4, 6, 1, '{}', '', '')"""
        )
        connection.commit()
        connection.close()

        self.service = XPService(database_path, Path.cwd() / "poziomy.json")
        profile = self.service.get_profile(7)
        self.assertEqual(profile["text_level"], self.level_for_xp(1000, 0, "text"))
        self.assertEqual(profile["voice_level"], self.level_for_xp(2000, 0, "voice"))
        self.assertEqual(profile["bumps"], 6)
        self.assertEqual(profile["text_prestige"], 0)
        self.assertEqual(profile["voice_prestige"], 0)
        self.assertFalse(profile["text_prestige_ready"])
        self.assertFalse(profile["voice_prestige_ready"])

    async def test_leaderboard_uses_path_prestige_and_rejects_total(self):
        cog = LevelingCog.__new__(LevelingCog)
        cog.dane_graczy = {
            "1": {
                "text_prestige": 0, "text_level": 50, "text_xp": 50000,
                "voice_prestige": 5, "voice_level": 130, "voice_xp": 500000,
                "bumps": 0,
            },
            "2": {
                "text_prestige": 1, "text_level": 1, "text_xp": 100,
                "voice_prestige": 0, "voice_level": 0, "voice_xp": 0,
                "bumps": 0,
            },
        }
        members = {
            1: SimpleNamespace(display_name="text-level-high"),
            2: SimpleNamespace(display_name="text-prestige-high"),
        }
        ctx = SimpleNamespace(
            guild=SimpleNamespace(get_member=members.get, icon=None),
            author=SimpleNamespace(id=1),
            send=AsyncMock(),
        )

        await LevelingCog.wyswietl_leaderboard.callback(cog, ctx, "text")
        text_embed = ctx.send.await_args.kwargs["embed"]
        self.assertLess(
            text_embed.description.index("text-prestige-high"),
            text_embed.description.index("text-level-high"),
        )

        await LevelingCog.wyswietl_leaderboard.callback(cog, ctx, "total")
        self.assertIn("$lb text", ctx.send.await_args.args[0])


if __name__ == "__main__":
    unittest.main()