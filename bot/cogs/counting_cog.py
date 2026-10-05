from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import re

import discord
from discord.ext import commands

from bot.config import (
    COUNTING_CHANNEL_ID,
    COUNTING_LOG_CHANNEL_ID,
    COUNTING_MILESTONES,
)


MAX_COUNTING_NUMBER = 2**63 - 1
COUNTING_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "counting.sqlite3"
INTEGER_MESSAGE_PATTERN = re.compile(r"^[0-9]+$")


class CountingControlView(discord.ui.View):
    def __init__(self, cog: "CountingCog"):
        super().__init__(timeout=900)
        self.cog = cog

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "Nie masz uprawnień do sterowania licznikiem.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Start od 1", style=discord.ButtonStyle.green)
    async def start_from_one(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.set_next_number(1)
        await interaction.response.send_message("Ustawiono następną liczbę na **1**.", ephemeral=True)

    @discord.ui.button(label="Ustaw liczbę", style=discord.ButtonStyle.primary)
    async def set_number(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SetCountingNumberModal(self.cog))

    @discord.ui.button(label="Resetuj", style=discord.ButtonStyle.red)
    async def reset(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.set_next_number(1)
        await interaction.response.send_message("Licznik zresetowano. Następna liczba to **1**.", ephemeral=True)


class SetCountingNumberModal(discord.ui.Modal, title="Ustaw następną liczbę"):
    number = discord.ui.TextInput(
        label="Następna liczba",
        placeholder="np. 1",
        min_length=1,
        max_length=19,
        required=True,
    )

    def __init__(self, cog: "CountingCog"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        parsed_number = self.cog.parse_number(self.number.value)
        if parsed_number is None:
            await interaction.response.send_message(
                "Podaj dodatnią liczbę całkowitą od 1 do 2^63-1.", ephemeral=True
            )
            return

        await self.cog.set_next_number(parsed_number)
        await interaction.response.send_message(
            f"Ustawiono następną liczbę na **{parsed_number}**.", ephemeral=True
        )


class CountingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.current_number: int | None = None
        self.last_user_id: int | None = None
        self.state_lock = asyncio.Lock()
        COUNTING_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(COUNTING_DB_PATH)
        self._create_schema()

    def _create_schema(self) -> None:
        COUNTING_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        with self.connection:
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS counting_milestones (
                    milestone INTEGER PRIMARY KEY,
                    awarded_by TEXT NOT NULL,
                    awarded_at TEXT NOT NULL
                )
                """
            )

    async def cog_unload(self):
        self.connection.close()

    @staticmethod
    def parse_number(content: str) -> int | None:
        if not INTEGER_MESSAGE_PATTERN.fullmatch(content):
            return None

        number = int(content)
        if number < 1 or number > MAX_COUNTING_NUMBER:
            return None
        return number
# komentarz
    async def set_next_number(self, next_number: int) -> None:
        async with self.state_lock:
            self.current_number = next_number - 1
            self.last_user_id = None

    async def _get_log_channel(self) -> discord.TextChannel | None:
        channel = self.bot.get_channel(COUNTING_LOG_CHANNEL_ID)
        if isinstance(channel, discord.TextChannel):
            return channel

        try:
            fetched_channel = await self.bot.fetch_channel(COUNTING_LOG_CHANNEL_ID)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None
        return fetched_channel if isinstance(fetched_channel, discord.TextChannel) else None

    async def _log_event(self, message: discord.Message, reason: str, expected: int | None) -> None:
        log_channel = await self._get_log_channel()
        if log_channel is None:
            return

        content = message.content.replace("`", "'")[:500]
        expected_text = str(expected) if expected is not None else "nieustalona"
        try:
            await log_channel.send(
                f"Counting: usunięto wiadomość użytkownika **{message.author}** "
                f"(ID `{message.author.id}`), powód: **{reason}**, "
                f"oczekiwano: **{expected_text}**, treść: `{content}`",
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            return

    async def _delete_and_log(self, message: discord.Message, reason: str, expected: int | None) -> None:
        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            await self._log_event(message, f"nie_usunięto ({reason})", expected)
            return
        await self._log_event(message, reason, expected)

    def _milestone_was_awarded(self, milestone: int) -> bool:
        row = self.connection.execute(
            "SELECT 1 FROM counting_milestones WHERE milestone = ?", (milestone,)
        ).fetchone()
        return row is not None

    def _mark_milestone_awarded(self, milestone: int, user_id: int) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT INTO counting_milestones(milestone, awarded_by, awarded_at) VALUES (?, ?, ?)",
                (milestone, str(user_id), datetime.now(timezone.utc).isoformat()),
            )

    async def _award_milestone(self, message: discord.Message, milestone: int, reward: int) -> None:
        if self._milestone_was_awarded(milestone):
            return

        self._mark_milestone_awarded(milestone, message.author.id)
        leveling_cog = self.bot.get_cog("LevelingCog")
        if leveling_cog is not None and reward > 0:
            await leveling_cog.dodaj_xp(
                message.author.id,
                reward,
                wiadomosc=message,
                guild=message.guild,
                source="bonus",
                reason=f"kamień milowy liczenia: {milestone}",
            )
        await self._log_event(message, f"kamień_milowy_{milestone}_plus_{reward}_XP", milestone)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.channel.id != COUNTING_CHANNEL_ID:
            return

        async with self.state_lock:
            expected = None if self.current_number is None else self.current_number + 1
            parsed_number = self.parse_number(message.content)

            if message.author.bot:
                await self._delete_and_log(message, "wiadomość_bota", expected)
                return
            if expected is None:
                await self._delete_and_log(message, "licznik_nieuruchomiony", expected)
                return
            if parsed_number is None:
                await self._delete_and_log(message, "niepoprawny_format", expected)
                return
            if parsed_number != expected:
                await self._delete_and_log(message, "nieprawidlowa_kolejnosc", expected)
                return
            if message.author.id == self.last_user_id:
                await self._delete_and_log(message, "dwie_liczby_tego_samego_uzytkownika", expected)
                return

            self.current_number = parsed_number
            self.last_user_id = message.author.id
            milestone_reward = COUNTING_MILESTONES.get(parsed_number)
            if milestone_reward is not None:
                await self._award_milestone(message, parsed_number, milestone_reward)

    @commands.command(name="counting_panel")
    @commands.has_permissions(administrator=True)
    async def counting_panel(self, ctx: commands.Context):
        embed = discord.Embed(
            title="Panel liczenia",
            description=(
                "Ustaw następną liczbę przed rozpoczęciem lub po restarcie bota.\n"
                "Błędne wiadomości są usuwane automatycznie."
            ),
            color=discord.Color.blurple(),
        )
        await ctx.send(embed=embed, view=CountingControlView(self))


async def setup(bot: commands.Bot):
    await bot.add_cog(CountingCog(bot))