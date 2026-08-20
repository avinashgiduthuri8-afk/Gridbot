# Production Deployment & Controlled Live Validation Guide

This document defines the architecture, persistent volume requirements, production preflight procedure, PAPER vs REAL routing safety contract, Emergency Stop protocol, recovery procedures, and human-in-the-loop live trade approval process for **GridBot**.

---

## 1. Deployment Architecture

GridBot is deployed to **Railway** as a containerized Python 3.12 service with an embedded read-only FastAPI dashboard backend and React/Vite frontend.

```
Railway Service Container (Python 3.12)
├── App Working Directory: /app
├── Railway Persistent Volume: /app/data
│   └── Database File: /app/data/grid_bot.db (SQLite)
├── Log Directory: /app/logs
├── Embedded Dashboard Backend: FastAPI (READ-ONLY GET-ONLY API)
└── Frontend UI: React / Vite Static Assets (port 8000 / PORT env)
```

---

## 2. Railway Volume & Database Persistence

| Property | Production Specification |
|---|---|
| **Mount Path** | `/app/data` |
| **Database File** | `/app/data/grid_bot.db` |
| **Environment Variable** | `DATABASE_PATH=data/grid_bot.db` |
| **Read-Only Access** | FastAPI Dashboard accesses via `file:/app/data/grid_bot.db?mode=ro` |
| **Write Access** | Trading Engine writes to `/app/data/grid_bot.db` under WAL mode |

> [!IMPORTANT]
> Railway deployments MUST attach a Persistent Volume at `/app/data`. Ephemeral container restarts without a persistent volume will lose grid state and order history.

---

## 3. Environment Variables Reference

| Variable | Description | Production Requirement |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Bot API token for notifications & commands | Required secret |
| `TELEGRAM_CHAT_ID` | Authorized user ID for alert routing | Required numeric ID |
| `COINDCX_API_KEY` | Exchange API Key | Required secret |
| `COINDCX_API_SECRET` | Exchange HMAC Secret | Required secret |
| `DATABASE_PATH` | SQLite database file path | `data/grid_bot.db` |
| `LOG_DIR` | Directory for log files | `logs` |
| `LOG_LEVEL` | Application logging level | `INFO` |
| `MAX_TOTAL_CAPITAL` | Max capital across all grids (INR) | Default `50000.0` |
| `MAX_CAPITAL_PER_COIN` | Max capital per asset (INR) | Default `20000.0` |
| `MAX_SIMULTANEOUS_GRIDS` | Maximum active grids limit | Default `20` |
| `MIN_WALLET_BALANCE` | Minimum required INR reserve | Default `500.0` |
| `DAILY_LOSS_LIMIT` | Daily loss emergency trigger (INR) | Default `2000.0` |

---

## 4. Production Preflight Validator

Before service launch, run the preflight script:

```bash
uv run python scripts/preflight.py
```

### Preflight Verification Tasks
1. **Secrets Audit:** Ensures `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `COINDCX_API_KEY`, and `COINDCX_API_SECRET` are non-empty. Secrets are masked in log output as `SET` or `MISSING`.
2. **Directory & Write Audit:** Validates `/app/data` exists and is writable.
3. **Configuration Audit:** Confirms risk settings, log levels, and polling intervals meet safety constraints.

---

## 5. PAPER vs REAL Routing Safety Contract

All order creation and cancellation requests MUST flow through `MixedOrderManager`:

- **PAPER Grid (`mode == "paper"`):** Routed exclusively to `PaperExchangeClient`. **CoinDCX REST API endpoints are never called.**
- **REAL Grid (`mode == "real"`):** Routed to `CoinDCXClient`.
- **Unknown / Missing Mode:** Defaults safely to `PaperExchangeClient`.

---

## 6. Emergency Stop Protocol

1. **Activation:** Can be triggered via Telegram `/emergencystop`, FastAPI dashboard endpoint, or `RiskManager.trigger_emergency_stop()`.
2. **Persistence:** Emergency Stop flag is written to `monitor_settings` in SQLite.
3. **Enforcement:** Blocks all new grid creation, new BUY orders, and trading mutations. Preserved across service restarts via `load_emergency_stop()`.
4. **Deactivation:** Requires explicit clear operation (`clear_emergency_stop()`).

---

## 7. Recovery Procedure

When the container restarts:
1. `Database.connect()` connects under WAL mode and runs migrations.
2. `RiskManager.load_emergency_stop()` restores Emergency Stop state.
3. `RecoveryManager.recover()` inspects open orders in SQLite against exchange status.
4. Stuck `PENDING` orders are cancelled/failed; no duplicate orders are created.

---

## 8. Live Trade Approval Gate & Checklist

> [!CAUTION]
> Automated tests MUST NEVER place live exchange orders. Live trading requires explicit manual approval.

### Pre-Live Approval Checklist
- [ ] Railway service confirmed as intended production target
- [ ] Persistent Volume mounted at `/app/data`
- [ ] Production `DATABASE_PATH` verified
- [ ] Production CoinDCX credentials verified non-empty
- [ ] Telegram notifications verified active
- [ ] Emergency Stop tested and verified working
- [ ] Dashboard verified read-only (0 POST/PUT/PATCH/DELETE endpoints)
- [ ] PAPER routing verified (`0` CoinDCX API calls)
- [ ] Risk limits confirmed (`MAX_TOTAL_CAPITAL`, `DAILY_LOSS_LIMIT`)
- [ ] Rollback procedure documented

---

## 9. Rollback & Emergency Procedures

If an anomaly is detected in production:
1. Trigger Emergency Stop immediately (`/emergencystop`).
2. Scale Railway service instances to `0` or stop container.
3. Inspect active CoinDCX orders directly via CoinDCX Web/App UI.
4. Cancel any open orders if required.
5. Reopen database in read-only mode to audit trade history.
6. Fix root cause, re-run preflight, and restart service.
