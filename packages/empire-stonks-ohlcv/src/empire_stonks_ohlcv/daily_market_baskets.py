"""Versioned configured equity baskets used by the EODData daily report."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DailyMarketBasketSpec:
    """A report-only ticker cohort, not authoritative index membership."""

    code: str
    title: str
    membership_version: str
    tickers: tuple[str, ...]
    preferred_market: str | None = None


MAG7_BASKET = DailyMarketBasketSpec(
    code="MAG7",
    title="Magnificent Seven",
    membership_version="empire-v1",
    tickers=("AAPL", "MSFT", "AMZN", "NVDA", "META", "TSLA", "GOOGL"),
    preferred_market="NASDAQ",
)

DOW30_BASKET = DailyMarketBasketSpec(
    code="DOW30",
    title="Dow 30 Configured Basket",
    membership_version="empire-v1",
    tickers=(
        "AAPL",
        "AMGN",
        "AMZN",
        "AXP",
        "BA",
        "CAT",
        "CRM",
        "CSCO",
        "CVX",
        "DIS",
        "DOW",
        "GS",
        "HD",
        "HON",
        "IBM",
        "INTC",
        "JNJ",
        "JPM",
        "KO",
        "MCD",
        "MMM",
        "MRK",
        "MSFT",
        "NKE",
        "PG",
        "TRV",
        "UNH",
        "V",
        "VZ",
        "WMT",
    ),
)

NASDAQ100_BASKET = DailyMarketBasketSpec(
    code="NASDAQ100",
    title="Nasdaq-100 Configured Basket",
    membership_version="empire-v1",
    tickers=(
        "AAPL", "MSFT", "AMZN", "NVDA", "META", "TSLA", "GOOGL", "GOOG",
        "AVGO", "COST", "PEP", "ADBE", "CSCO", "AMD", "NFLX", "INTC",
        "QCOM", "TXN", "AMGN", "HON", "INTU", "AMAT", "BKNG", "SBUX",
        "ISRG", "MU", "GILD", "VRTX", "REGN", "ADI", "LRCX", "KLAC",
        "PANW", "SNPS", "CDNS", "MDLZ", "CSX", "ADP", "ABNB", "MELI",
        "CRWD", "FTNT", "MRVL", "ORLY", "WDAY", "TEAM", "ASML", "NXPI",
        "PYPL", "CHTR", "MNST", "AEP", "ROST", "PAYX", "KDP", "PCAR",
        "CTAS", "MAR", "ODFL", "FAST", "IDXX", "EA", "EXC", "VRSK",
        "XEL", "KHC", "BIIB", "ILMN", "BKR", "DDOG", "ZS", "ANSS",
        "DXCM", "CPRT", "LULU", "CTSH", "WBD", "DLTR", "WBA", "SIRI",
        "SPLK", "SGEN", "NTES", "JD", "PDD", "BIDU", "DOCU", "ZM",
        "OKTA", "FISV", "EBAY", "CHKP", "ALGN", "MTCH", "LCID", "RIVN",
        "ENPH", "MRNA", "CEG", "GEHC",
    ),
    preferred_market="NASDAQ",
)

DAILY_MARKET_BASKETS = (MAG7_BASKET, DOW30_BASKET, NASDAQ100_BASKET)


__all__ = [
    "DAILY_MARKET_BASKETS",
    "DOW30_BASKET",
    "DailyMarketBasketSpec",
    "MAG7_BASKET",
    "NASDAQ100_BASKET",
]
