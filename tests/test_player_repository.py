import json
import sqlite3
import threading
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from bot.services.player_repository import PlayerRepository


class PlayerRepositoryTests(unittest.TestCase):
    def test_saves_separate_xp_pools_and_records_events(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
            database_path = Path(temporary_directory) / "discordbot.sqlite3"
            repository = PlayerRepository(database_path)
            repository.save_profiles(
                {
                    "7": {
                        "text_xp": 100,
                        "text_level": 1,
                        "text_prestige": 0,
                        "text_prestige_ready": False,
                        "voice_xp": 50,
                        "voice_level": 1,
                        "voice_prestige": 0,
                        "voice_prestige_ready": False,
                        "bumps": 0,
                    }
                }
            )
            repository.record_xp_event(7, "voice", 30, "test")

            profile = repository.load_profiles()["7"]
            event_count = repository.connection.execute(
                "SELECT COUNT(*) FROM xp_events"
            ).fetchone()[0]

            self.assertEqual(profile["text_xp"], 100)
            self.assertEqual(profile["voice_xp"], 50)
            self.assertEqual(
                set(profile),
                {
                    "text_xp", "text_level", "text_prestige", "text_prestige_ready",
                    "voice_xp", "voice_level", "voice_prestige",
                    "voice_prestige_ready", "bumps",
                },
            )
            self.assertEqual(event_count, 1)
            repository.close()

    def test_daily_reward_can_be_claimed_only_once_per_date(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
            repository = PlayerRepository(Path(temporary_directory) / "discordbot.sqlite3")
            profile = {
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

            results = [
                repository.claim_daily_reward(7, "2026-09-19", message_id, profile, 100)
                for message_id in range(101, 121)
            ]
            self.assertEqual(sum(results), 1)
            next_day_profile = {**profile, "text_xp": 50, "voice_xp": 50}
            self.assertTrue(
                repository.claim_daily_reward(
                    7, "2026-09-20", 103, next_day_profile, 100
                )
            )
            saved = repository.load_profiles()["7"]
            self.assertEqual((saved["text_xp"], saved["voice_xp"]), (50, 50))
            self.assertEqual(
                repository.connection.execute("SELECT COUNT(*) FROM daily_reward_claims").fetchone()[0],
                2,
            )
            repository.close()

    def test_concurrent_daily_claims_have_exactly_one_winner(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
            database_path = Path(temporary_directory) / "discordbot.sqlite3"
            schema_repository = PlayerRepository(database_path)
            schema_repository.close()
            barrier = threading.Barrier(2)

            def attempt_claim(user_id: int) -> bool:
                repository = PlayerRepository(database_path)
                profile = {
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
                barrier.wait()
                try:
                    return repository.claim_daily_reward(
                        user_id, "2026-09-19", 100 + user_id, profile, 100
                    )
                finally:
                    repository.close()

            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(attempt_claim, (7, 8)))

            self.assertEqual(sum(results), 1)
            repository = PlayerRepository(database_path)
            self.assertEqual(
                repository.connection.execute(
                    "SELECT COUNT(*) FROM daily_reward_claims"
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                repository.connection.execute(
                    "SELECT COUNT(*) FROM xp_events WHERE source = 'daily'"
                ).fetchone()[0],
                1,
            )
            repository.close()

    def test_daily_claim_survives_repository_restart(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
            database_path = Path(temporary_directory) / "discordbot.sqlite3"
            profile = {
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
            repository = PlayerRepository(database_path)
            self.assertTrue(
                repository.claim_daily_reward(7, "2026-09-19", 101, profile, 100)
            )
            repository.close()

            repository = PlayerRepository(database_path)
            self.assertFalse(
                repository.claim_daily_reward(8, "2026-09-19", 102, profile, 100)
            )
            self.assertEqual(repository.load_profiles()["7"]["text_xp"], 0)
            self.assertNotIn("8", repository.load_profiles())
            repository.close()

    def test_migrates_json_once_and_preserves_profiles(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
            root = Path(temporary_directory)
            legacy_json = root / "baza_graczy.json"
            legacy_json.write_text(
                json.dumps(
                    {
                        "42": {
                            "text_xp": 1250,
                            "voice_xp": 900,
                            "prestige": 1,
                            "bumps": 3,
                            "bonus_xp": 5000,
                            "total_xp": 9999,
                            "total_level": 99,
                            "prestige_ready": True,
                        }
                    }
                ),
                encoding="utf-8",
            )

            repository = PlayerRepository(root / "data" / "discordbot.sqlite3")
            self.assertEqual(repository.migrate_legacy_json(legacy_json), 1)
            migrated = repository.load_profiles()["42"]
            self.assertEqual(migrated["text_xp"], 1250)
            self.assertEqual(migrated["voice_xp"], 900)
            self.assertEqual(migrated["bumps"], 3)
            self.assertEqual(migrated["text_prestige"], 0)
            self.assertEqual(migrated["voice_prestige"], 0)
            self.assertFalse(migrated["text_prestige_ready"])
            self.assertFalse(migrated["voice_prestige_ready"])

            legacy_json.write_text("{}", encoding="utf-8")
            self.assertEqual(repository.migrate_legacy_json(legacy_json), 0)
            self.assertEqual(repository.load_profiles()["42"]["bumps"], 3)
            repository.close()

    def test_save_does_not_delete_profiles_missing_from_memory(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
            database_path = Path(temporary_directory) / "discordbot.sqlite3"
            repository = PlayerRepository(database_path)
            repository.save_profiles(
                {
                    "1": {"text_xp": 100, "bumps": 0},
                    "2": {"text_xp": 200, "bumps": 1},
                }
            )
            repository.save_profiles(
                {"1": {"text_xp": 150, "bumps": 0}}
            )

            profiles = repository.load_profiles()
            self.assertEqual(set(profiles), {"1", "2"})
            self.assertEqual(profiles["1"]["text_xp"], 150)
            repository.close()

    def test_migrates_sqlite_profile_without_trusting_old_levels(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temporary_directory:
            database_path = Path(temporary_directory) / "discordbot.sqlite3"
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
                    ('7', 1000, 2000, 900000, 999999, 99, 77, 88, 4, 6, 1, '{}', '', '')"""
            )
            connection.commit()
            connection.close()

            repository = PlayerRepository(database_path)
            profile = repository.load_profiles()["7"]
            self.assertEqual(profile["text_xp"], 1000)
            self.assertEqual(profile["voice_xp"], 2000)
            self.assertEqual(profile["bumps"], 6)
            self.assertEqual(profile["text_level"], 0)
            self.assertEqual(profile["voice_level"], 0)
            self.assertEqual(profile["text_prestige"], 0)
            self.assertEqual(profile["voice_prestige"], 0)
            self.assertFalse(profile["text_prestige_ready"])
            self.assertFalse(profile["voice_prestige_ready"])
            columns = {
                row[1]
                for row in repository.connection.execute(
                    "PRAGMA table_info(player_profiles)"
                )
            }
            self.assertFalse(
                columns
                & {
                    "bonus_xp", "total_xp", "total_level", "prestige",
                    "prestige_ready", "extra_json",
                }
            )
            repository.close()


if __name__ == "__main__":
    unittest.main()
