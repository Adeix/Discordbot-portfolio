import discord
from discord.ext import commands, tasks
import json
import os
import asyncio
from datetime import datetime, timedelta, time, timezone
from typing import Any, cast

# Importujemy wszystkie potrzebne zmienne konfiguracyjne
from bot.config import SUGGESTIONS_CHANNEL_ID, VOTE_ROLE_ID, ADMIN_SUGGESTIONS_CHANNEL_ID

# Ścieżka do pliku, w którym bot zapamięta aktywne propozycje na 7 dni
DB_PATH = "propozycje_aktywne.json"

class SuggestionsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.baza_propozycji = {}
        self.wczytaj_baze_propozycji()
        # Uruchomienie pętli zadań w tle (wykonuje się codziennie o 17:00)
        self.sprawdz_propozycje_loop.start()

    def wczytaj_baze_propozycji(self):
        """Wczytuje bazę danych propozycji z pliku JSON."""
        if os.path.exists(DB_PATH):
            try:
                with open(DB_PATH, "r", encoding="utf-8") as f:
                    self.baza_propozycji = json.load(f)
            except Exception as e:
                print(f"⚠️ Błąd wczytywania bazy propozycji: {e}")
                self.baza_propozycji = {}
        else:
            self.baza_propozycji = {}

    def zapisz_baze_propozycji(self):
        """Zapisuje aktualny stan propozycji do pliku JSON."""
        try:
            with open(DB_PATH, "w", encoding="utf-8") as f:
                json.dump(self.baza_propozycji, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"❌ Nie udało się zapisać bazy propozycji: {e}")

    async def cog_unload(self):
        """Zatrzymuje pętlę zadań w tle, jeśli Cog zostanie przeładowany."""
        self.sprawdz_propozycje_loop.cancel()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Podstawowe filtry bezpieczeństwa
        if SUGGESTIONS_CHANNEL_ID == 0 or message.guild is None or message.author.bot:
            return

        # Sprawdzamy, czy to kanał z propozycjami
        if message.channel.id != SUGGESTIONS_CHANNEL_ID:
            return

        # Ignorujemy wiadomości zaczynające się od prefiksu bota
        prefixes = await self.bot.get_prefix(message)
        if any(message.content.startswith(p) for p in prefixes):
            return

        # Pobieramy treść propozycji
        suggestion_text = message.content.strip() or "(Brak treści - tylko załącznik)"

        # Tworzymy elegancki Embed
        embed = discord.Embed(
            title="💡 Nowa propozycja!",
            description=suggestion_text,
            color=discord.Color.gold()
        )
        embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
        embed.add_field(name="📊 Głosowanie", value="Zostaw swoją opinię: 👍 lub 👎", inline=False)
        embed.set_footer(text=f"Identyfikator autora: {message.author.id}")

        # Jeśli użytkownik dodał zdjęcia/pliki, wrzucamy pierwsze z nich jako podgląd
        if message.attachments:
            embed.set_image(url=message.attachments[0].url)

        # 1. Usuwamy oryginalną wiadomość użytkownika
        try:
            await message.delete()
        except discord.Forbidden:
            print("⚠️ Brak uprawnień do usuwania wiadomości na kanale sugestii!")

        wzmianka_roli = f"<@&{VOTE_ROLE_ID}>" if VOTE_ROLE_ID != 0 else ""

        # 2. Bot wysyła wersję w Embedzie
        panel_message = await message.channel.send(content=wzmianka_roli, embed=embed)
        
        # 3. Bot dodaje reakcje do głosowania
        await panel_message.add_reaction("👍")
        await panel_message.add_reaction("👎")

        # 4. Bot otwiera wątek do dyskusji
        thread_id = None
        try:
            nazwa_watku = f"💬 Dyskusja: {message.author.display_name}"
            thread = await panel_message.create_thread(
                name=nazwa_watku,
                auto_archive_duration=1440
            )
            thread_id = thread.id
        except discord.HTTPException as e:
            print(f"❌ Nie udało się otworzyć wątku dla propozycji: {e}")

        # Zapisujemy propozycję do bazy (używamy nowoczesnego timezone.utc)
        self.baza_propozycji[str(panel_message.id)] = {
            "author_id": message.author.id,
            "author_name": message.author.display_name,
            "content": suggestion_text,
            "attachment_url": message.attachments[0].url if message.attachments else None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "thread_id": thread_id
        }
        self.zapisz_baze_propozycji()

    # Pętla wykonująca się codziennie o godzinie 17:00 czasu lokalnego
    @tasks.loop(time=time(hour=17, minute=0))
    async def sprawdz_propozycje_loop(self):
        """Przegląda aktywne propozycje i weryfikuje ich wiek oraz wyniki głosowania."""
        kanal_sugestii = self.bot.get_channel(SUGGESTIONS_CHANNEL_ID)
        kanal_admin = self.bot.get_channel(ADMIN_SUGGESTIONS_CHANNEL_ID)
        
        if not isinstance(kanal_sugestii, discord.TextChannel):
            print("❌ Główny kanał propozycji nie jest kanałem tekstowym lub nie istnieje!")
            return

        teraz = datetime.now(timezone.utc)
        do_usuniecia = [] 

        for msg_id_str, dane in list(self.baza_propozycji.items()):
            try:
                # Parsujemy datę z uwzględnieniem UTC strefowego
                data_stworzenia = datetime.fromisoformat(dane["created_at"])
                if data_stworzenia.tzinfo is None:
                    data_stworzenia = data_stworzenia.replace(tzinfo=timezone.utc)

                # Sprawdzamy, czy minęło pełne 7 dni
                if teraz - data_stworzenia < timedelta(days=7):
                    continue

                msg_id = int(msg_id_str)
                try:
                    message = await kanal_sugestii.fetch_message(msg_id)
                except discord.NotFound:
                    do_usuniecia.append(msg_id_str)
                    continue

                # Unikamy rate limitów przy sprawdzaniu wielu wiadomości
                await asyncio.sleep(0.5)

                glosy_za = 0
                glosy_przeciw = 0

                for reaction in message.reactions:
                    if str(reaction.emoji) == "👍":
                        glosy_za = reaction.count - 1  # Odejmujemy startowy głos bota
                    elif str(reaction.emoji) == "👎":
                        glosy_przeciw = reaction.count - 1

                suma_glosow = glosy_za + glosy_przeciw
                procent_za = (glosy_za / suma_glosow) if suma_glosow > 0 else 0

                orig_embed = message.embeds[0] if message.embeds else None
                
                if procent_za >= 0.65:
                    # ZAAKCEPTOWANE
                    if orig_embed:
                        nowy_embed = orig_embed.copy()
                        nowy_embed.color = discord.Color.green()
                        
                        status_val = f"✅ **Zaakceptowane przez społeczność** ({glosy_za} 👍 do {glosy_przeciw} 👎)"
                        # Bezpieczne ustawianie/dodawanie pola statusu
                        if len(nowy_embed.fields) > 0:
                            nowy_embed.set_field_at(0, name="📊 Status", value=status_val, inline=False)
                        else:
                            nowy_embed.add_field(name="📊 Status", value=status_val, inline=False)
                            
                        await message.edit(embed=nowy_embed)

                    # Przesłanie zaakceptowanej propozycji na kanał administracji
                    if isinstance(kanal_admin, discord.TextChannel):
                        admin_embed = discord.Embed(
                            title="📥 Zaakceptowana propozycja społeczności!",
                            description=dane["content"],
                            color=discord.Color.green()
                        )
                        admin_embed.set_author(name=dane["author_name"])
                        admin_embed.add_field(
                            name="📈 Wynik głosowania", 
                            value=f"Zgłoszenie uzyskało **{procent_za * 100:.1f}%** poparcia.\n👍 Za: {glosy_za}\n👎 Przeciw: {glosy_przeciw}", 
                            inline=False
                        )
                        admin_embed.set_footer(text=f"ID Autora: {dane['author_id']}")
                        if dane["attachment_url"]:
                            admin_embed.set_image(url=dane["attachment_url"])
                        
                        await kanal_admin.send(embed=admin_embed)
                else:
                    # ODRZUCONE
                    if orig_embed:
                        nowy_embed = orig_embed.copy()
                        nowy_embed.color = discord.Color.red()
                        
                        status_val = f"❌ **Odrzucone przez społeczność** ({glosy_za} 👍 do {glosy_przeciw} 👎)"
                        if len(nowy_embed.fields) > 0:
                            nowy_embed.set_field_at(0, name="📊 Status", value=status_val, inline=False)
                        else:
                            nowy_embed.add_field(name="📊 Status", value=status_val, inline=False)
                            
                        await message.edit(embed=nowy_embed)

                # Bezpieczne pobieranie i zamykanie wątku (nawet po restarcie bota)
                if dane.get("thread_id"):
                    thread_id = int(dane["thread_id"])
                    watek = kanal_sugestii.get_thread(thread_id)
                    
                    if not watek:
                        try:
                            # Próbujemy pobrać wątek z API, jeśli nie ma go w pamięci bota
                            watek = await kanal_sugestii.guild.fetch_channel(thread_id)
                        except discord.HTTPException:
                            watek = None

                    if isinstance(watek, discord.Thread):
                        try:
                            await watek.edit(archived=True, locked=True)
                        except discord.HTTPException as e:
                            print(f"⚠️ Nie udało się zarchiwizować wątku {thread_id}: {e}")

                do_usuniecia.append(msg_id_str)

            except Exception as e:
                print(f"❌ Błąd podczas przetwarzania propozycji {msg_id_str}: {e}")

        # Czyszczenie bazy z rozliczonych propozycji
        if do_usuniecia:
            for id_do_skasowania in do_usuniecia:
                if id_do_skasowania in self.baza_propozycji:
                    del self.baza_propozycji[id_do_skasowania]
            self.zapisz_baze_propozycji()

    @sprawdz_propozycje_loop.before_loop
    async def before_sprawdz_propozycje(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(SuggestionsCog(bot))