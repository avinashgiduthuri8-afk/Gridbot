# GridBot Production Deployment Guide (VPS / Docker Compose)

**Target Environment:** Linux VPS (Docker & Docker Compose)  
**Database:** SQLite on Persistent Host Volume (`./data:/app/data`)  
**Primary User Interface:** Web Dashboard (React/Vite + FastAPI on Port 8000)  
**Notifications / Secondary Control:** Telegram Bot (Optional)  

---

## 1. Architecture Overview

GridBot is deployed to a Linux VPS using Docker Compose. The Web Dashboard serves as the **primary operator interface** for monitoring, grid creation, emergency stop control, and manual order execution:

```
                  ┌─────────────────────────────────────────┐
                  │               Linux VPS                 │
                  │                                         │
                  │   ┌─────────────────────────────────┐   │
                  │   │   Docker Container: gridbot     │   │
                  │   │                                 │   │
Web Browser ─────►│───┼─► Port 8000: Web Dashboard      │   │
(Primary UI)      │   │     (React UI + FastAPI)        │   │
                  │   │                                 │   │
                  │   │   Trading Engine (main.py)      │   │
                  │   │    - DCAManager                 │   │
                  │   │    - RiskManager                │   │
                  │   │    - MixedOrderManager          │   │
                  │   │    - OrderMonitor & PriceMonitor│   │
                  │   │                                 │   │
                  │   │   Telegram Bot (Optional)       │   │
                  │   └───────┬───────────────────┬─────┘   │
                  │           │                   │         │
                  │     Bind Mount          Bind Mount      │
                  │           │                   │         │
                  │           ▼                   ▼         │
                  │      ./data (DB)         ./logs (Logs)  │
                  └───────────┼───────────────────┼─────────┘
                              │                   │
                              ▼                   ▼
                     Persistent SQLite    Rotating Log Files
```

---

## 2. Persistent Storage Configuration

SQLite requires persistent disk storage to survive container restarts and updates.

In `docker-compose.yml`, persistent directories are bind-mounted directly from the VPS host:
- `./data:/app/data` — Contains `grid_bot.db` (grids, orders, positions, risk states, daily stats)
- `./logs:/app/logs` — Contains rotating application logs (`gridbot.log`)

Rebuilding or restarting the container (`docker compose down && docker compose up -d`) preserves all trading state, open grids, and trade history.

---

## 3. Environment Variables Configuration

Copy `.env.production.example` to `.env` in the project root on the VPS:
```bash
cp .env.production.example .env
chmod 600 .env
```

### A. Required Production Secrets
| Variable | Value / Format | Purpose |
|---|---|---|
| `COINDCX_API_KEY` | `32-64 hex/alphanumeric` | CoinDCX API Key (Trade permissions only; NO withdrawal permission) |
| `COINDCX_API_SECRET` | `64+ character secret` | CoinDCX API Secret for HMAC-SHA256 request signing |

### B. Optional Telegram Credentials (If Telegram notifications are desired)
| Variable | Value / Format | Purpose |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | `123456:ABC-DEF...` | Telegram bot token from @BotFather (Leave empty for Web Dashboard only mode) |
| `TELEGRAM_CHAT_ID` | `987654321` | Numeric Telegram user ID (Leave empty for Web Dashboard only mode) |
| `TELEGRAM_ALLOWED_USER_IDS` | `111,222,333` | Optional additional authorized user IDs |

### C. Core Configuration (Pre-configured defaults)
| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_PATH` | `data/grid_bot.db` | SQLite database file location |
| `LOG_DIR` | `logs` | Application log directory |
| `LOG_LEVEL` | `INFO` | Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `COINDCX_BASE_URL` | `https://api.coindcx.com` | CoinDCX REST API base endpoint |
| `DASHBOARD_EMBEDDED_ENABLED` | `true` | Runs dashboard server inside container alongside bot |
| `DASHBOARD_PORT` | `8000` | Port for the Web Dashboard |
| `DASHBOARD_HOST` | `0.0.0.0` | Host interface to bind dashboard |

### D. Risk Management Settings (INR)
| Variable | Default | Description |
|---|---|---|
| `MAX_TOTAL_CAPITAL` | `50000` | Maximum total capital (INR) across all active grids |
| `MAX_CAPITAL_PER_COIN` | `20000` | Maximum capital (INR) allocated to any single coin |
| `MAX_SIMULTANEOUS_GRIDS`| `20` | Maximum number of grids allowed simultaneously (1 - 20) |
| `MIN_WALLET_BALANCE` | `500` | Minimum free INR wallet balance required |
| `DAILY_LOSS_LIMIT` | `2000` | Maximum daily realized loss (INR) before emergency trading halt |

---

## 4. Live Trading Verification Sequence

> [!IMPORTANT]
> An automated grid must **NEVER** be the first live test. Always follow this strict phased verification sequence:

1. **Deploy to VPS:** Clone repository and build containers with `docker compose up --build -d`.
2. **Configure Credentials:** Populate `.env` with production CoinDCX API Key & Secret.
3. **Run Preflight Check:** Run `python grid-trading-bot/scripts/preflight.py` to verify environment and write permissions.
4. **Open Web Dashboard:** Navigate to `http://<VPS_IP>:8000`.
5. **Confirm Emergency Stop is ON:** Verify the header displays `Emergency Stop: ON` (or toggle it on).
6. **Verify Read-Only Connectivity:** Check market ticker and wallet balances.
7. **Clear Emergency Stop:** Use the Dashboard Header toggle to turn Emergency Stop **OFF**.
8. **Place ONE Small Manual REAL Order:**
   - Create a single grid in **REAL** mode or execute a small manual Buy (e.g. ₹6,000 on BTCINR).
   - Review and accept the prominent **REAL LIVE-ORDER CONFIRMATION** modal.
9. **Verify Order Completely:**
   - Confirm order status on CoinDCX exchange.
   - Confirm order record and fill status in Dashboard Orders / Trade History.
   - Confirm position quantity and average entry price in Dashboard Positions.
10. **Enable Automated Grids:** Only after manual order validation succeeds, activate automated grid triggers.

---

## 5. Deployment & Operation Commands

### 1. Run Production Preflight Check
```bash
python grid-trading-bot/scripts/preflight.py
```

### 2. Build and Start Container
```bash
docker compose up --build -d
```

### 3. Check Container Status and Logs
```bash
docker compose ps
docker compose logs -f
```

### 4. Access Web Dashboard
```text
http://<YOUR_VPS_IP>:8000
```

### 5. Safe Stop & Restart
```bash
# Graceful stop
docker compose stop

# Restart
docker compose start

# Full tear-down and rebuild (persists data in ./data)
docker compose down
docker compose up --build -d
```
