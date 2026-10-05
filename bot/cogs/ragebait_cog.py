import os
import random
import re
import discord
from discord.ext import commands
from bot.config import COMMAND_PREFIX

class RagebaitCog(commands.Cog, name="Ragebait"):
    """Zaawansowany moduł do prowokowania, trollowania i tworzenia ragebaitu na serwerze."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
        # --- KONFIGURACJA PODSTAWOWA ---
        # Domyślna szansa w % (1% oznacza teraz faktycznie rzadkie reakcje)
        self.chance_percent: int = 1
        self.enabled: bool = True
        self.total_baits_sent: int = 0

        # --- LISTA SŁÓW AGRESYWNYCH / WULGARYZMÓW (Dla odpowiedzi na wiadomości bota) ---
        self.rage_keywords: list[str] = [
            "kurwo", "kurwa", "chuj", "pierdol", "debil", "jebaj", 
            "spierdalaj", "zamknij", "suka", "pizda", "cwel", "pysk", "morda", "japa",
        ]

        # --- ODPOWIEDZI TEKSTOWE NA WULGARYZMY (Modern 2026 Vibe) ---
        self.tilt_responses: list[str] = [
            "aura -1000000 za tę reakcję 💀",
            "bro jest całkowicie cooked XDD",
            "0/10 ragebait z Twojej strony, spróbuj mocniej",
            "bro się zagotował o piksele na ekranie 😭",
            "least aggressive discord user moment 📉",
            "idź na dwór dotknąć trawy, bo emocje wzięły górę 🌿",
            "bro naprawdę myślał, że to zadziała 🤡",
            "npc dialogue option #4, bro się zagotował",
            ]
        self.image_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "assets",
            "malpa_lew.png",
        )

        # --- LOSOWE ODPOWIEDZI (Modern / Nonchalant / Brainrot 2026) ---
        self.random_responses: list[str] = [
            "who let bro cook 💀",
            "npc dialogue option #4",
            "bro thought he cooked 😭",
            "real (nikt nie pytał)",
            "aura check: failed 📉",
            "bro pisze to ze łzami w oczach",
            "zero aura moment",
            "ok unc, wracaj do lekcji 🤓",
            "aint no way bro napisał to na poważnie 💀",
            "low quality bait, spróbuj ponownie",
            
        ]

        # --- SŁOWA KLUCZOWE I DEDYKOWANE ODPOWIEDZI ---
        self.keyword_triggers: dict[str, list[str]] = {
            "ez": [
                "EZ? Bro wygrał tutorial i się cieszy 💀",
                "ez to było w 2020, zaktualizuj system",
            ],
            "skill issue": [
                "twój cały kontent to skill issue",
                "skill issue w realu, nie w grze 📉",
            ],
            "bot": [
                "przynajmniej moje AI nie ma laga w mózgu 🤖",
                "npc talking to bot, classic",
            ],
        }

        self.annoying_emojis: list[str] = ["🤡", "🤓", "💀", "🫵", "📉", "🥱", "😤", "🤬", ]

    def _to_mock_case(self, text: str) -> str:
        """Przekształca tekst na mOcK tEkSt (Spongebob style)."""
        return "".join(
            char.upper() if idx % 2 == 0 else char.lower()
            for idx, char in enumerate(text)
        )

    # --- ZDARZENIE OBSŁUGUJĄCE WIADOMOŚCI ---

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignorujemy boty, wiadomości prywatne, wyłączony module i komendy
        if message.author.bot or not message.guild or not self.enabled:
            return

        if message.content.startswith(COMMAND_PREFIX):
            return

        content_lower = message.content.lower()

        # --- SEKCJA A: SPRAWDZANIE ODPOWIEDZI (REPLY) DO BOTA Z WULGARYZMEM ---
        if message.reference and message.reference.message_id:
            try:
                referenced_msg = await message.channel.fetch_message(message.reference.message_id)
                
                # Upewniamy się, że wiadomość była odpowiedzią do naszego bota
                if self.bot.user and referenced_msg.author.id == self.bot.user.id:
                    contains_rage = any(word in content_lower for word in self.rage_keywords)
                    
                    # Szansa na reakcję przy wyzwisku:
                    rage_chance = 95

                    if contains_rage and random.randint(1, 100) <= rage_chance:
                        self.total_baits_sent += 1
                        
                        choice = random.choice(["image", "mock", "text"])

                        if choice == "image" and os.path.exists(self.image_path):
                            discord_file = discord.File(self.image_path, filename="malpa_lew.png")
                            await message.reply(content="ale się zagotował XDD", file=discord_file, mention_author=True)
                        
                        elif choice == "mock":
                            mocked = self._to_mock_case(message.content)
                            await message.reply(f'"{mocked}" 🤓', mention_author=True)
                            
                        else:
                            reply_text = random.choice(self.tilt_responses)
                            await message.reply(reply_text, mention_author=True)
                        
                        return

            except discord.HTTPException:
                pass

       # --- SEKCJA B: SŁOWA KLUCZOWE (Regex + IGNORECASE) ---
        for keyword, responses in self.keyword_triggers.items():
            # \b wymusza całe słowo. re.escape zabezpiecza przed znakami specjalnymi.
            pattern = rf"\b{re.escape(keyword)}\b"
            
            # Search ignorujący wielkość liter
            if re.search(pattern, message.content, re.IGNORECASE):
                
                # 🛠️ UNCOMMENT DO TESTÓW: Odkomentuj poniższą linię, żeby widzieć w terminalu czy Regex wyłapuje słowo!
                # print(f"🔍 [DEBUG] Regex wykrył słowo: '{keyword}' w wiadomości z treścią: '{message.content}'")

                # Losowanie szansy na odpowiedź (1%)
                if random.randint(1, 100) <= self.chance_percent:
                    selected_reply = random.choice(responses)
                    await message.reply(selected_reply, mention_author=True)
                    self.total_baits_sent += 1
                    return
        # --- SEKCJA C: LOSOWA AKCJA (Gdy brak słów kluczowych) ---
        roll = random.randint(1, 100)
        if roll <= self.chance_percent:
            self.total_baits_sent += 1
            action_type = random.choice(["text", "reaction", "mock", "ratio"])

            try:
                if action_type == "text":
                    response_text = random.choice(self.random_responses)
                    await message.reply(response_text, mention_author=True)

                elif action_type == "reaction":
                    emoji = random.choice(self.annoying_emojis)
                    await message.add_reaction(emoji)

                elif action_type == "mock" and len(message.content) > 3:
                    mocked_text = self._to_mock_case(message.content)
                    await message.reply(f'"{mocked_text}" 🤓', mention_author=False)

                elif action_type == "ratio":
                    await message.reply("L + Ratio + 💀", mention_author=False)

            except discord.HTTPException as e:
                print(f"❌ Błąd wysyłania ragebaitu: {e}")

    # --- KOMENDY ---

   

    @commands.command(name="rb")
    async def ratio_user(self, ctx: commands.Context, member: discord.Member):
        """Nasyła bota na wskazanego użytkownika, żeby go zragebaitować."""
        if member.bot:
            await ctx.send("Nie możesz dać rb innemu botowi, ziutek.")
            return

        ratio_phrases = [
            f"{member.mention} bro weź się ogarnij, bo to co robisz to cringe 💀",
            f"{member.mention} bro naprawdę myślał, że ugra tym cokolwiek 💀",
            f"dajcie mi spokój z tym, nie będę się kłócił z {member.mention} bo to strata czasu ",
            f"Serio? {member.mention} zastanów się nad swoim życiem",
            f"{member.mention} bro naprawdę myślał, że jest jakiś super XDD",
        ]
        await ctx.send(random.choice(ratio_phrases))
        self.total_baits_sent += 1

    @commands.command(name="ragebait_chance")
    @commands.has_permissions(administrator=True)
    async def set_chance(self, ctx: commands.Context, szansa: int):
        """Ustawia procentową szansę na automatyczny ragebait (0-100%)."""
        if 0 <= szansa <= 100:
            self.chance_percent = szansa
            await ctx.send(f"⚙️ Ustawiono nową szansę na ragebait: **{szansa}%**")
        else:
            await ctx.send("❌ Szansa musi mieścić się w przedziale od 0 do 100!")

    @commands.command(name="ragebait_toggle")
    @commands.has_permissions(administrator=True)
    async def toggle_ragebait(self, ctx: commands.Context):
        """Włącza lub całkowicie wyłącza moduł Ragebait na serwerze."""
        self.enabled = not self.enabled
        status = "włączony" if self.enabled else "wyłączony"
        await ctx.send(f"⚙️ Ragebait jest teraz **{status}**.")


async def setup(bot: commands.Bot):
    await bot.add_cog(RagebaitCog(bot))