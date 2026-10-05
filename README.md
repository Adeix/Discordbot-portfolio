# Discord Bot — Portfolio Code Samples

Selected code samples from a private, long-running Discord bot project.

This repository is a **portfolio of implementation examples**, not a standalone runnable application. Production-specific configuration, credentials, Discord identifiers and user data have been removed or replaced with generic values.

## What this demonstrates

- Python application architecture with service/repository separation
- Async programming with `asyncio`
- SQLite persistence and transactions
- Migration from a legacy JSON data format
- Separate text and voice XP progression
- Level curves and Prestige progression
- Concurrency protection for state-changing operations
- Time-zone aware daily rewards
- Tests for persistence, migrations and concurrency edge cases

## Selected code

- `src/level_curve.py` — XP curve generation, validation and Prestige scaling
- `src/xp_service.py` — XP/level/Prestige business logic
- `src/player_repository.py` — SQLite persistence, migration and atomic operations
- `src/voice_tracker.py` — asynchronous voice activity tracking
- `tests/test_level_curve.py` — representative tests for progression logic

## Project context

The original bot is a private project used by a Discord community. It evolved from a simpler JSON-based leveling system into a SQLite-backed system with separate progression paths, Prestige, XP event history, daily rewards and concurrency handling.

> Production-specific configuration and identifiers have intentionally been removed.
