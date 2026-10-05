from __future__ import annotations

import discord


class LeaderboardView(discord.ui.View):
    def __init__(self, author_id: int, pages: list[str], author_footer: str):
        super().__init__(timeout=60.0)
        self.author_id = author_id
        self.pages = pages
        self.author_footer = author_footer
        self.current_page = 0
        self.message: discord.Message | None = None

    async def update_embed(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="🏆 GLOBALNY RANKING SERWERA 🏆",
            description=self.pages[self.current_page],
            color=discord.Color.gold(),
        )
        embed.add_field(
            name="──────────────",
            value=self.author_footer,
            inline=False,
        )
        embed.set_footer(
            text=f"Strona {self.current_page + 1} z {len(self.pages)}"
        )
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.NotFound:
                pass

    async def _reject_other_user(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return False

        await interaction.response.send_message(
            "❌ Tylko osoba wywołująca komendę może zmieniać strony!",
            ephemeral=True,
        )
        return True

    @discord.ui.button(label="◀ Wróć", style=discord.ButtonStyle.blurple)
    async def previous(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if await self._reject_other_user(interaction):
            return

        if self.current_page == 0:
            await interaction.response.send_message(
                "ℹ️ To jest już pierwsza strona!", ephemeral=True
            )
            return

        self.current_page -= 1
        await self.update_embed(interaction)

    @discord.ui.button(label="Dalej ▶", style=discord.ButtonStyle.blurple)
    async def next(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if await self._reject_other_user(interaction):
            return

        if self.current_page >= len(self.pages) - 1:
            await interaction.response.send_message(
                "ℹ️ To jest już ostatnia strona!", ephemeral=True
            )
            return

        self.current_page += 1
        await self.update_embed(interaction)
