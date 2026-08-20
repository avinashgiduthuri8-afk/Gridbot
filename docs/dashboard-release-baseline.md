# GridBot Dashboard Release Baseline

**Phase:** 2 — Dashboard  
**Step:** 3.4 — Integration Hardening & Release Baseline  
**Date:** 2026-08-20  
**Status:** VERIFIED STABLE  

---

## 1. Overview & Purpose
The GridBot Dashboard is an additive, read-only web interface for real-time monitoring and historical analytics of the Crypto Grid Trading Bot. It runs as an independent process from main.py (Telegram bot process) and reads directly from the bot's migrated SQLite database in read-only mode (mode=ro).

---

## 2. Read-Only Security Guarantee
- **Endpoints:** 100% GET-only (@router.get(...)). Zero POST, PUT, PATCH, or DELETE handlers exist on the dashboard backend.
- **UI Controls:** Zero trading mutation controls exist in the frontend (no BUY, SELL, START, STOP, PAUSE, RESUME, or CANCEL buttons).
- **Database Access:** Opened with Database(path, read_only=True) using URI mode=ro. All write/mutation SQL statements (INSERT, UPDATE, DELETE, CREATE, DROP) are rejected at the SQLite driver level with sqlite3.OperationalError.
- **Trading Engine Isolation:** Zero trading managers (DCAManager, OrderManager, PriceMonitor, RiskManager) or exchange execution logic are invoked by the dashboard.
- **Credential Protection:** Secrets (COINDCX_API_KEY, COINDCX_SECRET, TELEGRAM_BOT_TOKEN) are strictly excluded from API outputs.

---

## 3. Verified API Contract

| Endpoint | Method | Response Model | Description |
|---|---|---|---|
| /api/health | GET | HealthResponse | Database connection status and health check |
| /api/portfolio | GET | PortfolioResponse | Aggregate realized P&L, invested capital, return %, and grid counts |
| /api/grids | GET | GridListResponse | List of all DCA grid records with parameters and status |
| /api/grids/{grid_id} | GET | GridResponse | Single grid detail object |
| /api/positions | GET | PositionListResponse | Active/paused grid inventory holdings and P&L breakdown |
| /api/orders | GET | OrderListResponse | Buy/sell order lifecycle records (filterable by grid_id, limit) |
| /api/trade-history | GET | TradeHistoryResponse | Executed trade fill logs (filterable by grid_id, limit) |
| /api/analytics | GET | AnalyticsResponse | Win rate %, max drawdown %, profit factor, and completed cycles |
| /api/settings | GET | SettingsResponse | Risk control parameters, engine poll intervals, and subsystem flags |

---

## 4. Architecture & Locations
- **Backend Root:** grid-trading-bot/
- **Dashboard Backend App:** grid-trading-bot/dashboard/app.py
- **API Routers:** grid-trading-bot/api/routers/
- **Frontend Root:** grid-dashboard/
- **API Base URL Config:** import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api'
- **Polling Interval:** 15 seconds (pollIntervalMs = 15000 via useDashboardData.ts, cleaned up on unmount)

---

## 5. Operations & Startup Commands

### Start Backend Dashboard (API & SPA Host)
`powershell
# From grid-trading-bot/ directory:
uv run uvicorn dashboard.app:app --host 127.0.0.1 --port 8000
`

### Start Frontend Development Server
`powershell
# From grid-dashboard/ directory:
npm run dev
`
(Default URL: http://localhost:5173)

### Build Frontend for Production
`powershell
# From grid-dashboard/ directory:
npm run build
`

---

## 6. Verification & Test Baseline

- **Backend Pytest Suite:** 889 passed in 27.73s (5 new dedicated regression tests added in Step 3.4)
- **Frontend Production Build:** PASS (0 TypeScript errors, 0 Vite errors)
- **Frontend Code Quality:** 
px oxlint passed (0 errors)
- **Git Working Tree:** Clean (git status --short verified)

---

## 7. Known Limitations
- Time-series P&L equity charts are deferred as the current backend provides lifetime aggregate totals rather than historical daily mark-to-market snapshots.
- Web browser integration testing requires Playwright drivers installed locally when automated browser subagents are utilized.
