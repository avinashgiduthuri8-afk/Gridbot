# Manual Grid Trading Bot for CoinDCX

A production-ready Python bot that runs manual grid trading strategies on [CoinDCX](https://coindcx.com), controlled entirely through Telegram. There is no web UI — all interaction happens via Telegram commands.

## What this bot does

- You send `/startgrid` in Telegram and walk through a guided setup: choose a coin, set a price range and grid count, specify investment amount.
- The bot places buy/sell orders at each grid level and re-places orders as they fill, cycling profits through the grid.
- Risk limits cap total capital, per-coin exposure, and daily losses.
- On restart, `trading/recovery.py` reconciles live order state from CoinDCX and resumes all active grids automatically.

## Stack

- **Python** (asyncio) — `python-telegram-bot`, `httpx`, `aiosqlite`
- **SQLite** — local database at `data/grid_bot.db` (all state, no external DB)
- **CoinDCX REST API** — order placement and status
- **Telegram Bot API** — entire user interface

## Project layout

```
grid-trading-bot/
├── main.py                  # Entrypoint — wires everything together
├── config/settings.py       # Loads all config from env vars
├── bot_telegram/            # Telegram command handlers, keyboards, conversations, formatters
├── trading/                 # Core engine: DCA manager, order monitor, price monitor, recovery
├── exchange/                # CoinDCX API client (+ paper exchange stub)
├── grid/                    # Grid price generation + DCA engine (arithmetic/geometric)
├── risk/                    # Risk manager (capital limits, exposure caps, daily loss halts)
├── storage/                 # SQLite database, schema migrations, repositories, Drive backup/restore
├── notifications/           # Telegram notifier wrapper
├── api/                     # Read-only FastAPI dashboard backend (endpoints, routers)
├── dashboard/               # Dashboard app wiring (FastAPI app, deps, config)
├── schemas/                 # Pydantic schemas for the dashboard API
├── services/                # Dashboard service layer
├── webhooks/                # Optional webhook server (WEBHOOK_ENABLED)
├── replay/ , replay.py      # Replay/stress-testing framework for the DCA engine
├── scripts/                 # Operational scripts
├── tests/                   # pytest suite — 700+ tests, no live API or Telegram needed
└── requirements.txt
```

## Running the bot

The bot is **not currently configured to run** — it needs credentials first.

### Required secrets (set as Replit Secrets or in a `.env` file)

| Variable | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | From @BotFather on Telegram |
| `TELEGRAM_CHAT_ID` | Your numeric Telegram user ID (from @userinfobot) |
| `COINDCX_API_KEY` | From the CoinDCX API settings page |
| `COINDCX_API_SECRET` | From the CoinDCX API settings page |

### Optional configuration (with defaults)

See `grid-trading-bot/.env.example` for the full list of tunable parameters (risk limits, poll intervals, log level, etc.).

### Start command

```bash
cd grid-trading-bot && python main.py
```

### Running tests

```bash
cd grid-trading-bot && python -m pytest tests/ -v
```

## Important notes

- **This bot places real orders with real money** once configured with live CoinDCX credentials and a grid is started in `real` mode.
- A **paper-trading mode** exists (`mode="paper"`) — grids run against a simulated exchange (`exchange/paper_exchange.py`) with no real orders placed. It models configurable slippage, randomized fill latency, and partial fills (see `PAPER_*` vars in `.env.example`) — not just an instant-fill stub.
- Only Telegram user IDs listed in `TELEGRAM_CHAT_ID` / `TELEGRAM_ALLOWED_USER_IDS` can control the bot.
- A read-only FastAPI + React dashboard is available for viewing grid/trade state (see `api/`, `dashboard/`, and the separate frontend under `artifacts/grid-dashboard`).

## Deploying to Railway

Two ways to run this on Railway — pick one.

### Option A — one service (bot + dashboard together)

The simplest setup: a single Railway service runs both the Telegram bot and the dashboard (API + built frontend) from one process.

- Root Directory: repo root (**not** `grid-trading-bot` — the frontend build needs the sibling `lib/` workspace packages)
- Dockerfile Path: `Dockerfile.combined`
- Env vars: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `COINDCX_API_KEY`, `COINDCX_API_SECRET`, plus anything else from `.env.example` you want to override — `DASHBOARD_EMBEDDED_ENABLED=true` is already baked into `Dockerfile.combined`, no need to set it yourself
- Railway assigns `$PORT` automatically; `main.py`'s embedded dashboard already reads it (via `dashboard/config.py`), so no port config is required
- Mount a Railway volume and point `DATABASE_PATH` at it, same as any single-service SQLite deploy

How it works under the hood: `main.py` starts the dashboard's FastAPI app (`dashboard/app.py`) as a background `asyncio` task in the same event loop as Telegram polling — the same pattern already used for the webhook receiver and Drive backup loop. The dashboard opens its own SQLite connection to the same `DATABASE_PATH`; safe alongside the bot's own connection because WAL mode (`storage/database.py`) is built for exactly this — one writer, concurrent readers.

### Option B — two services (bot and dashboard independent)

Use this if you'd rather scale, restart, or redeploy the bot and dashboard independently.

**Service 1 — Telegram bot**
- Root Directory: `grid-trading-bot`
- Dockerfile Path: `Dockerfile` (the existing one)
- Env vars: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `COINDCX_API_KEY`, `COINDCX_API_SECRET`, plus anything else from `.env.example`
- No port needed — this process only makes outbound connections (unless `WEBHOOK_ENABLED=true`, see `.env.example`)

**Service 2 — Dashboard**
- Root Directory: repo root
- Dockerfile Path: `Dockerfile.dashboard`
- Railway assigns `$PORT` automatically; no port config required
- Must point `DATABASE_PATH` at the **same** volume/file as Service 1 for the dashboard to show live data

Both options: known gap — `pnpm-lock.yaml` is currently out of sync with the root `package.json` (two deps aren't reflected in the lockfile), so the frontend build stage runs `pnpm install --no-frozen-lockfile` rather than failing. Regenerating and committing the lockfile locally would make this fully reproducible.

## Project Roadmap

Original list of 40 planned items. Status verified against the codebase on 2026-08-11 —
35 of 40 are implemented and tested; 5 remain open.

### Remaining (5)

| # | Item | Audit Ref | Notes |
|---|---|---|---|
| 5 | Long-duration paper trading | M-10 | Paper mode exists and is tested; an actual multi-day soak run is an operational task, not a code change |
| 11 | Capital usage display | H-06 | No `/balance` or dashboard view currently shows total capital deployed vs. available across all grids |
| 35 | Realistic paper trading (slippage/latency) | M-10 | Paper exchange fills instantly at quoted price; no slippage or latency simulation |
| 37 | Live CoinDCX integration tests | L-02 | Only `test_fetch_coindcx_history.py` touches the real API; no opt-in live-exchange test suite |
| 40 | Performance & security audit before live deployment | — | No audit artifact in-repo; external/manual activity |

### Done (35)

All other items are implemented and covered by the test suite (707 passing), including:
shared exchange-rule validation across every order path, production hardening (SQLite busy-timeout,
graceful shutdown, memory-leak fixes, price sanity checks), restart recovery reconciliation,
duplicate-order prevention, dynamic per-market price/quantity precision formatting,
Next Buy/Sell price display, real-wallet `/balance`, `/coininfo`, persistent SQLite DB with
numbered schema migrations, automatic Google Drive backup, dust-position write-off, CoinDCX
order sync on restart, richer Telegram notifications, daily P&L summary, webhook server
(`WEBHOOK_ENABLED`), read-only FastAPI + React dashboard, trailing take-profit, `/manualbuy`
`/manualsell`, `/adjustgrid`, persisted price alerts, exponential backoff via `tenacity`,
per-grid `asyncio.Lock` concurrency protection, earlier `/newgrid` symbol validation,
Docker + GitHub Actions CI, and Telegram command/conversation test coverage.

## User preferences

*(none recorded yet)*
