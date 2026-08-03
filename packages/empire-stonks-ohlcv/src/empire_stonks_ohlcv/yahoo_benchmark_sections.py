"""Versioned page membership for the Yahoo daily benchmark report."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class YahooBenchmarkSectionSpec:
    """One ordered analytical section expressed in stable Empire tickers."""

    code: str
    title: str
    tickers: tuple[str, ...]
    membership_version: str = "2026-08-03"


YAHOO_BENCHMARK_SECTIONS = (
    YahooBenchmarkSectionSpec(
        code="US_CORE",
        title="Core U.S. Equity Benchmarks",
        tickers=(
            "SPX",
            "DJI",
            "DJT",
            "DJU",
            "NDX",
            "IXIC",
            "RUT",
            "RUA",
            "SP400",
            "SP600",
            "OEX",
            "NYA",
        ),
    ),
    YahooBenchmarkSectionSpec(
        code="US_RISK_RATES",
        title="U.S. Themes, Volatility, Dollar and Rates",
        tickers=(
            "NYFANG",
            "SOX",
            "VIX",
            "VXN",
            "VVIX",
            "SKEW",
            "DXY",
            "UST5Y",
            "UST10Y",
            "UST30Y",
        ),
    ),
    YahooBenchmarkSectionSpec(
        code="US_EQUITY_FUTURES",
        title="U.S. Equity Index Futures",
        tickers=("ES", "NQ", "RTY", "YM"),
    ),
    YahooBenchmarkSectionSpec(
        code="EUROPE",
        title="European Equity Benchmarks",
        tickers=(
            "AEX",
            "BEL20",
            "CAC",
            "DAX",
            "FTSE",
            "FTSEMIB",
            "IBEX",
            "OMXSTO30",
            "SMI",
            "STOXX50E",
            "STOXX600",
            "PSI20",
        ),
    ),
    YahooBenchmarkSectionSpec(
        code="ASIA_PACIFIC",
        title="Asia-Pacific Equity Benchmarks",
        tickers=(
            "N225",
            "HSI",
            "HSCEI",
            "SHCOMP",
            "SZCOMPONENT",
            "TWSE",
            "STI",
            "JCI",
            "KLCI",
            "KOSPI",
            "ASX200",
        ),
    ),
    YahooBenchmarkSectionSpec(
        code="GLOBAL_REGIONAL",
        title="Regional and Global Equity Benchmarks",
        tickers=(
            "ISEQ",
            "NIFTY50",
            "SENSEX",
            "TSXCOMP",
            "BOVESPA",
            "MERVAL",
            "MEXIPC",
            "JTOPI",
            "XU100",
            "TA125",
            "MSCIACWI",
            "MSCIWORLD",
        ),
    ),
    YahooBenchmarkSectionSpec(
        code="COMMODITY_ENERGY_METALS",
        title="Commodity, Energy and Metals Benchmarks",
        tickers=(
            "GSCI",
            "WTI",
            "BRENT",
            "NATGAS",
            "RBOB",
            "HEATOIL",
            "GOLD",
            "SILVER",
            "COPPER",
            "PLATINUM",
            "PALLADIUM",
        ),
    ),
    YahooBenchmarkSectionSpec(
        code="AGRICULTURE_LIVESTOCK",
        title="Agriculture and Livestock Futures",
        tickers=(
            "CORN",
            "WHEAT",
            "SOYBEANS",
            "SOYMEAL",
            "SOYOIL",
            "COCOA",
            "COFFEE",
            "COTTON",
            "SUGAR",
            "LEANHOGS",
            "LIVECATTLE",
        ),
    ),
)


__all__ = ["YAHOO_BENCHMARK_SECTIONS", "YahooBenchmarkSectionSpec"]
