# GridBot Dashboard Backend Audit Report

**Date:** August 20, 2026  
**Audited Repository:** `grid-trading-bot/`  
**Frontend Repository:** `grid-dashboard/`  
**Test Suite Status:** 884 Passed, 0 Failed (100% Green Baseline)

---

## A. Current Architecture

The GridBot application follows a decoupled, repository-based asynchronous Python architecture. 

```
                                  +-------------------------------------+
                                  |      FastAPI Dashboard Backend      |
                                  |         (dashboard/app.py)          |
                                  +------------------+------------------+
                                                     | (Read-Only)
                                                     v
+-----------------------+         +-------------------------------------+
|   Main Trading Bot    | -------->      SQLite Database File           |
|       (main.py)       | (Read/  |       (data/grid_bot.db)            |
+-----------------------+  Write) +-------------------------------------+
```

- **Core Bot (`main.py`):** Handles Telegram interactions, price polling, DCA grid logic execution, order creation, risk enforcement, and optional webhooks.
- **Dashboard API (`dashboard/app.py`):** An independent, read-only FastAPI application that reads directly from the SQLite database file without invoking any order execution or risk-modifying code.

---

## B. Backend Entry Point

1. **Trading Engine Entry Point:** `grid-trading-bot/main.py`
   - Invoked via: `python main.py`
   - Initializes logging, loads settings, connects SQLite DB with retries (`_connect_db_with_retry`), constructs repositories, exchange clients, Telegram notification bot, DCA manager, price/order monitors, and starts background polling loops.

2. **Dashboard API Entry Point:** `grid-trading-bot/dashboard/app.py`
   - Invoked via: `uvicorn dashboard.app:app --host 0.0.0.0 --port 8000` or `python -m dashboard.app`
   - Uses `create_app()` factory with `lifespan` context manager.
   - Opens the database in **read-only mode** (`Database(database_path, read_only=True)`).
   - Mounts 8 router modules under `/api` (`health`, `grids`, `positions`, `orders`, `trade_history`, `portfolio`, `analytics`, `settings`).

---

## C. Database Architecture

- **Engine:** SQLite using `aiosqlite` (`storage/database.py`).
- **Connection Management:** `Database` wrapper class providing async connection lifecycle (`connect()`, `close()`, `migrate()`).
- **Isolation:** The dashboard backend opens a separate `Database` instance initialized with `read_only=True`. This prevents accidental writes, schema modifications, or write-lock contention with the trading bot process.
- **Migrations:** Managed via `storage/database.py` (`_MIGRATIONS` list) recording version numbers in the `schema_migrations` table.

---

## D. Relevant Tables

| Table Name | Purpose | Primary Key | Key Columns |
| :--- | :--- | :--- | :--- |
| `dca_grids` | Grid configuration & state | `grid_id` | `symbol`, `status`, `mode`, `entry_price`, `base_investment`, `dip_percentage`, `profit_percentage`, `max_levels`, `current_level`, `accumulated_quantity`, `accumulated_cost`, `total_realized_pnl` |
| `orders` | Individual buy/sell grid orders | `order_id` | `grid_id`, `symbol`, `side`, `price`, `quantity`, `status`, `order_type`, `exchange_order_id` |
| `trade_history` | Completed buy/sell trade fills | `id` | `grid_id`, `symbol`, `side`, `price`, `quantity`, `fee`, `realized_pnl`, `cycle_number` |
| `daily_stats` | Daily P&L and volume rollup | `date` (YYYY-MM-DD) | `realized_pnl`, `total_volume`, `trades_count`, `completed_cycles` |
| `monitor_settings` | System-wide monitoring options | `key` | `value` |
| `price_alerts` | Custom price trigger alerts | `id` | `symbol`, `target_price`, `direction`, `status` |
| `grid_defaults` | Presets for coin grids | `symbol` | `dip_percentage`, `profit_percentage`, `max_levels` |

---

## E. Relevant Repository Methods

All repositories are encapsulated in `Repositories` (`storage/repositories.py`):

1. **`GridRepository` (`storage/repositories/grids.py`)**
   - `get_by_id(grid_id)`: Fetch single grid record.
   - `list_by_status(statuses)`: Fetch grids filtered by status list (e.g. `['active', 'paused']`).
   - `list_all()`: List all historical grids.

2. **`OrderRepository` (`storage/repositories/orders.py`)**
   - `list_by_grid(grid_id)`: Fetch all orders belonging to a specific grid.
   - `list_by_status(statuses)`: Fetch orders filtered by status (e.g. `['open', 'filled']`).
   - `list_all()`: Fetch all orders.

3. **`TradeHistoryRepository` (`storage/repositories/trade_history.py`)**
   - `list_by_grid(grid_id)`: Fills for a specific grid.
   - `list_recent(limit=50)`: Recent trade execution log.
   - `total_realized_pnl()`: Lifetime realized P&L sum.

4. **`DailyStatsRepository` (`storage/repositories/daily_stats.py`)**
   - `get(date_str)`: Daily stats record for a specific date.
   - `list_recent(days=30)`: Last N days performance summary.

---

## F. Grid Data Sources

- **Source:** `storage/repositories/grids.py` (`dca_grids` table).
- **Extracted Fields:**
  - `grid_id` (string)
  - `symbol` (e.g. `"BTCINR"`)
  - `status` (`"active"`, `"paused"`, `"stopped"`, `"completed"`)
  - `mode` (`"paper"`, `"real"`)
  - `entry_price` (Decimal)
  - `base_investment`, `dip_buy_amount`, `dip_percentage`, `profit_sell_amount`, `profit_percentage`, `max_levels`
  - `current_level`, `accumulated_quantity`, `accumulated_cost`, `total_realized_pnl`

---

## G. Position Data Sources

- **Source:** Derived dynamically from active/paused grids in `dca_grids` where `accumulated_quantity > 0`.
- **Computation Helper:** `trading/portfolio_metrics.py` (`calculate_position_metrics`, `compute_portfolio_summary`).
- **Extracted Fields:**
  - `symbol`
  - `quantity` (`accumulated_quantity`)
  - `average_entry_price` (`accumulated_cost / accumulated_quantity`)
  - `total_invested` (`accumulated_cost`)
  - `current_price` (from exchange ticker or cached ticker)
  - `unrealized_pnl` (`(current_price - avg_entry) * quantity`)
  - `realized_pnl` (`total_realized_pnl`)

---

## H. Order Data Sources

- **Source:** `storage/repositories/orders.py` (`orders` table).
- **Extracted Fields:**
  - `order_id` (UUID string)
  - `grid_id` (UUID string)
  - `symbol`
  - `side` (`"buy"`, `"sell"`)
  - `price`, `quantity`
  - `status` (`"open"`, `"filled"`, `"cancelled"`)
  - `exchange_order_id`
  - `created_at`, `updated_at`

---

## I. Trade History Data Sources

- **Source:** `storage/repositories/trade_history.py` (`trade_history` table).
- **Extracted Fields:**
  - `id` (integer auto-increment)
  - `grid_id`
  - `symbol`, `side`
  - `price`, `quantity`, `fee`
  - `realized_pnl`
  - `cycle_number`
  - `created_at`

---

## J. Risk Data Sources

- **Source Configuration:** `config/settings.py` (`RiskSettings` dataclass).
- **Extracted Risk Parameters:**
  - `max_total_capital` (default: 50,000 INR)
  - `max_capital_per_coin` (default: 20,000 INR)
  - `max_simultaneous_grids` (default: 5)
  - `min_wallet_balance` (default: 500 INR)
  - `daily_loss_limit` (default: 2,000 INR)
- **Current Risk Metrics:** Calculated by combining `RiskSettings` with active capital from `GridRepository` and today's loss from `DailyStatsRepository`.

---

## K. Existing HTTP/API Capabilities

The FastAPI dashboard server is **already implemented** inside `grid-trading-bot/dashboard/app.py` and `grid-trading-bot/api/routers/`.

- **Existing Endpoints:**
  - `GET /api/health` — System status check
  - `GET /api/grids` & `GET /api/grids/{grid_id}` — Active & historical grid listing
  - `GET /api/positions` — Current position metrics & unrealized P&L
  - `GET /api/orders` — Orders filtered by grid/status
  - `GET /api/trade-history` — Fills & execution logs
  - `GET /api/portfolio` — Portfolio summary & total capital usage
  - `GET /api/analytics` — Historical P&L performance
  - `GET /api/settings` — Read-only safe system settings
- **CORS Support:** Configured via `CORSMiddleware` reading `DASHBOARD_CORS_ORIGINS` (defaults to `["*"]`).

---

## L. Concurrency Considerations

1. **Database Access:** SQLite WAL mode ensures non-blocking concurrent reads while the main bot process writes. The dashboard connection uses `read_only=True`, guaranteeing no write locks are requested.
2. **Process Separation:** The dashboard runs as a separate process via `uvicorn` and does not share memory, threads, or event loops with the trading bot.

---

## M. Railway Considerations

- **Current Deploy:** Railway builds using `Dockerfile` running `CMD ["python", "main.py"]`.
- **Coexistence:** 
  - Option A: Run FastAPI dashboard on a separate Railway service pointing at a shared volume containing `data/grid_bot.db`.
  - Option B: Use `docker-compose.yml` / combined runner process if running on a single container instance.

---

## N. Recommended API Architecture

The existing FastAPI routers in `grid-trading-bot/api/routers/` already match the frontend requirements 1:1.

For local development:
1. Run the FastAPI backend:
   ```bash
   cd grid-trading-bot
   uvicorn dashboard.app:app --host 127.0.0.1 --port 8000
   ```
2. Connect `grid-dashboard` (Vite dev server on `http://localhost:5173`) to `http://127.0.0.1:8000/api`.

---

## O. Files to Modify in NEXT Task (API Integration)

Only frontend integration files in `grid-dashboard/` will be created/modified:
- `grid-dashboard/src/services/api.ts` (API client / fetch functions)
- `grid-dashboard/src/hooks/useDashboardData.ts` (React data fetching hooks)
- `grid-dashboard/src/pages/OverviewPage.tsx` & placeholder views (Binding live data)

---

## P. Files That Must NOT Be Modified

- `grid-trading-bot/main.py`
- `grid-trading-bot/trading/dca_manager.py`
- `grid-trading-bot/trading/order_manager.py`
- `grid-trading-bot/trading/order_monitor.py`
- `grid-trading-bot/trading/price_monitor.py`
- `grid-trading-bot/exchange/*.py`
- `grid-trading-bot/risk/risk_manager.py`
- `grid-trading-bot/storage/database.py` (Schema/Migrations)
- `grid-trading-bot/storage/repositories/*.py`

---

## Q. Risks & Blockers

- **None.** The backend API layer (`dashboard/app.py`) is fully functional, read-only, and tested. The full test suite of 884 tests passes cleanly.

---

## R. Recommended Next Step

Proceed to **Task: Connect `grid-dashboard` React frontend to the read-only FastAPI API backend (`http://127.0.0.1:8000/api`)**.
