# Comprehensive Stock Info & Fundamentals Engine (PROJECT-BETA)

## Objective
Enrich the Indian Stock Market Scanner & Signal Engine with detailed stock fundamentals, company profile data, financial ratios, quarterly performance, delivery data, and corporate actions aggregated from **NSE India official endpoints**, **Screener.in**, and **Yahoo Finance (`.NS`)**.

---

## Proposed Changes

### 1. Data Schema & Core Engine (`grid-trading-bot/engine/data/`)

#### [NEW] [stock_info_provider.py](file:///c:/Users/ASUS/Documents/GitHub/Gridbot%20-inr/grid-trading-bot/engine/data/stock_info_provider.py)
* Unified `StockInfo` dataclass:
  * **Company Overview**: `symbol`, `company_name`, `sector`, `industry`, `isin`, `market_cap_category`, `website`, `business_summary`.
  * **Valuation & Key Financial Ratios**: `market_cap_cr`, `current_price`, `high_52w`, `low_52w`, `stock_pe`, `industry_pe`, `book_value`, `price_to_book`, `dividend_yield_pct`, `roce_pct`, `roe_pct`, `debt_to_equity`, `interest_coverage`, `eps_ttm`, `peg_ratio`, `free_cash_flow_cr`.
  * **NSE Live Trading & Delivery Insights**: `delivery_pct`, `delivery_quantity`, `traded_volume`, `upper_circuit`, `lower_circuit`, `circuit_band_pct`, `total_buy_qty`, `total_sell_qty`, `upcoming_events`.
  * **Shareholding Pattern**: `promoter_holding_pct`, `pledged_pct`, `fii_holding_pct`, `dii_holding_pct`, `public_holding_pct`, `promoter_trend`.
* Multi-source fetching architecture:
  * Primary: Yahoo Finance `quoteSummary` API (`assetProfile`, `defaultKeyStatistics`, `financialData`, `summaryDetail`).
  * Secondary: NSE India API client (`/api/quote-equity`, delivery data) with cookie session management and rate limiting.
  * Resilient Fallback: Built-in Screener ratio calculator and benchmark sector valuation mappings for all NSE universe stocks.
* Dual TTL In-Memory Caching:
  * Intraday / Delivery: 15-minute TTL.
  * Fundamentals / Shareholding: 24-hour TTL.
  * Batch fetching: `get_batch_stock_info(symbols)`.

---

### 2. API Endpoints (`grid-trading-bot/api/routers/`)

#### [NEW] [stock_info.py](file:///c:/Users/ASUS/Documents/GitHub/Gridbot%20-inr/grid-trading-bot/api/routers/stock_info.py)
Expose:
* `GET /api/v1/stocks/{symbol}/info` – Full unified stock snapshot.
* `GET /api/v1/stocks/{symbol}/ratios` – Screener-style financial ratios.
* `GET /api/v1/stocks/{symbol}/delivery` – NSE delivery % and circuit limits.
* `GET /api/v1/stocks/batch-info?symbols=RELIANCE,TCS,INFY` – Batch fetch for scanner table.

#### [MODIFY] [dashboard/app.py](file:///c:/Users/ASUS/Documents/GitHub/Gridbot%20-inr/grid-trading-bot/dashboard/app.py)
* Register `stock_info` router under `/api/v1/stocks` and `/api/stocks`.

---

### 3. Frontend Dashboard Integration (`grid-dashboard/`)

#### [MODIFY] [src/types/dashboard.ts](file:///c:/Users/ASUS/Documents/GitHub/Gridbot%20-inr/grid-dashboard/src/types/dashboard.ts)
* Add `StockInfoResponse`, `FinancialRatiosResponse`, `DeliveryInfoResponse`, `ShareholdingResponse`, `CorporateEvent`.

#### [MODIFY] [src/services/api.ts](file:///c:/Users/ASUS/Documents/GitHub/Gridbot%20-inr/grid-dashboard/src/services/api.ts)
* Add client methods: `getStockInfo(symbol)`, `getStockRatios(symbol)`, `getStockDelivery(symbol)`, `getBatchStockInfo(symbols)`.

#### [NEW] [src/components/common/StockDetailDrawer.tsx](file:///c:/Users/ASUS/Documents/GitHub/Gridbot%20-inr/grid-dashboard/src/components/common/StockDetailDrawer.tsx)
* Slide-over interactive drawer when clicking any stock symbol:
  * 52-Week Range visual slider with live price marker.
  * Key financial ratio cards (Market Cap, P/E vs Industry P/E, ROCE, ROE, Debt/Equity, Div Yield).
  * Shareholding pattern breakdown (Promoter, FII, DII, Public, Pledged %).
  * NSE delivery % & circuit limits.
  * Direct external link action buttons (`NSE India`, `Screener.in`, `TradingView`).

#### [MODIFY] [src/pages/ScannerPage.tsx](file:///c:/Users/ASUS/Documents/GitHub/Gridbot%20-inr/grid-dashboard/src/pages/ScannerPage.tsx)
* Integrate batch stock info lookup for scanned candidates.
* Add table columns: Market Cap (₹ Cr), P/E vs Ind P/E, ROCE / ROE, Delivery % (Green/Amber/Grey badge), and External Links (`NSE`, `Screener`, `TradingView`).
* Wire symbol click to open `StockDetailDrawer`.

---

## 4. Verification Plan

### Automated Pytest Suite
```powershell
..\.venv\Scripts\python.exe -m pytest tests/test_stock_info.py -v
..\.venv\Scripts\python.exe -m pytest -v
```
* Test multi-source aggregation and graceful fallback.
* Test numerical formatting (Lakhs / Crores / Cr).
* Test TTL caching efficiency (< 50ms for cached items).
* Test all REST API endpoints.

### Frontend Production Build
```powershell
npm run build
```
Verify 0 TypeScript / compilation errors and deploy to `grid-trading-bot/dashboard/static`.
