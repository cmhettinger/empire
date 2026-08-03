"""Human-readable OHLCV reports."""

from empire_stonks_ohlcv.reports.eoddata_daily_pdf import (
    EODDATA_DAILY_PDF_REPORT_ID,
    render_eoddata_daily_pdf,
)
from empire_stonks_ohlcv.reports.eoddata_daily_market_pdf import (
    EODDATA_DAILY_MARKET_PDF_REPORT_ID,
    render_eoddata_daily_market_pdf,
)
from empire_stonks_ohlcv.reports.stooq_history_pdf import (
    STOOQ_HISTORY_PDF_REPORT_ID,
    render_stooq_history_pdf,
)
from empire_stonks_ohlcv.reports.yahoo_pdf import (
    YAHOO_BACKFILL_PDF_REPORT_ID,
    YAHOO_DAILY_PDF_REPORT_ID,
    render_yahoo_pdf,
)
from empire_stonks_ohlcv.reports.yahoo_daily_benchmark_pdf import (
    YAHOO_DAILY_BENCHMARK_PDF_REPORT_ID,
    render_yahoo_daily_benchmark_pdf,
)

__all__ = [
    "EODDATA_DAILY_PDF_REPORT_ID",
    "EODDATA_DAILY_MARKET_PDF_REPORT_ID",
    "STOOQ_HISTORY_PDF_REPORT_ID",
    "YAHOO_BACKFILL_PDF_REPORT_ID",
    "YAHOO_DAILY_PDF_REPORT_ID",
    "YAHOO_DAILY_BENCHMARK_PDF_REPORT_ID",
    "render_eoddata_daily_pdf",
    "render_eoddata_daily_market_pdf",
    "render_stooq_history_pdf",
    "render_yahoo_pdf",
    "render_yahoo_daily_benchmark_pdf",
]
