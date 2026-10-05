import re
from datetime import datetime, timezone
import discord
from discord.ext import commands

# Wyrażenie regularne (Regex) do wykrywania linków zaproszeń Discord.
# Wyłapuje różne formy: discord.gg/, discord.com/invite/, discordapp.com/invite/ itd.
DISCORD_INVITE_REGEX = re.compile(
    r"(discord\.(gg|io|me|li)\/.+|discord(app)?\.com\/invite\/.+)", 
    re.IGNORECASE
)

# Czas w minutach, przez który nowy użytkownik jest na "cenzurowanym"
MAX_JOIN_AGE_MINUTES = 15

class AntiScamCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignorujemy wiadomości od botów (w tym od samego siebie) oraz wiadomości w DM
        if message.author.bot or not message.guild:
            return

        # Sprawdzamy, czy treść wiadomości pasuje do wzorca zaproszenia Discord
        if DISCORD_INVITE_REGEX.search(message.content):
            author = message.author
            
            # Dla bezpieczeństwa typowania upewniamy się, że author to obiekt Member
            if not isinstance(author, discord.Member):
                return

            # Sprawdzamy, czy użytkownik ma uprawnienia administratora/moderatora,
            # aby bot przypadkiem nie zbanował admina testującego linki.
            if author.guild_permissions.manage_messages or author.guild_permissions.administrator:
                return

            # Pobieramy datę dołączenia użytkownika (joined_at jest w strefie czasowej UTC)
            joined_at = author.joined_at
            if not joined_at:
                return

            # Obliczamy różnicę czasu między "teraz" a momentem dołączenia
            now = datetime.now(timezone.utc)
            difference = now - joined_at
            difference_in_minutes = difference.total_seconds() / 60

            # Jeśli użytkownik jest na serwerze krócej niż 15 minut
            if difference_in_minutes < MAX_JOIN_AGE_MINUTES:
                try:
                    # 1. Usuwamy szkodliwą wiadomość
                    await message.delete()

                    # 2. Banujemy użytkownika z podaniem powodu do audytu (audit log)
                    reason = f"Automatyczny ban: Wysyłanie linku zaproszenia {difference_in_minutes:.1f} min po dołączeniu."
                    await author.ban(delete_message_days=1, reason=reason)

                    # 3. Opcjonalnie: Możemy wysłać informację na kanał, na którym to się stało
                    await message.channel.send(
                        f"🛡️ Użytkownik **{author.name}** został automatycznie zbanowany za próby reklamowania bezpośrednio po wejściu.",
                        delete_after=10  # Wiadomość bota usunie się sama po 10 sekundach, by nie robić śmietnika
                    )
                except discord.Forbidden:
                    # Ten błąd wystąpi, jeśli bot nie ma uprawnień do usuwania wiadomości lub banowania użytkowników
                    print(f"❌ Brak uprawnień do zbanowania {author.name} lub usunięcia jego wiadomości.")
                except discord.HTTPException as e:
                    print(f"❌ Błąd HTTP podczas próby ukarania użytkownika: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(AntiScamCog(bot))