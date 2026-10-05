import discord
from discord.ext import commands

# ID Twojego kanału do logów
AUDIT_LOG_CHANNEL_ID = 0

class AuditLogCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _send_log(self, embed: discord.Embed):
        """Pomocnicza funkcja do bezpiecznego wysyłania logów z obsługą błędów API."""
        channel = self.bot.get_channel(AUDIT_LOG_CHANNEL_ID)
        if channel and isinstance(channel, discord.TextChannel):
            try:
                await channel.send(embed=embed)
            except discord.HTTPException as e:
                print(f"⚠️ Nie udało się wysłać logu na kanał (limity Discorda): {e}")

    def _skroc_tekst(self, tekst: str, max_len: int = 1024) -> str:
        """Zabezpiecza bota przed błędem, gdy tekst wiadomości lub ról jest za długi dla pola Embed."""
        if len(tekst) > max_len:
            return tekst[:max_len - 15] + "... (ucięto)"
        return tekst

    # ==========================================
    # 1. MONITOROWANIE WIADOMOŚCI (TEKST)
    # ==========================================
    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        embed = discord.Embed(
            title="🗑️ Usunięto wiadomość", 
            color=discord.Color.red(), 
            timestamp=message.created_at
        )
        embed.add_field(name="Autor", value=f"{message.author.mention} ({message.author.id})", inline=True)
        
        # Jawne sprawdzenie typu dla Pylance, które gwarantuje dostęp do .mention
        if isinstance(message.channel, discord.TextChannel):
            kanal_txt = message.channel.mention
        else:
            kanal_txt = f"#{message.channel}"
            
        embed.add_field(name="Kanał", value=kanal_txt, inline=True)
        
        tresc = message.content if message.content else "*Brak treści tekstowej (np. sam obrazek) lub wiadomość spoza pamięci cache bota*"
        embed.add_field(name="Treść wiadomości", value=self._skroc_tekst(tresc), inline=False)
        await self._send_log(embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or before.guild is None or before.content == after.content:
            return

        embed = discord.Embed(
            title="✏️ Edytowano wiadomość", 
            color=discord.Color.blue(), 
            timestamp=after.edited_at or discord.utils.utcnow()
        )
        embed.add_field(name="Autor", value=f"{before.author.mention} ({before.author.id})", inline=True)
        
        # Jawne sprawdzenie typu dla Pylance, które gwarantuje dostęp do .mention
        if isinstance(before.channel, discord.TextChannel):
            kanal_txt = before.channel.mention
        else:
            kanal_txt = f"#{before.channel}"
            
        embed.add_field(name="Kanał", value=kanal_txt, inline=True)
        
        embed.add_field(name="Przed edycją", value=self._skroc_tekst(before.content or "*Brak*"), inline=False)
        embed.add_field(name="Po edycji", value=self._skroc_tekst(after.content or "*Brak*"), inline=False)
        await self._send_log(embed)

    # ==========================================
    # 2. RUCH UŻYTKOWNIKÓW (DOŁĄCZENIA / WYJŚCIA)
    # ==========================================
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        embed = discord.Embed(
            title="📥 Nowy użytkownik dołączył", 
            description=f"{member.mention} wszedł na serwer.", 
            color=discord.Color.green(), 
            timestamp=discord.utils.utcnow()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="ID Konta", value=member.id, inline=True)
        await self._send_log(embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        embed = discord.Embed(
            title="📤 Użytkownik wyszedł", 
            description=f"**{member.display_name}** opuścił serwer (lub został wyrzucony).", 
            color=discord.Color.dark_orange(), 
            timestamp=discord.utils.utcnow()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="ID Konta", value=member.id, inline=True)
        await self._send_log(embed)

    # ==========================================
    # 3. ZDARZENIA MODERACYJNE (BANY & TIMEOUTY)
    # ==========================================
    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User | discord.Member):
        embed = discord.Embed(
            title="🔨 Użytkownik Zbanowany", 
            description=f"**{user.name}** został zbanowany na serwerze.\n*Szczegóły i powód sprawdź we wbudowanym Audit Logu Discorda.*", 
            color=discord.Color.dark_red(), 
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="Użytkownik", value=user.mention, inline=True)
        embed.add_field(name="ID Konta", value=user.id, inline=True)
        await self._send_log(embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        embed = discord.Embed(
            title="🔓 Użytkownik Odbanowany", 
            description=f"**{user.name}** został odbanowany.", 
            color=discord.Color.light_embed(), 
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="ID Konta", value=user.id, inline=True)
        await self._send_log(embed)

    # ==========================================
    # 4. ZMIANY PROFILI (NICKI, ROLE, TIMEOUTY)
    # ==========================================
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        # A. Aktualizacja ról użytkownika
        if before.roles != after.roles:
            embed = discord.Embed(title="🛡️ Zmiana ról użytkownika", color=discord.Color.teal(), timestamp=discord.utils.utcnow())
            embed.add_field(name="Użytkownik", value=f"{after.mention} ({after.id})", inline=False)
            
            added = [r.mention for r in after.roles if r not in before.roles]
            removed = [r.mention for r in before.roles if r not in after.roles]
            
            if added: embed.add_field(name="🟢 Nadane role", value=self._skroc_tekst(", ".join(added)), inline=False)
            if removed: embed.add_field(name="🔴 Zabrane role", value=self._skroc_tekst(", ".join(removed)), inline=False)
            await self._send_log(embed)

        # B. Zmiana pseudonimu na serwerze
        if before.display_name != after.display_name:
            embed = discord.Embed(title="🏷️ Zmiana pseudonimu", color=discord.Color.orange(), timestamp=discord.utils.utcnow())
            embed.add_field(name="Użytkownik", value=after.mention, inline=True)
            embed.add_field(name="Stary Nick", value=before.display_name, inline=True)
            embed.add_field(name="Nowy Nick", value=after.display_name, inline=True)
            await self._send_log(embed)

        # C. Nadanie lub zdjęcie kary Timeout (Wyciszenia)
        if before.timed_out_until != after.timed_out_until:
            embed = discord.Embed(title="⏳ Status Przerwy (Timeout)", color=discord.Color.dark_grey(), timestamp=discord.utils.utcnow())
            embed.add_field(name="Użytkownik", value=after.mention, inline=True)
            if after.timed_out_until:
                embed.description = f"{after.mention} został wyciszony przez administrację."
                embed.add_field(name="Koniec kary (UTC)", value=after.timed_out_until.strftime('%Y-%m-%d %H:%M:%S'), inline=False)
            else:
                embed.description = f"Kara wyciszenia dla {after.mention} została zdjęta."
            await self._send_log(embed)

    # ==========================================
    # 5. STRUKTURA SERWERA (KANAŁY & ROLE)
    # ==========================================
    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        embed = discord.Embed(
            title="➕ Stworzono nowy kanał", 
            description=f"Nazwa: **{channel.name}**\nTyp: `{channel.type}`\n*Kto stworzył i uprawnienia: zobacz wbudowany Audit Log.*", 
            color=discord.Color.brand_green(), 
            timestamp=discord.utils.utcnow()
        )
        await self._send_log(embed)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        embed = discord.Embed(
            title="➖ Usunięto kanał", 
            description=f"Nazwa: **{channel.name}**\nTyp: `{channel.type}`", 
            color=discord.Color.dark_magenta(), 
            timestamp=discord.utils.utcnow()
        )
        await self._send_log(embed)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        embed = discord.Embed(
            title="✨ Stworzono nową rolę", 
            description=f"Rola: {role.mention} (**{role.name}**)\n*Konfigurację uprawnień roli sprawdź we wbudowanym logu serwera.*", 
            color=discord.Color.gold(), 
            timestamp=discord.utils.utcnow()
        )
        await self._send_log(embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        embed = discord.Embed(
            title="🔥 Usunięto rolę serwera", 
            description=f"Nazwa roli: **{role.name}**", 
            color=discord.Color.light_gray(), 
            timestamp=discord.utils.utcnow()
        )
        await self._send_log(embed)

    # ==========================================
    # 6. RUCH NA KANAŁACH GŁOSOWYCH (VOICE)
    # ==========================================
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if before.channel == after.channel:
            return

        embed = discord.Embed(color=discord.Color.blurple(), timestamp=discord.utils.utcnow())
        embed.add_field(name="Użytkownik", value=f"{member.mention} ({member.id})", inline=False)

        if before.channel is None and after.channel is not None:
            embed.title = "🔊 Połączono z Voice"
            embed.description = f"Użytkownik wszedł na kanał {after.channel.mention}"
            await self._send_log(embed)
        elif before.channel is not None and after.channel is None:
            embed.title = "🔇 Rozłączono z Voice"
            embed.description = f"Użytkownik opuścił kanał {before.channel.mention}"
            await self._send_log(embed)
        elif before.channel is not None and after.channel is not None:
            embed.title = "🔀 Przełączono kanał"
            embed.description = f"Przejście z kanału {before.channel.mention} ➡️ {after.channel.mention}"
            await self._send_log(embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(AuditLogCog(bot))