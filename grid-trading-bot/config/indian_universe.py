"""Curated Indian Stock Universe definitions, sector mappings, and index symbols.

Provides clean datasets for NIFTY 50, NIFTY 100, NIFTY 200, and NIFTY 500
with industry / sector taxonomy for relative strength and sector analysis.
"""

from __future__ import annotations

from typing import Any

# Major Benchmark and Sector Indices on NSE
INDEX_TICKERS: dict[str, dict[str, str]] = {
    "NIFTY_50": {"symbol": "NIFTY 50", "yahoo": "^NSEI", "name": "Nifty 50 Index"},
    "NIFTY_BANK": {"symbol": "NIFTY BANK", "yahoo": "^NSEBANK", "name": "Nifty Bank Index"},
    "INDIA_VIX": {"symbol": "INDIA VIX", "yahoo": "^INDIAVIX", "name": "India Volatility Index"},
    "NIFTY_IT": {"symbol": "NIFTY IT", "yahoo": "^CNXIT", "name": "Nifty IT Index"},
    "NIFTY_AUTO": {"symbol": "NIFTY AUTO", "yahoo": "^CNXAUTO", "name": "Nifty Auto Index"},
    "NIFTY_PHARMA": {"symbol": "NIFTY PHARMA", "yahoo": "^CNXPHARMA", "name": "Nifty Pharma Index"},
    "NIFTY_FMCG": {"symbol": "NIFTY FMCG", "yahoo": "^CNXFMCG", "name": "Nifty FMCG Index"},
    "NIFTY_METAL": {"symbol": "NIFTY METAL", "yahoo": "^CNXMETAL", "name": "Nifty Metal Index"},
    "NIFTY_ENERGY": {"symbol": "NIFTY ENERGY", "yahoo": "^CNXENERGY", "name": "Nifty Energy Index"},
    "NIFTY_REALTY": {"symbol": "NIFTY REALTY", "yahoo": "^CNXREALTY", "name": "Nifty Realty Index"},
    "NIFTY_FIN_SERVICE": {"symbol": "NIFTY FINANCIAL SERVICES", "yahoo": "NIFTY_FIN_SERVICE.NS", "name": "Nifty Financial Services"},
    "NIFTY_INFRA": {"symbol": "NIFTY INFRA", "yahoo": "^CNXINFRA", "name": "Nifty Infrastructure Index"},
    "NIFTY_PSE": {"symbol": "NIFTY PSE", "yahoo": "^CNXPSE", "name": "Nifty PSE Index"},
}

# NIFTY 50 Constituents with Sectors
NIFTY_50_STOCKS: dict[str, dict[str, Any]] = {
    "RELIANCE": {"name": "Reliance Industries Ltd", "sector": "Energy", "cap": "Large"},
    "TCS": {"name": "Tata Consultancy Services Ltd", "sector": "IT", "cap": "Large"},
    "HDFCBANK": {"name": "HDFC Bank Ltd", "sector": "Banking", "cap": "Large"},
    "ICICIBANK": {"name": "ICICI Bank Ltd", "sector": "Banking", "cap": "Large"},
    "INFY": {"name": "Infosys Ltd", "sector": "IT", "cap": "Large"},
    "BHARTIARTL": {"name": "Bharti Airtel Ltd", "sector": "Telecom", "cap": "Large"},
    "ITC": {"name": "ITC Ltd", "sector": "FMCG", "cap": "Large"},
    "SBIN": {"name": "State Bank of India", "sector": "Banking", "cap": "Large"},
    "LICI": {"name": "Life Insurance Corp of India", "sector": "Financial Services", "cap": "Large"},
    "HINDUNILVR": {"name": "Hindustan Unilever Ltd", "sector": "FMCG", "cap": "Large"},
    "LT": {"name": "Larsen & Toubro Ltd", "sector": "Infrastructure", "cap": "Large"},
    "BAJFINANCE": {"name": "Bajaj Finance Ltd", "sector": "Financial Services", "cap": "Large"},
    "HCLTECH": {"name": "HCL Technologies Ltd", "sector": "IT", "cap": "Large"},
    "MARUTI": {"name": "Maruti Suzuki India Ltd", "sector": "Auto", "cap": "Large"},
    "SUNPHARMA": {"name": "Sun Pharmaceutical Industries Ltd", "sector": "Pharma", "cap": "Large"},
    "ADANIENT": {"name": "Adani Enterprises Ltd", "sector": "Metals & Mining", "cap": "Large"},
    "KOTAKBANK": {"name": "Kotak Mahindra Bank Ltd", "sector": "Banking", "cap": "Large"},
    "TATAMOTORS": {"name": "Tata Motors Ltd", "sector": "Auto", "cap": "Large"},
    "AXISBANK": {"name": "Axis Bank Ltd", "sector": "Banking", "cap": "Large"},
    "NTPC": {"name": "NTPC Ltd", "sector": "Energy", "cap": "Large"},
    "ONGC": {"name": "Oil & Natural Gas Corp Ltd", "sector": "Energy", "cap": "Large"},
    "TITAN": {"name": "Titan Company Ltd", "sector": "Consumer Discretionary", "cap": "Large"},
    "ADANIPORTS": {"name": "Adani Ports and SEZ Ltd", "sector": "Infrastructure", "cap": "Large"},
    "POWERGRID": {"name": "Power Grid Corp of India Ltd", "sector": "Energy", "cap": "Large"},
    "M&M": {"name": "Mahindra & Mahindra Ltd", "sector": "Auto", "cap": "Large"},
    "BAJAJFINSV": {"name": "Bajaj Finserv Ltd", "sector": "Financial Services", "cap": "Large"},
    "COALINDIA": {"name": "Coal India Ltd", "sector": "Energy", "cap": "Large"},
    "TATASTEEL": {"name": "Tata Steel Ltd", "sector": "Metals", "cap": "Large"},
    "WIPRO": {"name": "Wipro Ltd", "sector": "IT", "cap": "Large"},
    "ASIANPAINT": {"name": "Asian Paints Ltd", "sector": "Consumer Discretionary", "cap": "Large"},
    "ULTRACEMCO": {"name": "UltraTech Cement Ltd", "sector": "Infrastructure", "cap": "Large"},
    "BAJAJ-AUTO": {"name": "Bajaj Auto Ltd", "sector": "Auto", "cap": "Large"},
    "NESTLEIND": {"name": "Nestle India Ltd", "sector": "FMCG", "cap": "Large"},
    "JSWSTEEL": {"name": "JSW Steel Ltd", "sector": "Metals", "cap": "Large"},
    "GRASIM": {"name": "Grasim Industries Ltd", "sector": "Materials", "cap": "Large"},
    "TECHM": {"name": "Tech Mahindra Ltd", "sector": "IT", "cap": "Large"},
    "HINDALCO": {"name": "Hindalco Industries Ltd", "sector": "Metals", "cap": "Large"},
    "SBILIFE": {"name": "SBI Life Insurance Co Ltd", "sector": "Financial Services", "cap": "Large"},
    "HDFCLIFE": {"name": "HDFC Life Insurance Co Ltd", "sector": "Financial Services", "cap": "Large"},
    "DRREDDY": {"name": "Dr Reddy's Laboratories Ltd", "sector": "Pharma", "cap": "Large"},
    "CIPLA": {"name": "Cipla Ltd", "sector": "Pharma", "cap": "Large"},
    "EICHERMOT": {"name": "Eicher Motors Ltd", "sector": "Auto", "cap": "Large"},
    "BRITANNIA": {"name": "Britannia Industries Ltd", "sector": "FMCG", "cap": "Large"},
    "TATACONSUM": {"name": "Tata Consumer Products Ltd", "sector": "FMCG", "cap": "Large"},
    "APOLLOHOSP": {"name": "Apollo Hospitals Enterprise Ltd", "sector": "Pharma", "cap": "Large"},
    "DIVISLAB": {"name": "Divi's Laboratories Ltd", "sector": "Pharma", "cap": "Large"},
    "HEROMOTOCO": {"name": "Hero MotoCorp Ltd", "sector": "Auto", "cap": "Large"},
    "INDUSINDBK": {"name": "IndusInd Bank Ltd", "sector": "Banking", "cap": "Large"},
    "SHRIRAMFIN": {"name": "Shriram Finance Ltd", "sector": "Financial Services", "cap": "Large"},
    "TRENT": {"name": "Trent Ltd", "sector": "Consumer Discretionary", "cap": "Large"},
    "BEL": {"name": "Bharat Electronics Ltd", "sector": "Capital Goods", "cap": "Large"},
}

# Extended Next 50 to complete NIFTY 100
NIFTY_NEXT_50_STOCKS: dict[str, dict[str, Any]] = {
    "ABB": {"name": "ABB India Ltd", "sector": "Capital Goods", "cap": "Large"},
    "ADANIGREEN": {"name": "Adani Green Energy Ltd", "sector": "Energy", "cap": "Large"},
    "ADANIPOWER": {"name": "Adani Power Ltd", "sector": "Energy", "cap": "Large"},
    "ATGL": {"name": "Adani Total Gas Ltd", "sector": "Energy", "cap": "Large"},
    "AMBUJACEM": {"name": "Ambuja Cements Ltd", "sector": "Infrastructure", "cap": "Large"},
    "BANKBARODA": {"name": "Bank of Baroda", "sector": "Banking", "cap": "Large"},
    "BERGEPAINT": {"name": "Berger Paints India Ltd", "sector": "Consumer Discretionary", "cap": "Large"},
    "BHARATFORG": {"name": "Bharat Forge Ltd", "sector": "Auto", "cap": "Large"},
    "BOSCHLTD": {"name": "Bosch Ltd", "sector": "Auto", "cap": "Large"},
    "CANBK": {"name": "Canara Bank", "sector": "Banking", "cap": "Large"},
    "CHOLAFIN": {"name": "Cholamandalam Investment and Finance Co", "sector": "Financial Services", "cap": "Large"},
    "COLPAL": {"name": "Colgate-Palmolive India Ltd", "sector": "FMCG", "cap": "Large"},
    "DLF": {"name": "DLF Ltd", "sector": "Realty", "cap": "Large"},
    "DABUR": {"name": "Dabur India Ltd", "sector": "FMCG", "cap": "Large"},
    "GAIL": {"name": "GAIL India Ltd", "sector": "Energy", "cap": "Large"},
    "GODREJCP": {"name": "Godrej Consumer Products Ltd", "sector": "FMCG", "cap": "Large"},
    "HAL": {"name": "Hindustan Aeronautics Ltd", "sector": "Capital Goods", "cap": "Large"},
    "HAVELLS": {"name": "Havells India Ltd", "sector": "Consumer Discretionary", "cap": "Large"},
    "ICICIGI": {"name": "ICICI Lombard General Insurance Co Ltd", "sector": "Financial Services", "cap": "Large"},
    "ICICIPRULI": {"name": "ICICI Prudential Life Insurance Co Ltd", "sector": "Financial Services", "cap": "Large"},
    "IOC": {"name": "Indian Oil Corporation Ltd", "sector": "Energy", "cap": "Large"},
    "IRCTC": {"name": "Indian Railway Catering and Tourism Corp", "sector": "Services", "cap": "Large"},
    "IRFC": {"name": "Indian Railway Finance Corp Ltd", "sector": "Financial Services", "cap": "Large"},
    "INDIGO": {"name": "InterGlobe Aviation Ltd", "sector": "Services", "cap": "Large"},
    "JINDALSTEL": {"name": "Jindal Steel & Power Ltd", "sector": "Metals", "cap": "Large"},
    "JIOFIN": {"name": "Jio Financial Services Ltd", "sector": "Financial Services", "cap": "Large"},
    "LTIM": {"name": "LTIMindtree Ltd", "sector": "IT", "cap": "Large"},
    "LUPIN": {"name": "Lupin Ltd", "sector": "Pharma", "cap": "Large"},
    "MARICO": {"name": "Marico Ltd", "sector": "FMCG", "cap": "Large"},
    "MOTHERSON": {"name": "Samvardhana Motherson International Ltd", "sector": "Auto", "cap": "Large"},
    "NAUKRI": {"name": "Info Edge India Ltd", "sector": "IT", "cap": "Large"},
    "PIDILITIND": {"name": "Pidilite Industries Ltd", "sector": "Materials", "cap": "Large"},
    "PFC": {"name": "Power Finance Corporation Ltd", "sector": "Financial Services", "cap": "Large"},
    "PNB": {"name": "Punjab National Bank", "sector": "Banking", "cap": "Large"},
    "RECLTD": {"name": "REC Ltd", "sector": "Financial Services", "cap": "Large"},
    "SBICARD": {"name": "SBI Cards and Payment Services Ltd", "sector": "Financial Services", "cap": "Large"},
    "SRF": {"name": "SRF Ltd", "sector": "Materials", "cap": "Large"},
    "SIEMENS": {"name": "Siemens Ltd", "sector": "Capital Goods", "cap": "Large"},
    "TATAELXSI": {"name": "Tata Elxsi Ltd", "sector": "IT", "cap": "Large"},
    "TATAPOWER": {"name": "Tata Power Company Ltd", "sector": "Energy", "cap": "Large"},
    "TORNTPHARM": {"name": "Torrent Pharmaceuticals Ltd", "sector": "Pharma", "cap": "Large"},
    "TVSHLTD": {"name": "TVS Holdings Ltd", "sector": "Auto", "cap": "Large"},
    "TVSMOTOR": {"name": "TVS Motor Company Ltd", "sector": "Auto", "cap": "Large"},
    "UNITDSPR": {"name": "United Spirits Ltd", "sector": "Consumer Discretionary", "cap": "Large"},
    "VBL": {"name": "Varun Beverages Ltd", "sector": "FMCG", "cap": "Large"},
    "VEDL": {"name": "Vedanta Ltd", "sector": "Metals", "cap": "Large"},
    "VOLTAS": {"name": "Voltas Ltd", "sector": "Consumer Discretionary", "cap": "Large"},
    "ZYDUSLIFE": {"name": "Zydus Lifesciences Ltd", "sector": "Pharma", "cap": "Large"},
    "ZOMATO": {"name": "Zomato Ltd", "sector": "Services", "cap": "Large"},
    "MAXHEALTH": {"name": "Max Healthcare Institute Ltd", "sector": "Pharma", "cap": "Large"},
}

# Liquid Midcap Stocks for NIFTY 200 & 500 Selection
NIFTY_MIDCAP_SELECTION: dict[str, dict[str, Any]] = {
    "ASTRAL": {"name": "Astral Ltd", "sector": "Infrastructure", "cap": "Mid"},
    "AUROPHARMA": {"name": "Aurobindo Pharma Ltd", "sector": "Pharma", "cap": "Mid"},
    "BALKRISIND": {"name": "Balkrishna Industries Ltd", "sector": "Auto", "cap": "Mid"},
    "BATAINDIA": {"name": "Bata India Ltd", "sector": "Consumer Discretionary", "cap": "Mid"},
    "BHEL": {"name": "Bharat Heavy Electricals Ltd", "sector": "Capital Goods", "cap": "Mid"},
    "BIOCON": {"name": "Biocon Ltd", "sector": "Pharma", "cap": "Mid"},
    "COFORGE": {"name": "Coforge Ltd", "sector": "IT", "cap": "Mid"},
    "CONCOR": {"name": "Container Corporation of India Ltd", "sector": "Services", "cap": "Mid"},
    "CROMPTON": {"name": "Crompton Greaves Consumer Electricals Ltd", "sector": "Consumer Discretionary", "cap": "Mid"},
    "CUMMINSIND": {"name": "Cummins India Ltd", "sector": "Capital Goods", "cap": "Mid"},
    "DEEPAKNTR": {"name": "Deepak Nitrite Ltd", "sector": "Materials", "cap": "Mid"},
    "DIXON": {"name": "Dixon Technologies India Ltd", "sector": "Consumer Discretionary", "cap": "Mid"},
    "ESCORTS": {"name": "Escorts Kubota Ltd", "sector": "Auto", "cap": "Mid"},
    "FEDERALBNK": {"name": "Federal Bank Ltd", "sector": "Banking", "cap": "Mid"},
    "GLENMARK": {"name": "Glenmark Pharmaceuticals Ltd", "sector": "Pharma", "cap": "Mid"},
    "GMRINFRA": {"name": "GMR Airports Infrastructure Ltd", "sector": "Infrastructure", "cap": "Mid"},
    "GODREJPROP": {"name": "Godrej Properties Ltd", "sector": "Realty", "cap": "Mid"},
    "GUJGASLTD": {"name": "Gujarat Gas Ltd", "sector": "Energy", "cap": "Mid"},
    "IDFCFIRSTB": {"name": "IDFC First Bank Ltd", "sector": "Banking", "cap": "Mid"},
    "IPCALAB": {"name": "IPCA Laboratories Ltd", "sector": "Pharma", "cap": "Mid"},
    "JUBLFOOD": {"name": "Jubilant FoodWorks Ltd", "sector": "Consumer Discretionary", "cap": "Mid"},
    "KPITTECH": {"name": "KPIT Technologies Ltd", "sector": "IT", "cap": "Mid"},
    "LTTS": {"name": "L&T Technology Services Ltd", "sector": "IT", "cap": "Mid"},
    "MFSL": {"name": "Max Financial Services Ltd", "sector": "Financial Services", "cap": "Mid"},
    "MPHASIS": {"name": "Mphasis Ltd", "sector": "IT", "cap": "Mid"},
    "MRF": {"name": "MRF Ltd", "sector": "Auto", "cap": "Mid"},
    "NATIONALUM": {"name": "National Aluminium Company Ltd", "sector": "Metals", "cap": "Mid"},
    "OBEROIRLTY": {"name": "Oberoi Realty Ltd", "sector": "Realty", "cap": "Mid"},
    "PAGEIND": {"name": "Page Industries Ltd", "sector": "Consumer Discretionary", "cap": "Mid"},
    "PERSISTENT": {"name": "Persistent Systems Ltd", "sector": "IT", "cap": "Mid"},
    "PETRONET": {"name": "Petronet LNG Ltd", "sector": "Energy", "cap": "Mid"},
    "POLYCAB": {"name": "Polycab India Ltd", "sector": "Capital Goods", "cap": "Mid"},
    "SAIL": {"name": "Steel Authority of India Ltd", "sector": "Metals", "cap": "Mid"},
    "SUNTV": {"name": "Sun TV Network Ltd", "sector": "Media", "cap": "Mid"},
    "TATACOMM": {"name": "Tata Communications Ltd", "sector": "Telecom", "cap": "Mid"},
    "TATATECH": {"name": "Tata Technologies Ltd", "sector": "IT", "cap": "Mid"},
    "TORNTPOWER": {"name": "Torrent Power Ltd", "sector": "Energy", "cap": "Mid"},
    "UNIONBANK": {"name": "Union Bank of India", "sector": "Banking", "cap": "Mid"},
}


def get_universe_stocks(universe: str = "NIFTY_100") -> dict[str, dict[str, Any]]:
    """Return symbol dictionary for chosen universe name."""
    u = universe.upper()
    if u in ("NIFTY_50", "NIFTY50"):
        return dict(NIFTY_50_STOCKS)
    if u in ("NIFTY_100", "NIFTY100"):
        combined = dict(NIFTY_50_STOCKS)
        combined.update(NIFTY_NEXT_50_STOCKS)
        return combined
    if u in ("NIFTY_200", "NIFTY200", "NIFTY_500", "NIFTY500", "ALL"):
        combined = dict(NIFTY_50_STOCKS)
        combined.update(NIFTY_NEXT_50_STOCKS)
        combined.update(NIFTY_MIDCAP_SELECTION)
        return combined
    return dict(NIFTY_100_STOCKS if "NIFTY_100_STOCKS" in globals() else NIFTY_50_STOCKS)


def get_stock_sector(symbol: str) -> str:
    """Return mapped sector for a symbol or 'General' if unknown."""
    sym = symbol.replace(".NS", "").upper()
    for dataset in (NIFTY_50_STOCKS, NIFTY_NEXT_50_STOCKS, NIFTY_MIDCAP_SELECTION):
        if sym in dataset:
            return dataset[sym].get("sector", "General")
    return "General"


def get_all_sectors() -> list[str]:
    """Return unique list of tracked sectors."""
    sectors = set()
    for dataset in (NIFTY_50_STOCKS, NIFTY_NEXT_50_STOCKS, NIFTY_MIDCAP_SELECTION):
        for info in dataset.values():
            if "sector" in info:
                sectors.add(info["sector"])
    return sorted(list(sectors))
