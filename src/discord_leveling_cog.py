from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass

import discord
from discord.ext import commands, tasks

from .xp_service import XPService
from .voice_tracker import VoiceTracker

@dataclass(frozen=True)
class LevelingConfig:
    command_prefix: str = "$"
    text_xp_cooldown: float = 60.0
    text_xp_min: int = 10
    text_xp_max: int = 20
    voice_xp_per_tick: int = 15

class LevelingCog(commands.Cog):
    """Discord adapter for the XP service.

    Discord events/commands stay here; progression rules live in XPService
    and persistence lives in PlayerRepository.
    """

    def __init__(self, bot: commands.Bot, xp_service: XPService, config: LevelingConfig):
        self.bot = bot
        self.xp_service = xp_service
        self.config = config
        self.cooldowns: dict[int, float] = {}
        self.profile_locks = xp_service.profile_locks
        self.voice_tracker = VoiceTracker(bot, self._award_voice_xp)
        self.dirty = False

    async def cog_load(self) -> None:
        self.voice_tracker.start()
        self.autosave.start()

    async def cog_unload(self) -> None:
        self.voice_tracker.cancel()
        self.autosave.cancel()
        self.xp_service.close()

    @tasks.loop(minutes=2)
    async def autosave(self) -> None:
        """Avoid a database write on every message."""
        if self.dirty:
            self.xp_service.save()
            self.dirty = False

    async def _award_voice_xp(self, member: discord.Member) -> None:
        await self.add_xp(member.id, self.config.voice_xp_per_tick, source="voice", reason="voice activity")

    async def add_xp(self, user_id: int, amount: int, *, source: str, reason: str) -> None:
        if source not in {"text", "voice"}:
            raise ValueError(f"Unknown XP source: {source}")

        amount = max(0, int(amount))
        lock = self.profile_locks.setdefault(user_id, asyncio.Lock())
        async with lock:
            profile = self.xp_service.get_profile(user_id)
            level_before = profile[f"{source}_level"]
            profile[f"{source}_xp"] += amount
            self.xp_service.recalculate_levels(profile, source)
            self.xp_service.repository.record_xp_event(user_id, source, amount, reason)
            self.dirty = True
            level_after = profile[f"{source}_level"]

        if level_after > level_before:
            await self._announce_level_up(user_id, source, level_before, level_after)

    async def _announce_level_up(self, user_id: int, source: str, old_level: int, new_level: int) -> None:
        channel = getattr(self.bot, "level_up_channel", None)
        if channel is None:
            return
        await channel.send(f"<@{user_id}> reached {source} level {old_level} -> {new_level}!")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if (
            message.guild is None
            or message.author.bot
            or message.webhook_id is not None
            or message.content.startswith(self.config.command_prefix)
        ):
            return

        now = time.monotonic()
        last_award = self.cooldowns.get(message.author.id, 0.0)
        if now - last_award < self.config.text_xp_cooldown:
            return

        self.cooldowns[message.author.id] = now
        amount = random.randint(self.config.text_xp_min, self.config.text_xp_max)
        await self.add_xp(message.author.id, amount, source="text", reason="text activity")

    @commands.command(name="level")
    async def show_level(self, ctx: commands.Context, member: discord.Member | None = None) -> None:
        member = member or ctx.author
        profile = self.xp_service.get_profile(member.id)
        await ctx.send(
            f"{member.display_name}: "
            f"Text P{profile['text_prestige']} L{profile['text_level']} | "
            f"Voice P{profile['voice_prestige']} L{profile['voice_level']}"
        )

    @commands.command(name="prestige")
    async def prestige(self, ctx: commands.Context, source: str) -> None:
        source = source.lower()
        if source not in {"text", "voice"}:
            await ctx.send("Use $prestige text or $prestige voice.")
            return
        updated = await self.xp_service.perform_prestige(ctx.author.id, source)
        if updated is None:
            await ctx.send("Prestige is not available for this path.")
            return
        self.dirty = True
        await ctx.send(f"{source.title()} Prestige -> {updated[f'{source}_prestige']}")