from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

import discord
from discord.ext import tasks

from bot.config import (
    VOICE_XP_EXCLUDED_CATEGORY_IDS,
    VOICE_XP_EXCLUDED_CHANNEL_IDS,
    VOICE_XP_TICK_SECONDS,
)


class VoiceTracker:
    """Przyznaje tick voice po pełnych 5 minutach spełnionej aktywności."""

    def __init__(
        self,
        bot: discord.Client,
        on_eligible_member: Callable[[discord.Member], Awaitable[None]],
    ):
        self.bot = bot
        self.on_eligible_member = on_eligible_member
        self.presence_started: dict[int, float] = {}

    def start(self) -> None:
        self._loop.start()

    def cancel(self) -> None:
        self._loop.cancel()

    @tasks.loop(minutes=5.0)
    async def _loop(self) -> None:
        if not self.bot.guilds:
            return

        guild = self.bot.guilds[0]
        eligible_members: list[discord.Member] = []
        for channel in guild.voice_channels:
            if self._is_excluded_channel(guild, channel):
                continue

            members = [member for member in channel.members if not member.bot]
            if len(members) >= 2:
                eligible_members.extend(members)

        now = time.monotonic()
        eligible_ids = {member.id for member in eligible_members}
        for user_id in list(self.presence_started):
            if user_id not in eligible_ids:
                del self.presence_started[user_id]

        for member in eligible_members:
            if member.voice and (member.voice.self_mute or member.voice.self_deaf):
                self.presence_started.pop(member.id, None)
                continue

            started_at = self.presence_started.setdefault(member.id, now)
            if now - started_at < VOICE_XP_TICK_SECONDS:
                continue

            self.presence_started[member.id] = now
            await self.on_eligible_member(member)

    @staticmethod
    def _is_excluded_channel(
        guild: discord.Guild, channel: discord.VoiceChannel
    ) -> bool:
        if channel.id in VOICE_XP_EXCLUDED_CHANNEL_IDS:
            return True
        if channel.category_id in VOICE_XP_EXCLUDED_CATEGORY_IDS:
            return True
        return guild.afk_channel is not None and channel.id == guild.afk_channel.id
