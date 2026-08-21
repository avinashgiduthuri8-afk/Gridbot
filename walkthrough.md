# Walkthrough: Indian Stock Market Scanner (PROJECT-BETA)

We have successfully redesigned and expanded the existing trading system into an institutional-grade **Indian Stock Market Scanner (NSE/BSE)** adhering to the core philosophy: **Signal Quality > Signal Quantity**.

---

## 1. Summary of Accomplishments

### 1.1 Market Data & Session Abstraction
* **`MarketDataProvider`** ([engine/data/base.py](file:///c:/Users/ASUS/Documents/GitHub/Gridbot%20-inr/grid-trading-bot/engine/data/base.py)): Pluggable data feed abstraction supporting Yahoo Finance (`.NS` tickers), NSE direct, broker APIs (Zerodha Kite / Angel One), and offline CSV backtest replay.
* **`IndianSessionManager`** ([engine/session/session_manager.py](file:///c:/Users/ASUS/Documents/GitHub/Gridbot%20-inr/grid-trading-bot/engine/session/session_manager.py)): Enforces IST market hours (09:15 – 15:30 IST), pre-market auction, closing session, and official NSE holiday calendar (2025–2027).

### 1.2 Stock Universe & Liquidity Filtering
* **`indian_universe.py`** ([config/indian_universe.py](file:///c:/Users/ASUS/Documents/GitHub/Gridbot%20-inr/grid-trading-bot/config/indian_universe.py)): Curated datasets for NIFTY 50, NIFTY 100, NIFTY 200, NIFTY 500, and 11 sector benchmark indices.
* **`StockUniverseFilter`** ([engine/universe/universe_filter.py](file:///c:/Users/ASUS/Documents/GitHub/Gridbot%20-inr/grid-trading-bot/engine/universe/universe_filter.py)): Strict liquidity filters for 20-day average volume (>= 200k shares), average daily traded turnover (>= ₹1 Cr), and price thresholds.

### 1.3 Technical Indicators & Multi-Timeframe Confluence
* **`TechnicalIndicatorEngine`** ([engine/indicators/technical.py](file:///c:/Users/ASUS/Documents/GitHub/Gridbot%20-inr/grid-trading-bot/engine/indicators/technical.py)): Vectorized computation of EMA 20/50/200, RSI (14), MACD (12, 26, 9), ATR (14), ADX (14) + DI+/DI-, Volume SMA (20), VWAP, and Bollinger Bands.
* **`MultiTimeframeAnalyzer`** ([engine/mtf/mtf_analyzer.py](file:///c:/Users/ASUS/Documents/GitHub/Gridbot%20-inr/grid-trading-bot/engine/mtf/mtf_analyzer.py)): Multi-timeframe trend alignment across **1D (Structure)**, **1H (Setup)**, and **15M (Trigger)**.

### 1.4 Market Regime, Sector Strength & Alpha
* **`MarketRegimeDetector`** ([engine/regime/regime_detector.py](file:///c:/Users/ASUS/Documents/GitHub/Gridbot%20-inr/grid-trading-bot/engine/regime/regime_detector.py)): Evaluates NIFTY 50, BANK NIFTY, and India VIX (Vol status: Low, Normal, Elevated, Extreme) to determine market regime (`STRONG_BULLISH`, `BULLISH`, `NEUTRAL`, `BEARISH`, `STRONG_BEARISH`, `HIGH_VOLATILITY`).
* **`SectorStrengthAnalyzer`** ([engine/sectors/sector_analyzer.py](file:///c:/Users/ASUS/Documents/GitHub/Gridbot%20-inr/grid-trading-bot/engine/sectors/sector_analyzer.py)): Momentum rank and alpha calculation across 11 key NSE sectors.
* **`RelativeStrengthCalculator`** ([engine/relative_strength/rs_calculator.py](file:///c:/Users/ASUS/Documents/GitHub/Gridbot%20-inr/grid-trading-bot/engine/relative_strength/rs_calculator.py)): Outperformance alpha over 5-day and 20-day windows.
* **`NewsSentimentEvaluator`** ([engine/sentiment/news_evaluator.py](file:///c:/Users/ASUS/Documents/GitHub/Gridbot%20-inr/grid-trading-bot/engine/sentiment/news_evaluator.py)): Corporate announcements, headline sentiment, and earnings event risk gating.

### 1.5 Risk/Reward Geometry & 100-Point Scoring Model
* **`RiskRewardCalculator`** ([engine/risk_reward/rr_calculator.py](file:///c:/Users/ASUS/Documents/GitHub/Gridbot%20-inr/grid-trading-bot/engine/risk_reward/rr_calculator.py)): Computes Entry, Stop Loss, Target 1, Target 2, and strictly rejects setups with **`R:R < 2.0`**.
* **`SignalScoringEngine`** ([engine/signals/scoring.py](file:///c:/Users/ASUS/Documents/GitHub/Gridbot%20-inr/grid-trading-bot/engine/signals/scoring.py)): 100-point institutional model:
  * Technical Trend: 20 pts
  * Momentum (RSI/MACD): 15 pts
  * Volume & VWAP: 15 pts
  * Price Action / Setup: 15 pts
  * Multi-Timeframe Confluence: 15 pts
  * Market Regime Fit: 10 pts
  * Sector Strength: 5 pts
  * News / Sentiment: 5 pts
* **`IndianStockScanner`** ([engine/signals/scanner.py](file:///c:/Users/ASUS/Documents/GitHub/Gridbot%20-inr/grid-trading-bot/engine/signals/scanner.py)): Complete 12-stage scanner orchestrator outputting top 1–3 high-conviction signals.

### 1.6 Signal History, Backtesting & SQLite Persistence
* **`stock_signals` & `signal_backtests` Tables** in SQLite with numbered migration 005 ([storage/database.py](file:///c:/Users/ASUS/Documents/GitHub/Gridbot%20-inr/grid-trading-bot/storage/database.py#L213-L255)).
* **`SignalRepository`** ([storage/repositories/signals.py](file:///c:/Users/ASUS/Documents/GitHub/Gridbot%20-inr/grid-trading-bot/storage/repositories/signals.py)): Persistence and MFE/MAE excursion tracking.
* **`ScannerBacktestEvaluator`** ([engine/backtest/evaluator.py](file:///c:/Users/ASUS/Documents/GitHub/Gridbot%20-inr/grid-trading-bot/engine/backtest/evaluator.py)): Forward simulator measuring Win Rate %, Profit Factor, Max Drawdown %, and regime-specific stats.

### 1.7 REST APIs & React Dashboard Redesign
* **FastAPI Routers**:
  * `POST /api/scanner/scan`, `GET /api/scanner/latest`, `GET /api/scanner/session`
  * `GET /api/regime` (Market Regime & India VIX)
  * `GET /api/sectors` (11 Sector rankings & alpha)
  * `GET /api/signals`, `GET /api/signals/{id}`, `GET /api/signals/performance`
  * `POST /api/backtest/run`
* **React Dashboard Pages & Components**:
  * [MarketRegimeBar.tsx](file:///c:/Users/ASUS/Documents/GitHub/Gridbot%20-inr/grid-dashboard/src/components/common/MarketRegimeBar.tsx): Real-time NIFTY/BANKNIFTY/VIX banner and IST session status badge.
  * [SignalCard.tsx](file:///c:/Users/ASUS/Documents/GitHub/Gridbot%20-inr/grid-dashboard/src/components/common/SignalCard.tsx): Card showcasing top high-conviction signals with R:R, score, and key levels.
  * [SignalDetailModal.tsx](file:///c:/Users/ASUS/Documents/GitHub/Gridbot%20-inr/grid-dashboard/src/components/common/SignalDetailModal.tsx): Transparent 8-dimension score progress bars, trade geometry, and rationale checklist.
  * [SectorHeatmap.tsx](file:///c:/Users/ASUS/Documents/GitHub/Gridbot%20-inr/grid-dashboard/src/components/common/SectorHeatmap.tsx): 11-sector interactive matrix with alpha vs NIFTY.
  * [ScannerPage.tsx](file:///c:/Users/ASUS/Documents/GitHub/Gridbot%20-inr/grid-dashboard/src/pages/ScannerPage.tsx): Dedicated Institutional Stock Scanner.
  * [SectorsPage.tsx](file:///c:/Users/ASUS/Documents/GitHub/Gridbot%20-inr/grid-dashboard/src/pages/SectorsPage.tsx): Dedicated Sector Momentum & Heatmap page.
  * [SignalsHistoryPage.tsx](file:///c:/Users/ASUS/Documents/GitHub/Gridbot%20-inr/grid-dashboard/src/pages/SignalsHistoryPage.tsx): MFE/MAE excursion tracking and win rate stats.
  * [BacktestPage.tsx](file:///c:/Users/ASUS/Documents/GitHub/Gridbot%20-inr/grid-dashboard/src/pages/BacktestPage.tsx): Interactive historical simulation suite.

---

## 2. Test & Verification Results

### Automated Pytest Suite
Executed full test suite across both legacy and new modules:
```
============================ 960 passed in 56.06s =============================
```
* **Indian Stock Session Manager**: 8 passed
* **Technical Indicators (EMA, RSI, MACD, ATR, ADX, VWAP, BB)**: 7 passed
* **Universe & Liquidity Screening**: 5 passed
* **Market Regime & India VIX**: 3 passed
* **Sector Strength & Matrix**: 1 passed
* **Risk/Reward Geometry & Gating**: 2 passed
* **Full 12-Stage Scanner Pipeline**: 1 passed
* **Backtest & MFE/MAE Evaluator**: 3 passed
* **FastAPI REST Endpoints**: 5 passed
* **Existing DCA Bot & Dashboard Suite**: 925 passed with zero regressions

### Frontend Production Build
```
vite v8.2.2 building client environment for production...
transforming...
✓ 1834 modules transformed.
rendering chunks...
dist/index.html                   0.46 kB
dist/assets/index-Bc3bzR0m.css   10.21 kB
dist/assets/index-BoqzsN9y.js   316.91 kB
✓ built in 1.39s
```
Built static files successfully copied to `grid-trading-bot/dashboard/static` for embedded FastAPI serving.
