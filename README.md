# Discord Bot — Portfolio Code Samples

A public, sanitized portfolio snapshot of a long-running private Discord bot project.

The production bot is private because it contains real community data and server-specific configuration. This repository keeps the **main application skeleton, Cogs, services, persistence layer, UI component and tests** that demonstrate how the project is structured.

> This is a portfolio codebase, not a drop-in production bot. Discord identifiers, credentials and production-specific values have been removed or replaced with placeholders.

## Architecture

```
main.py
  └── MyBot / setup_hook
        ├── Cogs (Discord event & command layer)
        │     ├── leveling
        │     ├── bump
        │     ├── suggestions
        │     ├── welcome
        │     ├── moderation / anti-scam
        │     ├── counting
        │     ├── LFG/activity
        │     ├── appeals / modals
        │     ├── audit logging
        │     └── developer tools
        │
        ├── Services
        │     ├── XPService
        │     ├── PlayerRepository
        │     ├── level curves
        │     └── voice activity tracking
        │
        └── UI
              └── paginated leaderboard
```

The important design boundary is that Discord-facing code lives mainly in Cogs, while progression and persistence logic is handled by services/repositories.

## What this demonstrates

- Python and object-oriented design
- `discord.py` Cogs and extension loading
- Async programming with `asyncio`
- Discord event listeners and commands
- Slash-command registration
- Global command error handling
- Logging and graceful error reporting
- Background tasks and task cancellation
- SQLite persistence and transactions
- JSON → SQLite migration
- Atomic state changes with SQLite transactions
- Per-user `asyncio.Lock` protection for concurrent updates
- Separate Text and Voice XP progression
- Level curves and Prestige progression
- Daily rewards and idempotent reward claims
- XP event history and retention
- Discord UI Views and interaction authorization
- Automated tests for progression, persistence and migration edge cases

## Project structure

### Application entry point

- `main.py` — bot initialization, intents, dynamic Cog loading, slash-command synchronization, presence, global command error handling and application lifecycle.
- `bot/config.py` — configuration and balancing constants. Secrets are read from environment variables.

### Cogs

- `bot/cogs/leveling_cog.py` — XP/levels, Text & Voice progression, Prestige, daily rewards, cooldowns, autosave and related commands.
- `bot/cogs/bump_cog.py` — reacts to successful DISBOARD bumps, awards XP and manages an asynchronous reminder.
- `bot/cogs/welcome_cog.py` — member join/leave handling with cache/API channel fallback.
- `bot/cogs/general_cog.py` — general commands and dynamic help generation.
- `bot/cogs/devTools_cog.py` — developer/admin diagnostics and controlled debugging tools.
- `bot/cogs/counting_cog.py` — persistent counting-game logic and milestone handling.
- `bot/cogs/suggestions_cog.py` — suggestion workflow and asynchronous processing.
- `bot/cogs/activity_lfg_cog.py` — activity/LFG workflow and background processing.
- `bot/cogs/appeal_modal_cog.py` — Discord modal-based appeal workflow.
- `bot/cogs/audit_log_cog.py` — server audit/event logging.
- `bot/cogs/anti_scam_cog.py` — invite/scam-link detection.
- `bot/cogs/ragebait_cog.py` — lightweight community interaction feature.

### Services

- `bot/services/xp_service.py` — progression business logic, XP calculations, Prestige and concurrency boundaries.
- `bot/services/player_repository.py` — SQLite schema, persistence, migration, XP history and atomic operations.
- `bot/services/level_curve.py` — XP curve generation, validation and Prestige scaling.
- `bot/services/voice_tracker.py` — asynchronous voice activity tracking based on monotonic timing.

### UI

- `bot/ui/leaderboard_view.py` — paginated Discord UI with interaction ownership checks and timeout handling.

### Tests

The repository contains tests covering level curves, XP service behaviour, daily rewards and SQLite persistence/migration.

## Production → portfolio transformation

The original project contains server-specific identifiers, real user/community data and production credentials. Those are deliberately not included here.

The code was adapted for public presentation by:

- removing real Discord IDs
- removing credentials
- keeping configuration environment-based
- excluding the production `Lib/site-packages` directory
- retaining the architectural relationships between Cogs, services, persistence and UI
- keeping representative production tests

The examples should therefore be read as **sanitized portfolio code**, not as a byte-for-byte copy of the deployed bot.

## Security

Never commit a Discord bot token or other credentials. GitHub recommends using secret scanning and push protection to prevent credentials from reaching a repository. citeturn1search0turn1search4
