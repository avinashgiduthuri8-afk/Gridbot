# Manual Grid Trading Bot for CoinDCX

A production-ready, standalone Python bot that runs manual grid trading
strategies on [CoinDCX](https://coindcx.com), controlled entirely through
Telegram. There is no web UI, no dashboard, no market scanner, and no AI
coin-picking — **you** decide which coin to trade and the price range; the
bot only manages the grid's order lifecycle.

## What this bot does

- You send `/startgrid` in Telegram and walk through a guided setup:
  choose a coin (e.g. `BTCINR`), an upper/lower price range, number of
  grid levels, investment per grid order, and grid type (arithmetic or
  geometric spacing).
- The bot places a ladder of buy orders across the range. When a buy
  fills, it automatically places a matching sell one level up. When that
  sell fills, profit is realized and a new buy is placed one level down —
  the grid keeps cycling until you pause or stop it.
- You can run multiple grids simultaneously (e.g. one for BTCINR, one for
  ETHINR), each with its own configuration.
- All state (grids, orders, positions, trade history) is persisted in
  SQLite, so if the bot process restarts or the server reboots, it
  reconciles with the exchange on startup and resumes exactly where it
  left off — no manual re-entry needed.
- Risk limits (max total capital, max capital per coin, max simultaneous
  grids, minimum wallet balance, daily loss limit) are enforced before
  every grid start and every order placement.
- Every material event (grid started/paused/stopped, buy/sell executed,
  profit updates, errors, recovery on restart) is pushed to you as a
  Telegram notification.

## Requirements

- Python 3.12+
- A Telegram bot token (from [@BotFather](https://t.me/BotFather))
- Your numeric Telegram user ID (from [@userinfobot](https://t.me/userinfobot))
- A CoinDCX account with API key + secret (Account → API Management)

## Project layout

```
grid-trading-bot/
├── main.py                  # Entrypoint: wires everything together, runs forever
├── requirements.txt
├── .env.example              # Copy to .env and fill in credentials
├── config/
│   ├── constants.py          # Enums, static limits
│   └── settings.py           # Loads & validates all env vars into a frozen Settings object
├── storage/
│   ├── database.py           # SQLite connection + schema migration
│   ├── models.py              # Dataclasses mirroring each table
│   └── repositories.py        # Typed CRUD access per table
├── exchange/
│   ├── base.py                # Abstract exchange interface
│   ├── coindcx.py             # CoinDCX REST client (HMAC-signed, retries, rate-limit handling)
│   └── exceptions.py
├── grid/
│   ├── generator.py           # Arithmetic / geometric grid price generation + validation
│   ├── lifecycle.py           # Pure profit/range calculations (unit-tested)
│   └── models.py
├── trading/
│   ├── grid_manager.py        # Core orchestrator: start/pause/resume/stop, fill handling
│   ├── order_manager.py       # Only component that places/cancels orders on the exchange
│   ├── position_manager.py    # Tracks open inventory until closed by a matching sell
│   ├── order_monitor.py       # Background loop polling for order fills
│   └── recovery.py            # Startup reconciliation against exchange state
├── risk/
│   └── risk_manager.py        # Centralized risk checks (capital limits, daily loss, emergency stop)
├── notifications/
│   └── notifier.py            # Telegram push notifications for all bot events
├── bot_telegram/               # Telegram bot layer (named to avoid clashing with the
│   ├── bot.py                  # `telegram` package from python-telegram-bot)
│   ├── handlers.py             # All non-conversation commands (/status, /grids, /pause, ...)
│   ├── conversations.py        # Guided /startgrid conversation flow
│   ├── keyboards.py            # Inline/reply keyboards
│   └── formatters.py           # DB row -> Telegram message formatting
├── utils/
│   ├── logger.py               # Per-channel rotating file logging
│   └── helpers.py               # ID generation, Decimal-safe math
├── tests/                      # pytest suite (grid math, risk checks, repository integration)
├── data/                        # SQLite database file lives here
└── logs/                        # Rotating log files (trading, exchange, telegram, database, grid, errors)
```

## Installation

1. **Install dependencies:**

   ```bash
   cd grid-trading-bot
   pip install -r requirements.txt
   ```

2. **Configure environment variables:**

   ```bash
   cp .env.example .env
   ```

   Edit `.env` and fill in:
   - `TELEGRAM_BOT_TOKEN` — from @BotFather
   - `TELEGRAM_CHAT_ID` — your numeric Telegram user ID (this is the bot owner)
   - `COINDCX_API_KEY` / `COINDCX_API_SECRET` — from CoinDCX API Management
   - Adjust risk limits (`MAX_TOTAL_CAPITAL`, `MAX_CAPITAL_PER_COIN`, etc.)
     to fit your account size and risk tolerance.

   On Replit, these are stored as Secrets instead of a `.env` file (see
   the "Running on Replit" section below) — the same variable names apply.

3. **Run the bot:**

   ```bash
   python main.py
   ```

   On first run, the SQLite database and schema are created automatically
   at `data/grid_bot.db`. Rotating log files are written to `logs/`.

4. **Talk to your bot on Telegram.** Send `/start`, then `/help` to see
   every command, and `/startgrid` to launch your first grid.

## Running on Replit

This project intentionally lives outside the `artifacts/` directory
because it is a background service, not a web app — it has no HTTP
server and nothing to preview in a browser. To run it continuously on
Replit:

1. Add `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `COINDCX_API_KEY`, and
   `COINDCX_API_SECRET` as Replit Secrets (already done if you're reading
   this after initial setup).
2. Register a workflow that runs `python grid-trading-bot/main.py`
   (or `cd grid-trading-bot && python main.py`) so Replit keeps the
   process alive and restarts it if it crashes.
3. For true 24/7 uptime independent of your browser session, deploy the
   workflow as a **Reserved VM deployment** (Background Worker) rather
   than relying on the development workspace alone.

## Command reference

**Grid control**
- `/startgrid` — guided setup for a new grid (pick coin, range, levels, investment, type)
- `/stopgrid <grid_id>` — stop a running grid and cancel its resting orders
- `/pause <grid_id>` — pause a grid (cancels resting orders, keeps config)
- `/resume <grid_id>` — resume a paused grid (re-places the buy ladder)

**Monitoring**
- `/status` — bot health, wallet balance, emergency-stop state
- `/grids` — list all grids with quick pause/resume/stop buttons
- `/positions` — all currently open positions across all grids
- `/profit` — realized profit per grid and in total
- `/summary` — today's P&L, lifetime profit, and active grid standings (on demand)
- `/history <symbol>` — most recent buy/sell fills for a coin, with per-sell P&L and originating grid
- `/export` — download the complete trade history as a CSV file (for offline accounting/tax analysis)
- `/logs` — most recent log entries

**Configuration**
- `/settings` — view saved per-coin defaults
- `/setinvestment <symbol> <amount>` — change investment per grid order for future grids
- `/setlevels <symbol> <levels>` — change grid level count for future grids
- `/setrange <symbol> <lower> <upper>` — change default price range for future grids

## Risk management

Configured via environment variables, enforced by `risk/risk_manager.py`
before every grid start and order placement:

| Variable | Purpose |
|---|---|
| `MAX_TOTAL_CAPITAL` | Cap on capital committed across all active grids |
| `MAX_CAPITAL_PER_COIN` | Cap on capital committed to any single coin |
| `MAX_SIMULTANEOUS_GRIDS` | Maximum number of grids that may run at once |
| `MIN_WALLET_BALANCE` | Minimum INR balance that must always remain free |
| `DAILY_LOSS_LIMIT` | Realized loss threshold that halts new trades for the day |

An emergency-stop switch also exists in code (`RiskManager.trigger_emergency_stop`)
that immediately blocks all new grid starts and order placements.

## Daily summary notifications

In addition to real-time push notifications for every grid lifecycle event
(grid started/stopped/paused, order filled, range breach, risk block, errors),
the bot pushes a periodic Telegram summary covering:

- Today's realized P&L and number of completed trades
- Lifetime realized profit across all grids
- Count of active/paused grids, with a per-grid profit/cycle breakdown

Controlled by `DAILY_SUMMARY_INTERVAL_SECONDS` in `.env` (default `86400`,
i.e. once every 24 hours). Set it lower (e.g. `3600` for hourly) if you want
more frequent check-ins. This runs as its own background task in `main.py`
and never blocks or crashes the rest of the bot — failures are logged and
retried on the next cycle.

You can also pull the same report on demand at any time with `/summary`
(no need to wait for the scheduled push).

## Recovery after restart

On every startup, `trading/recovery.py` runs before the Telegram bot
starts polling:

1. Loads all grids marked `active` or `paused` from SQLite.
2. Re-fetches the live status of every non-terminal local order from
   CoinDCX and updates local records for anything that filled or was
   cancelled while the bot was offline.
3. Sends a Telegram summary of what was restored.

The order monitor and range-breach checker then resume normally against
the reconciled state — no manual intervention required after a crash or
redeploy.

## Testing

```bash
cd grid-trading-bot
python -m pytest tests/ -v
```

The suite covers grid price generation (arithmetic/geometric), pure
profit/range calculations, risk manager decision logic, and SQLite
repository CRUD behavior — all without touching the real CoinDCX API or
Telegram.

## Production checklist (VPS / always-on deployment)

- [ ] `.env` contains real credentials and is **not** committed to version control (already gitignored).
- [ ] Risk limits in `.env` reviewed and set to values you are comfortable losing.
- [ ] CoinDCX API key permissions are limited to trading only (no withdrawal permission).
- [ ] Run under a process supervisor (systemd, `pm2`, or Replit's Reserved VM deployment) so the bot restarts automatically on crash or reboot.
- [ ] `logs/` directory is on persistent storage and monitored/rotated (rotation is already handled in-app via `RotatingFileHandler`).
- [ ] `data/grid_bot.db` is backed up regularly — this is the only source of truth for grid/order/position state.
- [ ] Telegram bot's `TELEGRAM_CHAT_ID` is your own ID, and `TELEGRAM_ALLOWED_USER_IDS` only includes people you trust with trading control.
- [ ] Test with small investment amounts (`INVESTMENT_PER_GRID`) and a narrow price range before committing significant capital.
- [ ] Confirm `/status` reports the expected wallet balance immediately after startup.
- [ ] Verify recovery works as expected: restart the process while a grid is active and confirm the Telegram recovery summary and `/grids` output match what you expect.

## Important notes

- This bot places real orders with real money once configured with live
  CoinDCX credentials. There is no paper-trading / simulation mode.
- The bot never scans markets, ranks coins, or recommends what to trade.
  Every grid is started explicitly by you via `/startgrid`.
- Only the Telegram user ID(s) in `TELEGRAM_CHAT_ID` / `TELEGRAM_ALLOWED_USER_IDS`
  can control the bot — all other users are rejected by every handler.
