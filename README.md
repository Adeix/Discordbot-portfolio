# Discord Bot — Portfolio Code Samples

Selected, cleaned code samples from a private, long-running Discord bot project.

This repository is a **portfolio of implementation examples**, not a standalone production bot. Production-specific configuration, credentials, Discord identifiers and user data have been removed or replaced with generic values.

## What this demonstrates

- Python application architecture with Discord adapter, service and repository layers
- Async programming with `asyncio` and Discord event handlers
- SQLite persistence, transactions and atomic state changes
- Migration from a legacy JSON data format
- Separate text and voice XP progression
- Level curves, Prestige progression and retained XP
- Per-user concurrency protection
- Time-zone aware daily rewards
- XP event history and retention
- Tests for progression, persistence and migration edge cases

## Selected code

- `src/discord_leveling_cog.py` — Discord-facing events, commands, cooldowns, background autosave and integration with the service layer
- `src/level_curve.py` — XP curve generation, validation and Prestige scaling
- `src/xp_service.py` — XP/level/Prestige business logic and concurrency boundaries
- `src/player_repository.py` — SQLite schema, persistence, migration and atomic operations
- `src/voice_tracker.py` — asynchronous voice activity tracking
- `tests/test_level_curve.py` — representative tests for progression logic
- `docs/architecture.md` — explanation of the production architecture and separation of responsibilities

## Project evolution

The original bot started as a simpler JSON-based leveling system. I extended it into a SQLite-backed system with:

- independent Text and Voice progression
- Prestige I–V with path-specific thresholds
- retained XP when performing Prestige
- daily rewards tied to the first valid message of the day
- XP event history
- background autosave and event retention
- per-user locks and database transactions for state-changing operations
- migration and normalization of legacy profile data

## Why this is a portfolio repository

The production bot is private because it contains real community data and server-specific configuration. This repository intentionally keeps the implementation patterns that demonstrate how the system was designed without exposing production data or secrets.

> The examples are cleaned/adapted for portfolio use; they should not be treated as a byte-for-byte copy of the private production repository.