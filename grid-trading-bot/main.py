"""Application entrypoint for the Manual DCA Grid Trading Bot.

Wires together configuration, database, exchange client, the DCA trading
engine, the order monitor, the price monitor, recovery, and the Telegram
bot — then runs forever.

Run with: python main.py
"""

from __future__ import annotations

import asyncio
import signal
from typing import TYPE_CHECKING

from telegram import Bot

from bot_telegram.bot import BotAppContext, build_application
from bot_telegram.formatters import format_daily_summary
from config.settings import ConfigError, load_settings
from exchange.coindcx import CoinDCXClient
from exchange.paper_exchange import PaperExchangeClient
from trading.mixed_order_manager import MixedOrderManager
from notifications.notifier import Notifier
from risk.risk_manager import RiskManager
from storage.database import Database
from storage.repositories import Repositories
from trading.alert_manager import AlertManager
from trading.dca_manager import DCAManager
from trading.order_manager import OrderManager
from trading.order_monitor import OrderMonitor
from trading.price_monitor import PriceMonitor
from trading.recovery import RecoveryManager
from utils.helpers import now_iso
from utils.logger import get_logger, setup_logging

if TYPE_CHECKING:
    # Only imported for type checking — the real import is lazy and
    # opt-in inside async_main(), so google-auth is not a hard dependency
    # for anyone who doesn't enable Drive backup.
    from storage.drive_backup import DriveBackupManager

log = get_logger("trading")


async def run_alert_check_loop(
    alert_manager: AlertManager,
    exchange: CoinDCXClient,
    notifier: Notifier,
    interval: int,
) -> None:
    """Poll live prices for symbols with active price alerts."""
    while True:
        await asyncio.sleep(interval)
        try:
            symbols = alert_manager.symbols_with_alerts()
            for symbol in symbols:
                try:
                    ticker = await exchange.get_ticker(symbol)
                    fired = await alert_manager.fire_and_persist(symbol, ticker.last_price)
                    for alert in fired:
                        direction_word = "reached" if alert.direction == "above" else "dropped to"
                        await notifier.send(
                            f"🔔 <b>Price Alert — {symbol}</b>\n"
                            f"Target ₹{alert.target_price:,.2f} {direction_word}.\n"
                            f"Current price: ₹{ticker.last_price:,.2f}"
                        )
                except Exception:  # noqa: BLE001
                    log.exception("Alert price check failed for %s", symbol)
        except Exception:  # noqa: BLE001
            log.exception("Alert check loop failed")


async def run_daily_summary_loop(
    notifier: Notifier, repos: Repositories, interval: int
) -> None:
    """Push a Telegram summary of today's P&L on the configured cadence."""
    while True:
        await asyncio.sleep(interval)
        try:
            today = now_iso()[:10]
            daily_stats = await repos.daily_stats.get(today)
            active_grids = await repos.grids.list_by_status(["active", "paused"])
            lifetime_realized = await repos.trade_history.total_realized_pnl()
            summary_text = format_daily_summary(today, daily_stats, active_grids, lifetime_realized)
            await notifier.daily_summary(summary_text)
        except Exception:  # noqa: BLE001
            log.exception("Daily summary loop failed")


async def run_drive_backup_loop(
    backup_manager: "DriveBackupManager", notifier: Notifier, interval_seconds: int
) -> None:
    """Periodically snapshot the DB and upload it to Google Drive.

    Runs on a fixed interval, same resilience pattern as the other
    background loops here: a failure in one cycle is logged and notified,
    never crashes the loop, and the next cycle proceeds normally.
    """
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            file_id = await backup_manager.create_backup_and_upload()
            await notifier.drive_backup_completed(file_id)
        except Exception as exc:  # noqa: BLE001
            log.exception("Drive backup loop failed")
            await notifier.drive_backup_failed(str(exc))


async def async_main() -> None:
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Configuration error: {exc}")
        raise SystemExit(1) from exc

    setup_logging(settings.log_dir, settings.log_level)
    log.info("Starting Manual DCA Grid Trading Bot...")

    db = Database(settings.database_path)
    await db.connect()
    await db.migrate()
    repos = Repositories(db)

    exchange = CoinDCXClient(
        api_key=settings.coindcx_api_key,
        api_secret=settings.coindcx_api_secret,
        base_url=settings.coindcx_base_url,
    )

    bot = Bot(token=settings.telegram_bot_token)
    chat_ids = tuple({settings.telegram_owner_id, *settings.telegram_allowed_ids})
    notifier = Notifier(bot, chat_ids)

    risk_manager = RiskManager(settings.risk, repos)
    await risk_manager.load_emergency_stop()
    order_manager = OrderManager(exchange, repos)
    paper_exchange = PaperExchangeClient(exchange)
    paper_order_manager = OrderManager(paper_exchange, repos)
    mixed_order_manager = MixedOrderManager(
        real=order_manager,
        paper=paper_order_manager,
        repos=repos,
    )
    alert_manager = AlertManager(repo=repos.price_alerts)
    # Restore any alerts that were set before the last restart.
    saved_alerts = await repos.price_alerts.list_all()
    alert_manager.load(saved_alerts)

    dca_manager = DCAManager(
        exchange=exchange,
        repos=repos,
        order_manager=mixed_order_manager,
        notifier=notifier,
        risk=risk_manager,
    )

    recovery_manager = RecoveryManager(
        exchange=exchange,
        repos=repos,
        notifier=notifier,
        dca_manager=dca_manager,
    )

    order_monitor = OrderMonitor(
        repos=repos,
        order_manager=mixed_order_manager,
        dca_manager=dca_manager,
        notifier=notifier,
        exchange=exchange,
        poll_interval=settings.order_poll_interval_seconds,
    )

    # Price Monitor — replaces the bare run_price_trigger_loop function.
    # Load the persisted interval from SQLite (falls back to settings default
    # if no interval has been set yet via /monitor).
    price_monitor = PriceMonitor(
        exchange=exchange,
        repos=repos,
        dca_manager=dca_manager,
        notifier=notifier,
        default_interval=settings.price_poll_interval_seconds,
    )
    await price_monitor.load_interval()

    app_context = BotAppContext(
        settings=settings,
        repos=repos,
        exchange=exchange,
        dca_manager=dca_manager,
        risk_manager=risk_manager,
        notifier=notifier,
        alert_manager=alert_manager,
        price_monitor=price_monitor,
    )
    application = build_application(app_context)

    await recovery_manager.recover()

    order_monitor.start()
    price_monitor.start()

    daily_summary_task = asyncio.create_task(
        run_daily_summary_loop(notifier, repos, settings.daily_summary_interval_seconds)
    )
    alert_task = asyncio.create_task(
        run_alert_check_loop(alert_manager, exchange, notifier, settings.price_poll_interval_seconds)
    )

    drive_backup_task: asyncio.Task | None = None
    if settings.backup.enabled:
        # Lazy, opt-in import — google-auth is only required when Drive
        # backup is actually turned on, not a hard dependency otherwise.
        try:
            from storage.drive_backup import DriveBackupManager
        except ImportError as exc:
            log.error(
                "GDRIVE_BACKUP_ENABLED=true but the google-auth package is not "
                "installed (pip install google-auth). Drive backup will NOT run "
                "this session. Original error: %s", exc,
            )
        else:
            drive_backup_manager = DriveBackupManager(
                db_path=settings.database_path,
                folder_id=settings.backup.folder_id,
                service_account_json_path=settings.backup.service_account_json_path,
                retention_count=settings.backup.retention_count,
            )
            interval_seconds = int(settings.backup.interval_hours * 3600)
            drive_backup_task = asyncio.create_task(
                run_drive_backup_loop(drive_backup_manager, notifier, interval_seconds)
            )
            log.info(
                "Google Drive backup enabled: every %.1fh, folder=%s, retention=%d",
                settings.backup.interval_hours, settings.backup.folder_id, settings.backup.retention_count,
            )

    stop_event = asyncio.Event()

    def _handle_signal() -> None:
        log.info("Shutdown signal received")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_signal)
        except NotImplementedError:
            pass

    async with application:
        await application.initialize()
        await application.start()
        await application.updater.start_polling(drop_pending_updates=True)
        log.info("Telegram bot polling started. Bot is live.")

        await stop_event.wait()

        log.info("Shutting down...")
        try:
            await notifier.send(
                "🔌 <b>Bot is shutting down.</b>\n"
                "No new trades will be placed until it restarts.\n"
                "Active grids are preserved — recovery will resume them on next start."
            )
        except Exception:  # noqa: BLE001
            log.warning("Could not send shutdown notification")
        await application.updater.stop()
        await application.stop()

    daily_summary_task.cancel()
    alert_task.cancel()
    if drive_backup_task is not None:
        drive_backup_task.cancel()
    await price_monitor.stop()
    await order_monitor.stop()
    await exchange.close()
    await db.close()
    log.info("Shutdown complete.")


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
