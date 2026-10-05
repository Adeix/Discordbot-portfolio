import time
import random
import math
import asyncio
import logging
import sqlite3
from datetime import datetime
import discord
from discord.ext import commands, tasks
from pathlib import Path
from typing import cast, Any

# Importujemy potrzebne rzeczy z configu
from bot.config import (
    BOOSTER_ROLE_ID,
    COUNTING_CHANNEL_ID,
    DAILY_REWARD_XP,
    GENERAL_CHANNEL_ID,
    LEVEL_UP_CHANNEL_ID,
    TEXT_PRESTIGE_ROLES,
    VOICE_PRESTIGE_ROLES,
    TEXT_XP_EXCLUDED_CATEGORY_IDS,
    TEXT_XP_COOLDOWN_SECONDS,
    TEXT_XP_MAX_AMOUNT,
    TEXT_XP_MIN_AMOUNT,
    VOICE_XP_PER_TICK,
)
from bot.services.xp_service import XPService
from bot.services.voice_tracker import VoiceTracker
from bot.services.level_curve import max_level_for_prestige
from bot.ui.leaderboard_view import LeaderboardView

BASE_DIR = Path(__file__).resolve().parent.parent.parent
COMMAND_PREFIX = "$" 
logger = logging.getLogger(__name__)

# ==========================================
# GŁÓWNY COG POZIOMÓW
# ==========================================
class LevelingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.xp_service = XPService(
            database_path=BASE_DIR / "data" / "players.sqlite3",
            curve_path=BASE_DIR / "poziomy.json",
        )
        self.player_repository = self.xp_service.repository
        self.dane_graczy = self.xp_service.profiles
        self.profile_locks = self.xp_service.profile_locks
        self.cooldowns = {}
        self.voice_tracker = VoiceTracker(self.bot, self._award_voice_xp)
        self.wymaga_zapisu = False
        self.poziomy_cache = self.xp_service.curve
        self.voice_poziomy_cache = self.xp_service.voice_curve

    async def cog_load(self):
        self.voice_tracker.start()
        self.autosave_bazy.start()

    async def cog_unload(self):
        self.voice_tracker.cancel()
        self.autosave_bazy.cancel()
        self.xp_service.close()

    def wczytaj_baze(self):
        return self.xp_service.profiles

    def wczytaj_poziomy(self):
        return self.xp_service.curve

    def zapisz_baze(self):
        self.xp_service.save()

    @tasks.loop(minutes=2.0)
    async def autosave_bazy(self):
        """[OPTYMALIZACJA ZAPISU]: Zapisuje bazę na dysk co 2 minuty i to tylko wtedy, gdy flaga wymaga_zapisu jest aktywna."""
        if self.wymaga_zapisu:
            self.zapisz_baze()
            self.wymaga_zapisu = False
            print("[Autosave] Zmiany zostały pomyślnie zrzucone na dysk.")
        self.xp_service.prune_events()

    def get_profil(self, user_id: int) -> dict:
        return self.xp_service.get_profile(user_id)

    def daj_prog_xp(self, poziom, prestige=0, source="text"):
        return self.xp_service.required_xp(poziom, prestige, source)

    def przelicz_poziom(
        self, profil: dict[str, Any], source: str | None = None
    ) -> None:
        self.xp_service.recalculate_levels(profil, source)

    async def dodaj_bump(self, user_id: int) -> int:
        return await self.xp_service.add_bump(user_id)

    @staticmethod
    def daily_reward_date(now: datetime | None = None) -> str:
        return XPService.daily_reward_date(now)

    async def przyznaj_daily_reward(self, message: discord.Message) -> bool:
        user_id = message.author.id
        lock = self.profile_locks.setdefault(user_id, asyncio.Lock())
        async with lock:
            profile_id = str(user_id)
            current_profile = self.get_profil(user_id)
            candidate_profile = current_profile.copy()
            text_amount, voice_amount = self.xp_service.split_bonus_xp(
                candidate_profile, DAILY_REWARD_XP
            )
            reward_date = self.daily_reward_date()

            for attempt in range(3):
                try:
                    claimed = self.player_repository.claim_daily_reward(
                        user_id,
                        reward_date,
                        message.id,
                        candidate_profile,
                        DAILY_REWARD_XP,
                        reason=(
                            f"pierwsza wiadomość dnia: {reward_date}; "
                            f"Text +{text_amount}, Voice +{voice_amount}"
                        ),
                    )
                    break
                except sqlite3.Error:
                    if attempt == 2:
                        logger.exception(
                            "Daily Reward DB claim failed after retries for user %s on %s",
                            user_id,
                            reward_date,
                        )
                        return False
                    await asyncio.sleep(0.25 * (2**attempt))

            if not claimed:
                return False
            self.dane_graczy[profile_id] = candidate_profile

        try:
            await message.channel.send(
                f"🌅 {message.author.mention} otrzymuje **+{DAILY_REWARD_XP} bonus XP** za pierwszą wiadomość dnia!"
            )
        except discord.HTTPException:
            logger.exception(
                "Daily Reward was granted but its announcement failed in #chat "
                "for user %s on %s",
                user_id,
                reward_date,
            )
        return True

    def oblicz_nagrode_bump(
        self, member: discord.Member, bump_number: int | None = None
    ) -> int:
        return self.xp_service.bump_reward(member, bump_number)

    async def dodaj_xp(
        self,
        user_id,
        ilosc,
        wiadomosc=None,
        guild=None,
        apply_booster=True,
        source="text",
        reason="aktywność",
    ):
        if source not in {"text", "voice", "bonus"}:
            raise ValueError(f"Nieznane źródło XP: {source}")

        aktualny_serwer = guild
        if wiadomosc and wiadomosc.guild:
            aktualny_serwer = wiadomosc.guild

        # Booster check
        ma_boostera = False
        if aktualny_serwer:
            czloneczek = aktualny_serwer.get_member(user_id)
            if czloneczek and any(rola.id == BOOSTER_ROLE_ID for rola in czloneczek.roles):
                ma_boostera = True

        if ma_boostera and apply_booster:
            ilosc = int(ilosc * 1.25)

        amount = max(0, int(ilosc))

        lock = self.profile_locks.setdefault(int(user_id), asyncio.Lock())
        async with lock:
            profil = self.get_profil(user_id)
            levels_before = {
                progression: profil[f"{progression}_level"]
                for progression in ("text", "voice")
            }
            ready_before = {
                progression: profil[f"{progression}_prestige_ready"]
                for progression in ("text", "voice")
            }
            if source == "bonus":
                text_amount, voice_amount = self.xp_service.split_bonus_xp(
                    profil, amount
                )
                event_reason = (
                    f"{reason}; Text +{text_amount}, Voice +{voice_amount}"
                )
            else:
                profil[f"{source}_xp"] += amount
                self.przelicz_poziom(profil, source)
                event_reason = reason
            self.player_repository.record_xp_event(
                user_id, source, amount, event_reason
            )
            if any(profil[f"{key}_prestige_ready"] for key in ("text", "voice")):
                self.player_repository.save_profiles(self.dane_graczy)
            self.wymaga_zapisu = True

        levels_gained = {
            progression: profil[f"{progression}_level"] > levels_before[progression]
            for progression in levels_before
        }
        if any(levels_gained.values()):
            self.wymaga_zapisu = True
            
            kanal_ogloszen = None
            if aktualny_serwer:
                kanal_ogloszen = self.bot.get_channel(LEVEL_UP_CHANNEL_ID)
            if kanal_ogloszen is None and wiadomosc:
                kanal_ogloszen = wiadomosc.channel

            if kanal_ogloszen:
                wzmianka_user = wiadomosc.author.mention if wiadomosc else f"<@{user_id}>"
                for progression, label in (("text", "Text"), ("voice", "Voice")):
                    if levels_gained[progression]:
                        await kanal_ogloszen.send(
                            f"🎉 Awans! {wzmianka_user}: **{label} Level "
                            f"{levels_before[progression]} → "
                            f"{profil[f'{progression}_level']}**!"
                        )

                    if (
                        profil[f"{progression}_prestige_ready"]
                        and not ready_before[progression]
                    ):
                        cap = max_level_for_prestige(
                            profil[f"{progression}_prestige"]
                        )
                        embed_prestige_info = discord.Embed(
                            title="👑 OSIĄGNIĘTO MAKSYMALNY POZIOM! 👑",
                            description=(
                                f"Gratulacje {wzmianka_user}! Osiągnąłeś "
                                f"**{label} Level {cap}**!\n\n"
                                "Odblokowałeś możliwość zwiększenia poziomu "
                                f"**{label} Prestige**!\n"
                                f"Wpisz `{COMMAND_PREFIX}prestige {progression}`."
                            ),
                            color=discord.Color.purple(),
                        )
                        await kanal_ogloszen.send(embed=embed_prestige_info)

    async def nagroda_specjalna(
        self, user_id, ilosc_xp, powod, kanal_tekstowy, apply_booster=True
    ):
        class FakeMessage:
            def __init__(self, ch, auth):
                self.channel = ch
                self.author = auth
                self.guild = ch.guild if ch else None

        czloneczek = kanal_tekstowy.guild.get_member(user_id)
        wzmianka = czloneczek.mention if czloneczek else f"<@{user_id}>"
        fake_msg = FakeMessage(kanal_tekstowy, czloneczek) if czloneczek else None
        
        await self.dodaj_xp(
            user_id,
            ilosc_xp,
            wiadomosc=fake_msg,
            guild=kanal_tekstowy.guild,
            apply_booster=apply_booster,
            source="bonus",
            reason=powod,
        )
        await kanal_tekstowy.send(f"🚀 {wzmianka} otrzymuje **+{ilosc_xp} XP** za: **{powod}**!")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if (
            message.guild is not None
            and message.channel.id == GENERAL_CHANNEL_ID
            and not message.author.bot
            and message.webhook_id is None
            and message.type in (discord.MessageType.default, discord.MessageType.reply)
            and not message.content.startswith(COMMAND_PREFIX)
        ):
            if await self.przyznaj_daily_reward(message):
                return

        if (
            message.guild is None
            or message.author.bot
            or message.webhook_id is not None
            or message.channel.id == COUNTING_CHANNEL_ID
            or getattr(message.channel, "category_id", None) in TEXT_XP_EXCLUDED_CATEGORY_IDS
            or message.content.startswith(COMMAND_PREFIX)
            or message.content.startswith("http://")
            or message.content.startswith("https://")
        ):
            return

        user_id = message.author.id
        teraz = time.time()

        if user_id in self.cooldowns and teraz - self.cooldowns[user_id] < TEXT_XP_COOLDOWN_SECONDS:
            return

        self.cooldowns[user_id] = teraz
        punkty = random.randint(TEXT_XP_MIN_AMOUNT, TEXT_XP_MAX_AMOUNT)
        await self.dodaj_xp(
            user_id,
            punkty,
            wiadomosc=message,
            source="text",
            reason="wiadomość tekstowa",
        )

    async def _award_voice_xp(self, member: discord.Member) -> None:
        await self.dodaj_xp(
            member.id,
            VOICE_XP_PER_TICK,
            guild=member.guild,
            source="voice",
            reason="aktywność voice",
        )

    @commands.command(name="level")
    async def pokaz_level(self, ctx: commands.Context, member: discord.Member | None = None):
        """Wyświetla poziom, XP, prestiż i liczbę bumpów danego użytkownika."""
        cel = member or ctx.author
        uid = str(cel.id)

        if uid not in self.dane_graczy:
            await ctx.send(f"{cel.display_name} nie ma jeszcze żadnych punktów.")
            return

        profil = self.get_profil(cel.id)

        bumpy = profil.get("bumps", 0)
        bumpy_txt = f" | 🚀 Bumpy: **{bumpy}**" if bumpy > 0 else ""
        text_next = self.daj_prog_xp(
            profil["text_level"] + 1,
            prestige=profil["text_prestige"],
            source="text",
        )
        voice_next = self.daj_prog_xp(
            profil["voice_level"] + 1,
            prestige=profil["voice_prestige"],
            source="voice",
        )
        await ctx.send(
            f"👤 **{cel.display_name}**{bumpy_txt}\n"
            f"💬 **Text** — P{profil['text_prestige']} • Level "
            f"{profil['text_level']}\n"
            f"XP: {profil['text_xp']}/{text_next or 'MAX'}\n"
            f"🔊 **Voice** — P{profil['voice_prestige']} • Level "
            f"{profil['voice_level']}\n"
            f"XP: {profil['voice_xp']}/{voice_next or 'MAX'}"
        )

    @commands.command(name="prestige")
    async def wykonaj_prestiz(
        self, ctx: commands.Context, path: str | None = None
    ):
        """Zwiększa Prestige wyłącznie wskazanej ścieżki XP."""
        if ctx.guild is None:
            return
        if path is None or path.lower() not in {"text", "voice"}:
            await ctx.send("ℹ️ Poprawna składnia: `$prestige text` lub `$prestige voice`.")
            return

        source = path.lower()
        author = cast(discord.Member, ctx.author)
        if str(author.id) not in self.dane_graczy:
            await ctx.send("🛑 Nie posiadasz jeszcze profilu w bazie danych!")
            return
        profile = self.get_profil(author.id)
        prestige_key = f"{source}_prestige"
        ready_key = f"{source}_prestige_ready"
        current_prestige = profile[prestige_key]
        if current_prestige >= 5:
            await ctx.send(
                f"⚔️ Osiągnąłeś już maksymalny (V) Prestige ścieżki **{source.title()}**!"
            )
            return

        cap = max_level_for_prestige(current_prestige)
        if not profile[ready_key]:
            await ctx.send(
                f"🛑 Musisz osiągnąć **{cap} poziom {source.title()}**, "
                "aby zdobyć kolejny Prestige!"
            )
            return

        updated_profile = await self.xp_service.perform_prestige(author.id, source)
        if updated_profile is None:
            await ctx.send("🛑 Ta ścieżka nie jest już gotowa na Prestige.")
            return

        new_prestige = updated_profile[prestige_key]
        roles = TEXT_PRESTIGE_ROLES if source == "text" else VOICE_PRESTIGE_ROLES
        old_role_id = roles.get(current_prestige)
        if old_role_id:
            old_role = ctx.guild.get_role(old_role_id)
            if old_role and old_role in author.roles:
                try:
                    await author.remove_roles(
                        old_role, reason=f"Awans na wyższy {source} Prestige"
                    )
                except discord.Forbidden:
                    logger.warning("Brak uprawnień do usunięcia roli %s", old_role.name)

        role_text = ""
        new_role_id = roles.get(new_prestige)
        if new_role_id:
            new_role = ctx.guild.get_role(new_role_id)
            if new_role:
                try:
                    await author.add_roles(
                        new_role, reason=f"Osiągnięcie {source} Prestige {new_prestige}"
                    )
                    role_text = f"\n🎖️ Otrzymujesz rangę: {new_role.mention}!"
                except discord.Forbidden:
                    role_text = "\n⚠️ Bot nie mógł nadać Ci roli Prestige."

        embed = discord.Embed(
            title="👑 NOWY PRESTIŻ ODKRYTY! 👑",
            description=(
                f"Użytkownik {author.mention} wkroczył na **{source.title()} "
                f"Prestige {new_prestige}** i zachował nadmiar XP!{role_text}"
            ),
            color=discord.Color.gold(),
        )
        await ctx.send(embed=embed)

    @commands.command(name="test_bump")
    @commands.has_permissions(administrator=True)
    async def testuj_bumpa(self, ctx: commands.Context, uzytkownik: discord.Member):
        """Testowa komenda do przyznawania bumpów i XP za podbicie serwera."""
        bump_number = await self.dodaj_bump(uzytkownik.id)
        nagroda_xp = self.oblicz_nagrode_bump(uzytkownik, bump_number)
        profil = self.get_profil(uzytkownik.id)
        levels_before = (profil["text_level"], profil["voice_level"])
        await self.dodaj_xp(
            uzytkownik.id,
            nagroda_xp,
            guild=ctx.guild,
            source="bonus",
            reason="test bump",
            apply_booster=False,
        )
        updated_profile = self.get_profil(uzytkownik.id)

        await ctx.send(f"🚀 {uzytkownik.mention} otrzymuje **+{nagroda_xp} XP** za: **Podbicie serwera (Disboard)**!")
        for source, level_before in zip(("text", "voice"), levels_before):
            level_after = updated_profile[f"{source}_level"]
            if level_after > level_before:
                await ctx.send(
                    f"🎉 Awans! {uzytkownik.mention}: **{source.title()} Level "
                    f"{level_before} → {level_after}**!"
                )

    @commands.command(name="level_sync")
    @commands.has_permissions(administrator=True)
    async def synchronizuj_baze(self, ctx: commands.Context):
        """Synchronizuje bazę danych z aktualnymi członkami serwera."""
        if ctx.guild is None:
            return

        id_czlonkow_serwera = [str(member.id) for member in ctx.guild.members if not member.bot]
        dodani = 0

        for uid in id_czlonkow_serwera:
            if uid not in self.dane_graczy:
                user_id = int(uid)
                lock = self.profile_locks.setdefault(user_id, asyncio.Lock())
                async with lock:
                    if uid not in self.dane_graczy:
                        self.get_profil(user_id)
                        dodani += 1

        self.zapisz_baze()
        self.wymaga_zapisu = False

        await ctx.send(
            f"🔄 **Synchronizacja bazy zakończona!**\n"
            f"📥 Dodani nowi członkowie: **{dodani}**\n"
            f"🛡️ Istniejące profile i XP zostały zachowane.\n"
            f"📊 Wielkość bazy: **{len(self.dane_graczy)} profili**"
        )

    @synchronizuj_baze.error
    async def sync_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("🛑 Ta komenda jest dostępna tylko dla Administratora serwera.")

    @commands.command(name="award_xp")
    @commands.has_permissions(administrator=True)
    async def przyznaj_xp_admin(self, ctx: commands.Context, uzytkownik: discord.Member, ilosc: int):
        """Komenda administracyjna do przyznawania XP innym użytkownikom."""
        if ilosc <= 0:
            await ctx.send("🛑 Ilość przyznawanego XP musi być większa od zera!")
            return

        current_profile = self.dane_graczy.get(str(uzytkownik.id), {})
        levels_before = (
            current_profile.get("text_level", 0),
            current_profile.get("voice_level", 0),
        )
        await self.dodaj_xp(
            uzytkownik.id,
            ilosc,
            guild=ctx.guild,
            source="bonus",
            reason="przyznanie administracyjne",
            apply_booster=False,
        )
        updated_profile = self.get_profil(uzytkownik.id)

        await ctx.send(f"🚀 {uzytkownik.mention} otrzymuje **+{ilosc} XP** od Administratora ({ctx.author.display_name})!")
        for source, level_before in zip(("text", "voice"), levels_before):
            level_after = updated_profile[f"{source}_level"]
            if level_after > level_before:
                await ctx.send(
                    f"🎉 Awans! {uzytkownik.mention}: **{source.title()} Level "
                    f"{level_before} → {level_after}**!"
                )

    @przyznaj_xp_admin.error
    async def award_xp_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("🛑 Ta komenda jest dostępna tylko dla osób z uprawnieniami Administratora.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("ℹ️ Poprawne użycie komendy: `$award_xp @użytkownik [ilość_xp]`")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("🛑 Podano nieprawidłowe dane! Upewnij się, że poprawnie oznaczyłeś użytkownika, a ilość XP to liczba całkowita.")

    @commands.command(name="lb", aliases=["leaderboard", "top"])
    async def wyswietl_leaderboard(
        self, ctx: commands.Context, tryb: str = "text"
    ):
        """Wyświetla ranking text albo voice."""
        if ctx.guild is None:
            return

        mode_keys = {
            "text": ("text_level", "text_xp", "text_prestige", "TEXT"),
            "voice": ("voice_level", "voice_xp", "voice_prestige", "VOICE"),
        }
        if tryb.lower() not in mode_keys:
            await ctx.send("ℹ️ Wybierz ranking: `$lb text` albo `$lb voice`.")
            return
        level_key, xp_key, prestige_key, mode_label = mode_keys[tryb.lower()]

        autor = cast(discord.Member, ctx.author)
        uid_str = str(autor.id)

        if not self.dane_graczy:
            await ctx.send("📊 Baza danych graczy jest obecnie pusta!")
            return

        posortowani = sorted(
            self.dane_graczy.items(),
            key=lambda x: (
                x[1].get(prestige_key, 0),
                x[1].get(level_key, 0),
                x[1].get(xp_key, 0)
            ),
            reverse=True
        )

        pozycja_autora = -1
        dane_autora = None
        for i, (u_id, dane) in enumerate(posortowani):
            if u_id == uid_str:
                pozycja_autora = i + 1
                dane_autora = dane
                break

        if pozycja_autora != -1 and dane_autora:
            p_txt = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V"}
            akt_p = dane_autora.get(prestige_key, 0)
            lvl = dane_autora.get(level_key, 0)
            xp = dane_autora.get(xp_key, 0)
            bumpy_autora = dane_autora.get("bumps", 0)
            
            stopka_autora = (
                f"👤 **Twoja pozycja:** #{pozycja_autora} | "
                f"Prestiż {p_txt.get(akt_p, str(akt_p))} | "
                f"{mode_label} poziom {lvl} | XP {xp} | "
                f"🚀 Bumpy: {bumpy_autora}"
            )
        else:
            stopka_autora = "👤 **Twoja pozycja:** Brak danych (napisz coś na czacie!)"

        graczy_na_strone = 10
        liczba_stron = math.ceil(len(posortowani) / graczy_na_strone)
        strony_tekstowe = []

        for numer_strony in range(liczba_stron):
            start = numer_strony * graczy_na_strone
            koniec = start + graczy_na_strone
            kawalek_listy = posortowani[start:koniec]

            linijki = []
            for index, (u_id, dane) in enumerate(kawalek_listy, start=start + 1):
                gracz = ctx.guild.get_member(int(u_id))
                nazwa = gracz.display_name if gracz else f"Nieznany gracz ({u_id})"
                
                pres = dane.get(prestige_key, 0)
                lvl = dane.get(level_key, 0)
                xp = dane.get(xp_key, 0)
                bumpy = dane.get("bumps", 0)
                p_tag = f" [P{pres}]" if pres > 0 else ""

                prefix = f"#{index}"
                if index == 1: prefix = "🥇"
                elif index == 2: prefix = "🥈"
                elif index == 3: prefix = "🥉"

                linijki.append(
                    f"{prefix} | **{nazwa}**{p_tag} — Lvl: **{lvl}** | XP: **{xp}** | 🚀 **{bumpy}**"
                )
            
            strony_tekstowe.append("\n".join(linijki))

        embed_startowy = discord.Embed(
            title=f"🏆 RANKING {mode_label} SERWERA 🏆",
            description=strony_tekstowe[0],
            color=discord.Color.gold()
        )
        if ctx.guild.icon:
            embed_startowy.set_thumbnail(url=ctx.guild.icon.url)
            
        embed_startowy.add_field(name="──────────────", value=stopka_autora, inline=False)
        embed_startowy.set_footer(text=f"Strona 1 z {liczba_stron}")

        if liczba_stron > 1:
            widok = LeaderboardView(
                author_id=autor.id,
                pages=strony_tekstowe,
                author_footer=stopka_autora,
            )
            message = await ctx.send(embed=embed_startowy, view=widok)
            widok.message = message
        else:
            await ctx.send(embed=embed_startowy)


async def setup(bot: commands.Bot):
    await bot.add_cog(LevelingCog(bot))
