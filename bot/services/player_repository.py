from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable


class PlayerRepository:
    """Trwałe przechowywanie profili graczy w lokalnej bazie SQLite."""

    _PROFILE_KEYS = {
        "text_xp",
        "text_level",
        "text_prestige",
        "text_prestige_ready",
        "voice_xp",
        "voice_level",
        "voice_prestige",
        "voice_prestige_ready",
        "bumps",
    }

    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self._create_schema()

    def _create_schema(self) -> None:
        existing_columns = {
            row[1]
            for row in self.connection.execute("PRAGMA table_info(player_profiles)").fetchall()
        }
        with self.connection:
            profile_columns = set(self._PROFILE_KEYS) | {"user_id", "created_at", "updated_at"}
            if existing_columns and not profile_columns.issubset(existing_columns):
                legacy_rows = self.connection.execute(
                    "SELECT * FROM player_profiles"
                ).fetchall()
                self.connection.execute("DROP TABLE player_profiles")
                self._create_profile_table()
                for row in legacy_rows:
                    values = row.keys()
                    self.connection.execute(
                        """
                        INSERT INTO player_profiles(user_id, text_xp, voice_xp, bumps)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            str(row["user_id"]),
                            max(0, int(row["text_xp"] or 0)) if "text_xp" in values else 0,
                            max(0, int(row["voice_xp"] or 0)) if "voice_xp" in values else 0,
                            max(0, int(row["bumps"] or 0)) if "bumps" in values else 0,
                        ),
                    )
            elif not existing_columns:
                self._create_profile_table()

            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS xp_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    amount INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_reward_claims (
                    reward_date TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def _create_profile_table(self) -> None:
        self.connection.execute(
            """
            CREATE TABLE player_profiles (
                user_id TEXT PRIMARY KEY,
                text_xp INTEGER NOT NULL DEFAULT 0,
                text_level INTEGER NOT NULL DEFAULT 0,
                text_prestige INTEGER NOT NULL DEFAULT 0,
                text_prestige_ready INTEGER NOT NULL DEFAULT 0,
                voice_xp INTEGER NOT NULL DEFAULT 0,
                voice_level INTEGER NOT NULL DEFAULT 0,
                voice_prestige INTEGER NOT NULL DEFAULT 0,
                voice_prestige_ready INTEGER NOT NULL DEFAULT 0,
                bumps INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

    @staticmethod
    def _normalise_profile(raw_profile: dict[str, Any]) -> dict[str, Any]:
        return {
            "text_xp": max(0, int(raw_profile.get("text_xp", 0))),
            "text_level": max(0, int(raw_profile.get("text_level", 0))),
            "text_prestige": max(0, int(raw_profile.get("text_prestige", 0))),
            "text_prestige_ready": bool(raw_profile.get("text_prestige_ready", False)),
            "voice_xp": max(0, int(raw_profile.get("voice_xp", 0))),
            "voice_level": max(0, int(raw_profile.get("voice_level", 0))),
            "voice_prestige": max(0, int(raw_profile.get("voice_prestige", 0))),
            "voice_prestige_ready": bool(raw_profile.get("voice_prestige_ready", False)),
            "bumps": max(0, int(raw_profile.get("bumps", 0))),
        }

    def migrate_legacy_json(self, legacy_json_path: Path) -> int:
        """Jednorazowo kopiuje profile ze starego JSON-a bez usuwania źródła."""
        migration_key = "legacy_json_migration_completed"
        already_migrated = self.connection.execute(
            "SELECT 1 FROM metadata WHERE key = ?", (migration_key,)
        ).fetchone()
        if already_migrated or not legacy_json_path.exists():
            return 0

        try:
            with legacy_json_path.open("r", encoding="utf-8") as legacy_file:
                legacy_profiles = json.load(legacy_file)
        except json.JSONDecodeError as error:
            raise RuntimeError(
                f"Nie można przenieść danych: {legacy_json_path.name} nie jest poprawnym JSON-em."
            ) from error

        if not isinstance(legacy_profiles, dict):
            raise RuntimeError(
                f"Nie można przenieść danych: {legacy_json_path.name} musi zawierać obiekt profili."
            )

        profiles_to_save: dict[str, dict[str, Any]] = {}
        for user_id, raw_profile in legacy_profiles.items():
            if not isinstance(raw_profile, dict):
                raise RuntimeError(
                    f"Nie można przenieść danych: profil użytkownika {user_id} jest niepoprawny."
                )
            profiles_to_save[str(user_id)] = {
                "text_xp": raw_profile.get("text_xp", 0),
                "voice_xp": raw_profile.get("voice_xp", 0),
                "bumps": raw_profile.get("bumps", 0),
            }

        self.save_profiles(profiles_to_save)
        with self.connection:
            self.connection.execute(
                "INSERT INTO metadata(key, value) VALUES (?, ?)",
                (migration_key, "true"),
            )
        return len(profiles_to_save)

    def load_profiles(self) -> dict[str, dict[str, Any]]:
        profiles: dict[str, dict[str, Any]] = {}
        rows = self.connection.execute(
            """
            SELECT user_id, text_xp, text_level, text_prestige, text_prestige_ready,
                voice_xp, voice_level, voice_prestige, voice_prestige_ready, bumps
            FROM player_profiles
            """
        ).fetchall()

        for row in rows:
            profiles[row["user_id"]] = {
                "text_xp": row["text_xp"],
                "text_level": row["text_level"],
                "text_prestige": row["text_prestige"],
                "text_prestige_ready": bool(row["text_prestige_ready"]),
                "voice_xp": row["voice_xp"],
                "voice_level": row["voice_level"],
                "voice_prestige": row["voice_prestige"],
                "voice_prestige_ready": bool(row["voice_prestige_ready"]),
                "bumps": row["bumps"],
            }
        return profiles

    def save_profiles(self, profiles: dict[str, dict[str, Any]]) -> None:
        rows = []
        for user_id, raw_profile in profiles.items():
            profile = self._normalise_profile(raw_profile)
            rows.append(
                (
                    str(user_id),
                    profile["text_xp"],
                    profile["text_level"],
                    profile["text_prestige"],
                    int(profile["text_prestige_ready"]),
                    profile["voice_xp"],
                    profile["voice_level"],
                    profile["voice_prestige"],
                    int(profile["voice_prestige_ready"]),
                    profile["bumps"],
                )
            )

        if not rows:
            return

        with self.connection:
            self.connection.executemany(
                """
                INSERT INTO player_profiles(
                    user_id, text_xp, text_level, text_prestige, text_prestige_ready,
                    voice_xp, voice_level, voice_prestige, voice_prestige_ready, bumps
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    text_xp = excluded.text_xp,
                    text_level = excluded.text_level,
                    text_prestige = excluded.text_prestige,
                    text_prestige_ready = excluded.text_prestige_ready,
                    voice_xp = excluded.voice_xp,
                    voice_level = excluded.voice_level,
                    voice_prestige = excluded.voice_prestige,
                    voice_prestige_ready = excluded.voice_prestige_ready,
                    bumps = excluded.bumps,
                    updated_at = CURRENT_TIMESTAMP
                """,
                rows,
            )

    def record_xp_event(self, user_id: int | str, source: str, amount: int, reason: str) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT INTO xp_events(user_id, source, amount, reason) VALUES (?, ?, ?, ?)",
                (str(user_id), source, int(amount), reason),
            )

    def claim_daily_reward(
        self,
        user_id: int,
        reward_date: str,
        message_id: int,
        profile: dict[str, Any],
        amount: int,
        reason: str | None = None,
    ) -> bool:
        normalized = self._normalise_profile(profile)
        values = (
            str(user_id),
            normalized["text_xp"],
            normalized["text_level"],
            normalized["text_prestige"],
            int(normalized["text_prestige_ready"]),
            normalized["voice_xp"],
            normalized["voice_level"],
            normalized["voice_prestige"],
            int(normalized["voice_prestige_ready"]),
            normalized["bumps"],
        )
        with self.connection:
            claim = self.connection.execute(
                """
                INSERT OR IGNORE INTO daily_reward_claims(reward_date, user_id, message_id)
                VALUES (?, ?, ?)
                """,
                (reward_date, str(user_id), str(message_id)),
            )
            if claim.rowcount == 0:
                return False

            self.connection.execute(
                """
                INSERT INTO player_profiles(
                    user_id, text_xp, text_level, text_prestige, text_prestige_ready,
                    voice_xp, voice_level, voice_prestige, voice_prestige_ready, bumps
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    text_xp = excluded.text_xp,
                    text_level = excluded.text_level,
                    text_prestige = excluded.text_prestige,
                    text_prestige_ready = excluded.text_prestige_ready,
                    voice_xp = excluded.voice_xp,
                    voice_level = excluded.voice_level,
                    voice_prestige = excluded.voice_prestige,
                    voice_prestige_ready = excluded.voice_prestige_ready,
                    bumps = excluded.bumps,
                    updated_at = CURRENT_TIMESTAMP
                """,
                values,
            )
            self.connection.execute(
                "INSERT INTO xp_events(user_id, source, amount, reason) VALUES (?, ?, ?, ?)",
                (
                    str(user_id),
                    "daily",
                    int(amount),
                    reason or f"pierwsza wiadomość dnia: {reward_date}",
                ),
            )
        return True

    def perform_prestige(
        self,
        user_id: int,
        source: str,
        transform: Callable[
            [dict[str, Any]], tuple[dict[str, Any], int, str] | None
        ],
    ) -> dict[str, Any] | None:
        if source not in {"text", "voice"}:
            raise ValueError(f"Nieznana ścieżka Prestige: {source}")

        ready_key = f"{source}_prestige_ready"
        xp_key = f"{source}_xp"
        level_key = f"{source}_level"
        prestige_key = f"{source}_prestige"
        with self.connection:
            self.connection.execute("BEGIN IMMEDIATE")
            row = self.connection.execute(
                "SELECT * FROM player_profiles WHERE user_id = ?", (str(user_id),)
            ).fetchone()
            if row is None or not row[ready_key]:
                return None

            profile = {
                key: bool(row[key]) if key.endswith("_ready") else row[key]
                for key in self._PROFILE_KEYS
            }
            transformed = transform(profile)
            if transformed is None:
                return None

            updated_profile, consumed_xp, reason = transformed
            self.connection.execute(
                f"""UPDATE player_profiles
                    SET {xp_key} = ?, {level_key} = ?, {prestige_key} = ?,
                        {ready_key} = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ?""",
                (
                    updated_profile[xp_key],
                    updated_profile[level_key],
                    updated_profile[prestige_key],
                    int(updated_profile[ready_key]),
                    str(user_id),
                ),
            )
            if consumed_xp:
                self.connection.execute(
                    "INSERT INTO xp_events(user_id, source, amount, reason) VALUES (?, ?, ?, ?)",
                    (str(user_id), source, -consumed_xp, reason),
                )
        return updated_profile

    def prune_xp_events(self, retention_days: int = 30) -> int:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=retention_days)
        ).strftime("%Y-%m-%d %H:%M:%S")
        with self.connection:
            cursor = self.connection.execute(
                "DELETE FROM xp_events WHERE created_at < ?", (cutoff,)
            )
        return cursor.rowcount

    def delete_profile(self, user_id: str) -> bool:
        with self.connection:
            cursor = self.connection.execute(
                "DELETE FROM player_profiles WHERE user_id = ?", (str(user_id),)
            )
        return cursor.rowcount > 0

    def close(self) -> None:
        self.connection.close()
