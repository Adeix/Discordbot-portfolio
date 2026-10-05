# Architecture

The production bot grew from a small JSON-based leveling script into a layered system.

```
Discord event / command
        |
        v
   LevelingCog
        |
        v
    XPService
   /        \
  v          v
Level curve  PlayerRepository
                 |
                 v
              SQLite
```

## Discord layer

The Cog handles Discord-specific concerns:

- message and voice events
- commands such as `$level` and `$prestige`
- cooldowns and event filtering
- announcements
- lifecycle of background tasks

## Service layer

`XPService` contains rules that should not depend on Discord:

- XP and level calculation
- separate text/voice progression
- Prestige thresholds and retained XP
- daily reward date calculation
- per-user locking for state-changing operations

## Repository layer

`PlayerRepository` owns SQLite operations:

- schema creation
- legacy JSON migration
- profile persistence
- XP event history
- idempotent daily reward claims
- atomic Prestige updates

## Why the split matters

A Discord event should not need to know how XP is stored. Likewise, the XP rules should be testable without connecting a Discord bot.

This separation also made the JSON -> SQLite migration possible without rewriting the Discord-facing commands from scratch.

## Concurrency

XP updates and Prestige are state-changing operations. The service uses an `asyncio.Lock` per user, while critical SQLite operations use transactions.

The goal is to prevent two simultaneous events from reading the same profile state and overwriting each other's changes.

## Portfolio scope

This repository contains cleaned and adapted examples from the private project. Production IDs, credentials, databases and server-specific configuration are intentionally excluded.