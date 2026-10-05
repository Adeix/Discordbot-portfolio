import asyncio
import io
import contextlib
import textwrap
import copy
import discord
from discord.ext import commands

class DevToolsCog(commands.Cog, name="DevTools"):
    """
    Cog z narzędziami deweloperskimi: eval, automatyczny testmode (sandbox z auto-backupem).
    Dostępny tylko dla właściciela bota.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Flaga trybu testowego
        self.test_mode = False
        # Słownik do przechowywania kopii zapasowych profili graczy
        self.backups = {}

    # ==========================================================================
    # METODY POMOCNICZE (Wewnętrzna logika backup / restore)
    # ==========================================================================
    def _do_backup(self, user_id: int) -> bool:
        """Wewnętrzna funkcja wykonująca kopię zapasową profilu gracza w RAM."""
        leveling_cog = self.bot.get_cog("LevelingCog")
        if leveling_cog:
            dane_graczy: dict = getattr(leveling_cog, "dane_graczy", {})
            user_data = dane_graczy.get(user_id) or dane_graczy.get(str(user_id))
            
            if user_data is not None:
                self.backups[user_id] = copy.deepcopy(user_data)
                return True
        return False

    async def _do_restore(self, user_id: int) -> bool:
        """Wewnętrzna funkcja przywracająca profil gracza z kopii zapasowej."""
        if user_id not in self.backups:
            return False

        leveling_cog = self.bot.get_cog("LevelingCog")
        if leveling_cog:
            dane_graczy = getattr(leveling_cog, "dane_graczy", None)
            
            if isinstance(dane_graczy, dict):
                lock = leveling_cog.profile_locks.setdefault(
                    user_id, asyncio.Lock()
                )
                async with lock:
                    profile_id = (
                        user_id if user_id in dane_graczy else str(user_id)
                    )
                    dane_graczy[profile_id] = copy.deepcopy(self.backups[user_id])
                    leveling_cog.zapisz_baze()
                return True
        return False

    # ==========================================================================
    # 1. KOMENDA EVAL (Wykonywanie kodu Pythona na żywo)
    # ==========================================================================
    @commands.command(name="eval", hidden=True)
    @commands.is_owner()
    async def eval_command(self, ctx: commands.Context, *, body: str):
        """Wykonuje dowolny kod Pythona przesłany na czacie Discorda."""
        if body.startswith("```") and body.endswith("```"):
            body = "\n".join(body.split("\n")[1:-1])
        else:
            body = body.strip("` \n")

        env = {
            "bot": self.bot,
            "ctx": ctx,
            "channel": ctx.channel,
            "author": ctx.author,
            "guild": ctx.guild,
            "message": ctx.message,
        }

        stdout = io.StringIO()
        code = f"async def _eval_func():\n{textwrap.indent(body, '    ')}"

        try:
            exec(code, env)
            _eval_func = env["_eval_func"]
            
            with contextlib.redirect_stdout(stdout):
                await _eval_func()
            
            output = stdout.getvalue()
            if output:
                await ctx.send(f"📥 **Wynik:**\n```py\n{output}\n```")
            else:
                await ctx.message.add_reaction("✅")
                
        except Exception as err:
            await ctx.send(f"❌ **Błąd wykonania:**\n```py\n{err}\n```")

    # ==========================================================================
    # 2. AUTOMATYCZNY TRYB TESTOWY (Test Mode ON/OFF z Backup/Restore)
    # ==========================================================================
    @commands.command(name="testmode", aliases=["tm"])
    @commands.is_owner()
    async def toggle_test_mode(self, ctx: commands.Context):
        """Przełącza tryb testowy z automatycznym wykonywaniem kopii i przywracaniem profilu."""
        self.test_mode = not self.test_mode
        user_id = ctx.author.id

        if self.test_mode:
            # 🧪 WŁĄCZAMY TRYB TESTOWY -> Robimy backup profilu
            backup_success = self._do_backup(user_id)
            
            if backup_success:
                await ctx.reply(
                    "🧪 **Tryb testowy WŁĄCZONY!**\n"
                    "1. 💾 Automatycznie **utworzono kopię zapasową** Twojego profilu w RAM.\n"
                    "2. 🛑 Zmiany testowe nie powinny być traktowane jako trwałe.\n"
                    " Możesz teraz bezpiecznie testować przez `eval` bez obaw o stan profilu!"
                )
            else:
                await ctx.reply(
                    "🧪 **Tryb testowy WŁĄCZONY!** (zmiany testowe są tymczasowe)\n"
                    "⚠️ *Uwaga: Nie odnaleziono Twojego profilu w `dane_graczy`, więc backup nie został utworzony.*"
                )

        else:
            # 🔴 WYŁĄCZAMY TRYB TESTOWY -> Przywracamy profil z backupu
            restore_success = await self._do_restore(user_id)
            
            if restore_success:
                await ctx.reply(
                    "🔴 **Tryb testowy WYŁĄCZONY!**\n"
                    "1. 🔄 **Przywrócono profil** do oryginalnego stanu sprzed testów.\n"
                    "2. 🟢 Przywrócony profil został zapisany w bazie SQLite."
                )
            else:
                await ctx.reply(
                    "🔴 **Tryb testowy WYŁĄCZONY!** Zapisywanie przywrócone.\n"
                    "⚠️ *Uwaga: Brak zapisanej kopii zapasowej do przywrócenia.*"
                )

    # ==========================================================================
    # 3. OPCJONALNE KOMENDY RĘCZNE (Na wypadek potrzeby ręcznego użycia)
    # ==========================================================================
    @commands.command(name="backup_me")
    @commands.is_owner()
    async def backup_profile(self, ctx: commands.Context):
        """Ręcznie tworzy kopię zapasową Twojego profilu."""
        if self._do_backup(ctx.author.id):
            await ctx.reply("💾 **Kopia zapasowa gotowa!** Twój profil został zapamiętany.")
        else:
            await ctx.reply("❌ Nie znaleziono Twojego profilu w `dane_graczy`.")

    @commands.command(name="restore_me")
    @commands.is_owner()
    async def restore_profile(self, ctx: commands.Context):
        """Ręcznie przywraca profil z kopii zapasowej."""
        if await self._do_restore(ctx.author.id):
            await ctx.reply("🔄 **Profil został przywrócony!** Statystyki wróciły do stanu sprzed testów.")
        else:
            await ctx.reply("❌ Błąd: Brak zapisanej kopii lub nie odnaleziono Coga `LevelingCog`.")


async def setup(bot: commands.Bot):
    await bot.add_cog(DevToolsCog(bot))