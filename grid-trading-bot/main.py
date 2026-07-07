"""Application entrypoint for the Manual DCA Grid Trading Bot.

Wires together configuration, database, exchange client, the DCA trading
engine, the order monitor, recovery, and the Telegram bot — then runs forever.

Run with: python main.py
"""

from __future__ import annotations

import asyncio
import signal

from telegram import Bot

from bot_telegram.bot import BotAppContext, build_application
from bot_telegram.formatters import format_daily_summary
from config.settings import ConfigError, load_settings
from exchange.coindcx import CoinDCXClient
from notifications.notifier import Notifier
from risk.risk_manager import RiskManager
from storage.database import Database
from storage.repositories import Repositories
from trading.alert_manager import AlertManager
from trading.dca_manager import DCAManager
from trading.order_manager import OrderManager
from trading.order_monitor import OrderMonitor
from trading.recovery import RecoveryManager
from utils.helpers import now_iso
from utils.logger import get_logger, setup_logging

log = get_logger("trading")


async def run_price_trigger_loop(
    dca_manager: DCAManager, repos: Repositories, interval: int
) -> None:
    """Poll active grids for dip-buy, profit-sell, and stop-loss triggers."""
    while True:
        try:
            active_grids = await repos.grids.list_by_status(["active"])
            for grid in active_grids:
                try:
                    ticker = await dca_manager._exchange.get_ticker(grid["symbol"])
                    await dca_manager.check_grid_triggers(grid["grid_id"], ticker.last_price)
                except Exception:  # noqa: BLE001
                    log.exception("Price trigger check failed for grid %s", grid["grid_id"])
        except Exception:  # noqa: BLE001
            log.exception("Price trigger loop cycle failed")
        await asyncio.sleep(interval)


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
                    fired = alert_manager.check_and_fire(symbol, ticker.last_price)
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
    order_manager = OrderManager(exchange, repos)
    alert_manager = AlertManager()

    dca_manager = DCAManager(
        exchange=exchange,
        repos=repos,
        order_manager=order_manager,
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
        order_manager=order_manager,
        dca_manager=dca_manager,
        poll_interval=settings.order_poll_interval_seconds,
    )

    app_context = BotAppContext(
        settings=settings,
        repos=repos,
        exchange=exchange,
        dca_manager=dca_manager,
        risk_manager=risk_manager,
        notifier=notifier,
        alert_manager=alert_manager,
    )
    application = build_application(app_context)

    await recovery_manager.recover()

    order_monitor.start()

    price_trigger_task = asyncio.create_task(
        run_price_trigger_loop(dca_manager, repos, settings.price_poll_interval_seconds)
    )
    daily_summary_task = asyncio.create_task(
        run_daily_summary_loop(notifier, repos, settings.daily_summary_interval_seconds)
    )
    alert_task = asyncio.create_task(
        run_alert_check_loop(alert_manager, exchange, notifier, settings.price_poll_interval_seconds)
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
        await application.updater.stop()
        await application.stop()

    price_trigger_task.cancel()
    daily_summary_task.cancel()
    alert_task.cancel()
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
