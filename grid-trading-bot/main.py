"""Application entrypoint.

Wires together configuration, database, exchange client, the trading
engine (grid manager, order manager, position manager, risk manager),
the order monitor, recovery, and the Telegram bot — then runs forever.

Run with: python main.py
"""

from __future__ import annotations

import asyncio
import signal

from telegram import Bot

from bot_telegram.bot import BotAppContext, build_application
from config.settings import ConfigError, load_settings
from exchange.coindcx import CoinDCXClient
from notifications.notifier import Notifier
from risk.risk_manager import RiskManager
from storage.database import Database
from storage.repositories import Repositories
from trading.grid_manager import GridManager
from trading.order_manager import OrderManager
from trading.order_monitor import OrderMonitor
from trading.position_manager import PositionManager
from trading.recovery import RecoveryManager
from utils.logger import get_logger, setup_logging

log = get_logger("trading")


async def run_range_check_loop(grid_manager: GridManager, repos: Repositories, interval: int) -> None:
    while True:
        try:
            active_grids = await repos.grids.list_by_status(["active"])
            for grid in active_grids:
                await grid_manager.check_range_breach(grid["grid_id"])
        except Exception:  # noqa: BLE001
            log.exception("Range check loop failed")
        await asyncio.sleep(interval)


async def async_main() -> None:
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Configuration error: {exc}")
        raise SystemExit(1) from exc

    setup_logging(settings.log_dir, settings.log_level)
    log.info("Starting Manual Grid Trading Bot...")

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
    position_manager = PositionManager(repos)
    grid_manager = GridManager(exchange, repos, order_manager, position_manager, risk_manager, notifier)
    recovery_manager = RecoveryManager(exchange, repos, notifier)
    order_monitor = OrderMonitor(repos, order_manager, grid_manager, settings.order_poll_interval_seconds)

    app_context = BotAppContext(
        settings=settings, repos=repos, exchange=exchange,
        grid_manager=grid_manager, risk_manager=risk_manager, notifier=notifier,
    )
    application = build_application(app_context)

    await recovery_manager.recover()

    order_monitor.start()
    range_check_task = asyncio.create_task(
        run_range_check_loop(grid_manager, repos, settings.price_poll_interval_seconds)
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
            # Signal handlers aren't supported on some platforms (e.g. Windows).
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

    range_check_task.cancel()
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
