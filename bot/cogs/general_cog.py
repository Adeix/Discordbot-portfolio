import discord
from discord.ext import commands
from bot.config import COMMAND_PREFIX

class GeneralCog(commands.Cog, name="Ogólne"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Usuwamy domyślną komendę help bota, aby nasza wersja działała bez konfliktów
        self.bot.remove_command("help")

    @commands.command(name="ping")
    async def ping(self, ctx: commands.Context):
        """Sprawdza opóźnienie bota i czy odpowiada."""
        latency = round(self.bot.latency * 1000)
        await ctx.send(f"🏓 Pong! Opóźnienie: **{latency}ms**")

    # Helper: sprawdza czy komenda jest przeznaczona tylko dla administratorów
    def _is_admin_command(self, cmd: commands.Command) -> bool:
        # Sprawdzamy czy w dekoratorach komendy znajduje się sprawdzanie uprawnień admina
        for check in cmd.checks:
            check_name = getattr(check, "__qualname__", "")
            if "has_permissions" in check_name or "is_owner" in check_name:
                return True
        return False

    # --- DYNAMICZNY HELP ---
    @commands.command(name="help", aliases=["pomoc"])
    async def help_command(self, ctx: commands.Context, command_name: str | None = None):
        """Dynamiczne menu pomocy, które automatycznie wykrywa komendy i ich opis."""
        
        # Sprawdzamy, czy osoba wywołująca komendę jest administratorem na serwerze
        jest_adminem = False
        if isinstance(ctx.author, discord.Member):
            jest_adminem = ctx.author.guild_permissions.administrator or (await self.bot.is_owner(ctx.author))

        # =========================================================================
        # 1. SZCZEGÓŁOWY HELP DLA POJEDYNCZEJ KOMENDY: e.g. !help level
        # =========================================================================
        if command_name:
            # Normalizacja nazwy — usuwamy ewentualny prefiks, jeśli użytkownik go wpisał
            normalized = command_name.lower()
            prefix_lower = COMMAND_PREFIX.lower()
            if normalized.startswith(prefix_lower):
                normalized = normalized[len(prefix_lower):]

            # Pobieramy obiekt komendy z bota
            cmd = self.bot.get_command(normalized)
            
            # Sprawdzamy warunki widoczności komendy
            is_admin_only = self._is_admin_command(cmd) if cmd else False
            
            if cmd is None or cmd.hidden or (is_admin_only and not jest_adminem):
                await ctx.send(f"❌ Nie znaleziono komendy `{command_name}`.")
                return

            # Budujemy opis szczegółowy komendy
            opis = cmd.help or "Brak opisu dla tej komendy."
            usagestr = f"{COMMAND_PREFIX}{cmd.name} {cmd.signature}".strip()
            
            embed = discord.Embed(
                title=f"ℹ️ Pomoc: {COMMAND_PREFIX}{cmd.name}",
                description=opis,
                color=discord.Color.blue()
            )
            embed.add_field(name="⚙️ Składnia użycia", value=f"`{usagestr}`", inline=False)
            
            if cmd.aliases:
                aliasy_str = ", ".join([f"`{a}`" for a in cmd.aliases])
                embed.add_field(name="🔀 Aliasy (Skróty)", value=aliasy_str, inline=False)

            if is_admin_only:
                embed.set_footer(text="🔒 Komenda wymagająca uprawnień administratora")

            await ctx.send(embed=embed)
            return

        # =========================================================================
        # 2. PEŁNE MENU POMOCY (LISTA WSZYSTKICH KOMEND)
        # =========================================================================
        embed = discord.Embed(
            title="📋 Dostępne komendy na serwerze", 
            description=f"Wpisz `{COMMAND_PREFIX}help [komenda]`, aby poznać szczegóły danej komendy.",
            color=discord.Color.blue()
        )

        zwykle_komendy = []
        admin_komendy = []

        # Przeglądamy wszystkie zarejestrowane komendy w bocie
        for cmd in self.bot.commands:
            # Ignorujemy ukryte komendy (hidden=True)
            if cmd.hidden:
                continue

            is_admin = self._is_admin_command(cmd)
            short_doc = cmd.help.split("\n")[0] if cmd.help else "Brak opisu."
            entry_text = f"🔹 **`{COMMAND_PREFIX}{cmd.name}`** — *{short_doc}*"

            if is_admin:
                if jest_adminem:
                    admin_komendy.append(f"🔸 **`{COMMAND_PREFIX}{cmd.name}`** — *{short_doc}*")
            else:
                zwykle_komendy.append(entry_text)

        # Dodajemy sekcję ogólnych komend
        if zwykle_komendy:
            embed.add_field(
                name="👥 Komendy dla każdego",
                value="\n".join(zwykle_komendy),
                inline=False
            )

        # Dodajemy sekcję administracyjną (widoczną tylko dla adminów)
        if admin_komendy and jest_adminem:
            embed.add_field(
                name="──────────────",
                value="🛠️ **Komendy Administracyjne**\n" + "\n".join(admin_komendy),
                inline=False
            )

        embed.set_footer(text=f"Wywołano przez: {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(GeneralCog(bot))