from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .level_curve import (
    build_curve,
    max_level_for_prestige,
    required_xp,
    scale_curve,
)
from .player_repository import PlayerRepository

MAX_LEVEL = 130
VOICE_XP_MULTIPLIER = 1.5
DAILY_REWARD_RESET_HOUR = 7

PROFILE_DEFAULTS: dict[str, Any] = {
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


class XPService:
    """Business logic shared by Discord commands and events."""

    def __init__(self, database_path):
        self.repository = PlayerRepository(database_path)
        self.profile_locks: dict[int, asyncio.Lock] = {}
        self.curve = build_curve(MAX_LEVEL)
        self.voice_curve = scale_curve(self.curve, VOICE_XP_MULTIPLIER)
        self.profiles = self.repository.load_profiles()

        for profile in self.profiles.values():
            self.recalculate_levels(profile)

    def close(self) -> None:
        self.repository.close()

    def save(self) -> None:
        self.repository.save_profiles(self.profiles)

    def get_profile(self, user_id: int) -> dict[str, Any]:
        profile_id = str(user_id)
        profile = self.profiles.get(profile_id)

        if profile is None:
            profile = PROFILE_DEFAULTS.copy()
            self.profiles[profile_id] = profile
            self.save()
        else:
            for key, default in PROFILE_DEFAULTS.items():
                profile.setdefault(key, default)

        return profile

    def required_xp(
        self,
        level: int,
        prestige: int = 0,
        source: str = "text",
    ) -> int:
        curve = self.voice_curve if source == "voice" else self.curve
        return required_xp(curve, level, prestige)

    def recalculate_levels(
        self,
        profile: dict[str, Any],
        source: str | None = None,
    ) -> None:
        sources = (source,) if source else ("text", "voice")

        for progression in sources:
            if progression not in {"text", "voice"}:
                raise ValueError(f"Unknown XP progression: {progression}")

            xp_key = f"{progression}_xp"
            level_key = f"{progression}_level"
            prestige_key = f"{progression}_prestige"
            ready_key = f"{progression}_prestige_ready"

            prestige = profile[prestige_key]
            cap = max_level_for_prestige(prestige)
            level = 0

            while level < cap and profile[xp_key] >= self.required_xp(
                level + 1, prestige, progression
            ):
                level += 1

            profile[level_key] = level
            profile[ready_key] = level >= cap

    def split_bonus_xp(
        self,
        profile: dict[str, Any],
        amount: int,
    ) -> tuple[int, int]:
        amount = max(0, int(amount))
        text_amount = amount // 2
        voice_amount = amount - text_amount

        profile["text_xp"] += text_amount
        profile["voice_xp"] += voice_amount
        self.recalculate_levels(profile)

        return text_amount, voice_amount

    async def perform_prestige(
        self,
        user_id: int,
        source: str,
    ) -> dict[str, Any] | None:
        if source not in {"text", "voice"}:
            raise ValueError(f"Unknown Prestige path: {source}")

        lock = self.profile_locks.setdefault(user_id, asyncio.Lock())

        async with lock:
            xp_key = f"{source}_xp"
            level_key = f"{source}_level"
            prestige_key = f"{source}_prestige"

            def transform(profile: dict[str, Any]):
                prestige = profile[prestige_key]

                if prestige >= 5:
                    return None

                cap = max_level_for_prestige(prestige)
                threshold = self.required_xp(cap, prestige, source)
                retained_xp = max(0, profile[xp_key] - threshold)

                updated = profile.copy()
                updated[prestige_key] = prestige + 1
                updated[xp_key] = retained_xp
                updated[level_key] = 0
                updated[f"{source}_prestige_ready"] = False

                self.recalculate_levels(updated, source)

                return (
                    updated,
                    profile[xp_key] - retained_xp,
                    f"{source} Prestige; retained XP: {retained_xp}",
                )

            updated_profile = self.repository.perform_prestige(
                user_id,
                source,
                transform,
            )

            if updated_profile is None:
                return None

            current_profile = self.get_profile(user_id)

            for key in (
                f"{source}_xp",
                f"{source}_level",
                f"{source}_prestige",
                f"{source}_prestige_ready",
            ):
                current_profile[key] = updated_profile[key]

            return current_profile

    @staticmethod
    def daily_reward_date(now: datetime | None = None) -> str:
        warsaw = ZoneInfo("Europe/Warsaw")
        current = now or datetime.now(warsaw)

        if current.tzinfo is None:
            current = current.replace(tzinfo=warsaw)
        else:
            current = current.astimezone(warsaw)

        if current.hour < DAILY_REWARD_RESET_HOUR:
            current -= timedelta(days=1)

        return current.date().isoformat()
