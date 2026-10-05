import asyncio
from typing import Any, Optional
import discord
from discord.ext import commands
from bot.config import DISBOARD_CHANNEL_ID, BUMP_ROLE_ID, BUMP_REMINDER_DELAY_SECONDS

class BumpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Przechowujemy referencję do aktywnego zadania przypomnienia
        self.active_reminder: Optional[asyncio.Task] = None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # 1. Filtrowanie (Szybkie wyjście)
        if message.channel.id != DISBOARD_CHANNEL_ID or not message.author.bot:
            return

        if not message.embeds:
            return

        embed = message.embeds[0]
        opis = embed.description or ""
        
# 2. Sprawdzanie sukcesu
        if "Podbito serwer" in opis or "Bump done" in opis:
            user = None
            if message.interaction and message.interaction.user:
                user = message.interaction.user

            # Domyślnie ustawiamy na 0, na wypadek gdyby LevelingCog nie odpowiedział
            ilosc_bumpow = 0
            nagroda_xp = 0

            # Sekcja przyznawania nagrody za bump
            if user:
                leveling_cog: Any = self.bot.get_cog("LevelingCog")
    
                if leveling_cog is not None:
                    # A. Zwiększamy licznik bumpów i wyliczamy dynamiczną nagrodę.
                    if hasattr(leveling_cog, "dodaj_bump"):
                        ilosc_bumpow = await leveling_cog.dodaj_bump(user.id)
                    else:
                        print("[Błąd] Brak metody 'dodaj_bump' w LevelingCog!")

                    # B. Odpalamy nagrodę XP
                    nagroda_xp = leveling_cog.oblicz_nagrode_bump(user, ilosc_bumpow)
                    await leveling_cog.nagroda_specjalna(
                        user_id=user.id,
                        ilosc_xp=nagroda_xp,
                        powod="Podbicie serwera (Disboard)",
                        kanal_tekstowy=message.channel,
                        apply_booster=False,
                    )
                else:
                    print("[Błąd] Nie znaleziono załadowanego Coga o nazwie 'LevelingCog'")

            # --- WIADOMOŚĆ POTWIERDZAJĄCA ---
            embed_potw = discord.Embed(
                title="✨ Serwer podbity!",
                description=(
                    f"🎁 {user.mention if user else 'Użytkownik'} dostaje **+{nagroda_xp if user else 0} XP**!\n"
                    f"🔥 To już Twój **{ilosc_bumpow}** bump na tym serwerze!"
                ),
                color=discord.Color.green()
            )
            if user and user.display_avatar:
                embed_potw.set_thumbnail(url=user.display_avatar.url)
            
            await message.channel.send(embed=embed_potw)
            
            # --- ODLICZANIE (ASYNC TASK) ---
            if self.active_reminder and not self.active_reminder.done():
                self.active_reminder.cancel()

            self.active_reminder = asyncio.create_task(self.bump_reminder(message))

    async def bump_reminder(self, message: discord.Message):
        """Osobna funkcja do odliczania, aby nie blokować listenera"""
        try:
            await asyncio.sleep(BUMP_REMINDER_DELAY_SECONDS)
            
            rola_bump = message.guild.get_role(BUMP_ROLE_ID) if message.guild else None
            wzmianka = rola_bump.mention if rola_bump else "@here"
            
            await message.channel.send(
                f"🔔 {wzmianka} - Minęły 2 godziny od podbicia! Można ponownie użyć `/bump`."
            )
        except asyncio.CancelledError:
            # Ta sekcja odpali się, gdy anulujemy zadanie przez `.cancel()`
            # Dzięki temu nie zobaczymy żadnych błędów w konsoli przy resetowaniu timera
            print("[DEBUG] Zadanie przypomnienia zostało pomyślnie przerwane.")
        except Exception as e:
            print(f"[Błąd] Wystąpił niespodziewany błąd w przypomnieniu: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(BumpCog(bot))