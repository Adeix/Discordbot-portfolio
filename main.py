import asyncio
import logging
import discord
from discord.ext import commands
from bot.config import TOKEN, COMMAND_PREFIX

# --- KONFIGURACJA LOGOWANIA (BŁĘDY W KONSOLI) ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("DiscordBot")

# Definiujemy uprawnienia (Intents) bota
intents = discord.Intents.default()
intents.message_content = True   
intents.members = True           
intents.voice_states = True      
intents.presences = True         
intents.moderation = True

# --- DZIEDZICZENIE PO BOT I OBSŁUGA SETUP_HOOK ---
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=COMMAND_PREFIX, intents=intents, help_command=None)

    async def setup_hook(self):
        """
        Ta metoda uruchamia się automatycznie po zalogowaniu bota (gdy application_id jest już znane),
        ale jeszcze przed nawiązaniem pełnego połączenia z WebSocketem.
        """
        # 1. Ładowanie wszystkich modułów (Cogów)
        cogs = [
            "bot.cogs.leveling_cog",
            "bot.cogs.bump_cog",
            "bot.cogs.suggestions_cog",
            "bot.cogs.general_cog",
            "bot.cogs.welcome_cog",
            "bot.cogs.audit_log_cog",
            "bot.cogs.anti_scam_cog",
            "bot.cogs.ragebait_cog",
            "bot.cogs.devTools_cog",
            "bot.cogs.activity_lfg_cog",
            "bot.cogs.appeal_modal_cog",
            "bot.cogs.counting_cog",
        ]
        
        for cog in cogs:
            try:
                await self.load_extension(cog)
                logger.info(f"📦 Załadowano moduł: {cog}")
            except Exception as e:
                logger.critical(f"❌ Krytyczny błąd ładowania modułu {cog}!")
                logger.error("Szczegóły błędu:", exc_info=e)

        # 2. Synchronizacja komend Slash (TUTAJ application_id jest już bezpiecznie dostępne)
        try:
            logger.info("⚡ Rejestrowanie komend Slash w API Discorda...")
            synced = await self.tree.sync()
            logger.info(f"✅ Zsynchronizowano {len(synced)} komend(y) Slash!")
        except Exception as e:
            logger.error("❌ Błąd podczas synchronizacji komend Slash:", exc_info=e)

bot = MyBot()

@bot.event
async def on_ready():
    logger.info("=========================================")
    logger.info(f"✅ Zalogowano jako: {bot.user}")
    logger.info(f"🤖 Prefiks bota: {COMMAND_PREFIX}")
    logger.info("=========================================")
    await bot.change_presence(activity=discord.Game(name=f"{COMMAND_PREFIX}help"))

# 🔥 GLOBALNY ŁAPACZ BŁĘDÓW DLA KOMEND (LOGOWANIE)
@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CommandNotFound):
        komenda = ctx.invoked_with
        await ctx.send(f"❓ Nie znaleziono komendy: `{komenda}`")
        return

    if isinstance(error, commands.MissingPermissions):
        await ctx.send("🛑 Brak uprawnień do użycia tej komendy!")
        logger.warning(f"Użytkownik {ctx.author} (ID: {ctx.author.id}) próbował użyć komendy {ctx.command} bez uprawnień.")
        return

    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"ℹ️ Brakujący argument! Poprawne użycie znajdziesz pod `{COMMAND_PREFIX}help {ctx.command}`")
        return

    await ctx.send("❌ Wystąpił błąd wewnętrzny bota podczas wykonywania tej komendy. Szczegóły zostały zapisane w konsoli.")
    oryginalny_blad = getattr(error, "original", error)
    logger.error(f"Wywaliło błąd w komendzie '{ctx.command}':", exc_info=oryginalny_blad)

# --- KOMENDA DEBUGUJĄCA DO SPRAWDZANIA REJESTRACJI ---
@bot.command(name="check_commands")
async def check_commands(ctx: commands.Context):
    """Pokazuje listę wszystkich komend, jakie bot aktualnie widzi."""
    lista = [f"• {cmd.name} (z: {cmd.cog_name if cmd.cog else 'Main'})" for cmd in bot.commands]
    cmd_txt = "\n".join(lista) if lista else "Brak zarejestrowanych komend!"
    
    embed = discord.Embed(
        title="🤖 Stan rejestracji komend bota",
        description=f"Wszystkie aktywne komendy wykryte przez bota:\n\n{cmd_txt}",
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed)

async def main():
    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())