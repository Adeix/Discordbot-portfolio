from collections import defaultdict
import json
import os
import time
import discord
from discord.ext import commands, tasks
import math

DB_FILE = "activity_db.json"


# --- 1. OBSŁUGA BAZY DANYCH (JSON) ---

def load_db_data() -> dict:
    """Wczytuje konfigurację z pliku JSON z obsługą trybu opt-out."""
    if not os.path.exists(DB_FILE):
        return {"opted_out": [], "target_channel_id": None, "live_message_id": None, "threshold": 0}
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {
                "opted_out": data.get("opted_out", []),
                "target_channel_id": data.get("target_channel_id"),
                "live_message_id": data.get("live_message_id"),
                "threshold": data.get("threshold", 0)
            }
    except Exception:
        return {"opted_out": [], "target_channel_id": None, "live_message_id": None, "threshold": 0}

def save_db_data(data: dict):
    """Zapisuje słownik konfiguracji do pliku JSON."""
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


# --- 2. INTERFEJS INTERAKTYWNY (UI VIEWS) ---

class LfgCloseView(discord.ui.View):
    """Widok ogłoszenia LFG z przyciskiem ręcznego usunięcia."""

    def __init__(self, cog, author_id: int, timeout: float = 3600.0): # Timeout awaryjny 1h
        super().__init__(timeout=timeout)
        self.cog = cog
        self.author_id = author_id

    @discord.ui.button(label="❌ Usuń ogłoszenie", style=discord.ButtonStyle.danger, custom_id="lfg_close_btn")
    async def close_lfg(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 1. Sprawdzamy czy użytkownik jest autorem ogłoszenia
        is_author = interaction.user.id == self.author_id

        # 2. Bezpiecznie sprawdzamy czy użytkownik jest członkiem serwera i ma uprawnienia moderatora
        is_admin = (
            isinstance(interaction.user, discord.Member) 
            and interaction.user.guild_permissions.manage_messages
        )

        if is_author or is_admin:
            # Czyszczenie z pamięci aktywnych LFG
            self.cog.active_lfgs.pop(self.author_id, None)
            
            # 3. Bezpieczne usunięcie wiadomości (upewniamy się, że nie jest None)
            if interaction.message:
                await interaction.message.delete()
        else:
            await interaction.response.send_message(
                "❌ Tylko autor tego ogłoszenia może je zamknąć!", 
                ephemeral=True
            )

    async def on_timeout(self):
        """Jeśli upłynie awaryjny czas 1h, usuwamy wpis z rejestru."""
        self.cog.active_lfgs.pop(self.author_id, None)
class LfgGameSelect(discord.ui.Select):
    """Rozwijana lista gier, w które ktoś aktualnie gra na serwerze."""

    def __init__(self, active_games: dict[str, list[int]], cog):
        self.active_games = active_games
        self.cog = cog

        options = []
        for game_name, players in active_games.items():
            options.append(
                discord.SelectOption(
                    label=game_name[:100],
                    description=f"Gra w to obecnie {len(players)} os.",
                    emoji="🎮",
                    value=game_name
                )
            )

        if not options:
            options.append(
                discord.SelectOption(
                    label="Brak aktywnych gier",
                    description="Nikt na serwerze w tej chwili nie gra.",
                    value="none"
                )
            )

        super().__init__(
            placeholder="🚀 Wybierz grę, aby zwołać ekipę...",
            min_values=1,
            max_values=1,
            options=options[:25],
            custom_id="lfg_game_select"
        )

    async def callback(self, interaction: discord.Interaction):
        game = self.values[0]
        if game == "none":
            await interaction.response.send_message("Nikt obecnie w nic nie gra!", ephemeral=True)
            return

        user_id = interaction.user.id

        # Jeśli użytkownik miał już aktywne LFG, kasujemy poprzednią wiadomość
        if user_id in self.cog.active_lfgs:
            old_lfg = self.cog.active_lfgs.pop(user_id)
            try:
                old_chan = self.cog.bot.get_channel(old_lfg["channel_id"])
                if isinstance(old_chan, discord.TextChannel):
                    old_msg = await old_chan.fetch_message(old_lfg["message_id"])
                    await old_msg.delete()
            except discord.HTTPException:
                pass

        player_ids = self.active_games.get(game, [])
        pings = [f"<@{pid}>" for pid in player_ids if pid != user_id]
        pings_str = " ".join(pings) if pings else "Brak innych osób w grze."

        embed = discord.Embed(
            title=f"📣 Szukam ekipy do {game}!",
            description=f"Gracz {interaction.user.mention} szuka chętnych do wspólnej gry!",
            color=discord.Color.green()
        )
        embed.add_field(name="Osoby w tej grze", value=pings_str, inline=False)
        embed.set_footer(text="Ogłoszenie zamknie się automatycznie, gdy wyłączysz grę!")

        close_view = LfgCloseView(cog=self.cog, author_id=user_id)

        await interaction.response.send_message(
            content=f"🎮 {pings_str}" if pings else None,
            embed=embed,
            view=close_view
        )

        msg = await interaction.original_response()

        # Zapisujemy aktywne LFG w pamięci Coga
        self.cog.active_lfgs[user_id] = {
            "game": game,
            "channel_id": msg.channel.id,
            "message_id": msg.id
        }


class ActivityPanelControlView(discord.ui.View):
    """Główny panel aktywności z listą gier oraz przyciskiem widoczności."""

    def __init__(self, cog, active_games: dict[str, list[int]]):
        super().__init__(timeout=None)
        self.cog = cog
        self.add_item(LfgGameSelect(active_games, cog))

    @discord.ui.button(
        label="🙈 Ukryj / Pokaż moje gry",
        style=discord.ButtonStyle.secondary,
        custom_id="optout_toggle",
        row=1
    )
    async def toggle_optout(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id

        if user_id in self.cog.opted_out_users:
            self.cog.opted_out_users.remove(user_id)
            self.cog.save_config()
            await interaction.response.send_message(
                "✅ Włączono widoczność! Twoje gry będą ponownie pojawiać się w panelu.",
                ephemeral=True
            )
        else:
            self.cog.opted_out_users.add(user_id)
            self.cog.save_config()
            await interaction.response.send_message(
                "❌ Ukryto widoczność! Twoje gry nie będą już pokazywane w panelu.",
                ephemeral=True
            )


# --- 3. GŁÓWNY COG AKTYWNOŚCI ---

class ActivityLfgCog(commands.Cog, name="Aktywność 24/7"):
    """Moduł automatycznie odświeżający panel gier z aktywnym systemem LFG i Auto-Cleanupem."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        db_data = load_db_data()
        self.opted_out_users: set[int] = set(db_data["opted_out"])
        self.target_channel_id: int | None = db_data["target_channel_id"]
        self.live_message_id: int | None = db_data["live_message_id"]
        self.threshold: int = db_data.get("threshold", 0)

        # Słownik aktywnych LFG: { user_id: {"game": str, "channel_id": int, "message_id": int} }
        self.active_lfgs: dict[int, dict] = {}

        self.auto_update_loop.start()

    def save_config(self):
        """Zapisuje aktualny stan Coga do pliku JSON."""
        save_db_data({
            "opted_out": list(self.opted_out_users),
            "target_channel_id": self.target_channel_id,
            "live_message_id": self.live_message_id,
            "threshold": self.threshold
        })

    async def cog_unload(self) -> None:
        self.auto_update_loop.cancel()

    # --- LISTENER ZMIANY STATUSU (AUTO-REMOVE LFG PO ZAKOŃCZENIU GRY) ---

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        """Wykrywa moment, w którym gracz wyłącza grę i kasuje jego ogłoszenie LFG."""
        user_id = after.id

        # Sprawdzamy czy ten gracz ma w ogóle otwarte ogłoszenie LFG
        if user_id not in self.active_lfgs:
            return

        lfg_data = self.active_lfgs[user_id]
        target_game = lfg_data["game"]

        # Sprawdzamy, czy po zmianie statusu gracz WCIĄŻ gra w tę konkretną grę
        is_still_playing = any(
            act.type == discord.ActivityType.playing and act.name == target_game
            for act in after.activities
        )

        # Jeśli gracz wyłączył tę grę lub przestał w nią grać:
        if not is_still_playing:
            channel_id = lfg_data["channel_id"]
            message_id = lfg_data["message_id"]

            # Usuwamy wpis ze słownika
            self.active_lfgs.pop(user_id, None)

            # Kasujemy wiadomość ogłoszenia na kanale
            channel = self.bot.get_channel(channel_id)
            if isinstance(channel, discord.TextChannel):
                try:
                    msg = await channel.fetch_message(message_id)
                    await msg.delete()
                except discord.HTTPException:
                    pass

    # --- METODY POMOCNICZE ---

    def _format_duration(self, start_time) -> str:
        """Przelicza timestamp na czytelny format czasu."""
        if not start_time:
            return "nieznany czas"
        elapsed = int(time.time() - start_time.timestamp())
        if elapsed < 0:
            return "0m"
        minutes = elapsed // 60
        hours = minutes // 60
        remaining_minutes = minutes % 60
        if hours > 0:
            return f"{hours}h {remaining_minutes}m"
        return f"{minutes}m"

    def _calculate_dynamic_threshold(self, total_active_players: int) -> tuple[int, bool]:
        """
        Wylicza dynamiczny próg wyróżniania gier na podstawie liczby aktywnych graczy.
        
        Parametry:
            total_active_players (int): Łączna liczba unikalnych graczy w grach.
            
        Zwraca:
            tuple[int, bool]: (wyliczony_próg, czy_jest_dynamiczny)
        """
        # Jeśli threshold <= 0, używamy trybu dynamicznego
        if self.threshold <= 0:
            if total_active_players <= 3:
                calculated = 1
            elif total_active_players <= 8:
                calculated = 2
            else:
                # 25% ze wszystkich grających, zaokrąglane w górę (np. 9 graczy -> 3, 13 graczy -> 4)
                calculated = math.ceil(total_active_players * 0.25)

            return calculated, True

        # Jeśli administrator ustawił ręczny próg (np. !set_prog 3)
        return self.threshold, False
    async def _build_activity_embed_and_map(
        self, guild: discord.Guild
    ) -> tuple[discord.Embed, dict[str, list[int]]]:
        """Buduje Embed z grami oraz zwraca mapę graczy dla menu LFG."""
        games_map: dict[str, list[str]] = defaultdict(list)
        active_game_user_ids: dict[str, list[int]] = defaultdict(list)
        total_active_players = 0

        for member in guild.members:
            if member.bot or member.id in self.opted_out_users:
                continue

            processed_games_for_member = set()

            for activity in member.activities:
                if activity.type == discord.ActivityType.playing and activity.name:
                    game_name = activity.name

                    if game_name in processed_games_for_member:
                        continue
                    processed_games_for_member.add(game_name)

                    start_time = getattr(activity, "start", None)
                    time_str = self._format_duration(start_time)

                    entry = f"• <@{member.id}> w grze **{game_name}** od `{time_str}`"
                    games_map[game_name].append(entry)
                    active_game_user_ids[game_name].append(member.id)
                    total_active_players += 1

        active_threshold, is_dynamic = self._calculate_dynamic_threshold(total_active_players)

        threshold_info = (
            f"⚡ **Tryb Dynamiczny:** Próg wyliczony na **{active_threshold} graczy** "
            f"(20% z {total_active_players} aktywnych)."
            if is_dynamic else
            f"📌 **Tryb Statyczny:** Próg ustawiony na stałe: **{active_threshold} graczy**."
        )

        embed = discord.Embed(
            title="🎮 Na Żywo: Aktywności Graczy & LFG",
            description=f"{threshold_info}\nUżyj menu pod spodem, aby **zwołać ekipę do gry**!",
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow()
        )

        featured_count = 0
        other_players: list[str] = []
        sorted_games = sorted(games_map.items(), key=lambda item: len(item[1]), reverse=True)

        for game_name, players in sorted_games:
            if len(players) >= active_threshold:
                embed.add_field(
                    name=f"🔥 {game_name} ({len(players)} graczy)",
                    value="\n".join(players),
                    inline=False
                )
                featured_count += 1
            else:
                other_players.extend(players)

        if featured_count == 0:
            embed.add_field(
                name="📌 Wyróżnione Gry",
                value=f"*Brak gier spełniających próg min. {active_threshold} graczy*",
                inline=False
            )

        other_text = "\n".join(other_players) if other_players else "*Brak pozostałych gier*"
        embed.add_field(name="🕹️ Inne Aktywności", value=other_text, inline=False)
        embed.set_footer(text="Automatyczna aktualizacja co 3 minuty")

        return embed, active_game_user_ids

    # --- PĘTLA 24/7 ---

    @tasks.loop(minutes=3)
    async def auto_update_loop(self):
        """Automatyczne odświeżanie wiadomości na kanale."""
        if not self.target_channel_id or not self.live_message_id:
            return

        channel = self.bot.get_channel(self.target_channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        guild = channel.guild
        if guild is None:
            return

        try:
            msg = await channel.fetch_message(self.live_message_id)
            embed, active_game_user_ids = await self._build_activity_embed_and_map(guild)
            view = ActivityPanelControlView(self, active_game_user_ids)

            await msg.edit(embed=embed, view=view, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException as e:
            print(f"⚠️ Błąd podczas auto-aktualizacji panelu LFG: {e}")

    @auto_update_loop.before_loop
    async def before_loop(self):
        await self.bot.wait_until_ready()

    # --- KOMENDY ADMINISTRACYJNE ---

    @commands.command(name="setup_aktywnosc")
    @commands.has_permissions(administrator=True)
    async def setup_activity_panel(self, ctx: commands.Context, prog: int = 0):
        """[ADMIN] Inicjalizuje nowy panel aktywności na wskazanym kanale."""
        if ctx.guild is None:
            await ctx.send("❌ Ta komenda działa tylko na serwerze!")
            return

        self.threshold = prog
        embed, active_game_user_ids = await self._build_activity_embed_and_map(ctx.guild)
        view = ActivityPanelControlView(self, active_game_user_ids)

        msg = await ctx.send(embed=embed, view=view)

        self.target_channel_id = ctx.channel.id
        self.live_message_id = msg.id
        self.save_config()

        mode_str = "AUTO (Dynamiczny)" if prog <= 0 else f"SZTYWNY ({prog} graczy)"
        await ctx.send(f"⚙️ Panel aktywowany! Tryb progu: **{mode_str}**.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ActivityLfgCog(bot))