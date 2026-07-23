# Manual DCA (Dollar-Cost-Averaging) Trading Bot for CoinDCX

A production-ready, standalone Python bot that runs manual per-coin DCA
trading strategies on [CoinDCX](https://coindcx.com), controlled entirely
through Telegram. There is no web UI, no dashboard, no market scanner, and no
AI coin-picking — **you** decide which coin to trade and its parameters; the
bot only manages the position's order lifecycle.

## What this bot does

- You send `/newgrid` in Telegram and walk through a guided setup: choose a
  coin (e.g. `BTCINR`), an entry price (or use the live market price), a base
  investment amount, a dip-buy amount and trigger percentage, a profit-sell
  amount and trigger percentage, a maximum number of DCA levels, a stop-loss
  percentage, an optional trailing take-profit, and a mode (**paper** or
  **real**).
- The bot places an initial buy, then averages down with further buys each
  time price drops by the configured dip percentage, and sells a configured
  portion each time price rises by the configured profit percentage off the
  *average* entry price. A stop-loss closes the entire position if price
  falls too far below the average entry.
- **Trailing take-profit** (optional, Custom Grid only): instead of selling
  the instant your profit target is hit, the bot keeps tracking the price
  upward and only sells once it pulls back a configured % from the highest
  point reached since the target was hit — captures more of a strong
  upward move instead of selling at the very first profit tick.
- **Paper mode** simulates order placement (no real money, no real exchange
  orders) while still using live market prices — useful for testing a
  configuration before running it for real. The simulation isn't an
  instant-fill toy: it models slippage (fills nudged slightly against you,
  like a real market order), latency (an order stays open for a random
  delay before it can fill, instead of filling the instant it's checked),
  and occasional partial fills — all tunable via `PAPER_SLIPPAGE_BPS_MAX`,
  `PAPER_LATENCY_MIN_SECONDS`/`PAPER_LATENCY_MAX_SECONDS`, and
  `PAPER_PARTIAL_FILL_PROBABILITY` in `.env`.
- You can run multiple DCA positions ("grids") simultaneously (e.g. one for
  BTCINR, one for ETHINR), each with its own configuration and mode.
- All state (grids, orders, trade history, price alerts) is persisted in
  SQLite, so if the bot process restarts or the server reboots, it
  reconciles with the exchange on startup and resumes exactly where it left
  off — no manual re-entry needed.
- Risk limits (max total capital, max capital per coin, max simultaneous
  grids, minimum wallet balance, daily loss limit) are enforced before every
  grid start and before every dip-buy.
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
│   └── repositories.py        # Typed CRUD access per table (grids, orders, trade history,
│                                daily stats, price alerts, monitor settings)
├── exchange/
│   ├── base.py                # Abstract exchange interface
│   ├── coindcx.py             # CoinDCX REST client (HMAC-signed, retries, rate-limit handling)
│   ├── paper_exchange.py       # Simulated order placement for paper-mode grids
│   └── exceptions.py
├── grid/
│   └── dca_engine.py          # Pure math: average-entry, next-buy/sell/stop-loss prices,
│                                shared exchange-rule validation (single source of truth)
├── trading/
│   ├── dca_manager.py         # Core orchestrator: start/pause/resume/stop, trigger checks, fill handling
│   ├── order_manager.py       # Places/cancels real or paper orders, order state machine
│   ├── mixed_order_manager.py # Routes order calls to real vs. paper OrderManager by grid mode
│   ├── order_monitor.py       # Background loop polling for order fills + periodic full sync
│   ├── price_monitor.py       # Background loop polling prices and dispatching trigger checks
│   ├── coin_validator.py      # Pre-flight investment/pair validation for the /newgrid conversation
│   ├── alert_manager.py       # One-shot price alerts, persisted in SQLite
│   └── recovery.py            # Startup reconciliation against exchange state
├── risk/
│   └── risk_manager.py        # Centralized risk checks (capital limits, daily loss, emergency stop)
├── notifications/
│   └── notifier.py            # Telegram push notifications for all bot events
├── bot_telegram/               # Telegram bot layer (named to avoid clashing with the
│   ├── bot.py                  # `telegram` package from python-telegram-bot)
│   ├── handlers.py             # All non-conversation commands (/status, /grids, /pause, ...)
│   ├── conversations.py        # Guided /newgrid conversation flow
│   ├── keyboards.py            # Inline/reply keyboards
│   └── formatters.py           # DB row -> Telegram message formatting
├── utils/
│   ├── logger.py               # Per-channel rotating file logging
│   └── helpers.py               # ID generation, Decimal-safe math
├── tests/                      # pytest suite (DCA math, risk checks, repository integration)
├── scripts/
│   └── audit_exchange_layer.py # Standalone dev script for spot-checking exchange-rule math
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
   every command, and `/newgrid` to launch your first grid.

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

## Running with Docker

A `Dockerfile` and `docker-compose.yml` are included for VPS or any other
Docker-capable host.

```bash
cp .env.example .env   # then fill in your real credentials
docker compose up --build -d
docker compose logs -f   # follow logs
```

Notes:
- The SQLite database (`./data`) and log files (`./logs`) are bind-mounted
  from the host, not baked into the image — this is what makes grid state
  survive `docker compose up --build` (a rebuild/redeploy), per the
  "Persistent database across redeploys" section above. Deleting `./data`
  on the host deletes your grid history; back it up the same way regardless
  of how you're running the bot.
- The container runs as a non-root user (uid 1000), not root. If
  `docker compose up` ever fails with a permission error writing to
  `./data` or `./logs`, it's almost always because those host directories
  already exist owned by a different user (e.g. created earlier by a
  root-run container, or by `sudo`). Fix it once with:
  ```bash
  mkdir -p data logs
  sudo chown -R 1000:1000 data logs
  ```
- If you enable Google Drive backup, mount your service-account key file
  read-only — uncomment and adjust the relevant line in
  `docker-compose.yml` — and point `GDRIVE_SERVICE_ACCOUNT_JSON` in `.env`
  at wherever you mounted it *inside* the container (e.g.
  `/app/gdrive-key.json`), not its path on the host.
- No ports are published by default; this bot doesn't listen for inbound
  connections unless you've turned on the optional CoinDCX webhook receiver
  (`WEBHOOK_ENABLED=true` — see below). Telegram itself always uses
  long-polling, never a webhook, in this codebase. If you do enable the
  webhook receiver in Docker, add `ports: ["8080:8080"]` (or your configured
  `WEBHOOK_PORT`) to the `gridbot` service in `docker-compose.yml`.

## Continuous Integration

`.github/workflows/ci.yml` runs on every push and pull request: a fast
compile-check across every module, the full `pytest` suite, and a Docker
build to catch a broken `Dockerfile` before it reaches a real deployment.

## Command reference

**Grid control**
- `/newgrid` — start a new grid; first choose:
  - **1️⃣ Default Grid** — type only a coin symbol, everything else uses your
    saved defaults (base investment, dip/profit amounts and percentages, max
    levels, stop loss, and last-used trading mode)
  - **2️⃣ Custom Grid** — the full guided setup (pick coin, entry price, base
    investment, dip-buy amount/percentage, profit-sell amount/percentage, max
    levels, stop-loss percentage, optional trailing take-profit, and
    paper/real mode)
- `/defaults` — view your saved Default Grid settings, or edit one with
  `/defaults set <field> <value>` (e.g. `/defaults set base_investment 750`,
  or `/defaults set last_mode paper` / `ask`). Saved in SQLite, persists
  across restarts.
- `/stopgrid <grid_id>` — stop a running grid and cancel its resting orders
- `/pause <grid_id>` — pause a grid (cancels resting orders, keeps config)
- `/resume <grid_id>` — resume a paused grid
- `/manualbuy <grid_id> <inr_amount>` — place an extra buy right now, outside
  the automatic dip-buy ladder. Shows a confirmation screen first; goes
  through the same exchange-rule validation and risk gate as an automatic
  dip-buy (emergency stop / daily loss limit / capital caps all apply)
- `/manualsell <grid_id> [inr_amount]` — sell part (or, if you omit the
  amount, all) of a grid's position right now, regardless of current profit.
  Shows a confirmation screen first. Manual sells are never blocked by
  emergency stop or risk limits, since reducing a position is always allowed
- `/adjustgrid <grid_id> <field> <value>` — change one setting on a running
  grid without stopping it. Adjustable fields: `dip_buy_amount`,
  `dip_percentage`, `profit_sell_amount`, `profit_percentage`, `max_levels`,
  `stop_loss_percentage`, `trailing_enabled`, `trailing_percentage`.
  Changing `dip_percentage`/`profit_percentage` immediately recomputes the
  grid's next buy/sell price so the change takes effect on the very next
  price tick, not just the next fill

**Monitoring**
- `/status` — bot health, wallet balance, emergency-stop state
- `/balance` — current CoinDCX wallet balance
- `/coininfo <symbol>` — exchange rules for a coin (step size, precision, min notional/quantity)
- `/paper` — list of paper-mode grids
- `/grids` — list all grids with quick pause/resume/stop buttons
- `/positions` — all currently open positions across all grids
- `/profit` — realized profit per grid and in total
- `/summary` — today's P&L, lifetime profit, and active grid standings (on demand)
- `/history <symbol>` — most recent buy/sell fills for a coin, with per-sell P&L and originating grid
- `/monitor` — price/order monitor health (poll interval, degraded state, failure counts)
- `/export` — download the complete trade history as a CSV file (for offline accounting/tax analysis)
- `/backup` — download the raw SQLite database file (all grids, configs, and history in one file)
- `/backupstatus` — check the automatic Google Drive backup's health: last
  successful backup, last error (if any), and a live count of backups
  currently in the Drive folder (if enabled)
- `/restorelist [page]` — browse available Google Drive backups, newest
  first, 10 per page with Prev/Next buttons. Shows date/time, file name,
  size, the database schema version it was taken at, and whether it was an
  automatic or manual backup
- `/verifybackup <number|latest>` — download a specific backup (using the
  number shown in `/restorelist`, or `latest` for the most recent) and
  confirm it's actually intact and restorable: runs SQLite's own
  `PRAGMA integrity_check`, confirms every critical table is present, and
  shows row counts. Every automatic backup is already verified this way
  immediately after upload — this lets you re-check any existing backup,
  including old ones, on demand
- `/restorebackup <number|latest>` — restore the entire database from a
  backup. **Never happens immediately or live** — it downloads and verifies
  the backup, stages it, and applies it automatically the *next time the
  bot restarts* (before any database connection is opened), backing up your
  current database first, automatically. Use `/restorebackup cancel` to
  back out of a staged restore before restarting, or `/restorebackup` with
  no arguments to check whether one is currently staged
- `/logs` — most recent log entries

**Price alerts** (persisted across restarts)
- `/alert <symbol> <price>` — set a one-shot alert; the bot checks the current live price to determine direction (above/below) and notifies you the moment the price crosses the target
- `/alerts` — list all active alerts
- `/delalert <symbol>` — cancel all alerts for a coin

**Emergency control**
- `/emergencystop` — immediately block all new grid starts and dip-buys (persisted — survives a restart); does not block profit-sells or stop-loss exits, since those reduce risk rather than add it
- `/clearemergency` — re-enable trading after an emergency stop (requires inline confirmation button press to prevent accidents); paused grids must be manually resumed with `/resume`

There is no `/settings`, `/setinvestment`, `/setlevels`, or `/setrange`
command — every grid's parameters are set once, at creation, via `/newgrid`.
To change a coin's parameters, stop the old grid and start a new one.

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
that immediately blocks all new grid starts and dip-buys, and is persisted in
SQLite so it survives a restart — it does not block profit-sells or
stop-loss exits.

## Daily summary notifications

In addition to real-time push notifications for every grid lifecycle event
(grid started/stopped/paused, order filled, dip/profit/stop-loss trigger, risk block, errors),
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

## Automatic Google Drive backup (optional)

The manual `/backup` command works anytime, but for unattended production
use you can also enable periodic automatic backups to Google Drive — off
by default, opt-in via environment variables.

1. Create a Google Cloud project (or reuse one), enable the **Drive API**,
   and create a **service account**. Download its JSON key file.
2. In Google Drive, create (or pick) a destination folder, open its
   **Share** settings, and share it with the service account's email
   address (found in the key file, looks like
   `something@project-id.iam.gserviceaccount.com`) with **Editor** access.
3. Copy the folder ID from the folder's URL
   (`https://drive.google.com/drive/folders/<this-part-is-the-id>`).
4. Install the one extra dependency this needs:
   `pip install google-auth` (already listed as optional in
   `requirements.txt`).
5. Set in your `.env`:
   ```
   GDRIVE_BACKUP_ENABLED=true
   GDRIVE_SERVICE_ACCOUNT_JSON=/path/to/your-key-file.json
   GDRIVE_FOLDER_ID=your_folder_id_here
   GDRIVE_BACKUP_INTERVAL_HOURS=6
   GDRIVE_BACKUP_RETENTION_COUNT=30
   ```

Every interval, the bot takes a **consistent snapshot** of the SQLite
database (using SQLite's own backup API, not a raw file copy — this
correctly captures any data still sitting in the WAL file that hasn't been
checkpointed yet, unlike a plain file copy would), **verifies the snapshot
is intact before uploading it**, uploads it to the configured folder,
**downloads it back and verifies that copy too** (confirming the round trip
through Drive didn't corrupt or truncate anything), and deletes the oldest
backups beyond `GDRIVE_BACKUP_RETENTION_COUNT`. If either verification step
fails, the whole backup is reported as failed — a backup that can't be
confirmed intact is treated as no backup at all, not a success with a
caveat. You'll get a Telegram notification on success or failure, and
`/backupstatus` always shows the latest outcome. Use `/verifybackup` any
time to re-check an existing (including old) backup on demand. If
`google-auth` isn't installed but `GDRIVE_BACKUP_ENABLED=true`, the bot
logs an error and simply skips Drive backup for that session rather than
failing to start — everything else continues normally.

## CoinDCX order-update webhooks (optional, experimental)

Off by default. The bot already detects fills reliably through polling
(`ORDER_POLL_INTERVAL_SECONDS`, default every few seconds) — this is purely
an optional accelerant for slightly faster fill detection, not something
you need for the bot to work correctly.

**Read this before enabling it in production:** this receiver's signature
verification and payload parsing were built without access to CoinDCX's
live webhook documentation (no network access at build time). Two things
are *assumptions*, not confirmed facts:
1. **Signing scheme** — assumes CoinDCX signs webhook bodies with
   HMAC-SHA256 using your API secret, sent in an `X-Webhook-Signature`
   header. Verify the actual header name and scheme against CoinDCX's
   current docs.
2. **Payload shape** — assumes fields named like their REST order-status
   responses (`id`, `status`, `filled_quantity`, `avg_price`).

Because of that uncertainty, this is designed so a missed or malformed
webhook is always silently caught by the next poll cycle anyway — never a
replacement for polling, only ever an accelerant on top of it. Applying a
fill twice (once from a webhook, once from the poller) is also safe, since
the underlying fill-handling is idempotent.

To enable:
```bash
pip install aiohttp   # see requirements.txt
```
```
WEBHOOK_ENABLED=true
WEBHOOK_HOST=0.0.0.0
WEBHOOK_PORT=8080
WEBHOOK_PATH=/webhooks/coindcx/order-update
WEBHOOK_SECRET=            # falls back to COINDCX_API_SECRET if left blank
```
Then point CoinDCX's webhook configuration (once you've confirmed the real
signature/payload format against their docs and adjusted
`webhooks/server.py` if needed) at
`http://your-host:8080/webhooks/coindcx/order-update`. A basic liveness
check is available at `/webhooks/health`.

## Recovery after restart

On every startup, one check runs before anything else even opens the
database: if a `/restorebackup` was staged during the previous session,
`storage/restore.py` applies it now — swapping in the backup's data,
after backing up whatever was there and re-verifying the staged file one
last time. See `/restorebackup` in the command reference above for how a
restore gets staged in the first place. Most of the time there's nothing
staged and this is a no-op.

Then `trading/recovery.py` runs, before the Telegram bot starts polling:

1. Loads all grids marked `active` or `paused` from SQLite.
2. Re-fetches the live status of every non-terminal local order from
   CoinDCX and updates local records for anything that filled or was
   cancelled while the bot was offline.
3. Sends a Telegram summary of what was restored.

The order monitor and price monitor then resume normally against
the reconciled state — no manual intervention required after a crash or
redeploy.

## Testing

```bash
cd grid-trading-bot
python -m pytest tests/ -v
```

The suite covers DCA math (average entry, next buy/sell/stop-loss prices,
exchange-rule validation), risk manager decision logic, order lifecycle and
recovery, and SQLite repository CRUD behavior — all without touching the
real CoinDCX API or Telegram.

## Production checklist (VPS / always-on deployment)

- [ ] `.env` contains real credentials and is **not** committed to version control (already gitignored).
- [ ] Risk limits in `.env` reviewed and set to values you are comfortable losing.
- [ ] CoinDCX API key permissions are limited to trading only (no withdrawal permission).
- [ ] Run under a process supervisor (systemd, `pm2`, or Replit's Reserved VM deployment) so the bot restarts automatically on crash or reboot.
- [ ] `logs/` directory is on persistent storage and monitored/rotated (rotation is already handled in-app via `RotatingFileHandler`).
- [ ] `data/grid_bot.db` is backed up regularly — this is the only source of truth for grid/order/position state. Either run `/backup` on a schedule yourself, or enable automatic Google Drive backups (see "Automatic Google Drive backup" above).
- [ ] Telegram bot's `TELEGRAM_CHAT_ID` is your own ID, and `TELEGRAM_ALLOWED_USER_IDS` only includes people you trust with trading control.
- [ ] Test with small investment amounts and a narrow dip/profit percentage in **paper mode** first, then with small real capital, before committing significant capital.
- [ ] Confirm `/status` reports the expected wallet balance immediately after startup.
- [ ] Verify recovery works as expected: restart the process while a grid is active and confirm the Telegram recovery summary and `/grids` output match what you expect.

## Important notes

- This bot places real orders with real money once you start a grid in
  **real** mode. A **paper** mode is also available (simulated order
  placement against live market prices, no real money at risk) — select it
  as the last step of `/newgrid`.
- The bot never scans markets, ranks coins, or recommends what to trade.
  Every grid is started explicitly by you via `/newgrid`.
- Only the Telegram user ID(s) in `TELEGRAM_CHAT_ID` / `TELEGRAM_ALLOWED_USER_IDS`
  can control the bot — all other users are rejected by every handler.
