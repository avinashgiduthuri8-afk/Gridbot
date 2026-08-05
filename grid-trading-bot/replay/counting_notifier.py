"""A Notifier that never actually sends anything (no Telegram bot needed
for replay), but reuses every real Notifier method's message-formatting
logic and counts specific event types the report cares about."""
from __future__ import annotations

from collections import Counter

from notifications.notifier import Notifier


class CountingNotifier(Notifier):
    def __init__(self) -> None:  # deliberately skip Notifier.__init__: no Bot/chat_ids needed
        self._bot = None
        self._chat_ids = ()
        self._last_sync_error_notified = {}
        self.counts: Counter[str] = Counter()

    async def send(self, message: str) -> None:
        # No real Telegram call — replay must never spam a live chat.
        pass

    async def trailing_activated(self, *args, **kwargs) -> None:
        self.counts["trailing_activated"] += 1
        await super().trailing_activated(*args, **kwargs)

    async def stop_loss_triggered(self, *args, **kwargs) -> None:
        self.counts["stop_loss_triggered"] += 1
        await super().stop_loss_triggered(*args, **kwargs)

    async def dust_position_written_off(self, *args, **kwargs) -> None:
        self.counts["dust_position_written_off"] += 1
        await super().dust_position_written_off(*args, **kwargs)

    async def order_failed(self, *args, **kwargs) -> None:
        self.counts["order_failed"] += 1
        await super().order_failed(*args, **kwargs)
