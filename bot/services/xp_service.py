from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, TYPE_CHECKING
from zoneinfo import ZoneInfo

from bot.config import (
    BUMP_BASE_XP,
    BUMP_MAX_XP,
    BUMP_NEW_MEMBER_DAYS,
    BUMP_NEW_MEMBER_MAX_LEVEL,
    BUMP_NEW_MEMBER_MULTIPLIER,
    BUMP_REWARD_TIERS,
    BOOSTER_ROLE_ID,
    DAILY_REWARD_RESET_HOUR,
    MAX_LEVEL,
    VOICE_XP_MULTIPLIER,
    XP_EVENT_RETENTION_DAYS,
)
from bot.services.level_curve import (
    build_curve,
    load_curve,
    max_level_for_prestige,
    required_xp,
    scale_curve,
)
from bot.services.player_repository import PlayerRepository

if TYPE_CHECKING:
    import discord


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
    """Wspólny stan i czyste operacje na profilach XP."""

    def __init__(self, database_path: Path, curve_path: Path):
        self.repository = PlayerRepository(database_path)
        self.profile_locks: dict[int, asyncio.Lock] = {}
        self.curve = self._load_curve(curve_path)
        self.voice_curve = scale_curve(self.curve, VOICE_XP_MULTIPLIER)
        self.profiles = self.repository.load_profiles()
        for profile in self.profiles.values():
            self.recalculate_levels(profile)
        self.save()

    @staticmethod
    def _load_curve(path: Path) -> dict[str, int]:
        try:
            curve = load_curve(path, max_level=MAX_LEVEL)
        except (OSError, ValueError):
            curve = build_curve(max_level=MAX_LEVEL)
        print(f"[XPService] Załadowano {len(curve) - 1} progów poziomów.")
        return curve

    def close(self) -> None:
        self.repository.close()

    def save(self) -> None:
        self.repository.save_profiles(self.profiles)

    def prune_events(self) -> int:
        return self.repository.prune_xp_events(XP_EVENT_RETENTION_DAYS)

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

    def required_xp(self, level: int, prestige: int = 0, source: str = "text") -> int:
        curve = self.voice_curve if source == "voice" else self.curve
        return required_xp(curve, level, prestige)

    def recalculate_levels(
        self, profile: dict[str, Any], source: str | None = None
    ) -> None:
        sources = (source,) if source else ("text", "voice")
        for progression in sources:
            if progression not in {"text", "voice"}:
                raise ValueError(f"Nieznana ścieżka XP: {progression}")

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

    def split_bonus_xp(self, profile: dict[str, Any], amount: int) -> tuple[int, int]:
        amount = max(0, int(amount))
        text_amount = amount // 2
        voice_amount = amount - text_amount
        profile["text_xp"] += text_amount
        profile["voice_xp"] += voice_amount
        self.recalculate_levels(profile)
        return text_amount, voice_amount

    async def add_bump(self, user_id: int) -> int:
        lock = self.profile_locks.setdefault(user_id, asyncio.Lock())
        async with lock:
            profile = self.get_profile(user_id)
            profile["bumps"] += 1
            self.repository.save_profiles(self.profiles)
            return profile["bumps"]

    async def perform_prestige(
        self, user_id: int, source: str
    ) -> dict[str, Any] | None:
        if source not in {"text", "voice"}:
            raise ValueError(f"Nieznana ścieżka Prestige: {source}")

        lock = self.profile_locks.setdefault(user_id, asyncio.Lock())
        async with lock:
            xp_key = f"{source}_xp"
            level_key = f"{source}_level"
            prestige_key = f"{source}_prestige"

            def transform(
                profile: dict[str, Any],
            ) -> tuple[dict[str, Any], int, str] | None:
                prestige = profile[prestige_key]
                if prestige >= 5:
                    return None

                cap = max_level_for_prestige(prestige)
                retained_xp = max(
                    0, profile[xp_key] - self.required_xp(cap, prestige, source)
                )
                updated = profile.copy()
                updated[prestige_key] = prestige + 1
                updated[xp_key] = retained_xp
                updated[level_key] = 0
                updated[f"{source}_prestige_ready"] = False
                self.recalculate_levels(updated, source)
                return (
                    updated,
                    profile[xp_key] - retained_xp,
                    f"{source} prestige; retained XP: {retained_xp}",
                )

            updated_profile = self.repository.perform_prestige(
                user_id, source, transform
            )
            if updated_profile is not None:
                current_profile = self.get_profile(user_id)
                for key in (
                    f"{source}_xp",
                    f"{source}_level",
                    f"{source}_prestige",
                    f"{source}_prestige_ready",
                ):
                    current_profile[key] = updated_profile[key]
                return current_profile
            return None

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

    def bump_reward(self, member: "discord.Member", bump_number: int | None = None) -> int:
        profile = self.get_profile(member.id)
        number = bump_number if bump_number is not None else profile["bumps"] + 1
        reward = BUMP_BASE_XP
        for minimum_bump, tier_reward in reversed(BUMP_REWARD_TIERS):
            if number >= minimum_bump:
                reward = tier_reward
                break

        joined_at = getattr(member, "joined_at", None)
        is_new = joined_at is not None and joined_at >= datetime.now(timezone.utc) - timedelta(days=BUMP_NEW_MEMBER_DAYS)
        is_low_level = (
            profile["text_level"] <= BUMP_NEW_MEMBER_MAX_LEVEL
            or profile["voice_level"] <= BUMP_NEW_MEMBER_MAX_LEVEL
        )
        if is_new or is_low_level:
            reward *= BUMP_NEW_MEMBER_MULTIPLIER

        if any(role.id == BOOSTER_ROLE_ID for role in getattr(member, "roles", ())):
            reward = int(reward * 1.25)
        return min(BUMP_MAX_XP, max(0, reward or BUMP_BASE_XP))
