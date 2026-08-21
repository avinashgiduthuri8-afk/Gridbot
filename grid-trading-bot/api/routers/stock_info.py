"""Stock Fundamentals, Profile & NSE Delivery REST API Routers.

Endpoints:
- GET /stocks/{symbol}/info: Full unified profile, ratios, shareholding & delivery stats
- GET /stocks/{symbol}/ratios: Screener-style financial ratios summary
- GET /stocks/{symbol}/delivery: NSE delivery %, traded volume, circuit limits
- GET /stocks/batch-info: Batch info map for multiple symbols (Scanner table)
"""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Query, HTTPException, status

from engine.data.stock_info_provider import StockInfoProvider
from utils.logger import get_logger

log = get_logger("stock_info_router")

router = APIRouter(tags=["stocks"])
_stock_info_provider = StockInfoProvider()


@router.get("/stocks/{symbol}/info", summary="Full Unified Stock Info & Fundamentals")
async def get_stock_info(symbol: str, force_refresh: bool = False) -> dict[str, Any]:
    """Retrieves unified company profile, valuation ratios, NSE delivery %, and shareholding pattern."""
    info = await _stock_info_provider.get_stock_info(symbol, force_refresh=force_refresh)
    return info.to_dict()


@router.get("/stocks/{symbol}/ratios", summary="Financial Ratios Summary (Screener-style)")
async def get_stock_ratios(symbol: str) -> dict[str, Any]:
    """Retrieves key valuation and financial ratios for fundamental analysis."""
    info = await _stock_info_provider.get_stock_info(symbol)
    return {
        "symbol": info.symbol,
        "company_name": info.company_name,
        "market_cap_cr": round(info.market_cap_cr, 2),
        "market_cap_category": info.market_cap_category,
        "current_price": round(info.current_price, 2),
        "stock_pe": round(info.stock_pe, 2),
        "industry_pe": round(info.industry_pe, 2),
        "book_value": round(info.book_value, 2),
        "price_to_book": round(info.price_to_book, 2),
        "dividend_yield_pct": round(info.dividend_yield_pct, 2),
        "roce_pct": round(info.roce_pct, 2),
        "roe_pct": round(info.roe_pct, 2),
        "debt_to_equity": round(info.debt_to_equity, 2),
        "interest_coverage": round(info.interest_coverage, 2),
        "eps_ttm": round(info.eps_ttm, 2),
        "peg_ratio": round(info.peg_ratio, 2),
        "free_cash_flow_cr": round(info.free_cash_flow_cr, 2),
        "promoter_holding_pct": round(info.promoter_holding_pct, 2),
        "pledged_pct": round(info.pledged_pct, 2),
    }


@router.get("/stocks/{symbol}/delivery", summary="NSE Delivery & Circuit Limits")
async def get_stock_delivery(symbol: str) -> dict[str, Any]:
    """Retrieves live NSE delivery percentages, volume, circuit bands, and depth summary."""
    info = await _stock_info_provider.get_stock_info(symbol)
    return {
        "symbol": info.symbol,
        "delivery_pct": round(info.delivery_pct, 2),
        "delivery_quantity": info.delivery_quantity,
        "traded_volume": info.traded_volume,
        "upper_circuit": round(info.upper_circuit, 2),
        "lower_circuit": round(info.lower_circuit, 2),
        "circuit_band_pct": round(info.circuit_band_pct, 1),
        "total_buy_qty": info.total_buy_qty,
        "total_sell_qty": info.total_sell_qty,
        "upcoming_events": [e.to_dict() for e in info.upcoming_events],
    }


@router.get("/stocks/batch-info", summary="Batch Stock Info for Scanner Table")
async def get_batch_stock_info(
    symbols: str = Query(..., description="Comma-separated stock symbols (e.g. RELIANCE,TCS,INFY)")
) -> dict[str, Any]:
    """Batch fetch StockInfo for multiple symbols to populate table columns efficiently."""
    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not sym_list:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No symbols provided")

    batch_map = await _stock_info_provider.get_batch_stock_info(sym_list)
    return {sym: info.to_dict() for sym, info in batch_map.items()}
