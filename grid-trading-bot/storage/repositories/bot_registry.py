"""Repository for Execution Bot Registry and Dispatch Delivery Receipts."""

from __future__ import annotations

import json
from typing import Any

from schemas.signal_dispatch import BotRegistration, DispatchReceipt
from storage.database import Database
from utils.helpers import now_iso
from utils.logger import get_logger

log = get_logger("database")


class BotRegistryRepository:
    """Manages downstream execution bot subscriptions and delivery audit receipts."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def register_bot(self, bot: BotRegistration) -> BotRegistration:
        """Saves or updates a downstream bot registration."""
        sql = """
        INSERT OR REPLACE INTO registered_bots (
            bot_id, name, target_broker, webhook_url, secret_key,
            subscribed_setups, min_confidence_score, is_active, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        setups_json = json.dumps(bot.subscribed_setups)
        params = (
            bot.bot_id,
            bot.name,
            bot.target_broker,
            bot.webhook_url,
            bot.secret_key,
            setups_json,
            bot.min_confidence_score,
            1 if bot.is_active else 0,
            bot.created_at or now_iso(),
        )
        async with self._db.connection.execute(sql, params):
            await self._db.connection.commit()
        log.info("Registered execution bot %s (%s)", bot.name, bot.bot_id)
        return bot

    async def get_bot(self, bot_id: str) -> BotRegistration | None:
        """Retrieves a single bot by ID."""
        sql = "SELECT * FROM registered_bots WHERE bot_id = ?"
        async with self._db.connection.execute(sql, (bot_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return self._row_to_bot(row)

    async def list_bots(self, active_only: bool = False) -> list[BotRegistration]:
        """Lists registered execution bots."""
        sql = "SELECT * FROM registered_bots"
        if active_only:
            sql += " WHERE is_active = 1"
        sql += " ORDER BY created_at DESC"

        async with self._db.connection.execute(sql) as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_bot(r) for r in rows]

    async def delete_bot(self, bot_id: str) -> bool:
        """Deletes a bot from the registry."""
        sql = "DELETE FROM registered_bots WHERE bot_id = ?"
        async with self._db.connection.execute(sql, (bot_id,)) as cursor:
            await self._db.connection.commit()
            return cursor.rowcount > 0

    async def save_receipt(self, receipt: DispatchReceipt) -> None:
        """Persists a signal dispatch delivery receipt."""
        sql = """
        INSERT INTO dispatch_receipts (
            dispatch_id, signal_id, bot_id, timestamp, status,
            response_code, latency_ms, error_message
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            receipt.dispatch_id,
            receipt.signal_id,
            receipt.bot_id,
            receipt.timestamp,
            receipt.status,
            receipt.response_code,
            receipt.latency_ms,
            receipt.error_message,
        )
        async with self._db.connection.execute(sql, params):
            await self._db.connection.commit()

    async def list_receipts(self, limit: int = 50) -> list[DispatchReceipt]:
        """Retrieves recent signal delivery receipts."""
        sql = "SELECT * FROM dispatch_receipts ORDER BY timestamp DESC LIMIT ?"
        async with self._db.connection.execute(sql, (limit,)) as cursor:
            rows = await cursor.fetchall()
            return [
                DispatchReceipt(
                    dispatch_id=r["dispatch_id"],
                    signal_id=r["signal_id"],
                    bot_id=r["bot_id"],
                    timestamp=r["timestamp"],
                    status=r["status"],
                    response_code=r["response_code"],
                    latency_ms=r["latency_ms"],
                    error_message=r["error_message"],
                )
                for r in rows
            ]

    def _row_to_bot(self, r: Any) -> BotRegistration:
        try:
            setups = json.loads(r["subscribed_setups"])
        except Exception:
            setups = ["ALL"]
        return BotRegistration(
            bot_id=r["bot_id"],
            name=r["name"],
            target_broker=r["target_broker"],
            webhook_url=r["webhook_url"],
            secret_key=r["secret_key"],
            subscribed_setups=setups,
            min_confidence_score=r["min_confidence_score"],
            is_active=bool(r["is_active"]),
            created_at=r["created_at"],
        )
