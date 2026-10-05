import os

# Główny prefiks bota
COMMAND_PREFIX = "$"

# --- BALANS POZIOMOW ---
MAX_LEVEL = 130
MAX_LEVEL_PER_PRESTIGE = 50
PRESTIGE_LEVEL_STEP = 20
PRESTIGE_XP_MULTIPLIER = 0.25
VOICE_XP_MULTIPLIER = 1.5
TEXT_XP_EXCLUDED_CATEGORY_IDS: tuple[int, ...] = ()
VOICE_XP_EXCLUDED_CHANNEL_IDS: tuple[int, ...] = ()
VOICE_XP_EXCLUDED_CATEGORY_IDS: tuple[int, ...] = ()
TEXT_XP_COOLDOWN_SECONDS = 60
TEXT_XP_MIN_AMOUNT = 15
TEXT_XP_MAX_AMOUNT = 25
DAILY_REWARD_XP = 100
DAILY_REWARD_RESET_HOUR = 7
VOICE_XP_PER_TICK = 30
VOICE_XP_TICK_SECONDS = 5 * 60
XP_EVENT_RETENTION_DAYS = 30
TEXT_LEVEL_ROLES: dict[int, int] = {}
VOICE_LEVEL_ROLES: dict[int, int] = {}

# --- SEKRETNY TOKEN BOTA ---
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# --- ID KANAŁÓW DISCORDA (Ustawione pod Twoje dane) ---

# Nowy dedykowany kanał na powiadomienia o wbiciu poziomu!
LEVEL_UP_CHANNEL_ID = 0 
# Kanał z powitaniami (powitania)
WELCOME_CHANNEL_ID = 0
GENERAL_CHANNEL_ID = 0
# Kanał, na którym wpisuje się komendę /bump (bump)
DISBOARD_CHANNEL_ID = 0
# Kanał do gry w liczenie; ustaw tutaj ID kanału.
COUNTING_CHANNEL_ID = 0
COUNTING_LOG_CHANNEL_ID = 0
COUNTING_MILESTONE_VALUES = (
    100,
    250,
    500,
    1_000,
    2_500,
    5_000,
    10_000,
    25_000,
    50_000,
    100_000,
    250_000,
    500_000,
    1_000_000,
    2_500_000,
    5_000_000,
    10_000_000,
    25_000_000,
    50_000_000,
    100_000_000,
    250_000_000,
    500_000_000,
    1_000_000_000,
    2_500_000_000,
    5_000_000_000,
    10_000_000_000,
    25_000_000_000,
    50_000_000_000,
    100_000_000_000,
    250_000_000_000,
    500_000_000_000,
    1_000_000_000_000,
    2_500_000_000_000,
    5_000_000_000_000,
    10_000_000_000_000,
    25_000_000_000_000,
    50_000_000_000_000,
    100_000_000_000_000,
    250_000_000_000_000,
    500_000_000_000_000,
    1_000_000_000_000_000,
    2_500_000_000_000_000,
    5_000_000_000_000_000,
    10_000_000_000_000_000,
    25_000_000_000_000_000,
    50_000_000_000_000_000,
    100_000_000_000_000_000,
    250_000_000_000_000_000,
    500_000_000_000_000_000,
    1_000_000_000_000_000_000,
    2_500_000_000_000_000_000,
    5_000_000_000_000_000_000,
    2**63 - 1,
)


def counting_milestone_reward(milestone: int) -> int:
    """Skaluje nagrody logarytmicznie i ogranicza je do 500 XP."""
    return min(500, 50 + (max(0, len(str(milestone)) - 3) * 25))


COUNTING_MILESTONES = {
    milestone: counting_milestone_reward(milestone)
    for milestone in COUNTING_MILESTONE_VALUES
}

# Kanał na propozycje użytkowników (propozycje)
SUGGESTIONS_CHANNEL_ID = 0
ADMIN_SUGGESTIONS_CHANNEL_ID = 0

# --- ID RÓL ---
# Rola użytkowników z boostem serwera (boost role id)
BOOSTER_ROLE_ID = 0
# Rola do oznaczania przy przypomnieniu o bumpie (bump role id)
BUMP_ROLE_ID = 0
# Rola Suggestii (suggestions role id)
VOTE_ROLE_ID = 0
# --- CZAS PRZYPOMNIENIA O BUMP (2 godziny) ---
BUMP_REMINDER_DELAY_SECONDS = 7200
BUMP_BASE_XP = 200
BUMP_REWARD_TIERS = (
    (1, 200),
    (26, 190),
    (51, 180),
    (101, 170),
    (201, 160),
    (401, 150),
)
BUMP_NEW_MEMBER_DAYS = 14
BUMP_NEW_MEMBER_MAX_LEVEL = 15
BUMP_NEW_MEMBER_MULTIPLIER = 2
BUMP_MAX_XP = 1000

# Słowniki ról Prestige (Prestige -> ID roli Discorda).
TEXT_PRESTIGE_ROLES = {
    1: 0,  # Prestiż I
    2: 0,  # Prestiż II
    3: 0,  # Prestiż III
    4: 0,  # Prestiż IV
    5: 0,  # Prestiż V
}
VOICE_PRESTIGE_ROLES: dict[int, int] = {}