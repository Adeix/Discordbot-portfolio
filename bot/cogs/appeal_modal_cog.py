import discord
from discord import app_commands
from discord.ext import commands

# --- 1. FORMULARZ APELACYJNY (MODAL) ---

class OfficialAppealModal(discord.ui.Modal, title="Formularz Apelacji od Kary"):
    """Formularz otwierany po wpisaniu komendy /apeluj."""

    user_nick = discord.ui.TextInput(
        label="Twój Nick / ID na Discordzie lub w grze",
        placeholder="np. adrian",
        required=True,
        max_length=50
    )

    penalty_info = discord.ui.TextInput(
        label="Rodzaj kary (Ban / Kick / Timeout)",
        placeholder="np. Ban za brak kultury",
        required=True,
        max_length=100
    )

    appeal_reason = discord.ui.TextInput(
        label="Dlaczego wnosisz o zdjęcie kary?",
        style=discord.TextStyle.paragraph,
        placeholder="Wyjaśnij sytuację...",
        required=True,
        min_length=10,
        max_length=1000
    )

    def __init__(self, appeal_channel_id: int):
        super().__init__()
        self.appeal_channel_id = appeal_channel_id

    async def on_submit(self, interaction: discord.Interaction):
        appeal_channel = interaction.client.get_channel(self.appeal_channel_id)

        if not isinstance(appeal_channel, discord.TextChannel):
            await interaction.response.send_message(
                "❌ Błąd: Kanał do odbioru apelacji nie został odnaleziony na serwerze.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="📩 Nowa Apelacja od Kary",
            color=discord.Color.red(),
            timestamp=interaction.created_at
        )
        embed.set_author(
            name=f"{interaction.user.name} ({interaction.user.id})",
            icon_url=interaction.user.display_avatar.url
        )
        embed.add_field(name="Nick / ID", value=self.user_nick.value, inline=True)
        embed.add_field(name="Rodzaj Kary", value=self.penalty_info.value, inline=True)
        embed.add_field(name="Treść Apelacji", value=self.appeal_reason.value, inline=False)

        await appeal_channel.send(embed=embed)
        await interaction.response.send_message(
            "✅ Twoja apelacja została pomyślnie przekazana do administracji!",
            ephemeral=True
        )


# --- 2. PRZYCISK Z LINKIEM INSTALL ---

class InstallAppView(discord.ui.View):
    """Przycisk z linkiem OAuth2 do instalacji User App w profilu."""

    def __init__(self, bot_client_id: int):
        super().__init__(timeout=None)
        
        install_url = (
            f"https://discord.com/oauth2/authorize?"
            f"client_id={bot_client_id}&"
            f"integration_type=1&"
            f"scope=applications.commands"
        )
        
        self.add_item(discord.ui.Button(
            label="Zainstaluj Aplikację Apelacji",
            style=discord.ButtonStyle.link,
            url=install_url,
            emoji="📲"
        ))


# --- 3. COG AUTOMATYCZNYCH APELACJI ---

class AutoUserAppAppealCog(commands.Cog, name="Automatyczne Apelacje User App"):
    """Łączy powiadomienia z Audit Loga z komendą /apeluj."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # ⚠️ PODMIEŃ NA ID KANAŁU DLA ADMINÓW
        self.appeal_channel_id: int = 0 
        # ⚠️ PODMIEŃ NA CLIENT ID TWOJEGO BOTA
        self.bot_client_id: int = 0     

    @app_commands.command(name="apeluj", description="Złóż oficjalną apelację od kary na serwerze.")
    async def appeal_command(self, interaction: discord.Interaction):
        """Oficjalna komenda Slash."""
        modal = OfficialAppealModal(appeal_channel_id=self.appeal_channel_id)
        await interaction.response.send_modal(modal)

    @commands.Cog.listener()
    async def on_audit_log_entry_create(self, entry: discord.AuditLogEntry):
        """Wyłapywanie zdarzeń nakładania kar z Audit Loga."""
        print(f"🔍 [AuditLog Event] Wykryto nową akcję: {entry.action}")

        # Ignorujemy wpisy stworzone przez bota
        if self.bot.user and entry.user_id == self.bot.user.id:
            return

        action_type = None
        if entry.action == discord.AuditLogAction.ban:
            action_type = "🚫 Zostałeś zbanowany"
        elif entry.action == discord.AuditLogAction.kick:
            action_type = "⚠️ Zostałeś wyrzucony (Kick)"
        elif entry.action == discord.AuditLogAction.member_update and hasattr(entry.changes.after, "timed_out_until"):
            if entry.changes.after.timed_out_until is not None:
                action_type = "⏳ Otrzymałeś przerwę (Timeout)"

        if action_type and isinstance(entry.target, (discord.User, discord.Member)):
            await self._send_auto_install_dm(
                user=entry.target,
                action_type=action_type,
                reason=entry.reason or "Brak powodu",
                guild=entry.guild
            )

    async def _send_auto_install_dm(self, user: discord.User | discord.Member, action_type: str, reason: str, guild: discord.Guild):
        """Wysyła wiadomość PV z instrukcją i przyciskiem."""
        embed = discord.Embed(
            title=f"{action_type} na serwerze {guild.name}",
            description=(
                f"**Powód:** {reason}\n\n"
                f"**Chcesz złożyć apelację?**\n"
                f"1. Kliknij przycisk **'Zainstaluj Aplikację Apelacji'** poniżej.\n"
                f"2. Dodaj bota do profilu.\n"
                f"3. Wpisz `/apeluj` na czacie prywatnym z botem!"
            ),
            color=discord.Color.dark_red()
        )
        view = InstallAppView(bot_client_id=self.bot_client_id)

        try:
            await user.send(embed=embed, view=view)
            print(f"✅ [AuditLog] Wysłąno PV do {user.name} ({user.id})")
        except discord.Forbidden:
            print(f"⚠️ [AuditLog] Nie można wysłać DM do {user.name} - wyłączone PV lub brak wspólnych serwerów.")
        except Exception as e:
            print(f"❌ [AuditLog] Błąd podczas wysyłania DM: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoUserAppAppealCog(bot))