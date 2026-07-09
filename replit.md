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
├── bot_telegram/            # Telegram command handlers, keyboards, formatters
├── trading/                 # Core engine: DCA manager, order monitor, price monitor, recovery
├── exchange/                # CoinDCX API client (+ paper exchange stub)
├── grid/                    # Grid price generation (arithmetic/geometric)
├── risk/                    # Risk manager (capital limits, daily loss halts)
├── storage/                 # SQLite database, models, repositories
├── notifications/           # Telegram notifier wrapper
├── tests/                   # pytest suite (no live API or Telegram needed)
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

- **This bot places real orders with real money** once configured with live CoinDCX credentials.
- There is no paper-trading / simulation mode.
- Only Telegram user IDs listed in `TELEGRAM_CHAT_ID` / `TELEGRAM_ALLOWED_USER_IDS` can control the bot.

## Project Roadmap

Consolidated list of 40 planned items, in rough priority order:

| # | Item | Audit Ref |
|---|---|---|
| 1 | Exchange validation audit | H-01, H-02, M-09 |
| 2 | Shared validation everywhere | M-01, M-02 |
| 3 | Production hardening | H-03–H-08, M-03–M-08 |
| 4 | End-to-end verification | — |
| 5 | Long-duration paper trading | M-10 |
| 6 | Restart recovery verification | C-05 |
| 7 | Duplicate order prevention | H-02 |
| 8 | Dynamic price formatting | — |
| 9 | Next Buy price display | — |
| 10 | Next Sell price display | — |
| 11 | Capital usage display | H-06 |
| 12 | Real wallet /balance | — |
| 13 | Better /coininfo | — |
| 14 | Persistent database across redeploys | — |
| 15 | Automatic Google Drive backup | C-02 |
| 16 | Dust position management | H-08 |
| 17 | Order synchronization with CoinDCX | C-05 |
| 18 | Better Telegram notifications | M-03, M-04, M-05, M-06 |
| 19 | Daily P&L summary | — |
| 20 | CoinDCX webhooks (V2) | L-09 |
| 21 | Web Dashboard | — |
| 22 | Dashboard Server/API | — |
| 23 | Trailing Take-Profit | — |
| 24 | Manual Buy/Sell commands | L-05 |
| 25 | Fix Paper/Real routing safety bug | C-01 |
| 26 | Persist price alerts | C-04 |
| 27 | API polling optimization & caching | H-01 |
| 28 | Rate-limit backoff | H-03 |
| 29 | Transaction-safe grid creation | H-04 |
| 30 | Database migration/versioning | H-05 |
| 31 | Risk manager based on total grid exposure | H-06 |
| 32 | Concurrency protection | H-07 |
| 33 | Earlier symbol validation in /newgrid | M-01 |
| 34 | Graceful shutdown | M-08 |
| 35 | Realistic paper trading (slippage/latency) | M-10 |
| 36 | Docker & CI/CD | L-01 |
| 37 | Live CoinDCX integration tests | L-02 |
| 38 | Telegram command & conversation tests | L-03 |
| 39 | /adjustgrid command | L-04 |
| 40 | Performance & security audit before live deployment | — |

## User preferences

*(none recorded yet)*
