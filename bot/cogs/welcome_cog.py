import asyncio
from typing import Optional
import discord
from discord.ext import commands
from bot.config import GENERAL_CHANNEL_ID, WELCOME_CHANNEL_ID

class WelcomeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _register_member(self, member: discord.Member) -> bool:
        leveling_cog = self.bot.get_cog("LevelingCog")
        if leveling_cog is None:
            print("⚠️ Nie można sprawdzić bazy graczy: LevelingCog nie jest załadowany.")
            return True

        user_id = str(member.id)
        lock = leveling_cog.profile_locks.setdefault(member.id, asyncio.Lock())
        async with lock:
            is_new_member = user_id not in leveling_cog.dane_graczy
            leveling_cog.get_profil(member.id)
        return is_new_member

    async def _get_or_fetch_channel(self, channel_id: int) -> Optional[discord.TextChannel]:
        """
        Bezpieczny pomocnik pobierający kanał. Najpierw sprawdza cache,
        a w razie pustki dociąga dane bezpośrednio z API Discorda.
        """
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            try:
                # Jeśli nie ma w cache, odpytujemy API Discorda
                fetched_channel = await self.bot.fetch_channel(channel_id)
                if isinstance(fetched_channel, discord.TextChannel):
                    return fetched_channel
            except (discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
                print(f"⚠️ Błąd podczas fetchowania kanału {channel_id}: {e}")
                return None
        
        return channel if isinstance(channel, discord.TextChannel) else None

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        is_new_member = await self._register_member(member)
        welcome_text = (
            "Witamy Cię tutaj po raz pierwszy! Mamy nadzieję, że znajdziesz "
            "swoje miejsce w naszej społeczności."
            if is_new_member
            else "Miło Cię znowu widzieć! Cieszymy się, że wróciłeś do naszej społeczności."
        )

        embed = discord.Embed(
            title=(
                f"Witaj po raz pierwszy, {member.name}!"
                if is_new_member
                else f"Witaj ponownie, {member.name}!"
            ),
            description=(
                f"Cześć {member.mention}! {welcome_text}"
            ),
            color=discord.Color.blue(),
        )
        # Pobieramy url awatara (zawsze bezpieczne w d.py v2+)
        embed.set_thumbnail(url=member.display_avatar.url)

        # 2. Pobieramy kanały z obsługą API fallbacku
        welcome_channel = await self._get_or_fetch_channel(WELCOME_CHANNEL_ID)
        general_channel = await self._get_or_fetch_channel(GENERAL_CHANNEL_ID)

        # 3. Wysyłamy wiadomości
        if welcome_channel:
            await welcome_channel.send(embed=embed)
        else:
            print(f"⚠️ Błąd: Nie znaleziono kanału powitalnego o ID {WELCOME_CHANNEL_ID}")

        if general_channel:
            if is_new_member:
                await general_channel.send(
                    f"Powitajcie nowego użytkownika: {member.mention}!"
                )
            else:
                await general_channel.send(
                    f"Powitajcie ponownie {member.mention}! Użytkownik wrócił na serwer."
                )
        else:
            print(f"⚠️ Błąd: Nie znaleziono kanału ogólnego o ID {GENERAL_CHANNEL_ID}")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        welcome_channel = await self._get_or_fetch_channel(WELCOME_CHANNEL_ID)
        
        if welcome_channel:
            await welcome_channel.send(f"Użytkownik **{member.name}** opuścił serwer.")
        else:
            print(f"⚠️ Błąd podczas próby pożegnania gracza: Brak kanału o ID {WELCOME_CHANNEL_ID}")

async def setup(bot: commands.Bot):
    await bot.add_cog(WelcomeCog(bot))