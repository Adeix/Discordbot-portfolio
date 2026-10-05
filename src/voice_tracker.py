from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

VOICE_XP_TICK_SECONDS = 5 * 60


class VoiceTracker:
    """Tracks eligible voice activity and awards XP after a full interval."""

    def __init__(
        self,
        on_eligible_member: Callable[[object], Awaitable[None]],
    ):
        self.on_eligible_member = on_eligible_member
        self.presence_started: dict[int, float] = {}

    async def process_tick(self, eligible_members: list[object]) -> None:
        now = time.monotonic()
        eligible_ids = {member.id for member in eligible_members}

        for user_id in list(self.presence_started):
            if user_id not in eligible_ids:
                del self.presence_started[user_id]

        for member in eligible_members:
            started_at = self.presence_started.setdefault(member.id, now)

            if now - started_at < VOICE_XP_TICK_SECONDS:
                continue

            self.presence_started[member.id] = now
            await self.on_eligible_member(member)
