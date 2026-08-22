"""Accelerated historical-data replay & stress testing for the trading engine.

This package is entirely additive: it does not modify DCAManager,
RiskManager, OrderManager, or any other production trading logic. It feeds
historical (or synthetically generated) price data into the *real*
DCAManager exactly the way PriceMonitor feeds live CoinDCX prices, by
implementing the same ExchangeClient interface and driving
check_grid_triggers() directly.

Modules:
    data_loader           — load OHLCV candles from CSV/JSON/SQLite
    scenarios             — synthetic price-path generators (bull, bear, ...)
    market_data_exchange  — ExchangeClient backed by a replay price feed
    fee_exchange          — thin fee-simulating wrapper around PaperExchangeClient
    engine                — ReplayEngine: drives DCAManager through a price feed
    validation            — post-replay database/business-rule integrity checks
    report                — replay/trading/system summary + PASS/FAIL report
    cli                   — command-line entry point (see replay.py at repo root)
"""
